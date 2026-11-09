use kitternel_light::{AppState, app, config::Config, db};
use std::{error::Error, net::Ipv4Addr, process::ExitCode};
use tokio::{net::TcpListener, sync::oneshot};

#[tokio::main]
async fn main() -> ExitCode {
    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("kitternel-light: {error}");
            ExitCode::FAILURE
        }
    }
}

async fn run() -> Result<(), Box<dyn Error>> {
    let config = Config::from_env()?;
    tracing_subscriber::fmt()
        .json()
        .with_max_level(config.log_level)
        .with_writer(std::io::stdout)
        .try_init()
        .map_err(|_| "could not initialize logging")?;

    // Register signal handlers before accepting connections.
    #[cfg(unix)]
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    #[cfg(unix)]
    let mut interrupt = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt())?;
    let shutdown_signal = async {
        #[cfg(unix)]
        tokio::select! {
            _ = terminate.recv() => {},
            _ = interrupt.recv() => {},
        }
        #[cfg(not(unix))]
        tokio::signal::ctrl_c().await?;
        Ok::<(), std::io::Error>(())
    };

    if !config.frontend_dir.join("index.html").is_file() {
        return Err(
            "FRONTEND_DIR must contain a built index.html; build the frontend first".into(),
        );
    }
    let pool = db::connect(&config.sqlite_path).await?;
    let state = AppState {
        pool: pool.clone(),
        frontend_dir: std::sync::Arc::new(config.frontend_dir),
    };
    let listener = TcpListener::bind((Ipv4Addr::UNSPECIFIED, config.port)).await?;
    tracing::info!(port = config.port, "server listening");
    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    let server = axum::serve(listener, app(state)).with_graceful_shutdown(async {
        let _ = shutdown_rx.await;
    });
    let server = std::future::IntoFuture::into_future(server);
    tokio::pin!(server);
    tokio::select! {
        result = &mut server => result?,
        signal = shutdown_signal => {
            signal?;
            tracing::info!("shutdown requested");
            let _ = shutdown_tx.send(());
            tokio::time::timeout(config.shutdown_timeout, &mut server)
                .await.map_err(|_| "graceful shutdown deadline exceeded")??;
        }
    }
    pool.close().await;
    tracing::info!("server stopped");
    Ok(())
}
