import { expect, test, type Page } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

const TASK_ID = "11111111-1111-4111-8111-111111111114";
const BATCH_ID = "22222222-2222-4222-8222-222222222224";
const CALIBRATION_ID = "33333333-3333-4333-8333-333333333334";
const JOB_ID = "44444444-4444-4444-8444-444444444445";
const COMPANY_IDS = [
  "55555555-5555-4555-8555-555555555551",
  "55555555-5555-4555-8555-555555555552",
  "55555555-5555-4555-8555-555555555553",
];

function discoveryCompany(companyId: string, position: number) {
  return {
    candidate_id: `66666666-6666-4666-8666-66666666666${position}`,
    position,
    company_id: companyId,
    company_name: ["Atlas Hardware", "Harbor Supply", "Summit Tools"][position],
    website: `https://company-${position}.example`,
    domain: `company-${position}.example`,
    address: null,
    region: "US",
    product_description: "Hardware importer",
    import_evidence: `BOL-${position}`,
    source: "manual_csv",
    source_url: `https://evidence.example/${position}`,
    external_id: `sample-${position}`,
    status: "ingested",
    is_duplicate: false,
    failure_reason: null,
    created_at: "2026-08-01T12:00:01Z",
  };
}

function batchCompany(companyId: string, position: number) {
  return {
    company_id: companyId,
    company_name: ["Atlas Hardware", "Harbor Supply", "Summit Tools"][position],
    position,
    pipeline_version: "d2a-prospect-pipeline-v1",
    current_stage: "completed",
    status: "completed",
    research_id: `77777777-7777-4777-8777-77777777777${position}`,
    opportunity_id: `88888888-8888-4888-8888-88888888888${position}`,
    selected_contact_id: `99999999-9999-4999-8999-99999999999${position}`,
    outreach_id: `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa${position}`,
    draft_version: 1,
    draft_id: `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa${position}:1`,
    score: 72,
    qualification_decision: "qualified",
    reasons: ["trusted import evidence"],
    contact_name: "Maria Chen",
    contact_email: `maria${position}@example.com`,
    contact_source_url: `https://company-${position}.example/contact`,
    contact_type: "personal",
    draft_subject: "Freight partnership",
    draft_status: "generated",
    error_code: null,
    error_summary: null,
    started_at: "2026-08-01T12:01:01Z",
    completed_at: "2026-08-01T12:01:08Z",
    blocking_claim_count: 0,
    resumed_at: null,
    resumed_from_stage: null,
    resume_count: 0,
    stage_timings: [
      {
        stage: "researching",
        started_at: "2026-08-01T12:01:01Z",
        completed_at: "2026-08-01T12:01:03Z",
        duration_ms: 2000,
      },
    ],
  };
}

function calibrationCompany(companyId: string, position: number, evaluation: unknown) {
  return {
    company_id: companyId,
    company_name: ["Atlas Hardware", "Harbor Supply", "Summit Tools"][position],
    final_status: "completed",
    error_code: null,
    error_summary: null,
    research: {
      request_succeeded: true,
      pages_fetched: 2,
      duration_ms: 1200,
      new_claim_count: 1,
      accepted_count: 1,
      edited_count: 0,
      rejected_count: 0,
      pending_count: 0,
      claims_without_source_count: 0,
      failure_reason: null,
    },
    opportunity: {
      generated: true,
      score: 72,
      qualification_decision: "qualified",
      major_positive_reasons: ["trusted import evidence"],
      major_deduction_reasons: [],
      limiting_reasons: [],
      trusted_evidence_count: 1,
      stopped_for_insufficient_evidence: false,
    },
    contact: {
      personal_contact_found: true,
      department_contact_found: false,
      contact_type: "personal",
      name: "Maria Chen",
      title_or_department: "Supply Chain Director",
      email: `maria${position}@example.com`,
      phone: null,
      source_url: `https://company-${position}.example/contact`,
      manually_confirmed: false,
      contact_not_found_reason: null,
    },
    draft: {
      generated: true,
      not_generated_reason: null,
      contact_type: "personal",
      fact_count: 1,
      facts: [
        {
          claim: "customs activity confirmed",
          source_urls: [`https://evidence.example/${position}`],
          traceable_to_company_evidence: true,
        },
      ],
      all_facts_traceable: true,
      contains_unreviewed_claim: false,
      contains_rejected_claim: false,
      awaiting_human_review: true,
      explicitly_not_sent: true,
    },
    worker: {
      queue_wait_ms: 50,
      total_duration_ms: 7000,
      stage_durations_ms: { researching: 2000, scoring: 1000 },
      attempt_count: 1,
      recovery_count: 0,
      lease_expired: false,
      duplicate_entity_count: 0,
    },
    evaluation,
  };
}

async function stubCalibrationApi(page: Page) {
  let savedEvaluation: Record<string, unknown> | null = null;
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
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        task_id: TASK_ID,
        original_prompt: "帮我找 3 家北美五金进口商",
        requested_count: 3,
        effective_count: 3,
        parsed_region: "North America",
        parsed_category: "hardware",
        parsed_keywords: ["hardware"],
        provider: "manual_csv",
        status: "completed",
        discovered_count: 3,
        ingested_count: 3,
        duplicate_count: 0,
        failed_count: 0,
        error_code: null,
        error_summary: null,
        created_at: "2026-08-01T12:00:00Z",
        started_at: "2026-08-01T12:00:00Z",
        completed_at: "2026-08-01T12:00:02Z",
      }),
    }),
  );
  await page.route(`**/api/v1/discovery-tasks/${TASK_ID}/companies`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        task_id: TASK_ID,
        companies: COMPANY_IDS.map(discoveryCompany),
      }),
    }),
  );
  await page.route(`**/api/v1/discovery-tasks/${TASK_ID}/calibrations`, (route) =>
    route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        calibration_id: CALIBRATION_ID,
        batch_id: BATCH_ID,
        job_id: JOB_ID,
        status: "pending",
        reused: false,
      }),
    }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        batch_id: BATCH_ID,
        discovery_task_id: TASK_ID,
        requested_count: 3,
        effective_count: 3,
        status: "completed",
        queued_count: 0,
        running_count: 0,
        completed_count: 3,
        needs_review_count: 0,
        failed_count: 0,
        created_at: "2026-08-01T12:01:00Z",
        started_at: "2026-08-01T12:01:01Z",
        completed_at: "2026-08-01T12:01:08Z",
        error_summary: null,
      }),
    }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/companies`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        batch_id: BATCH_ID,
        companies: COMPANY_IDS.map(batchCompany),
      }),
    }),
  );
  await page.route(`**/api/v1/prospect-batches/${BATCH_ID}/execution`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: JOB_ID,
        batch_id: BATCH_ID,
        status: "completed",
        available_at: "2026-08-01T12:01:00Z",
        attempt_count: 1,
        max_attempts: 3,
        heartbeat_at: "2026-08-01T12:01:08Z",
        last_error_code: null,
        last_error_summary: null,
        recovery_count: 0,
        last_recovered_at: null,
        created_at: "2026-08-01T12:01:00Z",
        started_at: "2026-08-01T12:01:01Z",
        completed_at: "2026-08-01T12:01:08Z",
        updated_at: "2026-08-01T12:01:08Z",
      }),
    }),
  );
  await page.route(`**/api/v1/calibrations/${CALIBRATION_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        calibration_id: CALIBRATION_ID,
        discovery_task_id: TASK_ID,
        prospect_batch_id: BATCH_ID,
        status: "completed",
        sample_source: "manual_csv",
        sample_reality_status: "user_supplied_unverified",
        created_at: "2026-08-01T12:01:00Z",
        updated_at: "2026-08-01T12:01:08Z",
        generated_at: "2026-08-01T12:02:00Z",
        providers: {
          website_fetch_mode: "fixture",
          research_provider_mode: "deterministic_fake",
          draft_provider_mode: "deterministic_fake",
          contact_source_mode: "official_website",
          paid_request_count: 0,
          research_provider_call_count: 0,
          draft_provider_call_count: 0,
          provider_duration_ms: 6600,
          token_usage_total: 0,
        },
        summary: {
          sample_count: 3,
          website_research_success_count: 3,
          website_research_success_rate: 1,
          evidence_review_company_count: 3,
          evidence_accepted_count: 3,
          evidence_rejected_count: 0,
          opportunity_generated_count: 3,
          opportunity_generation_rate: 1,
          qualified_count: 3,
          personal_contact_count: 3,
          personal_contact_coverage_rate: 1,
          department_contact_count: 0,
          department_contact_coverage_rate: 0,
          draft_generated_count: 3,
          draft_generation_rate: 1,
          ready_for_real_outreach_count: savedEvaluation ? 1 : 0,
          evaluated_company_count: savedEvaluation ? 1 : 0,
          worker_recovery_count: 0,
          average_processing_duration_ms: 7000,
          average_research_accuracy: savedEvaluation ? 4 : null,
          average_opportunity_reasonableness: savedEvaluation ? 4 : null,
          average_contact_usability: savedEvaluation ? 4 : null,
          average_draft_personalization: savedEvaluation ? 4 : null,
          average_draft_professionalism: savedEvaluation ? 4 : null,
        },
        truth_checks: {
          fabricated_contact_count: 0,
          unreviewed_fact_in_draft_count: 0,
          rejected_claim_in_score_or_draft_count: 0,
          pending_claim_bypassed_count: 0,
          draft_marked_sent_count: 0,
          duplicate_entity_count: 0,
          invalid_email_contact_count: 0,
          website_failure_mislabeled_company_missing_count: 0,
          opportunity_score_is_probability: false,
        },
        companies: COMPANY_IDS.map((companyId, position) =>
          calibrationCompany(companyId, position, position === 0 ? savedEvaluation : null),
        ),
      }),
    }),
  );
  await page.route(
    `**/api/v1/calibrations/${CALIBRATION_ID}/companies/${COMPANY_IDS[0]}/evaluation`,
    async (route) => {
      savedEvaluation = {
        ...route.request().postDataJSON(),
        reviewed_at: "2026-08-01T12:03:00Z",
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(savedEvaluation),
      });
    },
  );
}

test("D4a calibration report, evaluation and refresh recovery", async ({ page }) => {
  const guard = attachConsoleGuard(page);
  await stubCalibrationApi(page);
  await page.goto(`/?task_id=${TASK_ID}`);

  const panel = page.getByTestId("prospect-batch-panel");
  await panel.getByTestId("batch-select-all").click();
  await panel.getByTestId("start-calibration-run").click();

  const report = page.getByTestId("calibration-report");
  await expect(report).toBeVisible();
  await expect(report.getByTestId("calibration-company")).toHaveCount(3);
  await expect(report).toContainText("deterministic_fake");
  await expect(report).toContainText("硬性真实性门槛");
  await expect(page).toHaveURL(new RegExp(`calibration_id=${CALIBRATION_ID}`));

  await report.getByLabel("审核人 *").first().fill("E2E Reviewer");
  await report.getByLabel("可用于真实触达").first().check();
  await report.getByTestId("save-calibration-evaluation").first().click();
  await expect(report).toContainText("已保存：");
  await expect(report.getByText("可真实触达").first()).toBeVisible();

  await expect(report.getByRole("link", { name: "CSV" })).toHaveAttribute(
    "href",
    new RegExp(`${CALIBRATION_ID}/calibration-summary.csv$`),
  );
  await expect(report.getByRole("link", { name: "JSON" })).toHaveAttribute(
    "href",
    new RegExp(`${CALIBRATION_ID}/calibration-report.json$`),
  );

  await page.reload({ waitUntil: "networkidle" });
  const restored = page.getByTestId("calibration-report");
  await expect(restored).toBeVisible();
  await expect(restored.getByLabel("审核人 *").first()).toHaveValue("E2E Reviewer");
  await expect(restored.getByLabel("可用于真实触达").first()).toBeChecked();

  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(guard.problems()).toEqual([]);
});
