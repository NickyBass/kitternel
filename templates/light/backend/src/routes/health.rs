use crate::AppState;
use axum::{Json, extract::State, http::StatusCode, response::IntoResponse};
use serde::Serialize;

#[derive(Serialize)]
pub(super) struct Health {
    status: &'static str,
}

pub(super) async fn live() -> Json<Health> {
    Json(Health { status: "ok" })
}

pub(super) async fn ready(State(state): State<AppState>) -> impl IntoResponse {
    let result = tokio::time::timeout(
        std::time::Duration::from_secs(1),
        sqlx::query_scalar::<_, i32>("SELECT 1").fetch_one(&state.pool),
    )
    .await;
    match result {
        Ok(Ok(1)) => (StatusCode::OK, Json(Health { status: "ready" })),
        _ => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(Health {
                status: "unavailable",
            }),
        ),
    }
}
