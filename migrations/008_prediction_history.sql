-- Migration 008: Add Prediction History for Predictive Processing (Postgres + pgvector)
-- Created: 2026-02-14
-- Description: Stores bot predictions and their verification results.

-- Ensure vector extension exists
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS prediction_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    
    -- Bot's thought process
    bot_message TEXT NOT NULL,
    predicted_reaction TEXT NOT NULL,      -- "User will ask about..."
    
    -- Embeddings (PGVector type)
    predicted_embedding vector(1536),      -- Vector of predicted user response
    
    -- Verification (filled when next message arrives)
    actual_message TEXT,
    actual_embedding vector(1536),         -- Vector of actual user response
    
    prediction_error FLOAT,                -- 0.0 (Perfect) to 1.0 (Lost)
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    verified_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata for debugging
    meta_info JSONB,                       -- JSON: {state: "lost", modifiers: {...}}
    
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Index for fast retrieval of the LAST prediction for a session
CREATE INDEX IF NOT EXISTS idx_prediction_latest 
ON prediction_history(session_id, created_at DESC);

-- Index for analytics on errors
CREATE INDEX IF NOT EXISTS idx_prediction_error
ON prediction_history(prediction_error);
