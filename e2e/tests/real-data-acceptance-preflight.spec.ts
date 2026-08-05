import { expect, test } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

test("preflights NetEase data without writes and restores real-data mode", async ({
  page,
}) => {
  const consoleGuard = attachConsoleGuard(page);
  let importSessionCalled = false;
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
  await page.route("**/api/v1/acceptance/netease-preflight", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        file_type: "csv",
        file_size_bytes: 128,
        file_sha256: "a".repeat(64),
        encoding: "utf-8",
        sheets: ["CSV"],
        selected_sheet: "CSV",
        total_rows: 2,
        analyzed_rows: 2,
        inferred_data_type: "mixed",
        mapping_profile: "netease-foreign-trade-v1",
        suggested_mapping: {
          company_name: "公司名称",
          contact_email: "邮箱",
          product_description: "产品",
        },
        mapping_confidence: {
          company_name: "medium",
          contact_email: "medium",
          product_description: "medium",
        },
        source_columns: ["公司名称", "邮箱", "产品"],
        sample_values: {
          company_name: "A•••s",
          contact_email: "a•a@e•••••e.test",
          product_description: "h••••s",
        },
        manual_mapping_applied: false,
        unknown_fields: [],
        missing_required_fields: [],
        duplicate_columns: [],
        empty_rows: 0,
        invalid_rows: 0,
        estimated_company_count: 1,
        estimated_contact_count: 2,
        estimated_trade_record_count: 2,
        coverage: {
          external_company_id: 0,
          email: 1,
          website_domain: 0,
          phone: 0,
          address: 0,
        },
        estimated_high_confidence_reviews: 0,
        estimated_medium_confidence_reviews: 0,
        no_business_side_effects: true,
        real_data_gate: "blocked",
      }),
    }),
  );
  await page.route("**/api/v1/import-sessions", (route) => {
    importSessionCalled = true;
    return route.abort();
  });

  await page.goto("/");
  await expect(page.getByTestId("acceptance-step-nav")).toContainText(
    "网易文件 Preflight",
  );
  await page.getByTestId("acceptance-real-data-mode").check();
  await expect(page).toHaveURL(/real_data=1/);
  await page.getByTestId("bulk-import-file").setInputFiles({
    name: "netease.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "公司名称,邮箱,产品\nAtlas,a@example.test,hinges\nAtlas,b@example.test,locks\n",
    ),
  });
  await page.getByTestId("netease-preflight").click();
  await expect(page.getByTestId("netease-preflight-result")).toContainText(
    "netease-foreign-trade-v1",
  );
  await expect(page.getByTestId("structured-mapping-editor")).toContainText(
    "company_name",
  );
  await page.getByTestId("netease-mapping-confirmed").check();
  expect(importSessionCalled).toBe(false);
  await expect(page).toHaveURL(/real_data=1/);
  await expect(page).toHaveURL(/step=2/);
  expect(consoleGuard.problems()).toEqual([]);
});
