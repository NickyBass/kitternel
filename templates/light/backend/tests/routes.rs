use axum::{
    body::{Body, to_bytes},
    http::{Request, StatusCode},
};
use kitternel_light::{AppState, app, db};
use tower::ServiceExt;

async fn fixture() -> (tempfile::TempDir, AppState) {
    let directory = tempfile::tempdir().unwrap();
    let pool = db::connect(&directory.path().join("test.db"))
        .await
        .unwrap();
    let frontend = directory.path().join("public");
    std::fs::create_dir(&frontend).unwrap();
    std::fs::write(
        frontend.join("index.html"),
        "<!doctype html><title>Kitternel</title>",
    )
    .unwrap();
    (
        directory,
        AppState {
            pool,
            frontend_dir: std::sync::Arc::new(frontend),
        },
    )
}

async fn request(state: &AppState, method: &str, path: &str) -> axum::response::Response {
    app(state.clone())
        .oneshot(
            Request::builder()
                .method(method)
                .uri(path)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap()
}

async fn json(response: axum::response::Response) -> serde_json::Value {
    let bytes = to_bytes(response.into_body(), 4096).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

#[tokio::test]
async fn health_and_database_greeting() {
    let (_directory, state) = fixture().await;
    for (path, expected) in [
        ("/health/live", serde_json::json!({"status":"ok"})),
        ("/health/ready", serde_json::json!({"status":"ready"})),
        (
            "/api/hello",
            serde_json::json!({"message":"Hello from Kitternel Light."}),
        ),
    ] {
        let response = request(&state, "GET", path).await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()["content-type"], "application/json");
        assert_eq!(json(response).await, expected);
    }
    // Verify that the handler queries persistent data rather than a hard-coded greeting.
    sqlx::query("UPDATE greetings SET message = ? WHERE id = 1")
        .bind("A changed greeting")
        .execute(&state.pool)
        .await
        .unwrap();
    assert_eq!(
        json(request(&state, "GET", "/api/hello").await).await,
        serde_json::json!({"message":"A changed greeting"})
    );
    state.pool.close().await;
}

#[tokio::test]
async fn database_failure_is_sanitized_and_liveness_stays_up() {
    let (_directory, state) = fixture().await;
    state.pool.close().await;
    let ready = request(&state, "GET", "/health/ready").await;
    assert_eq!(ready.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(
        json(ready).await,
        serde_json::json!({"status":"unavailable"})
    );
    let hello = request(&state, "GET", "/api/hello").await;
    assert_eq!(hello.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(
        json(hello).await,
        serde_json::json!({"error":"service_unavailable"})
    );
    assert_eq!(
        request(&state, "GET", "/health/live").await.status(),
        StatusCode::OK
    );
}

#[tokio::test]
async fn readiness_is_bounded_when_pool_is_exhausted() {
    let (_directory, state) = fixture().await;
    let mut connections = Vec::new();
    for _ in 0..4 {
        connections.push(state.pool.acquire().await.unwrap());
    }
    let response = tokio::time::timeout(
        std::time::Duration::from_millis(1800),
        request(&state, "GET", "/health/ready"),
    )
    .await
    .expect("readiness must time out before pool acquisition timeout");
    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(
        request(&state, "GET", "/health/live").await.status(),
        StatusCode::OK
    );
    drop(connections);
    assert_eq!(
        request(&state, "GET", "/health/ready").await.status(),
        StatusCode::OK
    );
    state.pool.close().await;
}

#[tokio::test]
async fn missing_greeting_returns_sanitized_error() {
    let (_directory, state) = fixture().await;
    sqlx::query("DELETE FROM greetings")
        .execute(&state.pool)
        .await
        .unwrap();
    let response = request(&state, "GET", "/api/hello").await;
    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(
        json(response).await,
        serde_json::json!({"error":"service_unavailable"})
    );
    state.pool.close().await;
}

#[tokio::test]
async fn unknown_routes_are_404_and_read_only_routes_reject_writes() {
    let (_directory, state) = fixture().await;
    for path in ["/api/missing", "/health/missing"] {
        assert_eq!(
            request(&state, "GET", path).await.status(),
            StatusCode::NOT_FOUND
        );
    }
    for path in ["/health/live", "/health/ready", "/api/hello"] {
        assert_eq!(
            request(&state, "POST", path).await.status(),
            StatusCode::METHOD_NOT_ALLOWED
        );
    }
    state.pool.close().await;
}
