use kitternel_light::{AppState, app, db};

use axum::{
    body::{Body, to_bytes},
    http::{Request, StatusCode},
};
use tower::ServiceExt;

async fn fixture() -> (tempfile::TempDir, AppState) {
    let directory = tempfile::tempdir().unwrap();
    let frontend = directory.path().join("public");
    std::fs::create_dir_all(frontend.join("assets")).unwrap();
    std::fs::write(
        frontend.join("index.html"),
        "<!doctype html><title>Kitternel</title>",
    )
    .unwrap();
    std::fs::write(frontend.join("assets/app-abc123.js"), "export {}").unwrap();
    std::fs::write(directory.path().join("secret.txt"), "outside frontend root").unwrap();
    std::fs::write(frontend.join(".env"), "not a public asset").unwrap();
    let pool = db::connect(&directory.path().join("test.db"))
        .await
        .unwrap();
    (
        directory,
        AppState {
            pool,
            frontend_dir: std::sync::Arc::new(frontend),
        },
    )
}

async fn request(
    state: &AppState,
    method: &str,
    path: &str,
    headers: &[(&str, &str)],
) -> axum::response::Response {
    let mut builder = Request::builder().method(method).uri(path);
    for (key, value) in headers {
        builder = builder.header(*key, *value);
    }
    app(state.clone())
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap()
}

#[tokio::test]
async fn spa_navigation_serves_html_without_masking_reserved_routes_or_missing_assets() {
    let (_directory, state) = fixture().await;
    for path in ["/", "/index.html", "/example/client-route"] {
        let response = request(&state, "GET", path, &[("accept", "text/html")]).await;
        assert_eq!(response.status(), StatusCode::OK, "{path}");
        assert_eq!(response.headers()["cache-control"], "no-cache");
        assert!(
            response.headers()["content-type"]
                .to_str()
                .unwrap()
                .starts_with("text/html")
        );
        assert_eq!(
            to_bytes(response.into_body(), 4096).await.unwrap(),
            "<!doctype html><title>Kitternel</title>"
        );
    }
    for path in [
        "/api",
        "/api/missing",
        "/api%2fmissing",
        "/health",
        "/health/missing",
        "/assets",
        "/assets/missing",
        "/assets/missing.js",
        "/missing.css",
    ] {
        assert_eq!(
            request(&state, "GET", path, &[("accept", "text/html")])
                .await
                .status(),
            StatusCode::NOT_FOUND,
            "{path}"
        );
    }
    for accept in [
        "application/json",
        "*/*",
        "text/html;q=0",
        "text/html;q=invalid",
    ] {
        assert_eq!(
            request(&state, "GET", "/example", &[("accept", accept)])
                .await
                .status(),
            StatusCode::NOT_FOUND
        );
    }
    state.pool.close().await;
}

#[tokio::test]
async fn static_methods_security_headers_and_cache_are_correct() {
    let (_directory, state) = fixture().await;
    let response = request(&state, "GET", "/assets/app-abc123.js", &[]).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response.headers()["cache-control"],
        "public, max-age=31536000, immutable"
    );
    assert_eq!(response.headers()["x-content-type-options"], "nosniff");
    assert_eq!(response.headers()["x-frame-options"], "DENY");
    assert!(
        response.headers()["content-security-policy"]
            .to_str()
            .unwrap()
            .contains("script-src 'self'")
    );
    assert!(
        response
            .headers()
            .get("access-control-allow-origin")
            .is_none()
    );
    let head = request(&state, "HEAD", "/example", &[("accept", "text/html")]).await;
    assert_eq!(head.status(), StatusCode::OK);
    assert!(to_bytes(head.into_body(), 4096).await.unwrap().is_empty());
    assert_eq!(
        request(&state, "POST", "/example", &[("accept", "text/html")])
            .await
            .status(),
        StatusCode::METHOD_NOT_ALLOWED
    );
    let ready = request(&state, "GET", "/health/ready", &[]).await;
    assert_eq!(ready.headers()["cache-control"], "no-store");
    state.pool.close().await;
}

#[tokio::test]
async fn traversal_hidden_files_and_stale_index_requests_are_handled_safely() {
    let (_directory, state) = fixture().await;
    for path in [
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/%2eenv",
        "/assets/%2e%2e/.env",
        "/%5c..%5csecret.txt",
    ] {
        assert_eq!(
            request(&state, "GET", path, &[("accept", "text/html")])
                .await
                .status(),
            StatusCode::NOT_FOUND,
            "{path}"
        );
    }
    let response = request(
        &state,
        "GET",
        "/example",
        &[
            ("accept", "text/html"),
            ("if-modified-since", "Wed, 01 Jan 2100 00:00:00 GMT"),
            ("range", "bytes=0-4"),
        ],
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        to_bytes(response.into_body(), 4096).await.unwrap(),
        "<!doctype html><title>Kitternel</title>"
    );
    state.pool.close().await;
}
