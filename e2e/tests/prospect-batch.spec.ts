import { expect, test, type Page } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

const TASK_ID = "11111111-1111-4111-8111-111111111111";
const BATCH_ID = "22222222-2222-4222-8222-222222222222";
const COMPLETED_COMPANY_ID = "33333333-3333-4333-8333-333333333333";
const REVIEW_COMPANY_ID = "44444444-4444-4444-8444-444444444444";

const task = {
  task_id: TASK_ID,
  original_prompt: "帮我找 2 家北美五金进口商",
  requested_count: 2,
  effective_count: 2,
  parsed_region: "North America",
  parsed_category: "hardware",
  parsed_keywords: ["hardware"],
  provider: "manual_csv",
  status: "completed",
  discovered_count: 2,
  ingested_count: 2,
  duplicate_count: 0,
  failed_count: 0,
  error_code: null,
  error_summary: null,
  created_at: "2026-07-31T12:00:00Z",
  started_at: "2026-07-31T12:00:01Z",
  completed_at: "2026-07-31T12:00:02Z",
};

const companies = {
  task_id: TASK_ID,
  companies: [
    {
      candidate_id: "55555555-5555-4555-8555-555555555555",
      position: 0,
      company_id: COMPLETED_COMPANY_ID,
      company_name: "Atlas Hardware",
      website: "https://atlas.example",
      domain: "atlas.example",
      address: null,
      region: "US",
      product_description: "Hand tools importer",
      import_evidence: "BOL-ATLAS",
      source: "manual_csv",
      source_url: "https://evidence.example/atlas",
      external_id: null,
      status: "ingested",
      is_duplicate: false,
      failure_reason: null,
      created_at: "2026-07-31T12:00:01Z",
    },
    {
      candidate_id: "66666666-6666-4666-8666-666666666666",
      position: 1,
      company_id: REVIEW_COMPANY_ID,
      company_name: "Harbor Supply",
      website: "https://harbor.example",
      domain: "harbor.example",
      address: null,
      region: "US",
      product_description: "Industrial supply importer",
      import_evidence: "BOL-HARBOR",
      source: "manual_csv",
      source_url: "https://evidence.example/harbor",
      external_id: null,
      status: "ingested",
      is_duplicate: false,
      failure_reason: null,
      created_at: "2026-07-31T12:00:01Z",
    },
  ],
};

const batch = {
  batch_id: BATCH_ID,
  discovery_task_id: TASK_ID,
  requested_count: 2,
  effective_count: 2,
  status: "partial_failed",
  queued_count: 0,
  running_count: 0,
  completed_count: 1,
  needs_review_count: 1,
  failed_count: 0,
  created_at: "2026-07-31T12:01:00Z",
  started_at: "2026-07-31T12:01:01Z",
  completed_at: "2026-07-31T12:01:12Z",
  error_summary: "Harbor Supply: EVIDENCE_REVIEW_REQUIRED",
};

const batchCompanies = {
  batch_id: BATCH_ID,
  companies: [
    {
      company_id: COMPLETED_COMPANY_ID,
      company_name: "Atlas Hardware",
      position: 0,
      pipeline_version: "d2a-prospect-pipeline-v1",
      current_stage: "completed",
      status: "completed",
      research_id: "77777777-7777-4777-8777-777777777777",
      opportunity_id: "88888888-8888-4888-8888-888888888888",
      selected_contact_id: "99999999-9999-4999-8999-999999999999",
      outreach_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      draft_version: 1,
      draft_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa:1",
      score: 72.5,
      qualification_decision: "qualified",
      reasons: ["trusted import evidence"],
      contact_name: "Maria Chen",
      contact_email: "maria@atlas.example",
      contact_source_url: "https://atlas.example/contact",
      draft_subject: "Freight partnership for Atlas Hardware",
      draft_status: "generated",
      error_code: null,
      error_summary: null,
      started_at: "2026-07-31T12:01:01Z",
      completed_at: "2026-07-31T12:01:08Z",
    },
    {
      company_id: REVIEW_COMPANY_ID,
      company_name: "Harbor Supply",
      position: 1,
      pipeline_version: "d2a-prospect-pipeline-v1",
      current_stage: "awaiting_evidence_review",
      status: "needs_review",
      research_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      opportunity_id: null,
      selected_contact_id: null,
      outreach_id: null,
      draft_version: null,
      draft_id: null,
      score: null,
      qualification_decision: null,
      reasons: [],
      contact_name: null,
      contact_email: null,
      contact_source_url: null,
      draft_subject: null,
      draft_status: null,
      error_code: "EVIDENCE_REVIEW_REQUIRED",
      error_summary: "research claims were saved and require human confirmation",
      started_at: "2026-07-31T12:01:08Z",
      completed_at: "2026-07-31T12:01:12Z",
    },
  ],
};

async function stubBatchApi(page: Page) {
  let postedBody: unknown = null;
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "sender_profile_v1",
      JSON.stringify({
        sender_name: "Alex Morgan",
        sender_company: "Harbor Bridge Logistics",
        value_proposition: "We simplify Asia-to-US freight.",
      }),
    );
  });
  await page.route("**/api/v1/health/runtime", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        provider: "fake",
        model: "fake-static-v1",
        research_provider: "fake",
        research_model: "fake-research-v1",
        environment: "test",
      }),
    }),
  );
  await page.route(`**/api/v1/discovery-tasks/${TASK_ID}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(task) }),
  );
  await page.route(`**/api/v1/discovery-tasks/${TASK_ID}/companies`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(companies),
    }),
  );
  await page.route(`**/api/v1/discovery-tasks/${TASK_ID}/batch-process`, async (route) => {
    postedBody = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(batch),
    });
  });
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(batch) }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/companies`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(batchCompanies),
    }),
  );
  return { postedBody: () => postedBody };
}

test("D2a selection, results, filters, and refresh recovery", async ({ page }) => {
  const guard = attachConsoleGuard(page);
  const captured = await stubBatchApi(page);
  await page.goto(`/?task_id=${TASK_ID}`);

  const panel = page.getByTestId("prospect-batch-panel");
  await expect(panel).toBeVisible();
  await panel.getByTestId("batch-select-all").click();
  await expect(
    panel.locator('[data-testid="batch-company-checkbox"]:checked'),
  ).toHaveCount(2);
  await page.screenshot({
    path: "../artifacts/d2a/company-selection.png",
    fullPage: true,
  });

  await panel.getByTestId("start-prospect-batch").click();
  await expect(panel.getByTestId("prospect-batch-result")).toBeVisible();
  await expect(panel.getByTestId("batch-progress")).toHaveAttribute("style", /100%/);
  expect(captured.postedBody()).toMatchObject({
    company_ids: [COMPLETED_COMPANY_ID, REVIEW_COMPANY_ID],
    limit: 5,
    sender: {
      name: "Alex Morgan",
      company: "Harbor Bridge Logistics",
    },
  });
  await page.screenshot({
    path: "../artifacts/d2a/batch-progress.png",
    fullPage: true,
  });

  await panel.getByRole("button", { name: "需审核", exact: true }).click();
  await expect(panel.getByTestId("batch-company-needs_review")).toBeVisible();
  await expect(panel.getByText("EVIDENCE_REVIEW_REQUIRED")).toBeVisible();
  await page.screenshot({
    path: "../artifacts/d2a/needs-review.png",
    fullPage: true,
  });

  await panel.getByRole("button", { name: "已完成", exact: true }).click();
  await expect(panel.getByTestId("batch-company-completed")).toBeVisible();
  await expect(panel.getByText("Freight partnership for Atlas Hardware")).toBeVisible();
  await page.screenshot({
    path: "../artifacts/d2a/completed-company.png",
    fullPage: true,
  });

  await expect(page).toHaveURL(new RegExp(`batch_id=${BATCH_ID}`));
  await page.reload({ waitUntil: "networkidle" });
  const restored = page.getByTestId("prospect-batch-result");
  await expect(restored).toBeVisible();
  await expect(page.getByText("Atlas Hardware").first()).toBeVisible();
  await expect(page.getByText("Harbor Supply").first()).toBeVisible();
  await page.screenshot({
    path: "../artifacts/d2a/refresh-recovery.png",
    fullPage: true,
  });

  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(guard.problems()).toEqual([]);
});
