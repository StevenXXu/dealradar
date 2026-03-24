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
