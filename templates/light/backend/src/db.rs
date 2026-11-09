use crate::config::{ConfigError, validate_sqlite_path};
use sqlx::{
    SqlitePool,
    migrate::MigrateError,
    sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous},
};
use std::{error::Error, fmt, path::Path, time::Duration};

#[derive(Debug)]
pub enum InitError {
    Configuration(ConfigError),
    Storage(std::io::Error),
    Connection(sqlx::Error),
    Migration(MigrateError),
}

impl fmt::Display for InitError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Configuration(_) => "database initialization failed: SQLITE_PATH must be an ordinary persistent file path",
            Self::Storage(_) => "database initialization failed: cannot prepare storage directory",
            Self::Connection(_) => "database initialization failed: cannot open SQLite database; check storage permissions",
            Self::Migration(_) => "database initialization failed: migration rejected; check schema compatibility and backup before repair",
        })
    }
}

impl Error for InitError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        Some(match self {
            Self::Configuration(error) => error,
            Self::Storage(error) => error,
            Self::Connection(error) => error,
            Self::Migration(error) => error,
        })
    }
}

struct Diagnostic {
    stage: &'static str,
    category: &'static str,
    migration_version: Option<i64>,
    sqlite_code: Option<String>,
}

impl InitError {
    fn diagnostic(&self) -> Diagnostic {
        let mut diagnostic = Diagnostic {
            stage: "configuration",
            category: "invalid_path",
            migration_version: None,
            sqlite_code: None,
        };
        match self {
            Self::Configuration(_) => {}
            Self::Storage(error) => {
                diagnostic.stage = "storage";
                diagnostic.category = match error.kind() {
                    std::io::ErrorKind::PermissionDenied => "permission_denied",
                    std::io::ErrorKind::NotFound => "not_found",
                    _ => "io_error",
                };
            }
            Self::Connection(error) => {
                diagnostic.stage = "connection";
                diagnostic.category = match error {
                    sqlx::Error::PoolTimedOut => "pool_timeout",
                    sqlx::Error::Io(_) => "io_error",
                    sqlx::Error::Database(_) => "database_error",
                    _ => "connection_error",
                };
                diagnostic.sqlite_code = sqlite_code(error);
            }
            Self::Migration(error) => {
                diagnostic.stage = "migration";
                diagnostic.category = match error {
                    MigrateError::ExecuteMigration(error, version) => {
                        diagnostic.migration_version = Some(*version);
                        diagnostic.sqlite_code = sqlite_code(error);
                        "execution_failed"
                    }
                    MigrateError::Execute(error) => {
                        diagnostic.sqlite_code = sqlite_code(error);
                        "execution_failed"
                    }
                    MigrateError::VersionMismatch(version) => {
                        diagnostic.migration_version = Some(*version);
                        "checksum_mismatch"
                    }
                    MigrateError::VersionMissing(version)
                    | MigrateError::VersionNotPresent(version) => {
                        diagnostic.migration_version = Some(*version);
                        "missing_migration"
                    }
                    MigrateError::Dirty(version) => {
                        diagnostic.migration_version = Some(*version);
                        "dirty_migration"
                    }
                    _ => "migration_error",
                };
            }
        }
        diagnostic
    }

    fn log(&self) {
        let diagnostic = self.diagnostic();
        tracing::error!(
            stage = diagnostic.stage,
            category = diagnostic.category,
            migration_version = diagnostic.migration_version,
            sqlite_code = diagnostic.sqlite_code.as_deref(),
            "database initialization failed"
        );
    }
}

fn sqlite_code(error: &sqlx::Error) -> Option<String> {
    error
        .as_database_error()?
        .code()
        .filter(|code| {
            !code.is_empty() && code.len() <= 10 && code.bytes().all(|byte| byte.is_ascii_digit())
        })
        .map(|code| code.into_owned())
}

pub async fn connect(path: &Path) -> Result<SqlitePool, InitError> {
    let result = connect_inner(path).await;
    if let Err(error) = &result {
        error.log();
    }
    result
}

async fn connect_inner(path: &Path) -> Result<SqlitePool, InitError> {
    validate_sqlite_path(path).map_err(InitError::Configuration)?;
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        tokio::fs::create_dir_all(parent)
            .await
            .map_err(InitError::Storage)?;
    }
    let options = SqliteConnectOptions::new()
        .filename(path)
        .create_if_missing(true)
        .journal_mode(SqliteJournalMode::Wal)
        .synchronous(SqliteSynchronous::Full)
        .foreign_keys(true)
        .busy_timeout(Duration::from_secs(5));
    let pool = SqlitePoolOptions::new()
        .max_connections(4)
        .acquire_timeout(Duration::from_secs(2))
        .connect_with(options)
        .await
        .map_err(InitError::Connection)?;
    tracing::info!("database migrations starting");
    if let Err(error) = sqlx::migrate!().run(&pool).await {
        pool.close().await;
        return Err(InitError::Migration(error));
    }
    tracing::info!("database migrations complete");
    Ok(pool)
}
