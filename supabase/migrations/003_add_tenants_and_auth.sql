-- 003_add_tenants_and_auth.sql

-- Tenants table (Workspaces)
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Link Users to Tenants
-- Supabase auth.users is the built-in identity provider
CREATE TABLE IF NOT EXISTS user_tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, tenant_id)
);

-- Add tenant_id to existing tables
ALTER TABLE institutions ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE ai_inferences ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;

-- Update indexes
CREATE INDEX IF NOT EXISTS idx_institutions_tenant_id ON institutions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_companies_tenant_id ON companies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_signals_tenant_id ON signals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_inferences_tenant_id ON ai_inferences(tenant_id);
CREATE INDEX IF NOT EXISTS idx_user_tenants_user_id ON user_tenants(user_id);

-- Create a default 'system' tenant for existing public data if needed
DO $$
DECLARE
    default_tenant_id UUID;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'default') THEN
        INSERT INTO tenants (name, slug) VALUES ('Default System Tenant', 'default') RETURNING id INTO default_tenant_id;
        -- Backfill existing data to default tenant
        UPDATE institutions SET tenant_id = default_tenant_id WHERE tenant_id IS NULL;
        UPDATE companies SET tenant_id = default_tenant_id WHERE tenant_id IS NULL;
        UPDATE signals SET tenant_id = default_tenant_id WHERE tenant_id IS NULL;
        UPDATE ai_inferences SET tenant_id = default_tenant_id WHERE tenant_id IS NULL;
    END IF;
END $$;

-- RLS Policies
-- Drop the permissive Phase 1 policies
DROP POLICY IF EXISTS "allow_all_institutions" ON institutions;
DROP POLICY IF EXISTS "allow_all_companies" ON companies;
DROP POLICY IF EXISTS "allow_all_signals" ON signals;
DROP POLICY IF EXISTS "allow_all_ai_inferences" ON ai_inferences;

-- Enable RLS on new tables
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_tenants ENABLE ROW LEVEL SECURITY;

-- Policies for tenants and user_tenants
CREATE POLICY "Users can view their own tenants"
    ON tenants FOR SELECT
    USING (id IN (SELECT tenant_id FROM public.user_tenants WHERE user_id = auth.uid()));

CREATE POLICY "Users can view their own tenant links"
    ON user_tenants FOR SELECT
    USING (user_id = auth.uid());

-- Policies for business entities (isolation)
-- Allow viewing if the entity belongs to the user's tenant
CREATE POLICY "Tenant isolation for institutions"
    ON institutions FOR ALL
    USING (tenant_id IN (SELECT tenant_id FROM public.user_tenants WHERE user_id = auth.uid()));

CREATE POLICY "Tenant isolation for companies"
    ON companies FOR ALL
    USING (tenant_id IN (SELECT tenant_id FROM public.user_tenants WHERE user_id = auth.uid()));

CREATE POLICY "Tenant isolation for signals"
    ON signals FOR ALL
    USING (tenant_id IN (SELECT tenant_id FROM public.user_tenants WHERE user_id = auth.uid()));

CREATE POLICY "Tenant isolation for ai_inferences"
    ON ai_inferences FOR ALL
    USING (tenant_id IN (SELECT tenant_id FROM public.user_tenants WHERE user_id = auth.uid()));

