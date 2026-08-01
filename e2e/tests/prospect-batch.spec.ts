import { expect, test, type Page } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

const TASK_ID = "11111111-1111-4111-8111-111111111111";
const BATCH_ID = "22222222-2222-4222-8222-222222222222";
const COMPLETED_COMPANY_ID = "33333333-3333-4333-8333-333333333333";
const REVIEW_COMPANY_ID = "44444444-4444-4444-8444-444444444444";
const JOB_ID = "55555555-5555-4555-8555-555555555550";

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
      blocking_claim_count: 0,
      resumed_at: null,
      resumed_from_stage: null,
      resume_count: 0,
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
      blocking_claim_count: 1,
      resumed_at: null,
      resumed_from_stage: null,
      resume_count: 0,
    },
  ],
};

const completedExecution = {
  job_id: JOB_ID,
  batch_id: BATCH_ID,
  status: "completed",
  available_at: "2026-07-31T12:01:00Z",
  attempt_count: 1,
  max_attempts: 3,
  heartbeat_at: "2026-07-31T12:01:12Z",
  last_error_code: null,
  last_error_summary: null,
  recovery_count: 0,
  last_recovered_at: null,
  created_at: "2026-07-31T12:01:00Z",
  started_at: "2026-07-31T12:01:01Z",
  completed_at: "2026-07-31T12:01:12Z",
  updated_at: "2026-07-31T12:01:12Z",
};

async function stubBatchApi(page: Page) {
  let postedBody: unknown = null;
  let executionReads = 0;
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
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        batch_id: BATCH_ID,
        job_id: JOB_ID,
        status: "pending",
        reused: false,
      }),
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
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/execution`, (route) => {
    const execution =
      executionReads++ === 0
        ? {
            ...completedExecution,
            status: "pending",
            attempt_count: 0,
            heartbeat_at: null,
            started_at: null,
            completed_at: null,
            updated_at: completedExecution.created_at,
          }
        : completedExecution;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(execution),
    });
  });
  await page.route(
    `**/api/v1/prospect-batches/${BATCH_ID}/companies/${REVIEW_COMPANY_ID}/blockers`,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          batch_id: BATCH_ID,
          company_id: REVIEW_COMPANY_ID,
          research_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          blocking_claim_count: 1,
          pending_claim_count: 1,
          claims: [
            {
              claim_position: 0,
              status: "pending",
              decision: null,
              kind: "shipping_fit",
              detail: "Website mentions ocean freight",
              evidence_snippet: "ocean freight",
              source_url: "https://harbor.example",
              fetched_at: "2026-07-31T12:01:10Z",
              confidence: 0.8,
            },
          ],
        }),
      }),
  );
  return { postedBody: () => postedBody };
}

test("D2 selection, results, filters, and refresh recovery", async ({ page }) => {
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
  await expect(panel.getByTestId("batch-execution-status")).toContainText("等待执行");
  await expect(panel.getByTestId("batch-execution-status")).toContainText("执行完成");
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

test("historical D2 batch without a job record still restores", async ({ page }) => {
  const guard = attachConsoleGuard(page);
  await stubBatchApi(page);
  const executionPath = `**/api/v1/prospect-batches/${BATCH_ID}/execution`;
  await page.unroute(executionPath);
  await page.route(executionPath, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(null),
    }),
  );

  await page.goto(`/?task_id=${TASK_ID}&batch_id=${BATCH_ID}`);
  const panel = page.getByTestId("prospect-batch-panel");
  await expect(panel.getByTestId("prospect-batch-result")).toBeVisible();
  await expect(panel.getByTestId("batch-execution-status")).toContainText("历史批次");
  await expect(panel.getByText("Atlas Hardware").first()).toBeVisible();
  expect(guard.problems()).toEqual([]);
});

test("D2b reviews evidence, resumes at scoring, and survives refresh", async ({ page }) => {
  const guard = attachConsoleGuard(page);
  const researchId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  let reviewed = false;
  const currentBatch = structuredClone(batch) as {
    status: string;
    completed_count: number;
    needs_review_count: number;
    error_summary: string | null;
    [key: string]: unknown;
  };
  const currentCompanies = structuredClone(batchCompanies) as {
    companies: Array<{
      current_stage: string;
      status: string;
      opportunity_id: string | null;
      selected_contact_id: string | null;
      outreach_id: string | null;
      draft_version: number | null;
      draft_id: string | null;
      score: number | null;
      qualification_decision: string | null;
      contact_name: string | null;
      contact_email: string | null;
      draft_subject: string | null;
      draft_status: string | null;
      error_code: string | null;
      error_summary: string | null;
      resumed_at: string | null;
      resumed_from_stage: string | null;
      resume_count: number;
      [key: string]: unknown;
    }>;
    [key: string]: unknown;
  };
  const currentExecution = structuredClone(completedExecution) as {
    status: string;
    updated_at: string;
    completed_at: string | null;
    [key: string]: unknown;
  };

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
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(currentBatch),
    }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/companies`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(currentCompanies),
    }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/execution`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(currentExecution),
    }),
  );
  await page.route(
    `**/api/v1/prospect-batches/${BATCH_ID}/companies/${REVIEW_COMPANY_ID}/blockers`,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          batch_id: BATCH_ID,
          company_id: REVIEW_COMPANY_ID,
          research_id: researchId,
          blocking_claim_count: 1,
          pending_claim_count: reviewed ? 0 : 1,
          claims: [
            {
              claim_position: 0,
              status: reviewed ? "accepted" : "pending",
              decision: reviewed ? "accepted" : null,
              kind: "shipping_fit",
              detail: "Website mentions ocean freight",
              evidence_snippet: "ocean freight",
              source_url: "https://harbor.example",
              fetched_at: "2026-07-31T12:01:10Z",
              confidence: 0.8,
            },
          ],
        }),
      }),
  );
  await page.route(
    `**/api/v1/prospect-batches/${BATCH_ID}/companies/${REVIEW_COMPANY_ID}/resume`,
    (route) => {
      if (!reviewed) {
        return route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({
            code: "EVIDENCE_REVIEW_INCOMPLETE",
            message: "Evidence review is incomplete",
            pending_claim_count: 1,
            request_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
          }),
        });
      }
      currentBatch.status = "completed";
      currentBatch.completed_count = 2;
      currentBatch.needs_review_count = 0;
      currentBatch.error_summary = null;
      const company = currentCompanies.companies[1];
      company.current_stage = "completed";
      company.status = "completed";
      company.opportunity_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
      company.selected_contact_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
      company.outreach_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
      company.draft_version = 1;
      company.draft_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee:1";
      company.score = 74;
      company.qualification_decision = "qualified";
      company.contact_name = "Purchasing Team";
      company.contact_email = "purchasing@harbor.example";
      company.draft_subject = "Freight support for Harbor Supply";
      company.draft_status = "generated";
      company.error_code = null;
      company.error_summary = null;
      company.resumed_at = "2026-07-31T12:05:00Z";
      company.resumed_from_stage = "awaiting_evidence_review";
      company.resume_count = 1;
      currentExecution.status = "completed";
      currentExecution.updated_at = "2026-07-31T12:05:01Z";
      currentExecution.completed_at = "2026-07-31T12:05:01Z";
      return route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          batch_id: BATCH_ID,
          job_id: JOB_ID,
          status: "pending",
          reused: false,
        }),
      });
    },
  );
  await page.route(`**/api/v1/research/runs/${researchId}/confirm`, (route) => {
    reviewed = true;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        research_id: researchId,
        action: "applied",
        company_id: REVIEW_COMPANY_ID,
        summary: { accepted: 1, edited: 0, rejected: 0, total: 1 },
        promotions: [
          {
            claim_position: 0,
            decision: "accepted",
            kind: "shipping_fit",
            detail: "Website mentions ocean freight",
            company_source_position: 1,
            company_signal_position: 1,
            source_reused: false,
            idempotent: false,
          },
        ],
        application_payload: null,
        warnings: [],
      }),
    });
  });
  await page.route(`**/api/v1/research/runs/${researchId}`, (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        research_id: researchId,
        company_id: REVIEW_COMPANY_ID,
        company_name: "Harbor Supply",
        website: "https://harbor.example",
        status: "completed",
        failure_code: null,
        started_at: "2026-07-31T12:01:08Z",
        completed_at: "2026-07-31T12:01:12Z",
        pages_fetched: 1,
        pages_failed: 0,
        claims_extracted: 1,
        claims_validated: 1,
        extractor: {
          provider: "fake",
          model: "fake-research-v1",
          prompt_version: "test-v1",
        },
        profile: {
          summary: "Industrial supply importer",
          industry: "industrial supply",
          products: ["hardware"],
          locations: ["US"],
          size_hint: null,
          year_founded: null,
          mentions_importing: true,
        },
        pages: [
          {
            position: 0,
            url: "https://harbor.example",
            final_url: "https://harbor.example",
            http_status: 200,
            content_type: "text/html",
            fetched_at: "2026-07-31T12:01:10Z",
            content_chars: 120,
            truncated: false,
            discovery_reason: "homepage",
          },
        ],
        claims: [
          {
            position: 0,
            kind: "shipping_fit",
            detail: "Website mentions ocean freight",
            evidence_snippet: "ocean freight",
            source_url: "https://harbor.example",
            confidence: 0.8,
          },
        ],
        promotions: reviewed
          ? [
              {
                claim_position: 0,
                decision: "accepted",
                reviewed_at: "2026-07-31T12:04:00Z",
                reviewer_name: "reviewer",
                edited_detail: null,
                edited_kind: null,
                applied_to_company: true,
              },
            ]
          : [],
        rejected_claims: [],
        warnings: [],
        unknown_dimensions: [],
        output_language: "zh-CN",
      }),
    });
  });

  await page.goto(`/?task_id=${TASK_ID}&batch_id=${BATCH_ID}`);
  const panel = page.getByTestId("prospect-batch-panel");
  await expect(panel.getByTestId("batch-company-needs_review")).toBeVisible();
  await panel.getByTestId("resume-batch-company").click();
  await expect(page.getByText("仍有 1 条证据未审核，请先完成接受或拒绝。")).toBeVisible();

  await panel.getByTestId("review-batch-evidence").click();
  await expect(page).toHaveURL(new RegExp(`research_id=${researchId}`));
  await expect(page.getByTestId("research-claim-0")).toBeVisible();
  await page.getByTestId("accept-0").click();
  await page.getByTestId("research-confirm").click();
  await expect(page.getByTestId("batch-evidence-review-complete")).toBeVisible();
  await page.getByRole("link", { name: "返回批量结果" }).click();

  await expect(panel.getByTestId("batch-company-needs_review")).toBeVisible();
  await panel.getByTestId("resume-batch-company").click();
  await expect(panel.getByTestId("batch-company-completed")).toHaveCount(2);
  await expect(page.getByText("草稿待审核").last()).toBeVisible();
  await expect(page.getByText("没有发送邮件").last()).toBeVisible();

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByTestId("batch-company-completed")).toHaveCount(2);
  await expect(page.getByText("Freight support for Harbor Supply")).toBeVisible();
  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(
    guard
      .problems()
      .filter(
        (problem) =>
          !/^\[console\.error\] Failed to load resource:.*409 \(Conflict\)$/i.test(problem),
      ),
  ).toEqual([]);
});
