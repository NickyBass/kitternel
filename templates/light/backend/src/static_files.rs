use crate::AppState;
use axum::{
    body::Body,
    extract::{Request, State},
    http::{Method, StatusCode, header},
    response::{IntoResponse, Response},
};
use tower::ServiceExt;
use tower_http::services::{ServeDir, ServeFile};

pub async fn serve(State(state): State<AppState>, request: Request) -> Response {
    let Ok(path) = percent_encoding::percent_decode_str(request.uri().path()).decode_utf8() else {
        return StatusCode::BAD_REQUEST.into_response();
    };
    // Reserve server namespaces even when the URL contains encoded separators.
    if ["/api", "/health"]
        .iter()
        .any(|prefix| path == *prefix || path.starts_with(&format!("{prefix}/")))
    {
        return StatusCode::NOT_FOUND.into_response();
    }
    if path == "/assets" || path == "/assets/" {
        return StatusCode::NOT_FOUND.into_response();
    }
    if path.contains('\\')
        || path.contains('\0')
        || path.split('/').any(|segment| segment.starts_with('.'))
    {
        return StatusCode::NOT_FOUND.into_response();
    }
    if request.method() != Method::GET && request.method() != Method::HEAD {
        return StatusCode::METHOD_NOT_ALLOWED.into_response();
    }
    let navigation = request
        .headers()
        .get(header::ACCEPT)
        .and_then(|value| value.to_str().ok())
        .is_some_and(accepts_html)
        && !path.split('/').any(|segment| segment.contains('.'))
        && path != "/assets"
        && !path.starts_with("/assets/");
    let immutable_asset = path.starts_with("/assets/");
    let index = path == "/" || path == "/index.html";
    // Drop conditional/range headers for HTML to avoid serving stale deployment entrypoints.
    let mut request = request;
    if navigation || index {
        for header in [
            header::IF_MODIFIED_SINCE,
            header::IF_NONE_MATCH,
            header::RANGE,
            header::IF_RANGE,
        ] {
            request.headers_mut().remove(header);
        }
    }
    let service = ServeDir::new(state.frontend_dir.as_ref());
    let response = if navigation {
        service
            .fallback(ServeFile::new(state.frontend_dir.join("index.html")))
            .oneshot(request)
            .await
    } else {
        service.oneshot(request).await
    };
    match response {
        Ok(response) => {
            let mut response = response.map(Body::new);
            let cache = if immutable_asset
                && (response.status().is_success() || response.status() == StatusCode::NOT_MODIFIED)
            {
                "public, max-age=31536000, immutable"
            } else {
                "no-cache"
            };
            response.headers_mut().insert(
                header::CACHE_CONTROL,
                cache.parse().expect("static cache header"),
            );
            response
        }
        Err(error) => match error {},
    }
}

fn accepts_html(accept: &str) -> bool {
    accept.split(',').any(|item| {
        let mut parts = item.trim().split(';');
        parts
            .next()
            .is_some_and(|media| media.trim().eq_ignore_ascii_case("text/html"))
            && parts.all(|parameter| {
                let Some((name, value)) = parameter.trim().split_once('=') else {
                    return true;
                };
                !name.trim().eq_ignore_ascii_case("q")
                    || value
                        .trim()
                        .parse::<f32>()
                        .is_ok_and(|quality| quality > 0.0 && quality <= 1.0)
            })
    })
}
