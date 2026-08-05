import { expect, test, type Page } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

const IMPORT_ID = "91000000-0000-4000-8000-000000000001";
const EXPORT_BATCH_ID = "92000000-0000-4000-8000-000000000002";
const EXPORT_ROW_ID = "93000000-0000-4000-8000-000000000003";

const eventCounts = {
  sent: 0,
  delivered: 0,
  hard_bounced: 1,
  soft_bounced: 0,
  bounce_unknown: 0,
  unsubscribed: 0,
  complained: 0,
  replied: 0,
  opened: 0,
  clicked: 0,
};

function resultImport(applied: boolean) {
  return {
    result_import_id: IMPORT_ID,
    source_filename: "umail-results.csv",
    file_sha256: "a".repeat(64),
    mapping_version: "umail-result-import-contract-v1",
    mapping_snapshot: {
      export_batch_id: "export_batch_id",
      export_row_id: "export_row_id",
      email: "email",
      campaign: "campaign",
      event_type: "状态",
      occurred_at: "时间",
      bounce_type: "bounce_type",
      message_id: "message_id",
    },
    status: applied ? "partial_applied" : "ready_for_review",
    input_row_count: 5,
    matched_count: 1,
    unmatched_count: 1,
    ambiguous_count: 1,
    invalid_count: 1,
    duplicate_count: 1,
    projected_event_count: 1,
    projected_suppression_count: 1,
    applied_event_count: applied ? 1 : 0,
    suppression_created_count: applied ? 1 : 0,
    created_by: "local_reviewer",
    created_at: "2026-08-03T20:00:00Z",
    applied_at: applied ? "2026-08-03T20:01:00Z" : null,
    error_summary: null,
    reused: false,
    system_sent_email: false,
  };
}

const rows = [
  ["matched", "hard_bounced", "export_row_id", true, []],
  ["unmatched", "delivered", null, false, ["export_match_not_found"]],
  ["ambiguous", "clicked", null, false, ["ambiguous_campaign_email"]],
  ["invalid", null, null, false, ["unsupported_event"]],
  ["duplicate", "sent", null, false, ["duplicate_event"]],
].map(([matchStatus, eventType, matchMethod, suppressionImpact, errors], index) => ({
  result_row_id: `94000000-0000-4000-8000-00000000000${index}`,
  row_number: index + 2,
  export_batch_id: index === 0 ? EXPORT_BATCH_ID : null,
  export_row_id: index === 0 ? EXPORT_ROW_ID : null,
  normalized_email: `buyer-${index}@example.test`,
  campaign: "Hardware Campaign",
  canonical_event_type: eventType,
  occurred_at: "2026-08-03T19:00:00Z",
  bounce_type: eventType === "hard_bounced" ? "hard" : null,
  message_id: `message-${index}`,
  match_status: matchStatus,
  matched_export_row_id: matchStatus === "matched" ? EXPORT_ROW_ID : null,
  match_method: matchMethod,
  error_codes: errors,
  row_fingerprint: `${index}`.repeat(64),
  suppression_impact: suppressionImpact,
}));

async function stubApi(page: Page) {
  let applied = false;
  let uploadReceived = false;
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
  await page.route("**/api/v1/acceptance/umail-result-preflight", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        file_type: "csv",
        file_size_bytes: 128,
        file_sha256: "a".repeat(64),
        encoding: "utf-8",
        total_rows: 1,
        mapping_profile: "umail-result-preflight-v1",
        suggested_mapping: {
          email: "email",
          event_type: "状态",
          occurred_at: "时间",
        },
        mapping_confidence: {
          email: "high",
          event_type: "manual",
          occurred_at: "manual",
        },
        source_columns: ["email", "状态", "时间"],
        sample_values: {
          email: "b••••@e•••••e.test",
          event_type: "h••••••e",
          occurred_at: "2••••••Z",
        },
        manual_mapping_applied: false,
        unknown_fields: [],
        missing_required_fields: [],
        duplicate_columns: [],
        event_type_distribution: { hard_bounced: 1 },
        time_format_distribution: { iso8601: 1 },
        bounce_type_distribution: {},
        coverage: { export_row_id: 0, export_batch_id: 0, email: 1, campaign: 0 },
        estimated_strong_id_matches: 0,
        estimated_email_fallback_matches: 1,
        estimated_ambiguous_rows: 0,
        unsupported_event_count: 0,
        missing_occurred_at_count: 0,
        invalid_rows: 0,
        match_estimate_basis: "database_snapshot",
        no_business_side_effects: true,
        real_data_gate: "blocked",
      }),
    }),
  );
  await page.route("**/api/v1/umail-result-imports**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/statistics")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          result_import_id: IMPORT_ID,
          total_result_rows: 5,
          matched_rate: 0.2,
          rates: {
            total_events: applied ? 1 : 0,
            event_counts: applied ? eventCounts : { ...eventCounts, hard_bounced: 0 },
            delivered_rate: 0,
            reply_rate: 0,
            hard_bounce_rate: applied ? 1 : 0,
            unsubscribe_rate: 0,
            complaint_rate: 0,
          },
          campaign_statistics: applied
            ? { "Hardware Campaign": eventCounts }
            : {},
          route_statistics: applied ? { B: eventCounts } : {},
          company_statistics: applied
            ? [
                {
                  company_id: "95000000-0000-4000-8000-000000000005",
                  company_name: "Atlas Hardware",
                  event_counts: eventCounts,
                },
              ]
            : [],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/rows")) {
      const matchStatus = url.searchParams.get("match_status");
      const filtered = matchStatus
        ? rows.filter((row) => row.match_status === matchStatus)
        : rows;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          result_import_id: IMPORT_ID,
          page: 1,
          limit: 50,
          total: filtered.length,
          rows: filtered,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/apply")) {
      applied = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(resultImport(true)),
      });
      return;
    }
    if (request.method() === "POST") {
      uploadReceived = request.postDataBuffer()?.includes(Buffer.from("event_type")) ?? false;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(resultImport(false)),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(resultImport(applied)),
    });
  });
  return {
    applied: () => applied,
    uploadReceived: () => uploadReceived,
  };
}

test("uploads, restores, filters, and applies offline Umail results without sending", async ({
  page,
}) => {
  const consoleGuard = attachConsoleGuard(page);
  const state = await stubApi(page);
  await page.goto(`/?step=8&umail_export_batch_id=${EXPORT_BATCH_ID}`);

  await expect(page.getByTestId("umail-feedback-panel")).toBeVisible();
  await expect(
    page.getByText("导入的是外部发送结果，不代表本系统发送了邮件。"),
  ).toBeVisible();
  await page.getByTestId("umail-feedback-file").setInputFiles({
    name: "umail-results.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("email,状态,时间\nbuyer@example.test,hard_bounce,2026-08-03T19:00:00Z\n"),
  });
  await page.getByTestId("umail-feedback-preflight").click();
  await expect(page.getByTestId("structured-mapping-editor")).toBeVisible();
  await page.getByTestId("umail-preflight-mapping-confirmed").check();
  await page.getByTestId("umail-feedback-upload").click();
  await expect(page).toHaveURL(new RegExp(`umail_result_import_id=${IMPORT_ID}`));
  await expect(page.getByTestId("umail-feedback-preview")).toContainText("Matched");
  expect(state.uploadReceived()).toBe(true);

  await page.reload();
  await expect(page.getByTestId("umail-feedback-preview")).toBeVisible();
  await expect(page.getByTestId("umail-feedback-rows")).toContainText("export_row_id");

  await page.getByTestId("umail-feedback-match-filter").selectOption("ambiguous");
  await expect(page.getByTestId("umail-feedback-rows")).toContainText("Ambiguous");
  await expect(page.getByTestId("umail-feedback-rows")).not.toContainText("Matched");

  await page.getByTestId("acceptance-step-9").click();
  await page.getByTestId("umail-feedback-confirm").check();
  await page.getByTestId("umail-feedback-apply").click();
  await expect.poll(state.applied).toBe(true);
  await expect(page.getByText(/已追加 1 个 Engagement/)).toBeVisible();
  await expect(page.getByTestId("umail-feedback-statistics")).toContainText("100.0%");
  await expect(page.getByText("只回传结果，不发送邮件")).toBeVisible();
  expect(consoleGuard.problems()).toEqual([]);
});
