-- Migration: LLM Raw Responses (Circular Buffer)
-- Purpose: Log raw LLM responses for debugging (stores last 20 records)
-- Date: 2026-02-11

-- Create table
CREATE TABLE IF NOT EXISTS llm_raw_responses (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'system',
    session_id TEXT,
    timestamp TIMESTAMP DEFAULT NOW(),
    prompt_type TEXT NOT NULL,  -- 'council_report', 'response_generation', etc.
    raw_request TEXT,           -- Промпт (обрезанный до 2000 символов)
    raw_response TEXT,          -- Ответ LLM (обрезанный до 5000 символов)
    parse_status TEXT NOT NULL, -- 'success', 'json_error', 'timeout', 'api_error', 'missing_keys'
    error_message TEXT
);

-- Индекс для быстрого поиска последних записей по user_id
CREATE INDEX IF NOT EXISTS idx_llm_raw_user_time 
ON llm_raw_responses(user_id, timestamp DESC);

-- Индекс для поиска ошибок
CREATE INDEX IF NOT EXISTS idx_llm_raw_errors 
ON llm_raw_responses(parse_status) 
WHERE parse_status != 'success';

-- Комментарии
COMMENT ON TABLE llm_raw_responses IS 'Circular buffer для сырых ответов LLM. Хранит последние 20 записей.';
COMMENT ON COLUMN llm_raw_responses.prompt_type IS 'Тип запроса: council_report, response_generation, etc.';
COMMENT ON COLUMN llm_raw_responses.parse_status IS 'Статус парсинга: success, json_error, timeout, api_error, missing_keys';

-- Пример запроса для просмотра ошибок:
-- SELECT * FROM llm_raw_responses WHERE parse_status != 'success' ORDER BY timestamp DESC LIMIT 10;
