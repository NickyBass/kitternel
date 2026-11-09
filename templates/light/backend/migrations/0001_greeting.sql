CREATE TABLE greetings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    message TEXT NOT NULL CHECK (length(message) BETWEEN 1 AND 200)
);

INSERT INTO greetings (id, message) VALUES (1, 'Hello from Kitternel Light.');
