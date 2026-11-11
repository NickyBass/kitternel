use std::{env, error::Error, fmt, path::PathBuf, time::Duration};

const DEFAULT_SQLITE_PATH: &str = "data/kitternel.db";

#[derive(Debug)]
pub struct Config {
    pub port: u16,
    pub sqlite_path: PathBuf,
    pub frontend_dir: PathBuf,
    pub shutdown_timeout: Duration,
    pub header_timeout: Duration,
    pub max_connections: usize,
    pub log_level: tracing::Level,
}

#[derive(Debug, PartialEq, Eq)]
pub struct ConfigError(&'static str);

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.0)
    }
}

impl Error for ConfigError {}

impl Config {
    pub fn from_env() -> Result<Self, ConfigError> {
        Self::from_lookup(|name| {
            env::var(name).map(Some).or_else(|error| match error {
                env::VarError::NotPresent => Ok(None),
                env::VarError::NotUnicode(_) => {
                    Err(ConfigError("configuration must be valid Unicode"))
                }
            })
        })
    }

    fn from_lookup(
        lookup: impl Fn(&str) -> Result<Option<String>, ConfigError>,
    ) -> Result<Self, ConfigError> {
        let port = lookup("PORT")?
            .unwrap_or_else(|| "8080".into())
            .parse::<u16>()
            .ok()
            .filter(|port| *port > 0)
            .ok_or(ConfigError("PORT must be an integer between 1 and 65535"))?;
        let shutdown_secs = lookup("SHUTDOWN_TIMEOUT_SECS")?
            .unwrap_or_else(|| "10".into())
            .parse::<u64>()
            .ok()
            .filter(|secs| (1..=300).contains(secs))
            .ok_or(ConfigError(
                "SHUTDOWN_TIMEOUT_SECS must be an integer between 1 and 300",
            ))?;
        let log_level = match lookup("LOG_LEVEL")?.as_deref().unwrap_or("info") {
            "error" => tracing::Level::ERROR,
            "warn" => tracing::Level::WARN,
            "info" => tracing::Level::INFO,
            "debug" => tracing::Level::DEBUG,
            "trace" => tracing::Level::TRACE,
            _ => {
                return Err(ConfigError(
                    "LOG_LEVEL must be error, warn, info, debug, or trace",
                ));
            }
        };
        let sqlite_path = lookup("SQLITE_PATH")?.unwrap_or_else(|| DEFAULT_SQLITE_PATH.into());
        validate_sqlite_path(PathBuf::from(&sqlite_path).as_path())?;
        let header_secs = lookup("HTTP_HEADER_TIMEOUT_SECS")?
            .unwrap_or_else(|| "10".into())
            .parse::<u64>()
            .ok()
            .filter(|seconds| (1..=60).contains(seconds))
            .ok_or(ConfigError(
                "HTTP_HEADER_TIMEOUT_SECS must be an integer between 1 and 60",
            ))?;
        let max_connections = lookup("MAX_CONNECTIONS")?
            .unwrap_or_else(|| "128".into())
            .parse::<usize>()
            .ok()
            .filter(|count| (1..=4096).contains(count))
            .ok_or(ConfigError(
                "MAX_CONNECTIONS must be an integer between 1 and 4096",
            ))?;
        let frontend_dir = lookup("FRONTEND_DIR")?.unwrap_or_else(|| "../frontend/dist".into());
        if frontend_dir.trim().is_empty() {
            return Err(ConfigError(
                "FRONTEND_DIR must name the built frontend directory",
            ));
        }
        Ok(Self {
            port,
            frontend_dir: frontend_dir.into(),
            sqlite_path: sqlite_path.into(),
            shutdown_timeout: Duration::from_secs(shutdown_secs),
            header_timeout: Duration::from_secs(header_secs),
            max_connections,
            log_level,
        })
    }
}

// SQLx opens filenames with SQLITE_OPEN_URI. Only ordinary file paths are supported.
pub(crate) fn validate_sqlite_path(path: &std::path::Path) -> Result<(), ConfigError> {
    match path.to_str() {
        Some(value)
            if !value.trim().is_empty() && value != ":memory:" && !value.starts_with("file:") =>
        {
            Ok(())
        }
        _ => Err(ConfigError(
            "SQLITE_PATH must be an ordinary persistent file path; SQLite URIs are not supported",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config(values: &[(&str, &str)]) -> Result<Config, ConfigError> {
        Config::from_lookup(|key| {
            Ok(values
                .iter()
                .find(|(name, _)| *name == key)
                .map(|(_, value)| value.to_string()))
        })
    }

    #[test]
    fn defaults_and_overrides() {
        let defaults = config(&[]).unwrap();
        assert_eq!(defaults.port, 8080);
        assert_eq!(defaults.shutdown_timeout, Duration::from_secs(10));
        assert_eq!(defaults.log_level, tracing::Level::INFO);
        let custom = config(&[
            ("PORT", "65535"),
            ("SHUTDOWN_TIMEOUT_SECS", "300"),
            ("LOG_LEVEL", "warn"),
        ])
        .unwrap();
        assert_eq!(custom.port, 65535);
        assert_eq!(custom.shutdown_timeout, Duration::from_secs(300));
        assert_eq!(custom.log_level, tracing::Level::WARN);
    }

    #[test]
    fn rejects_invalid_ports_without_echoing_values() {
        for value in ["0", "65536", "-1", "", " 8080", "private-secret"] {
            let error = config(&[("PORT", value)]).unwrap_err();
            assert_eq!(
                error.to_string(),
                "PORT must be an integer between 1 and 65535"
            );
            assert!(!format!("{error:?}").contains(value) || value.is_empty());
        }
    }

    #[test]
    fn database_path_defaults_overrides_and_rejects_memory_or_empty() {
        let expected_path = PathBuf::from("data/kitternel.db");
        assert_eq!(config(&[]).unwrap().sqlite_path, expected_path);
        for path in [
            "/data/custom.db",
            "data/custom.db",
            "data/a path with spaces.db",
            "data/éclair.db",
        ] {
            assert_eq!(
                config(&[("SQLITE_PATH", path)]).unwrap().sqlite_path,
                PathBuf::from(path)
            );
        }
        for path in [
            "",
            "  ",
            ":memory:",
            "file::memory:?cache=shared",
            "file:review?mode=memory&cache=shared",
            "file:/data/app.db?mode=rwc",
        ] {
            assert!(config(&[("SQLITE_PATH", path)]).is_err());
        }
    }

    #[test]
    fn http_limits_have_safe_defaults_and_bounded_overrides() {
        let defaults = config(&[]).unwrap();
        assert_eq!(defaults.header_timeout, Duration::from_secs(10));
        assert_eq!(defaults.max_connections, 128);
        let custom =
            config(&[("HTTP_HEADER_TIMEOUT_SECS", "3"), ("MAX_CONNECTIONS", "32")]).unwrap();
        assert_eq!(custom.header_timeout, Duration::from_secs(3));
        assert_eq!(custom.max_connections, 32);
        for value in ["0", "61", "-1", "invalid"] {
            assert!(config(&[("HTTP_HEADER_TIMEOUT_SECS", value)]).is_err());
        }
        for value in ["0", "4097", "-1", "invalid"] {
            assert!(config(&[("MAX_CONNECTIONS", value)]).is_err());
        }
    }

    #[test]
    fn frontend_directory_has_a_default_and_rejects_empty_values() {
        assert_eq!(
            config(&[]).unwrap().frontend_dir,
            PathBuf::from("../frontend/dist")
        );
        assert_eq!(
            config(&[("FRONTEND_DIR", "/app/public")])
                .unwrap()
                .frontend_dir,
            PathBuf::from("/app/public")
        );
        assert!(config(&[("FRONTEND_DIR", " ")]).is_err());
    }

    #[test]
    fn rejects_invalid_shutdown_timeout_and_log_level() {
        for value in ["0", "301", "-1", "invalid"] {
            assert!(config(&[("SHUTDOWN_TIMEOUT_SECS", value)]).is_err());
        }
        assert!(config(&[("LOG_LEVEL", "invalid-secret")]).is_err());
    }
}
