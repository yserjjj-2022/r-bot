-- Миграция для добавления колонки sentiment в semantic_memory
-- Запустить, если Initialize DB не сработала автоматически

-- 1. Добавить колонку sentiment
ALTER TABLE semantic_memory 
ADD COLUMN IF NOT EXISTS sentiment JSONB DEFAULT NULL;

-- 2. Создать GIN-индекс для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_semantic_sentiment 
ON semantic_memory USING GIN (sentiment);

-- 3. Добавить метрики в rcore_metrics (если таблица существует)
ALTER TABLE rcore_metrics 
ADD COLUMN IF NOT EXISTS affective_triggers_detected INTEGER DEFAULT 0;

ALTER TABLE rcore_metrics 
ADD COLUMN IF NOT EXISTS sentiment_context_used BOOLEAN DEFAULT FALSE;

-- Проверка результата
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'semantic_memory' 
  AND column_name = 'sentiment';
