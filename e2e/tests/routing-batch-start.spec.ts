import { expect, test, type Page } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

const SESSION_ID = "10000000-0000-4000-8000-000000000001";
const ROUTING_RUN_ID = "20000000-0000-4000-8000-000000000002";
const ROUTE_ID = "30000000-0000-4000-8000-000000000003";
const BATCH_ID = "40000000-0000-4000-8000-000000000004";
const COMPANY_ID = "50000000-0000-4000-8000-000000000005";
const JOB_ID = "60000000-0000-4000-8000-000000000006";
const RESEARCH_ID = "70000000-0000-4000-8000-000000000007";

async function stubRoutingBatchApi(page: Page) {
  let started = false;
  let resumed = false;
  let confirmed = false;
  let executionReads = 0;
  let postedStart: unknown = null;

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
        real_data_gate: "blocked",
      }),
    }),
  );
  await page.route(`**/api/v1/import-sessions/${SESSION_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: SESSION_ID,
        source: "netease_foreign_trade",
        original_filename: "routing.csv",
        file_type: "csv",
        file_size_bytes: 1024,
        file_sha256: "a".repeat(64),
        encoding: "utf-8",
        status: "completed",
        total_rows: 12,
        accepted_rows: 12,
        invalid_rows: 0,
        duplicate_rows: 0,
        error_summary: null,
        created_at: "2026-08-02T12:00:00Z",
        started_at: "2026-08-02T12:00:00Z",
        completed_at: "2026-08-02T12:00:01Z",
        updated_at: "2026-08-02T12:00:01Z",
      }),
    }),
  );
  await page.route(`**/api/v1/import-sessions/${SESSION_ID}/rows**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rows: [], page: 1, limit: 20, total: 0 }),
    }),
  );
  await page.route(`**/api/v1/import-sessions/${SESSION_ID}/resolution`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        import_session_id: SESSION_ID,
        resolution_status: "completed",
        processing_status: "completed",
        total_rows: 12,
        processed_rows: 12,
        companies_created: 1,
        companies_reused: 0,
        company_reviews_required: 0,
        contacts_created: 1,
        contacts_reused: 0,
        company_contacts_created: 1,
        invalid_rows: 0,
        failed_rows: 0,
        started_at: "2026-08-02T12:00:01Z",
        completed_at: "2026-08-02T12:00:02Z",
        error_summary: null,
        job_id: null,
        attempt_count: 1,
        max_attempts: 3,
        heartbeat_at: null,
      }),
    }),
  );
  await page.route(`**/api/v1/import-sessions/${SESSION_ID}/entity-decisions**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ decisions: [], page: 1, limit: 100, total: 0 }),
    }),
  );
  await page.route(`**/api/v1/prospect-routing-runs/${ROUTING_RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        routing_run_id: ROUTING_RUN_ID,
        import_session_id: SESSION_ID,
        rules_version: "real-routing-v1.1",
        current_execution_generation: 1,
        available_generations: [1],
        status: "completed",
        total_companies: 1,
        routed_companies: 1,
        blocked_companies: 0,
        tier_a_count: 1,
        tier_b_count: 0,
        tier_c_count: 0,
        tier_d_count: 0,
        criteria: {
          target_product_keywords: ["hardware"],
          target_hs_codes: ["8205"],
          preferred_origin_countries: ["China"],
          preferred_pol: ["Shanghai"],
          preferred_pod: ["Los Angeles"],
          campaign_name: "D5d1 browser gate",
          notes: null,
        },
        weights_snapshot: {},
        processing_status: "completed",
        job_id: null,
        attempt_count: 1,
        max_attempts: 3,
        heartbeat_at: null,
        error_summary: null,
        created_at: "2026-08-02T12:00:02Z",
        started_at: "2026-08-02T12:00:02Z",
        completed_at: "2026-08-02T12:00:03Z",
        updated_at: "2026-08-02T12:00:03Z",
      }),
    }),
  );
  await page.route(`**/api/v1/prospect-routing-runs/${ROUTING_RUN_ID}/routes**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        routing_run_id: ROUTING_RUN_ID,
        execution_generation: 1,
        routes: [
          {
            route_id: ROUTE_ID,
            routing_run_id: ROUTING_RUN_ID,
            execution_generation: 1,
            company_id: COMPANY_ID,
            company_name: "Atlas Routed Hardware",
            pre_score: 88,
            recommended_tier: "A",
            effective_tier: "A",
            feature_snapshot: {},
            reason_codes: ["ROUTED_A"],
            warning_codes: [],
            review_status: "confirmed",
            override_reason: null,
            reviewed_by: "Browser Reviewer",
            reviewed_at: "2026-08-02T12:00:03Z",
            contact_count: 1,
            has_usable_contact: true,
            has_usable_email: true,
            preferred_role_category: "procurement",
            created_at: "2026-08-02T12:00:03Z",
            updated_at: "2026-08-02T12:00:03Z",
          },
        ],
        page: 1,
        limit: 200,
        total: 1,
      }),
    }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        batch_id: BATCH_ID,
        source_kind: "prospect_routing",
        discovery_task_id: null,
        routing_run_id: ROUTING_RUN_ID,
        routing_execution_generation: 1,
        requested_count: 1,
        effective_count: 1,
        status: resumed ? "completed" : started ? "partial_failed" : "pending",
        queued_count: started ? 0 : 1,
        running_count: 0,
        completed_count: resumed ? 1 : 0,
        needs_review_count: started && !resumed ? 1 : 0,
        failed_count: 0,
        created_at: "2026-08-02T12:00:04Z",
        started_at: started ? "2026-08-02T12:00:05Z" : null,
        completed_at: started ? "2026-08-02T12:00:06Z" : null,
        error_summary: started && !resumed ? "Atlas: EVIDENCE_REVIEW_REQUIRED" : null,
      }),
    }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/companies`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        batch_id: BATCH_ID,
        companies: [
          {
            company_id: COMPANY_ID,
            company_name: "Atlas Routed Hardware",
            position: 0,
            pipeline_version: "d2a-prospect-pipeline-v1",
            current_stage: resumed
              ? "completed"
              : started
                ? "awaiting_evidence_review"
                : "queued",
            status: resumed ? "completed" : started ? "needs_review" : "queued",
            research_id: started ? RESEARCH_ID : null,
            opportunity_id: resumed ? "80000000-0000-4000-8000-000000000008" : null,
            selected_contact_id: resumed ? "90000000-0000-4000-8000-000000000009" : null,
            outreach_id: resumed ? "a0000000-0000-4000-8000-00000000000a" : null,
            draft_version: resumed ? 1 : null,
            draft_id: resumed ? "a0000000-0000-4000-8000-00000000000a:1" : null,
            score: resumed ? 82 : null,
            qualification_decision: resumed ? "qualified" : null,
            reasons: resumed ? ["trusted evidence"] : [],
            contact_name: resumed ? "Maria Chen" : null,
            contact_email: resumed ? "maria@example.test" : null,
            contact_source_url: resumed ? "https://atlas.example/contact" : null,
            draft_subject: resumed ? "Freight partnership for Atlas" : null,
            draft_status: resumed ? "generated" : null,
            error_code: started && !resumed ? "EVIDENCE_REVIEW_REQUIRED" : null,
            error_summary: started && !resumed ? "research claims require review" : null,
            started_at: started ? "2026-08-02T12:00:05Z" : null,
            completed_at: started ? "2026-08-02T12:00:06Z" : null,
            blocking_claim_count: started && !resumed ? 1 : 0,
            resumed_at: resumed ? "2026-08-02T12:00:08Z" : null,
            resumed_from_stage: resumed ? "awaiting_evidence_review" : null,
            resume_count: resumed ? 1 : 0,
          },
        ],
      }),
    }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/execution`, (route) => {
    if (!started) {
      return route.fulfill({ status: 200, contentType: "application/json", body: "null" });
    }
    executionReads += 1;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: JOB_ID,
        batch_id: BATCH_ID,
        status: executionReads === 1 && !resumed ? "pending" : "completed",
        available_at: "2026-08-02T12:00:05Z",
        attempt_count: 1,
        max_attempts: 3,
        heartbeat_at: "2026-08-02T12:00:06Z",
        last_error_code: null,
        last_error_summary: null,
        recovery_count: 0,
        last_recovered_at: null,
        created_at: "2026-08-02T12:00:05Z",
        started_at: "2026-08-02T12:00:05Z",
        completed_at: "2026-08-02T12:00:06Z",
        updated_at: "2026-08-02T12:00:06Z",
      }),
    });
  });
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/start`, async (route) => {
    postedStart = route.request().postDataJSON();
    started = true;
    executionReads = 0;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        batch_id: BATCH_ID,
        job_id: JOB_ID,
        status: "pending",
        reused: false,
        processing_started: true,
      }),
    });
  });
  await page.route(
    `**/api/v1/prospect-batches/${BATCH_ID}/companies/${COMPANY_ID}/resume`,
    async (route) => {
      resumed = true;
      executionReads = 0;
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
    },
  );
  await page.route(`**/api/v1/research/runs/${RESEARCH_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        research_id: RESEARCH_ID,
        company_id: COMPANY_ID,
        company_name: "Atlas Routed Hardware",
        website: "https://atlas.example",
        status: "completed",
        failure_code: null,
        started_at: "2026-08-02T12:00:05Z",
        completed_at: "2026-08-02T12:00:06Z",
        pages_fetched: 1,
        pages_failed: 0,
        claims_extracted: 1,
        claims_validated: 1,
        extractor: {
          provider: "fake",
          model: "fake-research-v1",
          prompt_version: "website-research-v1",
        },
        profile: {},
        pages: [
          {
            position: 0,
            url: "https://atlas.example",
            final_url: "https://atlas.example",
            http_status: 200,
            content_type: "text/html",
            fetched_at: "2026-08-02T12:00:05Z",
            content_chars: 100,
            truncated: false,
            discovery_reason: "home",
          },
        ],
        claims: [
          {
            position: 0,
            kind: "import_activity",
            detail: "Atlas imports industrial hardware.",
            evidence_snippet:
              "We import industrial hardware on a monthly schedule.",
            source_url: "https://atlas.example/about",
            confidence: 0.9,
          },
        ],
        promotions: confirmed
          ? [
              {
                claim_position: 0,
                decision: "accepted",
                reviewed_at: "2026-08-02T12:01:00Z",
                reviewer_name: "reviewer",
                applied_to_company: true,
                kind: "import_activity",
                detail: "Atlas imports industrial hardware.",
              },
            ]
          : [],
        rejected_claims: [],
        warnings: [],
        unknown_dimensions: [],
      }),
    }),
  );
  await page.route(`**/api/v1/research/runs/${RESEARCH_ID}/confirm`, async (route) => {
    confirmed = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        research_id: RESEARCH_ID,
        action: "reviewed",
        company_id: COMPANY_ID,
        summary: { accepted: 1, edited: 0, rejected: 0, total: 1 },
        promotions: [],
        application_payload: null,
        warnings: [],
      }),
    });
  });
  return { postedStart: () => postedStart };
}

test("routing batch explicit start, review gate, resume, and refresh recovery", async ({
  page,
}) => {
  const guard = attachConsoleGuard(page);
  const captured = await stubRoutingBatchApi(page);
  await page.goto(
    `/?step=6&import_session_id=${SESSION_ID}&routing_run_id=${ROUTING_RUN_ID}&batch_id=${BATCH_ID}`,
  );

  const batch = page.getByTestId("prospect-routing-batch-created");
  await expect(batch).toContainText("来源：销售路由");
  await expect(batch).toContainText("generation 1");
  await expect(batch.getByTestId("prospect-routing-batch-status")).toContainText(
    "尚未启动",
  );
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("系统不会自动接受证据，也不会发送邮件");
    await dialog.accept();
  });
  await batch.getByTestId("prospect-routing-batch-start").click();
  await expect(page).toHaveURL(new RegExp(`batch_id=${BATCH_ID}.*job_id=${JOB_ID}`));
  expect(captured.postedStart()).toMatchObject({
    confirmation: true,
    provider_mode: "configured",
    sender: {
      name: "Alex Morgan",
      company: "Harbor Bridge Logistics",
    },
  });
  await expect(batch.getByTestId("prospect-routing-batch-status")).toContainText(
    "等待人工审核 Research 证据",
    { timeout: 5_000 },
  );
  await expect(batch.getByText("没有发送邮件")).toBeVisible();
  await expect(batch.getByTestId("batch-running-status")).toBeVisible();
  await expect(page.getByTestId("deep-analysis-running")).toBeVisible();
  await expect(batch.getByTestId("deep-analysis-start")).toHaveCount(0);
  await expect(page.getByTestId("human-review-center")).toBeVisible();
  await expect(page.getByTestId("human-review-evidence")).toContainText("1");

  // Inline evidence review: no company-workspace navigation required.
  await batch.getByTestId("evidence-review-toggle").click();
  await expect(batch.getByTestId("inline-evidence-review")).toBeVisible();
  await expect(batch.getByText("Atlas imports industrial hardware.")).toBeVisible();
  await expect(
    batch.getByTestId("inline-claim-0").getByRole("link", { name: /atlas.example/ }),
  ).toBeVisible();
  await batch.getByTestId("inline-accept-0").click();
  await batch.getByTestId("evidence-submit").click();

  // Auto resume after the last evidence decision: no extra "continue" click.
  await expect(batch.getByTestId("prospect-routing-batch-status")).toContainText(
    "深度处理完成，草稿等待人工审核",
    { timeout: 5_000 },
  );
  await expect(batch.getByText("已生成草稿 1")).toBeVisible();
  await expect(batch.getByText("没有发送邮件")).toBeVisible();

  await page.reload({ waitUntil: "networkidle" });
  const restored = page.getByTestId("prospect-routing-batch-created");
  await expect(restored.getByTestId("prospect-routing-batch-status")).toContainText(
    "深度处理完成，草稿等待人工审核",
  );
  await expect(restored.getByTestId("batch-running-status")).toBeVisible();
  await expect(restored.getByTestId("global-error")).not.toBeVisible();

  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(guard.problems()).toEqual([]);
});

const B_COMPANY_ID = "b0000000-0000-4000-8000-00000000000b";

async function stubStep7UnlockApi(page: Page) {
  let bConfirmed = false;
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
        draft_provider: "fake",
        draft_model: "fake-static-v1",
        draft_available: false,
        email_send_enabled: false,
        environment: "test",
        real_data_gate: "blocked",
      }),
    }),
  );
  await page.route(`**/api/v1/import-sessions/${SESSION_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: SESSION_ID,
        source: "netease_foreign_trade",
        original_filename: "routing.csv",
        file_type: "csv",
        file_size_bytes: 1024,
        file_sha256: "a".repeat(64),
        encoding: "utf-8",
        status: "completed",
        total_rows: 12,
        accepted_rows: 12,
        invalid_rows: 0,
        duplicate_rows: 0,
        mapping_json: { logical_fields: {} },
        error_summary: null,
        created_at: "2026-08-02T12:00:00Z",
        completed_at: "2026-08-02T12:00:01Z",
      }),
    }),
  );
  await page.route(`**/api/v1/import-sessions/${SESSION_ID}/rows**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rows: [], page: 1, limit: 20, total: 0 }),
    }),
  );
  await page.route(`**/api/v1/import-sessions/${SESSION_ID}/resolution`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        import_session_id: SESSION_ID,
        resolution_status: "completed",
        processing_status: "completed",
        total_rows: 12,
        processed_rows: 12,
        companies_created: 2,
        companies_reused: 0,
        company_reviews_required: 0,
        contacts_created: 2,
        contacts_reused: 0,
        company_contacts_created: 2,
        canonical_company_count: 2,
        canonical_contact_count: 2,
        invalid_rows: 0,
        failed_rows: 0,
        started_at: "2026-08-02T12:00:01Z",
        completed_at: "2026-08-02T12:00:02Z",
        error_summary: null,
        job_id: null,
        attempt_count: 1,
        max_attempts: 3,
        heartbeat_at: null,
      }),
    }),
  );
  await page.route(`**/api/v1/import-sessions/${SESSION_ID}/entity-decisions**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ decisions: [], page: 1, limit: 100, total: 0 }),
    }),
  );
  await page.route(`**/api/v1/prospect-routing-runs/${ROUTING_RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        routing_run_id: ROUTING_RUN_ID,
        import_session_id: SESSION_ID,
        rules_version: "real-routing-v1.1",
        current_execution_generation: 1,
        available_generations: [1],
        status: "completed",
        total_companies: 2,
        routed_companies: 2,
        blocked_companies: 0,
        tier_a_count: 1,
        tier_b_count: 1,
        tier_c_count: 0,
        tier_d_count: 0,
        criteria: {
          target_product_keywords: ["fitness"],
          target_hs_codes: ["950691"],
          preferred_origin_countries: [],
          preferred_pol: [],
          preferred_pod: [],
          campaign_name: "D5e2h5 step7",
          notes: null,
        },
        weights_snapshot: {},
        processing_status: "completed",
        job_id: null,
        attempt_count: 1,
        max_attempts: 3,
        heartbeat_at: null,
        error_summary: null,
        created_at: "2026-08-02T12:00:02Z",
        started_at: "2026-08-02T12:00:02Z",
        completed_at: "2026-08-02T12:00:03Z",
        updated_at: "2026-08-02T12:00:03Z",
      }),
    }),
  );
  const routeRow = (companyId: string, name: string, tier: "A" | "B") => ({
    route_id: `${companyId}-route`,
    routing_run_id: ROUTING_RUN_ID,
    execution_generation: 1,
    company_id: companyId,
    company_name: name,
    pre_score: tier === "A" ? 88 : 55,
    recommended_tier: tier,
    effective_tier: tier,
    feature_snapshot: {},
    reason_codes: [tier === "A" ? "TARGET_A_CANDIDATE" : "TARGET_B_CANDIDATE"],
    warning_codes: [],
    review_status:
      tier === "B" && bConfirmed
        ? "confirmed"
        : "suggested",
    override_reason: null,
    reviewed_by: bConfirmed && tier === "B" ? "Browser Reviewer" : null,
    reviewed_at: bConfirmed && tier === "B" ? "2026-08-02T12:00:05Z" : null,
    contact_count: 1,
    has_usable_contact: true,
    has_usable_email: true,
    preferred_role_category: "procurement",
    created_at: "2026-08-02T12:00:03Z",
    updated_at: "2026-08-02T12:00:03Z",
  });
  await page.route(`**/api/v1/prospect-routing-runs/${ROUTING_RUN_ID}/routes**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        routing_run_id: ROUTING_RUN_ID,
        execution_generation: 1,
        routes: [
          routeRow(COMPANY_ID, "Atlas Priority Fitness", "A"),
          routeRow(B_COMPANY_ID, "Beta Batch Fitness", "B"),
        ],
        page: 1,
        limit: 200,
        total: 2,
      }),
    }),
  );
  await page.route(`**/api/v1/prospect-routes/*/review`, async (route) => {
    bConfirmed = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        route_id: `${B_COMPANY_ID}-route`,
        routing_run_id: ROUTING_RUN_ID,
        execution_generation: 1,
        company_id: B_COMPANY_ID,
        company_name: "Beta Batch Fitness",
        pre_score: 55,
        recommended_tier: "B",
        effective_tier: "B",
        feature_snapshot: {},
        reason_codes: ["TARGET_B_CANDIDATE"],
        warning_codes: [],
        review_status: "confirmed",
        override_reason: null,
        reviewed_by: "Browser Reviewer",
        reviewed_at: "2026-08-02T12:00:05Z",
        contact_count: 1,
        has_usable_contact: true,
        has_usable_email: true,
        preferred_role_category: "procurement",
        created_at: "2026-08-02T12:00:03Z",
        updated_at: "2026-08-02T12:00:05Z",
      }),
    });
  });
}

test("B confirmation unlocks Step 7 without touching A", async ({ page }) => {
  const guard = attachConsoleGuard(page);
  await stubStep7UnlockApi(page);
  await page.goto(
    `/?step=6&import_session_id=${SESSION_ID}&routing_run_id=${ROUTING_RUN_ID}`,
  );

  await expect(page.getByTestId("routing-split")).toBeVisible();
  await expect(page.getByTestId("a-selection-count")).toContainText("优先客户：1 家");
  await expect(page.getByTestId("routing-branch-b")).toContainText("Beta Batch Fitness");
  // Step 7 is locked until a B route is human-confirmed.
  await expect(page.getByTestId("acceptance-step-7")).toBeDisabled();

  await page
    .getByRole("checkbox", { name: /加入批量开发 Beta Batch Fitness/ })
    .check();
  await expect(page.getByTestId("confirm-b-batch")).toContainText("1");
  await page.getByTestId("confirm-b-batch").click();

  // Route confirmation is persisted; Step 7 unlocks and is navigable.
  await expect(page.getByTestId("acceptance-step-7")).toBeEnabled();
  await page.getByTestId("acceptance-step-7").click();
  await expect(page.getByTestId("umail-export-panel")).toBeVisible();
  await expect(page.getByTestId("global-error")).not.toBeVisible();

  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(guard.problems()).toEqual([]);
});
