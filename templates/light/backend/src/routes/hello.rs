use crate::{AppState, error::ApiError};
use axum::{Json, extract::State};
use serde::Serialize;

#[derive(Serialize)]
pub(super) struct Greeting {
    message: String,
}

pub(super) async fn hello(State(state): State<AppState>) -> Result<Json<Greeting>, ApiError> {
    let result = tokio::time::timeout(
        std::time::Duration::from_secs(3),
        sqlx::query_scalar::<_, String>("SELECT message FROM greetings WHERE id = ?")
            .bind(1)
            .fetch_one(&state.pool),
    )
    .await;
    match result {
        Ok(Ok(message)) => Ok(Json(Greeting { message })),
        _ => {
            // Deliberately omit SQL, database paths, and user data from logs/responses.
            tracing::warn!("greeting database query unavailable");
            Err(ApiError)
        }
    }
}
