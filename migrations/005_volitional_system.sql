-- migrations/005_volitional_system.sql
-- Migration: Add comprehensive fields for Volitional System (Intensity, Learning, Time)
-- Date: 2026-02-13

-- 1. Add base intensity and learning fields
ALTER TABLE volitional_patterns
ADD COLUMN IF NOT EXISTS intensity FLOAT DEFAULT 0.5, -- Base strength (0.0 - 1.0)
ADD COLUMN IF NOT EXISTS learned_delta FLOAT DEFAULT 0.0, -- Accumulated reinforcement/decay (-1.0 to +1.0)
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE; -- Global switch for pattern

-- 2. Add time-coupling fields for decay and fatigue
ALTER TABLE volitional_patterns
ADD COLUMN IF NOT EXISTS last_activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- For calculating dt (decay)
ADD COLUMN IF NOT EXISTS decay_rate FLOAT DEFAULT 0.01, -- How much intensity is lost per day
ADD COLUMN IF NOT EXISTS reinforcement_rate FLOAT DEFAULT 0.05; -- How much is gained per activation

-- 3. Add metadata for future extensions
ALTER TABLE volitional_patterns
ADD COLUMN IF NOT EXISTS energy_cost FLOAT DEFAULT 0.1; -- How much "mental energy" this pattern consumes

-- Verify
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'volitional_patterns' 
        AND column_name = 'learned_delta'
    ) THEN
        RAISE NOTICE '✅ Migration 005: Volitional System fields added successfully';
    END IF;
END $$;
