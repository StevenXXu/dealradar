-- supabase/migrations/001_initial_schema.sql

-- VC/Incubator Registry
CREATE TABLE IF NOT EXISTS institutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    website_url TEXT,
    tier INT DEFAULT 3,  -- 1=Top Tier, 2=Mid, 3=Emerging
    portfolio_url TEXT,
    slug TEXT,  -- e.g. 'blackbird', 'airtree'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Master Portfolio (the inventory)
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id UUID REFERENCES institutions(id) ON DELETE SET NULL,
    company_name TEXT NOT NULL,
    domain TEXT,
    one_liner TEXT,
    sector TEXT,
    signal_score INT DEFAULT 0,
    tags TEXT[],
    last_raise_amount TEXT,
    last_raise_date DATE,
    funding_clock DATE,
    ai_model_used TEXT,
    source_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(domain)
);

-- Raw Signals (UGC + automated)
CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    source TEXT,  -- 'ugc', 'linkedin', 'github', 'webhook'
    content JSONB,  -- flexible payload: {title, body, author, links...}
    signal_score INT DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'rejected')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- AI Inferences (the reasoning layer)
CREATE TABLE IF NOT EXISTS ai_inferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    logic_summary TEXT,
    investment_score INT,
    tags TEXT[],
    model_used TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS idx_companies_institution_id ON companies(institution_id);
CREATE INDEX IF NOT EXISTS idx_companies_signal_score ON companies(signal_score DESC);
CREATE INDEX IF NOT EXISTS idx_companies_funding_clock ON companies(funding_clock) WHERE funding_clock IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_signals_company_id_status ON signals(company_id, status);
CREATE INDEX IF NOT EXISTS idx_ai_inferences_company_id ON ai_inferences(company_id);

-- RLS (Row Level Security) — permissive for anon for Phase 1, tighten later
ALTER TABLE institutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_inferences ENABLE ROW LEVEL SECURITY;

-- Phase 1: allow all operations (auth comes later via Clerk JWT validation in API routes)
CREATE POLICY "allow_all_institutions" ON institutions FOR ALL USING (true);
CREATE POLICY "allow_all_companies" ON companies FOR ALL USING (true);
CREATE POLICY "allow_all_signals" ON signals FOR ALL USING (true);
CREATE POLICY "allow_all_ai_inferences" ON ai_inferences FOR ALL USING (true);