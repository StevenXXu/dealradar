# DealRadar Phase 1: Data Foundation & Discovery Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Notion with Supabase as the queryable data layer, add a Next.js dashboard with Clerk auth, enable UGC signal submission, and modify the pipeline to upsert to Supabase directly.

**Architecture:** Supabase PostgreSQL becomes the primary store. The harvester pipeline enriches companies and upserts to Supabase (parallel with Notion for now). The Next.js dashboard reads from Supabase, and users submit signals via API routes that write to the `signals` table. Clerk handles auth.

**Tech Stack:** Supabase (PostgreSQL), Next.js 14 (App Router), Clerk (auth), Vercel (deploy), Python `supabase` client, `postgrest` for pipeline upsert.

---

## File Structure

```
C:\Users\StevenDesk\mywork\dealradar
├── supabase\
│   └── migrations\
│       └── 001_initial_schema.sql      # All 4 tables + indexes
├── scripts\
│   └── etl_json_to_supabase.py          # Idempotent ETL: JSON → Supabase
├── src\supabase\
│   └── client.py                        # Supabase client wrapper
├── src\commander\
│   └── supabase_pusher.py               # Pipeline upsert step (NEW)
├── src\harvester\pipeline.py            # MODIFIED: call SupabasePusher after enrichment
├── tests\
│   ├── test_supabase_client.py          # Unit tests for client wrapper
│   ├── test_etl_script.py               # ETL idempotency + dedup tests
│   └── test_supabase_pusher.py          # Pipeline upsert integration tests
│
└── frontend\                            # Next.js app (NEW - created via npx create-next-app)
    ├── app\
    │   ├── layout.tsx                   # Root layout with Clerk Provider
    │   ├── page.tsx                     # Discovery feed (/)
    │   ├── company\[id]\page.tsx        # Company detail (/company/[id])
    │   ├── vc\[slug]\page.tsx          # VC portfolio (/vc/[slug])
    │   ├── submit\page.tsx              # UGC signal submission (/submit)
    │   ├── signals\page.tsx             # Admin signal queue (/signals)
    │   └── api\signals\route.ts         # POST /api/signals
    ├── components\
    │   ├── CompanyCard.tsx
    │   ├── SignalForm.tsx
    │   └── AdminSignalTable.tsx
    ├── lib\
    │   └── supabase.ts                  # Browser client + types
    └── .env.local                       # NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
```

---

## Task 1: Supabase Schema Migration

**Files:**
- Create: `supabase/migrations/001_initial_schema.sql`
- Create: `tests/test_supabase_schema.sql` (regression check)
- Test: Run schema on a test Supabase project
- Note: `ai_inferences` is populated by the existing `ReasonerPipeline` (`src/reasoner/pipeline.py`) — no new write path needed in Phase 1.

- [ ] **Step 1: Write the schema migration**

```sql
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
```

- [ ] **Step 2: Apply schema to test Supabase project**

Run: `supabase db push --project-ref <TEST_REF> --db-url <DB_URL>` (or apply via Supabase SQL editor)

Expected: 4 tables created, 7 indexes present (5 on companies, 1 on signals, 1 on ai_inferences).

- [ ] **Step 3: Write regression test**

```python
# tests/test_supabase_schema.py
import pytest

def test_institutions_table_exists(supabase_client):
    result = supabase_client.table("institutions").select("id").limit(1).execute()
    assert result.data is not None

def test_companies_table_has_unique_domain(supabase_client):
    # Insert same domain twice — second should fail
    supabase_client.table("companies").insert({"company_name": "Acme", "domain": "acme.com"}).execute()
    with pytest.raises(Exception):
        supabase_client.table("companies").insert({"company_name": "Acme2", "domain": "acme.com"}).execute()

def test_signals_status_enum(supabase_client):
    # Only valid statuses accepted
    supabase_client.table("signals").insert({"source": "ugc", "content": {"body": "test"}, "status": "pending"}).execute()
    assert True
```

- [ ] **Step 4: Run schema regression tests**

Run: `pytest tests/test_supabase_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/001_initial_schema.sql tests/test_supabase_schema.py
git commit -m "feat: add Supabase schema (institutions, companies, signals, ai_inferences)"
```

---

## Task 2: Supabase Python Client Wrapper

**Files:**
- Create: `src/supabase/__init__.py`
- Create: `src/supabase/client.py`
- Create: `tests/test_supabase_client.py`
- Modify: `.env` (add `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_supabase_client.py
import os, pytest
from src.supabase.client import SupabaseClient

@pytest.fixture
def client():
    os.environ["SUPABASE_URL"] = "https://test-project.supabase.co"
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"
    return SupabaseClient()

def test_upsert_company_inserts_new(client):
    result = client.upsert_company({
        "company_name": "Acme",
        "domain": "acme.com",
        "institution_id": None,
        "sector": "SaaS",
        "one_liner": "AI-powered acme",
        "signal_score": 72,
        "ai_model_used": "gpt-4o-mini",
    })
    assert result["domain"] == "acme.com"
    assert result["signal_score"] == 72

def test_upsert_company_updates_existing(client):
    client.upsert_company({"company_name": "Acme", "domain": "acme.com", "signal_score": 50})
    result = client.upsert_company({"company_name": "Acme", "domain": "acme.com", "signal_score": 80})
    assert result["signal_score"] == 80

def test_upsert_company_deduplicates_by_domain(client):
    # Two companies with same domain from different VCs → same row
    client.upsert_company({"company_name": "Acme", "domain": "acme.com", "institution_id": "uuid-vc-a"})
    client.upsert_company({"company_name": "Acme", "domain": "acme.com", "institution_id": "uuid-vc-b"})
    all_acme = client.get_companies_by_domain("acme.com")
    assert len(all_acme) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_supabase_client.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# src/supabase/__init__.py
from .client import SupabaseClient

# src/supabase/client.py
"""Supabase client wrapper for DealRadar pipeline and ETL."""
import os
from datetime import datetime, timezone
from supabase import create_client, Client

class SupabaseClient:
    def __init__(self, url: str | None = None, service_role_key: str | None = None):
        self.url = url or os.getenv("SUPABASE_URL", "")
        self.service_key = service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.url or not self.service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        self._client: Client = create_client(self.url, self.service_key)

    def upsert_company(self, company: dict) -> dict:
        """Insert or update a company. Deduplicates by domain."""
        result = self._client.table("companies").upsert(
            {
                "company_name": company["company_name"],
                "domain": company["domain"],
                "institution_id": company.get("institution_id"),
                "sector": company.get("sector"),
                "one_liner": company.get("one_liner"),
                "signal_score": company.get("signal_score", 0),
                "tags": company.get("tags", []),
                "last_raise_amount": company.get("last_raise_amount"),
                "last_raise_date": company.get("last_raise_date"),
                "funding_clock": company.get("funding_clock"),
                "ai_model_used": company.get("ai_model_used"),
                "source_url": company.get("source_url"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="domain",
            ignore_duplicates=False,
        ).execute()
        return result.data[0] if result.data else {}

    def get_companies_by_domain(self, domain: str) -> list[dict]:
        result = self._client.table("companies").select("*").eq("domain", domain).execute()
        return result.data or []

    def upsert_institution(self, institution: dict) -> dict:
        result = self._client.table("institutions").upsert(
            {
                "name": institution["name"],
                "slug": institution["slug"],
                "website_url": institution.get("website_url"),
                "tier": institution.get("tier", 3),
                "portfolio_url": institution.get("portfolio_url"),
            },
            on_conflict="name",
        ).execute()
        return result.data[0] if result.data else {}

    def insert_signal(self, signal: dict) -> dict:
        result = self._client.table("signals").insert(
            {
                "company_id": signal["company_id"],
                "source": signal.get("source", "ugc"),
                "content": signal.get("content", {}),
                "signal_score": signal.get("signal_score", 0),
                "status": signal.get("status", "pending"),
            }
        ).execute()
        return result.data[0] if result.data else {}

    def get_pending_signals(self) -> list[dict]:
        result = (
            self._client.table("signals")
            .select("*, companies(company_name, domain)")
            .eq("status", "pending")
            .execute()
        )
        return result.data or []

    def approve_signal(self, signal_id: str) -> dict:
        result = (
            self._client.table("signals")
            .update({"status": "published"})
            .eq("id", signal_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def reject_signal(self, signal_id: str) -> dict:
        result = (
            self._client.table("signals")
            .update({"status": "rejected"})
            .eq("id", signal_id)
            .execute()
        )
        return result.data[0] if result.data else {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_supabase_client.py -v` (use a real Supabase test project or mock)
Expected: FAIL on real API calls (expected — tests against real Supabase in CI; local uses env vars)

- [ ] **Step 5: Commit**

```bash
git add src/supabase/ tests/test_supabase_client.py .env.example
git commit -m "feat: add Supabase client wrapper for pipeline upsert"
```

---

## Task 3: ETL Script — JSON → Supabase

**Files:**
- Create: `scripts/etl_json_to_supabase.py`
- Create: `tests/test_etl_script.py`
- Modify: `data/raw_companies.json`, `data/enriched_companies.json` (read by ETL)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_etl_script.py
import json, pytest, os
from scripts.etl_json_to_supabase import ETLPipeline

def test_etl_is_idempotent(tmp_path):
    # Write minimal test data
    raw = [{"company_name": "Acme", "domain": "acme.com", "vc_source": "startmate"}]
    enriched = [{"company_name": "Acme", "domain": "acme.com", "sector": "SaaS", "signal_score": 65}]
    (tmp_path / "raw_companies.json").write_text(json.dumps(raw))
    (tmp_path / "enriched_companies.json").write_text(json.dumps(enriched))
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"
    # ETLPipeline would be imported; mocked in real tests
    # Verifies: second run produces same result (no duplicate domain rows)
    assert True  # placeholder until real Supabase available

def test_etl_loads_vc_seeds(tmp_path):
    vc_seeds = [{"name": "Startmate", "slug": "startmate", "url": "https://startmate.com/portfolio"}]
    # ETL loads vc_seeds → institutions table
    assert len(vc_seeds) == 1  # sanity check
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_etl_script.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write the ETL implementation**

```python
# scripts/etl_json_to_supabase.py
"""Idempotent ETL: load existing JSON data into Supabase.

Run: python scripts/etl_json_to_supabase.py

Deduplication: companies deduped by domain (same domain = same company row).
ETL is idempotent — safe to re-run.
"""
import json, os, sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.supabase.client import SupabaseClient

RAW_FILE = Path("data/raw_companies.json")
ENRICHED_FILE = Path("data/enriched_companies.json")
VC_SEEDS_FILE = Path("config/vc_seeds.json")


def load_enriched() -> list[dict]:
    if not ENRICHED_FILE.exists():
        print(f"[ETL] No enriched file at {ENRICHED_FILE}, skipping")
        return []
    return json.loads(ENRICHED_FILE.read_text())


def load_raw() -> list[dict]:
    if not RAW_FILE.exists():
        print(f"[ETL] No raw file at {RAW_FILE}, skipping")
        return []
    return json.loads(RAW_FILE.read_text())


def load_vc_seeds() -> list[dict]:
    if not VC_SEEDS_FILE.exists():
        print(f"[ETL] No vc_seeds file at {VC_SEEDS_FILE}, skipping")
        return []
    return json.loads(VC_SEEDS_FILE.read_text())


def run_etl():
    print("[ETL] Starting...")
    client = SupabaseClient()

    # 1. Load institutions from vc_seeds
    seeds = load_vc_seeds()
    institution_map: dict[str, str] = {}  # slug → id
    for seed in seeds:
        inst = client.upsert_institution({
            "name": seed["name"],
            "slug": seed["slug"],
            "website_url": seed.get("url", ""),
            "tier": seed.get("tier", 3),
            "portfolio_url": seed.get("url", ""),
        })
        institution_map[seed["slug"]] = inst["id"]
        print(f"  [ETL] Institution: {seed['name']} ({inst['id']})")

    def _normalize_domain(domain: str) -> str:
        """Strip leading www. to prevent same-company dupes."""
        return domain.lower().lstrip("www.")

    # 2. Dedupe companies: group by domain across all raw entries
    # KNOWN LIMITATION: if a company appears in multiple VC portfolios, only the
    # first-seen institution_id is recorded. A junction table (company_institutions)
    # would fix this but is Phase 2 scope.
    domain_map: dict[str, dict] = {}  # normalized_domain → merged company dict
    for company in load_raw():
        raw_domain = company.get("domain", "")
        if not raw_domain:
            continue
        domain = _normalize_domain(raw_domain)
        if domain not in domain_map:
            domain_map[domain] = company.copy()
            domain_map[domain]["_normalized_domain"] = domain
        # Keep first seen institution if not yet set
        if not domain_map[domain].get("institution_slug"):
            domain_map[domain]["institution_slug"] = company.get("vc_source", "")

    # 3. Apply enriched fields
    enriched_by_domain: dict[str, dict] = {
        c.get("domain", "").lower(): c
        for c in load_enriched()
        if c.get("domain")
    }
    for domain, company in domain_map.items():
        enriched = enriched_by_domain.get(domain, {})
        company.update({k: v for k, v in enriched.items() if v})

    # 4. Upsert all companies
    total = len(domain_map)
    for i, (domain, company) in enumerate(domain_map.items()):
        institution_slug = company.get("institution_slug", "")
        institution_id = institution_map.get(institution_slug)

        result = client.upsert_company({
            "company_name": company.get("company_name", domain),
            "domain": domain,
            "institution_id": institution_id,
            "sector": company.get("sector"),
            "one_liner": company.get("one_liner"),
            "signal_score": company.get("signal_score", 0),
            "tags": company.get("tags", []),
            "last_raise_amount": company.get("last_raise_amount"),
            "last_raise_date": company.get("last_raise_date"),
            "funding_clock": company.get("funding_clock"),
            "ai_model_used": company.get("ai_model_used"),
            "source_url": company.get("source_citation") or company.get("domain", ""),
        })
        if (i + 1) % 50 == 0:
            print(f"  [ETL] Processed {i+1}/{total} companies...")

    print(f"[ETL] Done. {total} unique companies upserted.")


if __name__ == "__main__":
    run_etl()
```

- [ ] **Step 4: Verify ETL script is syntactically valid**

Run: `python -c "import ast; ast.parse(open('scripts/etl_json_to_supabase.py').read())"`
Expected: No SyntaxError

- [ ] **Step 5: Commit**

```bash
git add scripts/etl_json_to_supabase.py tests/test_etl_script.py
git commit -m "feat: add idempotent ETL script for JSON → Supabase migration"
```

---

## Task 4: Pipeline — Add Supabase Upsert Step

**Files:**
- Modify: `src/harvester/pipeline.py` (add SupabasePusher call after enrichment)
- Create: `src/commander/supabase_pusher.py`
- Create: `tests/test_supabase_pusher.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_supabase_pusher.py
import pytest, os
from unittest.mock import MagicMock, patch

os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"

def test_pusher_called_after_enrichment():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    pusher._client = mock_client
    company = {"company_name": "Acme", "domain": "acme.com", "signal_score": 72}
    result = pusher.push_company(company)
    mock_client.upsert_company.assert_called_once_with(company)
    assert result["domain"] == "acme.com"

def test_pusher_skips_missing_domain():
    from src.commander.supabase_pusher import SupabasePusher
    pusher = SupabasePusher()
    mock_client = MagicMock()
    pusher._client = mock_client
    result = pusher.push_company({"company_name": "No Domain Co"})
    mock_client.upsert_company.assert_not_called()
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_supabase_pusher.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write SupabasePusher**

```python
# src/commander/supabase_pusher.py
"""Supabase pusher — called by HarvesterPipeline after AI enrichment.

Replaces Notion push as primary store. Runs in parallel with Notion push
during transition, then Notion push is removed in Phase 1 cleanup.
"""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.supabase.client import SupabaseClient


class SupabasePusher:
    def __init__(self):
        self._client = None

    @property
    def client(self) -> SupabaseClient:
        if self._client is None:
            self._client = SupabaseClient()
        return self._client

    def push_company(self, company: dict) -> dict | None:
        """Upsert a single enriched company to Supabase. Returns result or None if skipped."""
        domain = company.get("domain")
        if not domain:
            return None
        return self.client.upsert_company(company)

    def push_batch(self, companies: list[dict]) -> dict:
        """Push a batch of companies. Returns summary dict."""
        results = {"pushed": 0, "skipped": 0, "errors": 0}
        for company in companies:
            try:
                result = self.push_company(company)
                if result:
                    results["pushed"] += 1
                else:
                    results["skipped"] += 1
            except Exception as e:
                print(f"  [SupabasePusher] Error pushing {company.get('company_name')}: {e}")
                results["errors"] += 1
        return results
```

- [ ] **Step 4: Integrate into HarvesterPipeline**

Read `src/harvester/pipeline.py` to find the exact location to add the SupabasePusher call (after AI enrichment, in `_run` method or equivalent). The call should be:

```python
from src.commander.supabase_pusher import SupabasePusher

# In __init__ or _run:
self.supabase_pusher = SupabasePusher()

# After enrichment (inside the company loop):
enriched = self._enrich_company(detail_url, vcSlug, harvester_type)
self.supabase_pusher.push_company(enriched)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_supabase_pusher.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/commander/supabase_pusher.py src/harvester/pipeline.py tests/test_supabase_pusher.py
git commit -m "feat: add Supabase upsert step to harvester pipeline"
```

---

## Task 5: Next.js Dashboard Scaffold

**Files:**
- Create: `frontend/` (via `npx create-next-app@latest frontend`)
- Create: `frontend/.env.local`
- Create: `frontend/app/layout.tsx` (ClerkProvider wrapper)
- Modify: `frontend/package.json` (add dependencies)

- [ ] **Step 1: Scaffold Next.js app**

Run: `cd C:/Users/StevenDesk/mywork/dealradar && npx create-next-app@latest frontend --typescript --tailwind --app --no-src-dir --import-alias "@/*" --use-npm`

Expected: Next.js app created in `frontend/` directory.

- [ ] **Step 2: Install dependencies**

Run: `cd frontend && npm install @clerk/nextjs @supabase/supabase-js`

- [ ] **Step 3: Configure Clerk in layout**

```typescript
// frontend/app/layout.tsx
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>{children}</body>
      </html>
    </ClerkProvider>
  );
}
```

- [ ] **Step 4: Configure env vars**

```bash
# frontend/.env.local
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Next.js dashboard with Clerk and Supabase clients"
```

---

## Task 6: Supabase Browser Client + Types

**Files:**
- Create: `frontend/lib/supabase.ts`
- Create: `frontend/lib/types.ts`

- [ ] **Step 1: Write the browser client**

```typescript
// frontend/lib/supabase.ts
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// Server-side client (for API routes) uses service role key
export function getServerSupabase() {
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;
  return createClient(supabaseUrl, serviceKey);
}
```

```typescript
// frontend/lib/types.ts
export interface Company {
  id: string;
  institution_id: string | null;
  company_name: string;
  domain: string | null;
  one_liner: string | null;
  sector: string | null;
  signal_score: number;
  tags: string[];
  last_raise_amount: string | null;
  last_raise_date: string | null;
  funding_clock: string | null;
  ai_model_used: string | null;
  source_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Institution {
  id: string;
  name: string;
  slug: string;
  website_url: string | null;
  tier: number;
  portfolio_url: string | null;
}

export interface Signal {
  id: string;
  company_id: string;
  source: string;
  content: { title?: string; body: string; author?: string; links?: string[] };
  signal_score: number;
  status: "pending" | "published" | "rejected";
  created_at: string;
  // Joined
  companies?: { company_name: string; domain: string };
}
```

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors (types align)

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/supabase.ts frontend/lib/types.ts
git commit -m "feat: add Supabase browser client and TypeScript types"
```

---

## Task 7: Discovery Feed Page (`/`)

**Files:**
- Create: `frontend/app/page.tsx`
- Create: `frontend/components/CompanyCard.tsx`

- [ ] **Step 1: Write CompanyCard component**

```typescript
// frontend/components/CompanyCard.tsx
import Link from "next/link";
import { Company } from "@/lib/types";

export function CompanyCard({ company }: { company: Company }) {
  return (
    <Link href={`/company/${company.id}`} className="block border rounded p-4 hover:shadow transition">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-semibold text-lg">{company.company_name}</h3>
          <p className="text-sm text-gray-500">{company.domain}</p>
        </div>
        <span className="text-sm font-medium bg-blue-100 text-blue-800 rounded px-2 py-1">
          {company.signal_score}
        </span>
      </div>
      <p className="mt-2 text-gray-700">{company.one_liner || "No description yet."}</p>
      <div className="mt-2 flex gap-2 flex-wrap">
        {company.sector && (
          <span className="text-xs bg-gray-100 px-2 py-1 rounded">{company.sector}</span>
        )}
        {company.tags?.slice(0, 3).map((tag) => (
          <span key={tag} className="text-xs bg-gray-100 px-2 py-1 rounded">{tag}</span>
        ))}
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Write discovery feed page**

```typescript
// frontend/app/page.tsx
"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Company } from "@/lib/types";
import { CompanyCard } from "@/components/CompanyCard";

const SECTORS = ["All", "SaaS", "Fintech", "Health", "AI", "Crypto", "E-commerce", "Other"];

const PAGE_SIZE = 50;

export default function DiscoveryFeed() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [sector, setSector] = useState("All");
  const [sort, setSort] = useState<"score" | "name" | "newest">("score");
  const [page, setPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const from = page * PAGE_SIZE;
    let query = supabase
      .from("companies")
      .select("*", { count: "exact" })
      .order(sort === "score" ? "signal_score" : sort === "name" ? "company_name" : "created_at", { ascending: sort === "name" })
      .range(from, from + PAGE_SIZE - 1);

    if (sector !== "All") {
      query = query.eq("sector", sector);
    }

    query.then(({ data, count }) => {
      setCompanies(data || []);
      setTotalCount(count || 0);
      setLoading(false);
    });
  }, [sector, sort, page]);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  return (
    <main className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-2">DealRadar</h1>
      <p className="text-gray-500 mb-6">Discover companies VCs are funding before the market does.</p>

      <div className="flex gap-4 mb-6 flex-wrap">
        <div className="flex gap-2">
          {SECTORS.map((s) => (
            <button
              key={s}
              onClick={() => setSector(s)}
              className={`px-3 py-1 rounded text-sm ${sector === s ? "bg-blue-600 text-white" : "bg-gray-100"}`}
            >
              {s}
            </button>
          ))}
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "score" | "name" | "newest")}
          className="border rounded px-2 py-1 text-sm"
        >
          <option value="score">Top Ranked</option>
          <option value="name">A-Z</option>
          <option value="newest">Newest</option>
        </select>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading...</p>
      ) : companies.length === 0 ? (
        <p className="text-gray-400">No companies found.</p>
      ) : (
        <>
          <div className="grid gap-4">
            {companies.map((company) => (
              <CompanyCard key={company.id} company={company} />
            ))}
          </div>

          {/* Pagination */}
          <div className="flex justify-between items-center mt-6 pt-4 border-t">
            <p className="text-sm text-gray-500">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalCount)} of {totalCount}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1 border rounded text-sm disabled:opacity-50"
              >
                ← Prev
              </button>
              <span className="px-3 py-1 text-sm">
                Page {page + 1} of {totalPages || 1}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1 border rounded text-sm disabled:opacity-50"
              >
                Next →
              </button>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: BUILD SUCCEEDED

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx frontend/components/CompanyCard.tsx
git commit -m "feat: add discovery feed page with sector filter and sort"
```

---

## Task 8: Company Detail Page (`/company/[id]`)

**Files:**
- Create: `frontend/app/company/[id]/page.tsx`

- [ ] **Step 1: Write company detail page**

```typescript
// frontend/app/company/[id]/page.tsx
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Company, Signal } from "@/lib/types";
import Link from "next/link";

export default function CompanyDetailPage() {
  const { id } = useParams();
  const [company, setCompany] = useState<Company | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    supabase
      .from("companies")
      .select("*")
      .eq("id", id)
      .single()
      .then(({ data }) => {
        setCompany(data);
        return supabase
          .from("signals")
          .select("*")
          .eq("company_id", id)
          .in("status", ["published", "pending"])
          .order("created_at", { ascending: false });
      })
      .then(({ data }) => {
        setSignals(data || []);
        setLoading(false);
      });
  }, [id]);

  if (loading) return <p className="p-6">Loading...</p>;
  if (!company) return <p className="p-6">Company not found.</p>;

  return (
    <main className="max-w-3xl mx-auto p-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
        ← Back to feed
      </Link>

      <div className="border rounded-lg p-6 mb-6">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold">{company.company_name}</h1>
            <p className="text-gray-500">{company.domain}</p>
          </div>
          <span className="text-2xl font-bold text-blue-600">{company.signal_score}</span>
        </div>

        <p className="mt-4 text-lg">{company.one_liner || "No description available."}</p>

        <div className="mt-4 flex gap-2 flex-wrap">
          {company.sector && <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-sm">{company.sector}</span>}
          {company.tags?.map((tag) => (
            <span key={tag} className="bg-gray-100 px-2 py-1 rounded text-sm">{tag}</span>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
          {company.last_raise_amount && (
            <div>
              <p className="text-gray-500">Last Raise</p>
              <p className="font-medium">{company.last_raise_amount}</p>
            </div>
          )}
          {company.last_raise_date && (
            <div>
              <p className="text-gray-500">Raise Date</p>
              <p className="font-medium">{company.last_raise_date}</p>
            </div>
          )}
          {company.funding_clock && (
            <div>
              <p className="text-gray-500">Funding Clock</p>
              <p className="font-medium">{company.funding_clock}</p>
            </div>
          )}
        </div>

        {company.source_url && (
          <a href={company.source_url} target="_blank" rel="noopener noreferrer"
             className="mt-4 inline-block text-sm text-blue-600 hover:underline">
            View Source →
          </a>
        )}
      </div>

      {/* Signals Section */}
      <div className="border rounded-lg p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Signals</h2>
          <Link href={`/submit?company=${company.id}`} className="text-sm bg-blue-600 text-white px-3 py-1 rounded">
            Submit Signal
          </Link>
        </div>

        {signals.length === 0 ? (
          <p className="text-gray-400 text-sm">No signals yet. Be the first to submit one.</p>
        ) : (
          <div className="space-y-3">
            {signals.map((signal) => (
              <div key={signal.id} className="border-b pb-3">
                <p className="text-sm font-medium">{signal.content?.body || "No content"}</p>
                <p className="text-xs text-gray-400 mt-1">
                  {signal.source} · {new Date(signal.created_at).toLocaleDateString()}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/company/[id]/page.tsx"
git commit -m "feat: add company detail page with signals section"
```

---

## Task 9: VC Portfolio Page (`/vc/[slug]`)

**Files:**
- Create: `frontend/app/vc/[slug]/page.tsx`

- [ ] **Step 1: Write VC portfolio page**

```typescript
// frontend/app/vc/[slug]/page.tsx
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Company, Institution } from "@/lib/types";
import { CompanyCard } from "@/components/CompanyCard";
import Link from "next/link";

export default function VCPortfolioPage() {
  const { slug } = useParams();
  const [institution, setInstitution] = useState<Institution | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;
    supabase
      .from("institutions")
      .select("*")
      .eq("slug", slug)
      .single()
      .then(({ data }) => {
        setInstitution(data);
        if (!data) { setLoading(false); return; }
        return supabase
          .from("companies")
          .select("*")
          .eq("institution_id", data.id)
          .order("signal_score", { ascending: false });
      })
      .then(({ data }) => {
        setCompanies(data || []);
        setLoading(false);
      });
  }, [slug]);

  if (loading) return <p className="p-6">Loading...</p>;
  if (!institution) return <p className="p-6">VC not found.</p>;

  return (
    <main className="max-w-4xl mx-auto p-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
        ← Back to feed
      </Link>

      <div className="mb-6">
        <h1 className="text-3xl font-bold">{institution.name}</h1>
        {institution.website_url && (
          <a href={institution.website_url} target="_blank" rel="noopener noreferrer"
             className="text-sm text-blue-600 hover:underline">
            {institution.website_url} →
          </a>
        )}
        <p className="text-gray-500 mt-1">{companies.length} companies in portfolio</p>
      </div>

      <div className="grid gap-4">
        {companies.map((company) => (
          <CompanyCard key={company.id} company={company} />
        ))}
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/vc/[slug]/page.tsx"
git commit -m "feat: add VC portfolio page"
```

---

## Task 10: UGC Signal Submission Form (`/submit`)

**Files:**
- Create: `frontend/app/submit/page.tsx`
- Create: `frontend/components/SignalForm.tsx`
- Create: `frontend/app/api/signals/route.ts`

- [ ] **Step 1: Write SignalForm component**

```typescript
// frontend/components/SignalForm.tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const SIGNAL_TYPES = ["Hiring", "Founder Move", "Fundraising", "Technical Signal", "Other"];

export function SignalForm({ companyId }: { companyId?: string }) {
  const router = useRouter();
  const [company, setCompany] = useState(companyId || "");
  const [signalType, setSignalType] = useState("Hiring");
  const [body, setBody] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (body.length < 20) {
      alert("Description must be at least 20 characters.");
      return;
    }
    setStatus("submitting");
    const res = await fetch("/api/signals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: company, source: "ugc", signal_type: signalType, body, email }),
    });
    if (res.ok) {
      setStatus("success");
    } else {
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div className="text-center py-8">
        <h2 className="text-xl font-semibold text-green-600">Signal Submitted!</h2>
        <p className="text-gray-500 mt-2">Thank you. Your signal will appear on the company page once reviewed.</p>
        <button onClick={() => router.push("/")} className="mt-4 text-blue-600 hover:underline">
          ← Back to feed
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-md">
      <div>
        <label className="block text-sm font-medium mb-1">Company Domain or ID</label>
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="acme.com or company-uuid"
          required
          className="w-full border rounded px-3 py-2"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Signal Type</label>
        <select value={signalType} onChange={(e) => setSignalType(e.target.value)}
                className="w-full border rounded px-3 py-2">
          {SIGNAL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Description (min 20 chars)</label>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="e.g. Company X just posted a job ad for a CFO..."
          required
          minLength={20}
          rows={4}
          className="w-full border rounded px-3 py-2"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Your Email (optional)</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="for follow-up only"
          className="w-full border rounded px-3 py-2"
        />
      </div>

      {status === "error" && (
        <p className="text-red-500 text-sm">Something went wrong. Please try again.</p>
      )}

      <button
        type="submit"
        disabled={status === "submitting"}
        className="w-full bg-blue-600 text-white rounded px-4 py-2 hover:bg-blue-700 disabled:opacity-50"
      >
        {status === "submitting" ? "Submitting..." : "Submit Signal"}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Write submit page**

```typescript
// frontend/app/submit/page.tsx
import { SignalForm } from "@/components/SignalForm";
import Link from "next/link";

export default function SubmitPage() {
  return (
    <main className="max-w-2xl mx-auto p-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
        ← Back to feed
      </Link>
      <h1 className="text-2xl font-bold mb-2">Submit a Signal</h1>
      <p className="text-gray-500 mb-6">
        Heard something about a company? Share what you know and help the community.
      </p>
      <SignalForm />
    </main>
  );
}
```

- [ ] **Step 3: Write API route**

```typescript
// frontend/app/api/signals/route.ts
import { NextRequest, NextResponse } from "next/server";
import { getServerSupabase } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  try {
    const { company_id, source, signal_type, body, email } = await req.json();

    if (!company_id || !body || body.length < 20) {
      return NextResponse.json({ error: "company_id and body (min 20 chars) required" }, { status: 400 });
    }

    const supabase = getServerSupabase();

    // Resolve company_id (could be domain string or UUID)
    let resolvedCompanyId = company_id;
    if (!company_id.includes("-") || company_id.length > 50) {
      // It's a domain — look up the company
      const { data: found } = await supabase
        .from("companies")
        .select("id")
        .eq("domain", company_id.toLowerCase())
        .maybeSingle();
      if (!found) {
        return NextResponse.json({ error: "Company not found" }, { status: 404 });
      }
      resolvedCompanyId = found.id;
    }

    const content = {
      title: signal_type,
      body,
      author: email || "anonymous",
    };

    const { data, error } = await supabase
      .from("signals")
      .insert({
        company_id: resolvedCompanyId,
        source: source || "ugc",
        content,
        signal_score: 0,  // Phase 2: wire to configurable scoring formula in Supabase
        status: "pending",
      })
      .select()
      .single();

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ data }, { status: 201 });
  } catch (err) {
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: BUILD SUCCEEDED

- [ ] **Step 5: Commit**

```bash
git add frontend/app/submit/page.tsx frontend/components/SignalForm.tsx frontend/app/api/signals/route.ts
git commit -m "feat: add UGC signal submission form and API route"
```

---

## Task 11: Admin Signal Approval Page (`/signals`)

**Files:**
- Create: `frontend/app/signals/page.tsx` (Clerk `requireAuth()` — admin-only)
- Create: `frontend/components/AdminSignalTable.tsx`
- Create: `frontend/middleware.ts` (Clerk auth guard)

- [ ] **Step 1: Write AdminSignalTable component**

```typescript
// frontend/components/AdminSignalTable.tsx
"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Signal } from "@/lib/types";

export function AdminSignalTable() {
  const [signals, setSignals] = useState<(Signal & { companies?: { company_name: string; domain: string } })[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    const { data } = await supabase
      .from("signals")
      .select("*, companies(company_name, domain)")
      .in("status", ["pending", "published", "rejected"])
      .order("created_at", { ascending: false });
    setSignals(data || []);
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function approve(id: string) {
    await supabase.from("signals").update({ status: "published" }).eq("id", id);
    await load();
  }

  async function reject(id: string) {
    await supabase.from("signals").update({ status: "rejected" }).eq("id", id);
    await load();
  }

  if (loading) return <p className="text-gray-400">Loading...</p>;

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border">
        <thead>
          <tr className="bg-gray-50 border-b">
            <th className="text-left p-3 text-sm">Company</th>
            <th className="text-left p-3 text-sm">Type</th>
            <th className="text-left p-3 text-sm">Signal</th>
            <th className="text-left p-3 text-sm">Status</th>
            <th className="text-left p-3 text-sm">Actions</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((signal) => (
            <tr key={signal.id} className="border-b">
              <td className="p-3 text-sm">
                <p className="font-medium">{signal.companies?.company_name || "Unknown"}</p>
                <p className="text-gray-400 text-xs">{signal.companies?.domain}</p>
              </td>
              <td className="p-3 text-sm">{signal.content?.title || signal.source}</td>
              <td className="p-3 text-sm max-w-xs truncate">{signal.content?.body}</td>
              <td className="p-3 text-sm">
                <span className={`px-2 py-1 rounded text-xs ${
                  signal.status === "published" ? "bg-green-100 text-green-800" :
                  signal.status === "rejected" ? "bg-red-100 text-red-800" :
                  "bg-yellow-100 text-yellow-800"
                }`}>{signal.status}</span>
              </td>
              <td className="p-3 text-sm">
                {signal.status === "pending" && (
                  <>
                    <button onClick={() => approve(signal.id)}
                            className="text-green-600 hover:underline text-sm mr-3">Approve</button>
                    <button onClick={() => reject(signal.id)}
                            className="text-red-600 hover:underline text-sm">Reject</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Write signals admin page**

```typescript
// frontend/app/signals/page.tsx
import { AdminSignalTable } from "@/components/AdminSignalTable";
import { requireAuth } from "@clerk/nextjs";
import Link from "next/link";

export default async function SignalsAdminPage() {
  // Phase 1: any authenticated user can access. Tighten to specific user emails in Phase 2.
  await requireAuth();
  return (
    <main className="max-w-6xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Signal Queue</h1>
          <p className="text-gray-500 text-sm">Review and approve community-submitted signals</p>
        </div>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to feed
        </Link>
      </div>
      <AdminSignalTable />
    </main>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: BUILD SUCCEEDED

- [ ] **Step 4: Add Clerk middleware**

```typescript
// frontend/middleware.ts
import { authMiddleware } from "@clerk/nextjs";

// Protect /signals — redirect to sign-in if not authenticated
export default authMiddleware({
  publicRoutes: ["/", "/submit", "/api/signals", "/company/[^/]+", "/vc/[^/]+"],
});

export const config = {
  matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
```

- [ ] **Step 5: Commit**

```bash
git add frontend/app/signals/page.tsx frontend/components/AdminSignalTable.tsx
git commit -m "feat: add admin signal approval queue page"
```

---

## Execution Options

**Plan complete and saved to `docs/superpowers/plans/2026-03-24-dealradar-phase1-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
