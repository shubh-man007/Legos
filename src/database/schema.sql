-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Companies table
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Deals table (for organizing documents by deal/transaction)
CREATE TABLE deals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    deal_name VARCHAR(255) NOT NULL,
    deal_type VARCHAR(100), -- 'nda', 'msa', 'acquisition', 'partnership', etc.
    status VARCHAR(50) DEFAULT 'active', -- 'active', 'completed', 'cancelled'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE(company_id, deal_name)
);

-- File uploads table
CREATE TABLE file_uploads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    original_filename VARCHAR(500) NOT NULL,
    gcs_bucket VARCHAR(255) NOT NULL,
    gcs_path VARCHAR(1000) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(255),
    file_hash VARCHAR(64), -- SHA-256 hash
    upload_status VARCHAR(50) DEFAULT 'uploaded', -- 'uploaded', 'processing', 'completed', 'failed'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE(gcs_bucket, gcs_path)
);

-- File tags table (many-to-many relationship)
CREATE TABLE file_tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- File upload tags junction table
CREATE TABLE file_upload_tags (
    file_upload_id UUID NOT NULL REFERENCES file_uploads(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES file_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (file_upload_id, tag_id)
);

-- Processing jobs table
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_upload_id UUID NOT NULL REFERENCES file_uploads(id) ON DELETE CASCADE,
    job_type VARCHAR(100) NOT NULL, -- 'full_pipeline', 'analysis_only', 'extraction_only'
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Document analysis results table
CREATE TABLE document_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_upload_id UUID NOT NULL REFERENCES file_uploads(id) ON DELETE CASCADE,
    processing_job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    
    -- File detection results
    detected_type VARCHAR(100), -- 'pdf_text', 'pdf_scanned', 'word', 'excel', 'text', 'image'
    extraction_engine VARCHAR(100), -- 'extractDocx', 'extractText', 'excelProcessor', 'ocr_docai', etc.
    pages_processed INTEGER,
    extraction_confidence FLOAT,
    
    -- Document classification
    document_type VARCHAR(100), -- 'nda', 'msa', 'company_profile', 'historical_data', 'playbook', 'other'
    classification_confidence FLOAT,
    key_topics TEXT[], -- Array of topics
    
    -- Content analysis
    summary TEXT,
    word_count INTEGER,
    character_count INTEGER,
    
    -- Legal analysis
    contract_type VARCHAR(100),
    parties TEXT[], -- Array of party names
    key_dates JSONB, -- JSON object with date information
    jurisdiction VARCHAR(255),
    
    -- Processing metadata
    processing_log TEXT[],
    warnings TEXT[],
    errors TEXT[],
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Redlines table (legal issues identified)
CREATE TABLE redlines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_analysis_id UUID NOT NULL REFERENCES document_analysis(id) ON DELETE CASCADE,
    issue_description TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL, -- 'low', 'medium', 'high'
    clause_reference VARCHAR(500),
    recommendation TEXT,
    category VARCHAR(100), -- 'liability', 'termination', 'payment', 'confidentiality', etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Common grounds table (areas of agreement)
CREATE TABLE common_grounds (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_analysis_id UUID NOT NULL REFERENCES document_analysis(id) ON DELETE CASCADE,
    area VARCHAR(255) NOT NULL,
    description TEXT,
    leverage TEXT,
    category VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Vector storage metadata table
CREATE TABLE vector_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_analysis_id UUID NOT NULL REFERENCES document_analysis(id) ON DELETE CASCADE,
    vector_ids TEXT[], -- Array of Pinecone vector IDs
    chunk_count INTEGER,
    embedding_model VARCHAR(100),
    index_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_companies_name ON companies(name);
CREATE INDEX idx_deals_company_id ON deals(company_id);
CREATE INDEX idx_deals_status ON deals(status);
CREATE INDEX idx_file_uploads_deal_id ON file_uploads(deal_id);
CREATE INDEX idx_file_uploads_status ON file_uploads(upload_status);
CREATE INDEX idx_file_uploads_hash ON file_uploads(file_hash);
CREATE INDEX idx_processing_jobs_file_upload_id ON processing_jobs(file_upload_id);
CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX idx_document_analysis_file_upload_id ON document_analysis(file_upload_id);
CREATE INDEX idx_document_analysis_document_type ON document_analysis(document_type);
CREATE INDEX idx_redlines_document_analysis_id ON redlines(document_analysis_id);
CREATE INDEX idx_redlines_severity ON redlines(severity);
CREATE INDEX idx_common_grounds_document_analysis_id ON common_grounds(document_analysis_id);

-- Full-text search indexes
CREATE INDEX idx_document_analysis_summary_fts ON document_analysis USING gin(to_tsvector('english', summary));
CREATE INDEX idx_redlines_issue_fts ON redlines USING gin(to_tsvector('english', issue_description));

-- Triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_companies_updated_at BEFORE UPDATE ON companies FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_deals_updated_at BEFORE UPDATE ON deals FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_file_uploads_updated_at BEFORE UPDATE ON file_uploads FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_document_analysis_updated_at BEFORE UPDATE ON document_analysis FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
