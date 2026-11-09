use axum::Router;
use hyper::server::conn::http1;
use hyper_util::{
    rt::{TokioIo, TokioTimer},
    service::TowerToHyperService,
};
use std::{future::Future, io, time::Duration};
use tokio::{
    net::TcpListener,
    sync::watch,
    task::{JoinError, JoinSet},
};

#[derive(Clone, Copy)]
pub struct Settings {
    pub header_timeout: Duration,
    pub max_connections: usize,
    pub shutdown_timeout: Duration,
}

// Keep transport limits here: handler middleware cannot time out incomplete headers.
pub async fn serve(
    listener: TcpListener,
    router: Router,
    shutdown: impl Future<Output = io::Result<()>>,
    settings: Settings,
) -> io::Result<()> {
    if settings.max_connections == 0
        || settings.header_timeout.is_zero()
        || settings.shutdown_timeout.is_zero()
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "HTTP limits must be positive",
        ));
    }
    let (shutdown_tx, shutdown_rx) = watch::channel(false);
    let mut connections = JoinSet::new();
    tokio::pin!(shutdown);
    loop {
        tokio::select! {
            biased;
            result = &mut shutdown => { result?; break; }
            result = connections.join_next(), if !connections.is_empty() => {
                if let Some(result) = result { result.map_err(connection_task_error)?; }
            }
            accepted = listener.accept(), if connections.len() < settings.max_connections => {
                let (stream, _) = match accepted {
                    Ok(connection) => connection,
                    Err(error) if matches!(error.kind(), io::ErrorKind::ConnectionAborted | io::ErrorKind::ConnectionReset | io::ErrorKind::Interrupted | io::ErrorKind::WouldBlock) => continue,
                    Err(error) => return Err(error),
                };
                let service = TowerToHyperService::new(router.clone());
                let mut stop = shutdown_rx.clone();
                connections.spawn(async move {
                    let mut builder = http1::Builder::new();
                    builder.timer(TokioTimer::new())
                        .header_read_timeout(settings.header_timeout)
                        .max_headers(64)
                        .max_buf_size(32 * 1024);
                    let connection = builder.serve_connection(TokioIo::new(stream), service);
                    tokio::pin!(connection);
                    let result = tokio::select! {
                        result = &mut connection => result,
                        _ = stop.changed() => {
                            connection.as_mut().graceful_shutdown();
                            connection.await
                        }
                    };
                    if let Err(error) = result {
                        // Request contents and peer identity are intentionally omitted.
                        tracing::debug!(timeout = error.is_timeout(), "HTTP connection closed after protocol or transport error");
                    }
                });
            }
        }
    }
    drop(listener);
    tracing::info!("shutdown requested");
    shutdown_tx.send_replace(true);
    match tokio::time::timeout(settings.shutdown_timeout, async {
        while let Some(result) = connections.join_next().await {
            result.map_err(connection_task_error)?;
        }
        Ok(())
    })
    .await
    {
        Ok(result) => result,
        Err(_) => {
            connections.abort_all();
            // Reap aborted tasks before returning so their sockets are closed.
            while connections.join_next().await.is_some() {}
            Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "graceful HTTP shutdown deadline exceeded",
            ))
        }
    }
}

fn connection_task_error(_: JoinError) -> io::Error {
    io::Error::other("HTTP connection task failed")
}
