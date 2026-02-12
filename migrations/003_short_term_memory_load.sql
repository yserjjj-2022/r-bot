-- migrations/003_short_term_memory_load.sql
-- Migration: Add short_term_memory_load counter for hippocampus consolidation
-- Date: 2026-02-13
-- Author: R-Bot Team
-- Description: Добавляет счётчик для триггера "ленивого гиппокампа"

-- Add counter for "lazy hippocampus" consolidation trigger
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS short_term_memory_load INTEGER NOT NULL DEFAULT 0;

-- Add last_consolidation_at timestamp for debugging/analytics
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS last_consolidation_at TIMESTAMP DEFAULT NULL;

-- Create partial index for fast queries (only when consolidation is needed)
CREATE INDEX IF NOT EXISTS idx_user_profiles_stm_load 
ON user_profiles(short_term_memory_load) 
WHERE short_term_memory_load >= 20;

-- Verify migration
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_profiles' 
        AND column_name = 'short_term_memory_load'
    ) THEN
        RAISE NOTICE '✅ Migration 003: short_term_memory_load successfully added';
    ELSE
        RAISE EXCEPTION '❌ Migration 003 failed: column not created';
    END IF;
END $$;
