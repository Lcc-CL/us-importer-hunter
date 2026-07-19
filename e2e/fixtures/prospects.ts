/**
 * Synthetic prospects. Never real customers, never real contacts.
 *
 * Every fixture derives a unique company name AND a unique website host from a
 * per-run token. The host matters as much as the name: company deduplication
 * matches on website host, so a fixed host would silently merge each run into
 * the previous run's company and the assertions would drift.
 */

export interface SignalInput {
  kind: string;
  detail: string;
}

export interface ProspectPayload {
  company: {
    name: string;
    website: string;
    sources: Array<{ source: string; reference: string }>;
    signals: SignalInput[];
  };
  contact: {
    name: string;
    title: string;
    email: string;
    source: string;
  };
  sender: { name: string; company: string; value_proposition: string };
  options: { generate_email: boolean };
}

export function runToken(): string {
  return `${Date.now()}${Math.floor(Math.random() * 1000)}`;
}

/**
 * Seven canonical kinds with Chinese detail — the v0.1.1 P0 regression shape.
 * Scores 70.5 with completeness 1.0 and confidence 0.7 → QUALIFIED.
 * `pain_point` is included deliberately: it must be stored and must not score.
 */
export function qualifiedProspect(token = runToken()): ProspectPayload {
  const host = `e2e-qualified-${token}.example`;
  return {
    company: {
      name: `E2E Qualified Importer ${token}`,
      website: `https://${host}`,
      sources: [
        { source: "importyeti", reference: `https://importyeti.test/company/${token}` },
        { source: "company_website", reference: `https://${host}/about` },
      ],
      signals: [
        { kind: "import_activity", detail: "过去 12 个月记录了 108 票海运进口，最近 90 天有 31 票" },
        { kind: "china_dependency", detail: "约 82% 的进口批次来自中国，供应商集中在广东和浙江" },
        { kind: "shipping_fit", detail: "主要采用 40HQ 整柜运输，并存在少量拼箱补货" },
        { kind: "cargo_value_potential", detail: "预计年度进口货值约为 120 万至 180 万美元" },
        { kind: "company_scale", detail: "中型五金产品分销商，员工规模约 50 至 100 人" },
        { kind: "growth_signal", detail: "最近 12 个月进口批次同比增长约 35%，并计划增加 SKU" },
        { kind: "logistics_complexity", detail: "从多个供应商采购，并向两个美国仓储节点补货" },
        { kind: "pain_point", detail: "旺季舱位波动和到仓时间不稳定，增加协调成本" },
      ],
    },
    contact: {
      name: "E2E Test Persona",
      title: "Director of Supply Chain",
      email: `persona@${host}`,
      source: "company_website",
    },
    sender: {
      name: "E2E Sender",
      company: "Harbor Bridge Logistics",
      value_proposition: "We simplify Asia-to-US inbound freight.",
    },
    options: { generate_email: true },
  };
}

/**
 * Thin but not empty evidence: three dimensions plus a website.
 * Assessed weight 55% clears the 0.40 research floor, while the score (37.5)
 * stays under the 70 qualification bar → REVIEW, and no draft.
 * This lands on REVIEW purely through input shape; no threshold is touched.
 */
export function reviewProspect(token = runToken()): ProspectPayload {
  const host = `e2e-review-${token}.example`;
  return {
    company: {
      name: `E2E Review Importer ${token}`,
      website: `https://${host}`,
      sources: [
        { source: "importyeti", reference: `https://importyeti.test/company/${token}` },
        { source: "company_website", reference: `https://${host}/about` },
      ],
      signals: [
        { kind: "import_activity", detail: "有少量海运进口记录，频率不稳定" },
        { kind: "china_dependency", detail: "部分批次来自中国，占比尚不明确" },
        { kind: "company_scale", detail: "规模中等，员工人数约 50 人" },
      ],
    },
    contact: {
      name: "E2E Review Persona",
      title: "Procurement Manager",
      email: `review-persona@${host}`,
      source: "company_website",
    },
    sender: {
      name: "E2E Sender",
      company: "Harbor Bridge Logistics",
      value_proposition: "We simplify Asia-to-US inbound freight.",
    },
    options: { generate_email: true },
  };
}

/** Expected arithmetic for the qualified fixture — asserted, not assumed. */
export const QUALIFIED_EXPECTATION = {
  score: 70.5,
  completeness: 1.0,
  confidence: 0.7,
  decision: "qualified",
  recommendedAction: "prepare_outreach",
} as const;

export const REVIEW_EXPECTATION = {
  score: 37.5,
  completeness: 0.55,
  decision: "review",
  recommendedAction: "human_review",
} as const;
