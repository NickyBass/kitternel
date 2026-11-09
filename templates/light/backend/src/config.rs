use std::{env, error::Error, fmt, path::PathBuf, time::Duration};

#[derive(Debug)]
pub struct Config {
    pub port: u16,
    pub sqlite_path: PathBuf,
    pub frontend_dir: PathBuf,
    pub shutdown_timeout: Duration,
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
        let sqlite_path = lookup("SQLITE_PATH")?.unwrap_or_else(|| "data/kitternel.db".into());
        if sqlite_path.trim().is_empty() || sqlite_path == ":memory:" {
            return Err(ConfigError(
                "SQLITE_PATH must name a persistent database file",
            ));
        }
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
            log_level,
        })
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
        assert_eq!(
            config(&[]).unwrap().sqlite_path,
            PathBuf::from("data/kitternel.db")
        );
        assert_eq!(
            config(&[("SQLITE_PATH", "/data/custom.db")])
                .unwrap()
                .sqlite_path,
            PathBuf::from("/data/custom.db")
        );
        for path in ["", "  ", ":memory:"] {
            assert!(config(&[("SQLITE_PATH", path)]).is_err());
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
