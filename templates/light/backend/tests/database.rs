use kitternel_light::db;

#[tokio::test]
async fn migrations_are_repeatable_and_preserve_data_with_safe_connection_pragmas() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("database.sqlite");
    let pool = db::connect(&path).await.unwrap();
    // Hold all connections concurrently so every pool connection is checked.
    let mut connections = Vec::new();
    for _ in 0..4 {
        connections.push(pool.acquire().await.unwrap());
    }
    for connection in &mut connections {
        let journal: String = sqlx::query_scalar("PRAGMA journal_mode")
            .fetch_one(&mut **connection)
            .await
            .unwrap();
        let fk: i32 = sqlx::query_scalar("PRAGMA foreign_keys")
            .fetch_one(&mut **connection)
            .await
            .unwrap();
        let busy: i32 = sqlx::query_scalar("PRAGMA busy_timeout")
            .fetch_one(&mut **connection)
            .await
            .unwrap();
        let sync: i32 = sqlx::query_scalar("PRAGMA synchronous")
            .fetch_one(&mut **connection)
            .await
            .unwrap();
        assert_eq!(journal, "wal");
        assert_eq!(fk, 1);
        assert_eq!(busy, 5000);
        assert_eq!(sync, 2);
    }
    drop(connections);
    sqlx::query("UPDATE greetings SET message = ? WHERE id = ?")
        .bind("Persisted test greeting")
        .bind(1)
        .execute(&pool)
        .await
        .unwrap();
    assert!(
        sqlx::query("INSERT INTO greetings (id, message) VALUES (2, 'invalid')")
            .execute(&pool)
            .await
            .is_err()
    );
    pool.close().await;
    let reopened = db::connect(&path).await.unwrap();
    let message: String = sqlx::query_scalar("SELECT message FROM greetings WHERE id = 1")
        .fetch_one(&reopened)
        .await
        .unwrap();
    assert_eq!(message, "Persisted test greeting");
    let migrations: i32 =
        sqlx::query_scalar("SELECT COUNT(*) FROM _sqlx_migrations WHERE success = 1")
            .fetch_one(&reopened)
            .await
            .unwrap();
    assert_eq!(migrations, 1);
    reopened.close().await;
}

#[tokio::test]
async fn incompatible_schema_refuses_startup() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("bad.sqlite");
    let options = sqlx::sqlite::SqliteConnectOptions::new()
        .filename(&path)
        .create_if_missing(true);
    let pool = sqlx::SqlitePool::connect_with(options).await.unwrap();
    sqlx::query("CREATE TABLE greetings (wrong_column TEXT)")
        .execute(&pool)
        .await
        .unwrap();
    pool.close().await;
    assert!(db::connect(&path).await.is_err());
}
