/**
 * Canned research responses.
 *
 * The panel's states — needs_browser, robots_denied, budget_exceeded — depend
 * on what a real website does, which an offline suite cannot arrange. These
 * fixtures are served through `page.route`, so the tests drive the frontend
 * deterministically without the backend ever fetching anything.
 *
 * The shapes mirror the API contract exactly; a drift between them shows up as
 * a TypeScript-free runtime mismatch, which the "applied payload" assertions
 * would catch.
 */

export const RESEARCH_RUN_ID = "11111111-2222-3333-4444-555555555555";

export interface ResearchRunFixture {
  research_id: string;
  company_id: string | null;
  company_name: string;
  website: string;
  status: "completed" | "partial" | "failed";
  failure_code: string | null;
  started_at: string;
  completed_at: string | null;
  pages_fetched: number;
  pages_failed: number;
  claims_extracted: number;
  claims_validated: number;
  extractor: { provider: string; model: string; prompt_version: string } | null;
  profile: Record<string, unknown>;
  pages: Array<Record<string, unknown>>;
  claims: Array<Record<string, unknown>>;
  rejected_claims: Array<Record<string, unknown>>;
  warnings: string[];
  unknown_dimensions: string[];
  output_language: string;
  action?: string;
}

const NOW = "2026-07-19T12:00:00Z";

function page(position: number, path: string, reason: string) {
  return {
    position,
    url: `https://acme.example${path}`,
    final_url: `https://acme.example${path}`,
    http_status: 200,
    content_type: "text/html",
    fetched_at: NOW,
    content_chars: 812,
    truncated: false,
    discovery_reason: reason,
  };
}

function claim(
  position: number,
  kind: string,
  detail: string,
  path: string,
  confidence: number,
) {
  return {
    position,
    kind,
    detail,
    evidence_snippet: `verbatim sentence supporting ${kind}`,
    source_url: `https://acme.example${path}`,
    confidence,
  };
}

const BASE: ResearchRunFixture = {
  research_id: RESEARCH_RUN_ID,
  company_id: null,
  company_name: "Acme Hardware",
  website: "https://acme.example",
  status: "completed",
  failure_code: null,
  started_at: NOW,
  completed_at: NOW,
  pages_fetched: 2,
  pages_failed: 0,
  claims_extracted: 3,
  claims_validated: 3,
  extractor: {
    provider: "fake",
    model: "fake-research-v1",
    prompt_version: "research-extract-fake-v1",
  },
  profile: {
    summary: "Hardware importer",
    industry: null,
    products: [],
    locations: [],
    size_hint: null,
    year_founded: null,
    mentions_importing: true,
  },
  pages: [page(0, "/", "homepage"), page(1, "/about", "ranked:about")],
  claims: [
    claim(0, "import_activity", "进口五金，来自亚洲", "/", 0.8),
    claim(1, "company_scale", "自有仓库约 12 万平方英尺", "/", 0.6),
    claim(2, "growth_signal", "进口量逐年增长", "/about", 0.7),
  ],
  rejected_claims: [
    {
      reason: "snippet_not_found",
      kind: "cargo_value_potential",
      detail: "invented value claim",
      warning: "claim rejected (snippet_not_found): not present on page",
    },
  ],
  warnings: [],
  unknown_dimensions: ["shipping_fit", "pain_point"],
  output_language: "zh-CN",
  action: "recorded",
};

export const COMPLETED_RUN: ResearchRunFixture = { ...BASE };

export const PARTIAL_RUN: ResearchRunFixture = {
  ...BASE,
  status: "partial",
  failure_code: null,
  pages_fetched: 1,
  pages_failed: 1,
  pages: [page(0, "/", "homepage")],
  warnings: ["https://acme.example/about could not be read (http_error): HTTP 404"],
  action: "partial",
};

export const NEEDS_BROWSER_RUN: ResearchRunFixture = {
  ...BASE,
  status: "partial",
  failure_code: "needs_browser",
  claims: [],
  claims_extracted: 0,
  claims_validated: 0,
  rejected_claims: [],
  warnings: ["pages yielded almost no text — the site likely requires a browser"],
  action: "partial",
};

export const ROBOTS_DENIED_RUN: ResearchRunFixture = {
  ...BASE,
  status: "failed",
  failure_code: "robots_denied",
  pages: [],
  pages_fetched: 0,
  claims: [],
  claims_extracted: 0,
  claims_validated: 0,
  rejected_claims: [],
  warnings: ["robots.txt disallows the homepage: https://acme.example"],
  action: "failed",
};

export const BUDGET_EXCEEDED_RUN: ResearchRunFixture = {
  ...BASE,
  status: "partial",
  failure_code: "budget_exceeded",
  warnings: ["time budget exhausted — extracting from pages read so far"],
  action: "partial",
};

/** What confirm returns for a run with no company: the form payload. */
export function confirmResponse(
  signals: Array<{ kind: string; detail: string }>,
  sources: Array<{ source: string; reference: string }>,
) {
  return {
    research_id: RESEARCH_RUN_ID,
    action: "recorded",
    company_id: null,
    summary: {
      accepted: signals.length,
      edited: 0,
      rejected: 0,
      total: signals.length,
    },
    promotions: signals.map((signal, index) => ({
      claim_position: index,
      decision: "accepted",
      kind: signal.kind,
      detail: signal.detail,
      company_source_position: null,
      company_signal_position: null,
      source_reused: false,
      idempotent: false,
    })),
    application_payload: {
      company_name: "Acme Hardware",
      website: "https://acme.example",
      sources,
      signals,
    },
    warnings: [],
  };
}
