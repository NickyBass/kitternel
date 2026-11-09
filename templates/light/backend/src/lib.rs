pub mod config;
pub mod db;
mod error;
mod routes;
mod static_files;

use axum::{
    Router,
    http::{HeaderValue, header},
};
use sqlx::SqlitePool;
use std::{path::PathBuf, sync::Arc};
use tower_http::set_header::SetResponseHeaderLayer;

#[derive(Clone)]
pub struct AppState {
    pub pool: SqlitePool,
    pub frontend_dir: Arc<PathBuf>,
}

pub fn app(state: AppState) -> Router {
    routes::router()
        .fallback(static_files::serve)
        .with_state(state)
        .layer(SetResponseHeaderLayer::if_not_present(header::CACHE_CONTROL, HeaderValue::from_static("no-store")))
        .layer(SetResponseHeaderLayer::overriding(header::X_CONTENT_TYPE_OPTIONS, HeaderValue::from_static("nosniff")))
        .layer(SetResponseHeaderLayer::overriding(header::X_FRAME_OPTIONS, HeaderValue::from_static("DENY")))
        .layer(SetResponseHeaderLayer::overriding(header::REFERRER_POLICY, HeaderValue::from_static("no-referrer")))
        .layer(SetResponseHeaderLayer::overriding(header::CONTENT_SECURITY_POLICY, HeaderValue::from_static("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")))
}
