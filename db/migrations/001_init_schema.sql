-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Customers Table (Managed by EspoCRM optionally, but good to have a dedicated table for AI references)
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID,
    full_name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(50),
    email VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Call Logs Table (Written by Person 2's Voice Orchestrator)
CREATE TABLE IF NOT EXISTS call_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID,
    ticket_id VARCHAR(50),
    customer_id UUID REFERENCES customers(id),
    twilio_call_sid VARCHAR(255),
    call_status VARCHAR(50) NOT NULL,
    outcome VARCHAR(50),
    complaint_transcript TEXT,
    ai_summary TEXT,                     -- Enhancement: AI generated summary
    customer_sentiment VARCHAR(50),      -- Enhancement: Satisfied / Neutral / Angry
    call_attempts INTEGER DEFAULT 1,     -- Tracking for retry logic
    next_retry_at TIMESTAMP,             -- When to try again if no response
    duration_secs INTEGER,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Document Chunks Table (Written by Person 3's RAG Ingestion)
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL,       -- CRITICAL: Multi-tenant isolation
    source_file VARCHAR(255) NOT NULL,
    page_number INTEGER,                 -- Enhancement: Exact page citation
    chunk_index INTEGER,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),              -- Amazon Bedrock Titan dimension size
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Create vector index for faster similarity search
CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx 
ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 4. Chat Interactions Table (Written by Person 3's RAG Chatbot)
CREATE TABLE IF NOT EXISTS chat_interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID,
    user_id UUID,                        -- Agent ID from EspoCRM
    query_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    topic_guard_status VARCHAR(50),      -- ALLOWED or BLOCKED
    source_type VARCHAR(50),             -- kb_match / fallback_general
    similarity_score FLOAT,
    feedback VARCHAR(20),                -- thumbs_up / thumbs_down
    latency_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. AI Learning & Assessment Tables (Populated during Weeks 1-2)
CREATE TABLE IF NOT EXISTS call_lessons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID,
    lesson_text TEXT NOT NULL,           -- e.g. "If user says X, do Y"
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS corrections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID,
    original_query TEXT NOT NULL,
    wrong_answer TEXT,
    correct_answer TEXT NOT NULL,
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
