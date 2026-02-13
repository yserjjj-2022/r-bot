-- migrations/004_semantic_memory_embedding.sql
-- Migration: Add embedding vector for semantic similarity clustering
-- Date: 2026-02-13
-- Author: R-Bot Team
-- Description: Добавляет vector embedding для дедупликации фактов через pgvector

-- Ensure pgvector extension exists
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column (dimension 1536 для OpenAI text-embedding-3-small)
ALTER TABLE semantic_memory
ADD COLUMN IF NOT EXISTS embedding vector(1536) DEFAULT NULL;

-- Create HNSW index for fast similarity search (cosine distance)
-- HNSW (Hierarchical Navigable Small World) - наиболее эффективный индекс для больших датасетов
CREATE INDEX IF NOT EXISTS idx_semantic_memory_embedding 
ON semantic_memory 
USING hnsw (embedding vector_cosine_ops)
WHERE embedding IS NOT NULL;

-- Create GIN index for combined queries (user_id + embedding)
CREATE INDEX IF NOT EXISTS idx_semantic_memory_user_embedding
ON semantic_memory(user_id)
WHERE embedding IS NOT NULL;

-- Verify migration
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'semantic_memory' 
        AND column_name = 'embedding'
    ) THEN
        RAISE NOTICE '✅ Migration 004: embedding column successfully added';
    ELSE
        RAISE EXCEPTION '❌ Migration 004 failed: column not created';
    END IF;
END $$;
