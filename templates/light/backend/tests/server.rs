use axum::{Router, routing::get};
use kitternel_light::server::{self, Settings};
use std::{io, sync::Arc, time::Duration};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::{Notify, oneshot},
    task::JoinHandle,
};

struct Running {
    address: std::net::SocketAddr,
    stop: oneshot::Sender<()>,
    task: JoinHandle<io::Result<()>>,
}

async fn start(router: Router, max_connections: usize, shutdown_timeout: Duration) -> Running {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (stop, stopped) = oneshot::channel();
    let task = tokio::spawn(server::serve(
        listener,
        router,
        async {
            let _ = stopped.await;
            Ok(())
        },
        Settings {
            header_timeout: Duration::from_millis(250),
            max_connections,
            shutdown_timeout,
        },
    ));
    Running {
        address,
        stop,
        task,
    }
}

async fn request(address: std::net::SocketAddr, path: &str) -> TcpStream {
    let mut stream = TcpStream::connect(address).await.unwrap();
    stream
        .write_all(
            format!("GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                .as_bytes(),
        )
        .await
        .unwrap();
    stream
}

async fn response(stream: &mut TcpStream) -> Vec<u8> {
    let mut response = Vec::new();
    tokio::time::timeout(Duration::from_secs(3), stream.read_to_end(&mut response))
        .await
        .unwrap()
        .unwrap();
    response
}

async fn stop(server: Running) {
    server.stop.send(()).unwrap();
    tokio::time::timeout(Duration::from_secs(3), server.task)
        .await
        .unwrap()
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn incomplete_headers_time_out_without_stopping_healthy_requests() {
    let server = start(
        Router::new().route("/", get(|| async { "ok" })),
        4,
        Duration::from_secs(1),
    )
    .await;
    let mut slow = TcpStream::connect(server.address).await.unwrap();
    slow.write_all(b"GET / HTTP/1.1\r\nHost: localhost\r\n")
        .await
        .unwrap();
    let reply = response(&mut slow).await;
    assert!(
        reply.is_empty() || reply.starts_with(b"HTTP/1.1 408"),
        "incomplete headers must close or return 408"
    );
    let mut healthy = request(server.address, "/").await;
    assert!(response(&mut healthy).await.starts_with(b"HTTP/1.1 200"));
    stop(server).await;
}

#[tokio::test]
async fn connection_limit_applies_backpressure_and_recovers() {
    let entered = Arc::new(Notify::new());
    let release = Arc::new(Notify::new());
    let router = Router::new().route("/", get(|| async { "ok" })).route(
        "/slow",
        get({
            let entered = entered.clone();
            let release = release.clone();
            move || {
                let entered = entered.clone();
                let release = release.clone();
                async move {
                    entered.notify_one();
                    release.notified().await;
                    "finished"
                }
            }
        }),
    );
    let server = start(router, 1, Duration::from_secs(1)).await;
    let mut first = request(server.address, "/slow").await;
    tokio::time::timeout(Duration::from_secs(3), entered.notified())
        .await
        .unwrap();
    let mut second = request(server.address, "/").await;
    let mut byte = [0u8; 1];
    assert!(
        tokio::time::timeout(Duration::from_millis(100), second.read(&mut byte))
            .await
            .is_err()
    );
    release.notify_one();
    assert!(response(&mut first).await.starts_with(b"HTTP/1.1 200"));
    assert!(response(&mut second).await.starts_with(b"HTTP/1.1 200"));
    stop(server).await;
}

#[tokio::test]
async fn shutdown_drains_an_inflight_response() {
    let entered = Arc::new(Notify::new());
    let release = Arc::new(Notify::new());
    let router = Router::new().route(
        "/",
        get({
            let entered = entered.clone();
            let release = release.clone();
            move || {
                let entered = entered.clone();
                let release = release.clone();
                async move {
                    entered.notify_one();
                    release.notified().await;
                    "finished"
                }
            }
        }),
    );
    let server = start(router, 4, Duration::from_secs(2)).await;
    let mut stream = request(server.address, "/").await;
    tokio::time::timeout(Duration::from_secs(3), entered.notified())
        .await
        .unwrap();
    server.stop.send(()).unwrap();
    release.notify_one();
    let reply = response(&mut stream).await;
    assert!(reply.starts_with(b"HTTP/1.1 200"));
    assert!(reply.ends_with(b"finished"));
    tokio::time::timeout(Duration::from_secs(3), server.task)
        .await
        .unwrap()
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn shutdown_deadline_aborts_stuck_connections() {
    let entered = Arc::new(Notify::new());
    let router = Router::new().route(
        "/",
        get({
            let entered = entered.clone();
            move || {
                let entered = entered.clone();
                async move {
                    entered.notify_one();
                    std::future::pending::<&'static str>().await
                }
            }
        }),
    );
    let server = start(router, 4, Duration::from_millis(100)).await;
    let mut stream = request(server.address, "/").await;
    tokio::time::timeout(Duration::from_secs(3), entered.notified())
        .await
        .unwrap();
    server.stop.send(()).unwrap();
    let error = tokio::time::timeout(Duration::from_secs(3), server.task)
        .await
        .unwrap()
        .unwrap()
        .unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::TimedOut);
    assert!(response(&mut stream).await.is_empty());
}
