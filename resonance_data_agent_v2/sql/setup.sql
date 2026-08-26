-- ============================================================
-- RESONANCE DATA AGENT - SUPABASE SETUP
-- Run this in your Supabase SQL Editor (Dashboard > SQL Editor)
-- ============================================================

-- 1. Raw data table (stores all collected records)
CREATE TABLE IF NOT EXISTS raw_data (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    record_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    content_type TEXT,
    author_id TEXT,
    author_name TEXT,
    author_handle TEXT,
    title TEXT,
    text TEXT,
    url TEXT,
    platform TEXT,
    channel TEXT,
    thread_id TEXT,
    parent_id TEXT,
    likes BIGINT,
    comments BIGINT,
    shares BIGINT,
    views BIGINT,
    engagement_rate FLOAT,
    created_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB,
    subculture_tags JSONB,
    value_keywords JSONB,
    sentiment TEXT,
    resonance_score FLOAT,
    inserted_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_data(source);
CREATE INDEX IF NOT EXISTS idx_raw_platform ON raw_data(platform);
CREATE INDEX IF NOT EXISTS idx_raw_channel ON raw_data(channel);
CREATE INDEX IF NOT EXISTS idx_raw_author ON raw_data(author_id);
CREATE INDEX IF NOT EXISTS idx_raw_collected ON raw_data(collected_at);
CREATE INDEX IF NOT EXISTS idx_raw_record ON raw_data(record_id);
CREATE INDEX IF NOT EXISTS idx_raw_inserted ON raw_data(inserted_at);

-- 3. Collection state table (watermarks for incremental pulls)
CREATE TABLE IF NOT EXISTS collection_state (
    source TEXT NOT NULL,
    sub_source TEXT NOT NULL,
    last_timestamp TEXT,
    last_record_id TEXT,
    record_count BIGINT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source, sub_source)
);

-- 4. Enable Row Level Security (optional but recommended)
ALTER TABLE raw_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE collection_state ENABLE ROW LEVEL SECURITY;

-- 5. Create policy for service role (full access)
CREATE POLICY IF NOT EXISTS "Service role full access" ON raw_data
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY IF NOT EXISTS "Service role full access state" ON collection_state
    FOR ALL USING (true) WITH CHECK (true);

-- 6. Verify
SELECT 'raw_data table created' as status;
SELECT 'collection_state table created' as status;
SELECT COUNT(*) as total_records FROM raw_data;
