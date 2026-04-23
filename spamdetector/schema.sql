CREATE TABLE IF NOT EXISTS requests_history (
    id SERIAL PRIMARY KEY,
    input_text TEXT,
    spam BOOL NOT NULL,
    model_name VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
)