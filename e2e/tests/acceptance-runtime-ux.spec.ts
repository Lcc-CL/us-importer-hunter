import { expect, test, type Page } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

async function mockHealthyDependencies(page: Page, gate: "enabled" | "blocked" = "blocked") {
  await page.route(/\/api\/v1\/health\/ready$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ready",
        dependencies: [
          { name: "postgres", healthy: true, detail: null },
          { name: "redis", healthy: true, detail: null },
          { name: "worker", healthy: true, detail: null },
        ],
      }),
    }),
  );
  await page.route(/\/api\/v1\/health\/runtime$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        provider: "fake",
        model: "fake-static-v1",
        research_provider: "fake",
        research_model: "fake-research-v1",
        environment: "test",
        real_data_gate: gate,
      }),
    }),
  );
}

test("loads runtime health through the configured browser-facing API path", async ({ page }) => {
  const consoleGuard = attachConsoleGuard(page);
  const healthRequest = page.waitForRequest(/\/api\/v1\/health$/);
  await page.goto("/");
  const request = await healthRequest;
  await expect(page.getByTestId("runtime-status-card")).toHaveAttribute(
    "data-health-phase",
    "healthy",
  );
  await expect(page.getByTestId("runtime-status-card")).toContainText("后端已连接");
  expect(new URL(request.url()).origin).toBe(new URL(page.url()).origin);
  await expect(page.getByRole("link", { name: "API 文档" })).toHaveCount(0);
  expect(consoleGuard.problems()).toEqual([]);
});

test("shows an actionable unavailable state and recovers without reload", async ({ page }) => {
  let backendAvailable = false;
  await mockHealthyDependencies(page);
  await page.route(/\/api\/v1\/health$/, (route) => {
    if (!backendAvailable) {
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          code: "backend_unavailable",
          message: "Backend unavailable",
          request_id: "test-request",
        }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", app: "us-importer-hunter", environment: "test" }),
    });
  });

  await page.goto("/");
  const card = page.getByTestId("runtime-status-card");
  await expect(card).toHaveAttribute("data-health-phase", "unavailable");
  await expect(card).toContainText("请求目标");
  await expect(card).toContainText("/api/v1");
  await expect(page.getByTestId("netease-preflight")).toBeDisabled();
  await expect(page.getByTestId("acceptance-workspace-step-1")).toBeVisible();
  await expect(page.getByTestId("acceptance-workspace-step-2")).toHaveCount(0);
  await expect(page.getByTestId("discovery-task-panel")).toBeHidden();
  await expect(page.getByTestId("advanced-form")).toHaveCount(0);

  backendAvailable = true;
  await page.getByTestId("runtime-retry").click();
  await expect(card).toHaveAttribute("data-health-phase", "healthy");
  await expect(card).toContainText("后端已连接");
  await expect(card).toContainText("PostgreSQL");
  await expect(card).toContainText("Worker");
});

test("uses a structured mapping table and preserves valid mapping after invalid JSON", async ({ page }) => {
  const consoleGuard = attachConsoleGuard(page);
  await mockHealthyDependencies(page, "blocked");
  await page.route(/\/api\/v1\/health$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", app: "us-importer-hunter", environment: "test" }),
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
          company_name: "high",
          contact_email: "medium",
          product_description: "medium",
        },
        source_columns: ["公司名称", "邮箱", "产品", "未识别列"],
        sample_values: {
          company_name: "A••••s",
          contact_email: "a•a@e•••••e.test",
          product_description: "h••••s",
        },
        manual_mapping_applied: false,
        unknown_fields: ["未识别列"],
        missing_required_fields: [],
        duplicate_columns: [],
        empty_rows: 0,
        invalid_rows: 0,
        estimated_company_count: 1,
        estimated_contact_count: 2,
        estimated_trade_record_count: 2,
        coverage: { external_company_id: 0, email: 1, website_domain: 0, phone: 0, address: 0 },
        estimated_high_confidence_reviews: 0,
        estimated_medium_confidence_reviews: 0,
        no_business_side_effects: true,
        real_data_gate: "blocked",
      }),
    }),
  );

  await page.goto("/");
  await expect(page.getByTestId("runtime-status-card")).toHaveAttribute("data-health-phase", "healthy");
  await page.getByTestId("acceptance-real-data-mode").check();
  await page.getByTestId("bulk-import-file").setInputFiles({
    name: "acceptance.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("公司名称,邮箱,产品\nAtlas,a@example.test,hinges\n"),
  });
  await page.getByTestId("netease-preflight").click();

  await expect(page).toHaveURL(/step=2/);
  await expect(page.getByTestId("structured-mapping-editor")).toBeVisible();
  const companySelect = page.getByTestId("mapping-select-company_name");
  await expect(companySelect).toHaveValue("公司名称");
  await expect(page.getByTestId("structured-mapping-editor")).toContainText("A••••s");

  await page.getByText("高级 JSON 编辑").click();
  await page.getByTestId("mapping-json-editor").fill("{invalid");
  await page.getByTestId("mapping-json-apply").click();
  await expect(page.getByTestId("structured-mapping-editor")).toContainText("当前 Mapping 未被覆盖");
  await expect(companySelect).toHaveValue("公司名称");

  await page.getByTestId("netease-mapping-confirmed").check();
  await expect(page.getByTestId("bulk-import-upload")).toBeDisabled();
  await expect(page.getByTestId("bulk-import-disabled-reason")).toContainText(
    "real_data_acknowledged",
  );
  expect(consoleGuard.problems()).toEqual([]);
});
