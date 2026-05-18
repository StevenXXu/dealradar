-- Migration: Add region and funding_stage columns to companies table
-- Region: derived from institution (VC) geographic focus
-- Funding_stage: derived from last_raise_amount parsing

ALTER TABLE companies ADD COLUMN IF NOT EXISTS region TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS funding_stage TEXT;

-- Create index for region filter performance
CREATE INDEX IF NOT EXISTS idx_companies_region ON companies(region);
CREATE INDEX IF NOT EXISTS idx_companies_funding_stage ON companies(funding_stage);
CREATE INDEX IF NOT EXISTS idx_companies_signal_score ON companies(signal_score DESC);

-- Add check constraint for region values
ALTER TABLE companies DROP CONSTRAINT IF EXISTS chk_region;
ALTER TABLE companies ADD CONSTRAINT chk_region
  CHECK (region IS NULL OR region IN (
    'North America', 'Europe', 'Asia Pacific', 'Latin America',
    'Middle East & Africa', 'Global', 'Australia & New Zealand'
  ));

-- Add check constraint for funding_stage values
ALTER TABLE companies DROP CONSTRAINT IF EXISTS chk_funding_stage;
ALTER TABLE companies ADD CONSTRAINT chk_funding_stage
  CHECK (funding_stage IS NULL OR funding_stage IN (
    'Pre-seed', 'Seed', 'Series A', 'Series B', 'Series C+'
  ));

-- Seed data: VC slug → region mapping (AU/NZ VCs = Asia Pacific)
-- This will be populated by the region_backfill script
COMMENT ON COLUMN companies.region IS 'Geographic region based on VC source. Values: North America, Europe, Asia Pacific, Latin America, Middle East & Africa, Global, Australia & New Zealand';
COMMENT ON COLUMN companies.funding_stage IS 'Funding stage derived from last_raise_amount. Values: Pre-seed, Seed, Series A, Series B, Series C+';
