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
        signal_score: 0,
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