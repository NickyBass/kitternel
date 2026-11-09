use sqlx::{
    SqlitePool,
    sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous},
};
use std::{error::Error, fmt, path::Path, time::Duration};

#[derive(Debug)]
pub enum InitError {
    Storage(std::io::Error),
    Connection(sqlx::Error),
    Migration(sqlx::migrate::MigrateError),
}

impl fmt::Display for InitError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Storage(_) => "database initialization failed: cannot prepare storage directory",
            Self::Connection(_) => "database initialization failed: cannot open SQLite database; check storage permissions",
            Self::Migration(_) => "database initialization failed: migration rejected; check schema compatibility and backup before repair",
        })
    }
}

impl Error for InitError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        Some(match self {
            Self::Storage(error) => error,
            Self::Connection(error) => error,
            Self::Migration(error) => error,
        })
    }
}

pub async fn connect(path: &Path) -> Result<SqlitePool, InitError> {
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
        tracing::error!("database migration failed");
        pool.close().await;
        return Err(InitError::Migration(error));
    }
    tracing::info!("database migrations complete");
    Ok(pool)
}
