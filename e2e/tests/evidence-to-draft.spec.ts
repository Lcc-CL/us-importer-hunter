import { expect, test, type Page } from "@playwright/test";

import { COMPLETED_RUN, confirmResponse } from "../fixtures/research";
import { attachConsoleGuard } from "../utils/console-guard";

const COMPANY_ID = "22222222-2222-2222-2222-222222222222";

const analysis = {
  request_id: "11111111-1111-1111-1111-111111111111",
  overall_status: "PARTIAL",
  company: { action: "CREATED", company_id: COMPANY_ID, name: "Pacific Home Goods Inc.", notes: [] },
  opportunity: {
    action: "REVIEW",
    opportunity_id: "33333333-3333-3333-3333-333333333333",
    score: 37,
    confidence: 0.5,
    data_completeness: 0.625,
    qualification_decision: "review",
    recommended_action: "human_review",
    reasons: ["缺少可靠进口活动和来源地证据"],
  },
  contact: { action: "CREATED", contact_id: "44444444-4444-4444-4444-444444444444", notes: [] },
  decision_maker: {
    action: "SELECTED",
    selected_contact_id: "44444444-4444-4444-4444-444444444444",
    recommended_channel: "email",
    confidence: 0.9,
    reasons: [],
  },
  email_draft: {
    action: "SKIPPED",
    outreach_id: null,
    version: null,
    subject: null,
    body: null,
    status: null,
    notes: [],
  },
  warnings: [],
  created_at: "2026-07-21T12:00:00Z",
};

const evidence = {
  status: "completed",
  company_id: COMPANY_ID,
  import_job_id: "55555555-5555-5555-5555-555555555555",
  aggregate_id: "66666666-6666-6666-6666-666666666666",
  records_received: 3,
  records_normalized: 3,
  shipments_matched: 3,
  quality_status: "VERIFIED",
  quality_score: 92,
  promoted_signals: ["import_activity", "china_dependency", "logistics_complexity"],
  previous_qualification_score: 37,
  qualification_score: 70.5,
  qualification_status: "qualified",
  qualification_reasons: [],
  draft_status: "generated",
  warnings: [],
};

const detail = {
  company: {
    company_id: COMPANY_ID,
    name: "Pacific Home Goods Inc.",
    website: "https://pacifichomegoods.example",
    verified: true,
    sources: [{ source: "company_website", reference_count: 1 }],
    signals: ["company_scale: warehouse and employees"],
  },
  latest_assessment: {
    opportunity_id: "33333333-3333-3333-3333-333333333333",
    score: 70.5,
    confidence: 0.85,
    data_completeness: 1,
    qualification_decision: "qualified",
    recommended_action: "prepare_outreach",
    reasons: ["Import Evidence 已补齐进口维度"],
    scoring_version: "mvp-explainable-scoring-v1",
    policy_version: "mvp-qualification-policy-v1",
    assessed_at: "2026-07-21T12:05:00Z",
    explanation: null,
  },
  qualification_decision: "qualified",
  contacts: [{
    contact_id: "44444444-4444-4444-4444-444444444444",
    name: "Maria Chen",
    title: "Director of Supply Chain",
    department: "supply_chain",
    seniority: "director",
    status: "active",
    channels: [{ type: "email", value: "maria@pacifichomegoods.example", verification_status: "unverified" }],
  }],
  decision_maker: { selected_contact_id: "44444444-4444-4444-4444-444444444444", rankings: [], selection: null },
  latest_email_draft: {
    outreach_id: "77777777-7777-7777-7777-777777777777",
    version: 1,
    subject: "Pacific Home Goods 进口运输合作建议",
    body: "Maria 您好，\n\n这是仅供人工审核的开发信草稿。",
    status: "generated",
    approval_status: "generated",
    approved_at: null,
    approved_by_name: null,
    provider: "fake",
    model: "fake-deterministic-v1",
    prompt_version: "mvp-email-v1",
    generated_at: "2026-07-21T12:06:00Z",
  },
  draft_history: [],
};

async function stubFlow(page: Page) {
  const confirm = confirmResponse(
    [
      { kind: "company_scale", detail: "warehouse and employees" },
      { kind: "growth", detail: "growing operations" },
    ],
    [{ source: "company_website", reference: "https://pacifichomegoods.example" }],
  );
  await page.route("**/api/v1/research/**", async (route) => {
    if (route.request().url().includes("/confirm")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(confirm) });
    } else {
      await route.fulfill({ status: route.request().method() === "POST" ? 201 : 200, contentType: "application/json", body: JSON.stringify(COMPLETED_RUN) });
    }
  });
  await page.route("**/api/v1/mvp/prospects/analyze", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(analysis) }),
  );
  await page.route(`**/api/v1/companies/${COMPANY_ID}/import-evidence/upload`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(evidence) }),
  );
  await page.route(`**/api/v1/companies/${COMPANY_ID}/import-evidence`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(evidence) }),
  );
  await page.route(`**/api/v1/mvp/prospects/${COMPANY_ID}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail) }),
  );
}

test("研究 → CSV 证据 → 资格更新 → Draft → Reload", async ({ page }) => {
  const guard = attachConsoleGuard(page);
  await stubFlow(page);
  await page.goto("/");

  await page.getByLabel("Research target name").fill("Pacific Home Goods Inc.");
  await page.getByLabel("Research target website").fill("https://pacifichomegoods.example");
  await page.getByRole("button", { name: "开始自动研究" }).click();
  await expect(page.getByTestId("research-result")).toBeVisible();
  await page.getByTestId("accept-0").click();
  await page.getByTestId("accept-1").click();
  await page.getByTestId("research-confirm").click();

  await page.getByTestId("guided-contact-name").fill("Maria Chen");
  await page.getByTestId("guided-contact-email").fill("maria@pacifichomegoods.example");
  await page.getByTestId("guided-contact-source").fill("company_website");
  await page.getByTestId("guided-sender-name").fill("Alex Morgan");
  await page.getByTestId("guided-sender-company").fill("Harbor Bridge Logistics");
  await page.getByTestId("guided-sender-value").fill("我们简化亚洲到美国的进口运输。");
  await page.getByTestId("guided-continue").click();

  await expect(page.getByTestId("import-evidence-panel")).toBeVisible();
  await page.getByTestId("evidence-file").setInputFiles("../fixtures/import-evidence/demo-hardware-imports.csv");
  await page.getByTestId("evidence-upload").click();
  await expect(page.getByTestId("evidence-signals")).toContainText("持续进口活动");
  await expect(page.getByTestId("evidence-signals")).toContainText("中国来源依赖");
  await expect(page.getByTestId("evidence-score")).toContainText("37.0 → 70.5");
  await expect(page.getByText("Pacific Home Goods 进口运输合作建议")).toBeVisible();

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByTestId("evidence-signals")).toContainText("中国来源依赖");
  await expect(page.getByText("Pacific Home Goods 进口运输合作建议")).toBeVisible();
  expect(guard.problems()).toEqual([]);
});
