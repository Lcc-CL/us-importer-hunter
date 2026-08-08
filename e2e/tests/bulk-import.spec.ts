import { expect, test } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

test("bulk import entity resolution review survives refresh", async ({
  page,
}) => {
  const guard = attachConsoleGuard(page);
  // The isolated fake E2E stack keeps the real-data gate blocked; enable it in
  // the page so the routing approval step can be exercised after entity review.
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
        real_data_gate: "enabled",
      }),
    }),
  );
  await page.goto("/");
  await expect(page.getByTestId("runtime-status-card")).toHaveAttribute(
    "data-health-phase",
    "healthy",
  );

  const panel = page.getByTestId("bulk-import-panel");
  await expect(
    panel.getByText(
      "本步骤仅完成原始数据导入和质量检查，尚未进行公司归并、机会评分或邮件发送。",
    ),
  ).toBeVisible();
  await panel.getByTestId("bulk-import-file").setInputFiles({
    name: "netease-raw-e2e.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      [
        "公司名称,外部ID,官网,地址,公司类型,联系人,邮箱,职位,产品,HS,日期,来源国,POL,POD",
        "D5B1 E2E Atlas,ATLAS-E2E,atlas-e2e.example,100 Main St Austin TX,importer,Maria Chen,maria@atlas-e2e.example,Director Logistics,fitness equipment,950691,2026-07-01,United States,Shanghai,Los Angeles",
        "D5B1 Unrelated Fitness,,atlas-e2e.example,900 Ocean Dr Miami FL,warehouse,Pat Lee,pat@unrelated.example,Procurement Manager,fitness accessories,950691,2026-07-15,United States,Ho Chi Minh,Long Beach",
        "BrokenOnly",
      ].join("\n"),
    ),
  });
  await panel.getByTestId("netease-preflight").click();
  await expect(panel.getByTestId("structured-mapping-editor")).toBeVisible();
  await panel.getByText("高级 JSON 编辑").click();
  await panel.getByTestId("mapping-json-editor").fill(
    '{"company_name":"公司名称","external_company_id":"外部ID","website":"官网","address":"地址","company_type":"公司类型","contact_name":"联系人","contact_email":"邮箱","contact_title":"职位","product_description":"产品","hs_code":"HS","shipment_date":"日期","origin_country":"来源国","pol":"POL","pod":"POD"}',
  );
  await panel.getByTestId("mapping-json-apply").click();
  await panel.getByTestId("netease-preflight-again").click();
  await panel.getByTestId("netease-mapping-confirmed").check();
  await panel.getByTestId("bulk-import-upload").click();

  const result = panel.getByTestId("bulk-import-result");
  await expect(result.getByText("导入完成，部分行无效")).toBeVisible();
  await expect(
    result.getByText("总行数", { exact: true }).locator("..").getByText("3", { exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/import_session_id=[0-9a-f-]{36}/);
  await expect(panel.getByTestId("acceptance-current-executable")).toContainText("Step 4");
  await expect(panel.getByTestId("acceptance-current-executable")).not.toContainText("Step 1");

  await panel.getByTestId("acceptance-step-4").click();
  await panel.getByTestId("import-resolution-start").click();
  const resolution = panel.getByTestId("import-resolution-result");
  await expect(resolution.getByText("实体归并完成")).toBeVisible();
  await expect(panel.getByTestId("stage-boundary")).toContainText(
    "公司与联系人实体已完成归并",
  );
  await expect(
    resolution.getByText("公司待复核", { exact: true }).locator("..").getByText("1", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(panel.getByTestId("import-resolution-reviews")).toBeVisible();

  await page.reload({ waitUntil: "networkidle" });
  const restored = page.getByTestId("bulk-import-result");
  await expect(restored.getByText("导入完成，部分行无效")).toBeVisible();
  const restoredResolution = restored.getByTestId("import-resolution-result");
  await expect(restoredResolution.getByText("实体归并完成")).toBeVisible();
  await expect(restored.getByTestId("import-resolution-reviews")).toBeVisible();

  // Step 5: the preset auto-fills the preview parameters; routing stays
  // blocked while the entity review is pending.
  await page.getByTestId("acceptance-step-5").click();
  await expect(
    restored.getByTestId("routing-campaign-summary"),
  ).toContainText("fitness-equipment-us-v1");
  await expect(page.getByTestId("acceptance-step-nav")).toContainText(
    "Canonical 公司",
  );
  await expect(restored.getByTestId("prospect-routing-products")).toHaveValue(
    "fitness, gym equipment",
  );
  await restored.getByTestId("routing-preview-generate").click();
  await expect(restored.getByTestId("global-error")).not.toBeVisible();
  await expect(
    restored.getByTestId("routing-apply-blocker").getByText("仍有 1 条实体需要审核。"),
  ).toBeVisible();
  await expect(restored.getByTestId("prospect-routing-start")).toBeDisabled();

  // Low-confidence merge opens the confirmation modal with both candidates.
  await page.getByTestId("acceptance-step-4").click();
  await restored.getByRole("button", { name: "确认同一实体", exact: true }).click();
  await expect(page.getByTestId("merge-confirm-candidates")).toBeVisible();
  await page.getByTestId("merge-confirm-submit").click();
  await expect(restored.getByText("当前没有待复核决定。")).toBeVisible();
  await expect(
    restoredResolution.getByText("公司待复核", { exact: true }).locator("..").getByText("0", {
      exact: true,
    }),
  ).toBeVisible();

  await page.getByTestId("acceptance-step-5").click();
  await restored.getByTestId("routing-preview-generate").click();
  await expect(restored.getByTestId("routing-apply-blocker")).not.toBeVisible();
  await restored.getByTestId("prospect-routing-start").click();
  await page.getByTestId("routing-apply-confirm-submit").click();

  const routing = restored.getByTestId("prospect-routing-result");
  await expect(routing.getByText("路由完成")).toBeVisible();
  await expect(page).toHaveURL(/routing_run_id=[0-9a-f-]{36}/);
  await page.getByTestId("acceptance-step-6").click();
  await expect(restored.getByTestId("prospect-routing-routes")).toBeVisible();

  await page.reload({ waitUntil: "networkidle" });
  const restoredRouting = page.getByTestId("prospect-routing-result");
  await expect(restoredRouting.getByText("路由完成")).toBeVisible();
  await expect(page.getByTestId("prospect-routing-routes")).toBeVisible();

  await restoredRouting.getByRole("button", { name: "确认推荐", exact: true }).click();
  await expect(page.getByTestId("deep-analysis-start")).toContainText("1 家");
  // Deselecting updates the count immediately.
  await page
    .getByTestId("prospect-routing-routes")
    .getByRole("checkbox", { name: /D5B1 E2E Atlas/ })
    .uncheck();
  await expect(page.getByTestId("deep-analysis-start")).toContainText("0 家");
  await page
    .getByTestId("prospect-routing-routes")
    .getByRole("checkbox", { name: /D5B1 E2E Atlas/ })
    .check();
  await expect(page.getByTestId("deep-analysis-start")).toContainText("1 家");
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByTestId("deep-analysis-start").click();
  await expect(page.getByTestId("prospect-routing-batch-created")).toBeVisible();
  await expect(page.getByText("深度处理已启动", { exact: false })).toBeVisible();

  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(guard.problems()).toEqual([]);
});
