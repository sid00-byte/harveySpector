-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm for BM25-like text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable full-text search
-- (built-in, no extension needed, but we create the search config)

-- Create the knowledge base table for Companies Act chunks
CREATE TABLE IF NOT EXISTS act_chunks (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(255) UNIQUE NOT NULL,
    document_name VARCHAR(500) NOT NULL DEFAULT 'Companies Act, 2013',
    chapter_number VARCHAR(20),
    chapter_title VARCHAR(500),
    section_number VARCHAR(50),
    section_title VARCHAR(500),
    subsection VARCHAR(50),
    text TEXT NOT NULL,
    page_number INTEGER,
    line_start INTEGER,
    line_end INTEGER,
    parent_chunk_id VARCHAR(255),
    related_sections TEXT[],
    related_forms TEXT[],
    related_rules TEXT[],
    amendment_info TEXT,
    keywords TEXT[],
    embedding vector(768),  -- Gemini text-embedding-004 outputs 768 dimensions
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient retrieval
CREATE INDEX IF NOT EXISTS idx_act_chunks_section ON act_chunks(section_number);
CREATE INDEX IF NOT EXISTS idx_act_chunks_chapter ON act_chunks(chapter_number);
CREATE INDEX IF NOT EXISTS idx_act_chunks_chunk_id ON act_chunks(chunk_id);
CREATE INDEX IF NOT EXISTS idx_act_chunks_embedding ON act_chunks 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- GIN index for full-text search (BM25-like)
CREATE INDEX IF NOT EXISTS idx_act_chunks_text_search ON act_chunks 
    USING gin(to_tsvector('english', text));

-- GIN index for keyword array search
CREATE INDEX IF NOT EXISTS idx_act_chunks_keywords ON act_chunks USING gin(keywords);

-- Create table for uploaded documents
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(255) PRIMARY KEY,
    case_id VARCHAR(255),
    file_name VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(1000),
    extracted_text TEXT,
    page_count INTEGER,
    file_size_bytes BIGINT,
    processing_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create table for analysis results
CREATE TABLE IF NOT EXISTS analyses (
    id VARCHAR(255) PRIMARY KEY,
    case_id VARCHAR(255),
    document_id VARCHAR(255) REFERENCES documents(id),
    status VARCHAR(50) DEFAULT 'processing',
    compliance_score FLOAT,
    report JSONB,
    references JSONB,
    suggestions JSONB,
    required_forms TEXT[],
    processing_time_ms INTEGER,
    llm_model VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create table for chat messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id VARCHAR(255) PRIMARY KEY,
    case_id VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    references JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_case ON chat_messages(case_id);
CREATE INDEX IF NOT EXISTS idx_analyses_case ON analyses(case_id);
CREATE INDEX IF NOT EXISTS idx_documents_case ON documents(case_id);
