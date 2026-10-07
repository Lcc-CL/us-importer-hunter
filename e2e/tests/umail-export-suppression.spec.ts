import { expect, test, type Page } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

const SESSION_ID = "11000000-0000-4000-8000-000000000001";
const ROUTING_RUN_ID = "22000000-0000-4000-8000-000000000002";
const ROUTE_ID = "33000000-0000-4000-8000-000000000003";
const COMPANY_ID = "44000000-0000-4000-8000-000000000004";
const BATCH_ID = "55000000-0000-4000-8000-000000000005";
const CONTACT_ID = "66000000-0000-4000-8000-000000000006";
const SUPPRESSION_ID = "77000000-0000-4000-8000-000000000007";

function exportBatch() {
  return {
    batch_id: BATCH_ID,
    routing_run_id: ROUTING_RUN_ID,
    execution_generation: 1,
    campaign: "Hardware B prospects",
    mapping_version: "umail-export-contract-v1",
    selection_hash: "a".repeat(64),
    status: "prepared",
    total_rows: 4,
    ready_count: 1,
    suppressed_count: 1,
    invalid_count: 1,
    duplicate_count: 1,
    content_sha256: "b".repeat(64),
    downloaded_at: null,
    created_at: "2026-08-02T12:00:00Z",
    updated_at: "2026-08-02T12:00:00Z",
    reused: false,
    sent: false,
    rows: [
      ["ready", null, "buyer@atlas.example"],
      ["suppressed", `suppressed_email:${SUPPRESSION_ID}`, "blocked@atlas.example"],
      ["invalid", "invalid_email", "invalid-address"],
      ["duplicate", "duplicate_email", "buyer@atlas.example"],
    ].map(([status, exclusionReason, email], index) => ({
      row_id: `88000000-0000-4000-8000-00000000000${index}`,
      position: index + 1,
      company_id: COMPANY_ID,
      contact_id: CONTACT_ID,
      company_name: "Atlas B Importer",
      company_website: "https://atlas.example",
      contact_name: `Buyer ${index + 1}`,
      contact_title: "Procurement Director",
      contact_role: "procurement",
      contact_seniority: "director",
      is_department_contact: false,
      email,
      route: "B",
      route_review_status: "confirmed",
      pre_score: 72,
      status,
      exclusion_reason: exclusionReason,
      row_fingerprint: `${index}`.repeat(64),
    })),
  };
}

async function stubApi(page: Page) {
  let suppressions: Array<Record<string, unknown>> = [];
  let postedCompanyIds: string[] = [];
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
        original_filename: "b-routes.csv",
        file_type: "csv",
        file_size_bytes: 100,
        file_sha256: "c".repeat(64),
        mapping_json: {},
        encoding: "utf-8",
        status: "completed",
        total_rows: 1,
        accepted_rows: 1,
        invalid_rows: 0,
        duplicate_rows: 0,
        started_at: "2026-08-02T11:59:00Z",
        completed_at: "2026-08-02T11:59:01Z",
        error_summary: null,
        created_at: "2026-08-02T11:59:00Z",
        updated_at: "2026-08-02T11:59:01Z",
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
        total_rows: 1,
        processed_rows: 1,
        companies_created: 1,
        companies_reused: 0,
        company_reviews_required: 0,
        contacts_created: 1,
        contacts_reused: 0,
        company_contacts_created: 1,
        invalid_rows: 0,
        failed_rows: 0,
        started_at: "2026-08-02T11:59:01Z",
        completed_at: "2026-08-02T11:59:02Z",
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
        processing_job_id: null,
        processing_status: "completed",
        status: "completed",
        rules_version: "real-routing-v1.1",
        execution_generation: 1,
        current_execution_generation: 1,
        available_generations: [1],
        criteria: {
          target_product_keywords: ["hardware"],
          target_hs_codes: ["8205"],
          preferred_origin_countries: ["China"],
          preferred_pol: ["Shanghai"],
          preferred_pod: ["Los Angeles"],
          campaign_name: "Hardware B prospects",
          notes: null,
        },
        weights_snapshot: {},
        total_companies: 1,
        routed_companies: 1,
        blocked_companies: 0,
        tier_a_count: 0,
        tier_b_count: 1,
        tier_c_count: 0,
        tier_d_count: 0,
        attempt_count: 1,
        max_attempts: 3,
        heartbeat_at: null,
        last_error_code: null,
        last_error_summary: null,
        started_at: "2026-08-02T11:59:02Z",
        completed_at: "2026-08-02T11:59:03Z",
        error_summary: null,
        created_at: "2026-08-02T11:59:02Z",
        updated_at: "2026-08-02T11:59:03Z",
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
        page: 1,
        limit: 200,
        total: 1,
        routes: [
          {
            route_id: ROUTE_ID,
            routing_run_id: ROUTING_RUN_ID,
            execution_generation: 1,
            company_id: COMPANY_ID,
            company_name: "Atlas B Importer",
            pre_score: 72,
            recommended_tier: "B",
            effective_tier: "B",
            feature_snapshot: {},
            reason_codes: ["B_ROUTE"],
            warning_codes: [],
            review_status: "confirmed",
            override_reason: null,
            reviewed_by: "Browser Reviewer",
            reviewed_at: "2026-08-02T11:59:03Z",
            contact_count: 2,
            has_usable_contact: true,
            has_usable_email: true,
            preferred_role_category: "procurement",
            created_at: "2026-08-02T11:59:03Z",
            updated_at: "2026-08-02T11:59:03Z",
          },
        ],
      }),
    }),
  );
  await page.route("**/api/v1/suppressions**", async (route) => {
    if (route.request().method() === "POST") {
      const request = route.request().postDataJSON() as Record<string, unknown>;
      const created = {
        suppression_id: SUPPRESSION_ID,
        email: request.email,
        domain: request.domain,
        company: request.company,
        active: true,
        reason: request.reason,
        source: "manual",
        created_by: "local_reviewer",
        deactivated_by: null,
        deactivated_at: null,
        created_at: "2026-08-02T12:01:00Z",
        updated_at: "2026-08-02T12:01:00Z",
      };
      suppressions = [created];
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(created) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ page: 1, limit: 200, total: suppressions.length, entries: suppressions }),
    });
  });
  await page.route(`**/api/v1/suppressions/${SUPPRESSION_ID}/deactivate`, async (route) => {
    const deactivated = { ...suppressions[0], active: false, deactivated_by: "local_reviewer", deactivated_at: "2026-08-02T12:02:00Z" };
    suppressions = [deactivated];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(deactivated) });
  });
  await page.route(
    `**/api/v1/prospect-routing-runs/${ROUTING_RUN_ID}/umail-export-batches`,
    async (route) => {
      const request = route.request().postDataJSON() as { company_ids: string[] };
      postedCompanyIds = request.company_ids;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(exportBatch()),
      });
    },
  );
  await page.route(`**/api/v1/umail-export-batches/${BATCH_ID}/download`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/csv; charset=utf-8",
      headers: { "Content-Disposition": `attachment; filename="umail-export-${BATCH_ID}.csv"` },
      body: "company_name,email\r\nAtlas B Importer,buyer@atlas.example\r\n",
    }),
  );
  await page.route(`**/api/v1/umail-export-batches/${BATCH_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(exportBatch()),
    }),
  );
  return { postedCompanyIds: () => postedCompanyIds };
}

test("restores B export preview, manages suppression, and downloads CSV without send", async ({
  page,
}) => {
  const consoleGuard = attachConsoleGuard(page);
  const state = await stubApi(page);
  await page.goto(
    `/?step=7&import_session_id=${SESSION_ID}&routing_run_id=${ROUTING_RUN_ID}&umail_export_batch_id=${BATCH_ID}`,
  );

  await expect(page.getByTestId("umail-export-panel")).toBeVisible();
  await expect(page.getByTestId("umail-export-preview")).toContainText("Ready");
  await expect(page.getByTestId("umail-export-preview")).toContainText("Suppressed");
  await expect(page.getByText("已导出但尚未发送").first()).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("umail-export-preview")).toBeVisible();

  await page.getByTestId("suppression-target").fill("blocked@atlas.example");
  await page.getByTestId("suppression-reason").fill("manual opt out");
  await page.getByTestId("suppression-create").click();
  await expect(page.getByText("blocked@atlas.example · manual opt out")).toBeVisible();

  await page.getByLabel("停用 Suppression blocked@atlas.example").click();
  await expect(page.getByText("blocked@atlas.example · manual opt out")).toHaveClass(/line-through/);

  await page.getByLabel("选择已确认 B 类 Atlas B Importer").check();
  await page.getByTestId("umail-export-prepare").click();
  await expect.poll(state.postedCompanyIds).toEqual([COMPANY_ID]);

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("umail-export-download").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`umail-export-${BATCH_ID}.csv`);
  expect(consoleGuard.problems()).toEqual([]);
});
