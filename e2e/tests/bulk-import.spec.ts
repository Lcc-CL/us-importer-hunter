import { expect, test } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

test("bulk import entity resolution review survives refresh", async ({
  page,
}) => {
  const guard = attachConsoleGuard(page);
  await page.goto("/");

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
        "D5B1 E2E Atlas,ATLAS-E2E,atlas-e2e.example,100 Main St Austin TX,importer,Maria Chen,maria@atlas-e2e.example,Director Logistics,industrial hardware tools,8205.40,2026-07-01,China,Shanghai,Los Angeles",
        "D5B1 Unrelated Furniture,,atlas-e2e.example,900 Ocean Dr Miami FL,warehouse,Pat Lee,pat@unrelated.example,Procurement Manager,upholstered furniture,9401,2026-07-15,Vietnam,Ho Chi Minh,Long Beach",
        "BrokenOnly",
      ].join("\n"),
    ),
  });
  await panel
    .getByTestId("bulk-import-mapping")
    .fill(
      '{"company_name":"公司名称","external_company_id":"外部ID","website":"官网","address":"地址","company_type":"公司类型","contact_name":"联系人","contact_email":"邮箱","contact_title":"职位","product_description":"产品","hs_code":"HS","shipment_date":"日期","origin_country":"来源国","pol":"POL","pod":"POD"}',
    );
  await panel.getByTestId("bulk-import-upload").click();

  const result = panel.getByTestId("bulk-import-result");
  await expect(result.getByText("导入完成，部分行无效")).toBeVisible();
  await expect(
    result.getByText("总行数", { exact: true }).locator("..").getByText("3", { exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/import_session_id=[0-9a-f-]{36}/);

  await panel.getByTestId("import-resolution-start").click();
  const resolution = panel.getByTestId("import-resolution-result");
  await expect(resolution.getByText("实体归并完成")).toBeVisible();
  await expect(
    resolution.getByText("公司待复核", { exact: true }).locator("..").getByText("1", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(panel.getByTestId("import-resolution-reviews")).toBeVisible();

  await page.reload({ waitUntil: "networkidle" });
  const restored = page.getByTestId("bulk-import-result");
  await expect(restored.getByText("导入完成，部分行无效")).toBeVisible();
  await expect(restored.getByTestId("bulk-import-rows").locator("tr")).toHaveCount(3);
  const restoredResolution = restored.getByTestId("import-resolution-result");
  await expect(restoredResolution.getByText("实体归并完成")).toBeVisible();
  await expect(restored.getByTestId("import-resolution-reviews")).toBeVisible();

  await restored.getByRole("button", { name: "合并", exact: true }).click();
  await expect(restored.getByText("当前没有待复核决定。")).toBeVisible();
  await expect(
    restoredResolution.getByText("公司待复核", { exact: true }).locator("..").getByText("0", {
      exact: true,
    }),
  ).toBeVisible();

  await restored.getByTestId("prospect-routing-products").fill("hardware");
  await restored.getByTestId("prospect-routing-hs").fill("8205");
  await restored.getByTestId("prospect-routing-origins").fill("China");
  await restored.getByTestId("prospect-routing-pol").fill("Shanghai");
  await restored.getByTestId("prospect-routing-pod").fill("Los Angeles");
  await restored.getByTestId("prospect-routing-campaign").fill("D5c E2E hardware");
  await restored.getByTestId("prospect-routing-start").click();

  const routing = restored.getByTestId("prospect-routing-result");
  await expect(routing.getByText("路由完成")).toBeVisible();
  await expect(page).toHaveURL(/routing_run_id=[0-9a-f-]{36}/);
  await expect(restored.getByTestId("prospect-routing-routes")).toBeVisible();

  await page.reload({ waitUntil: "networkidle" });
  const restoredRouting = page.getByTestId("prospect-routing-result");
  await expect(restoredRouting.getByText("路由完成")).toBeVisible();
  await expect(page.getByTestId("prospect-routing-routes")).toBeVisible();

  await restoredRouting.getByRole("button", { name: "确认推荐", exact: true }).click();
  await page
    .getByTestId("prospect-routing-routes")
    .getByRole("checkbox", { name: /D5B1 E2E Atlas/ })
    .check();
  await page.getByTestId("prospect-routing-create-batch").click();
  await expect(page.getByTestId("prospect-routing-batch-created")).toContainText(
    "已创建深度处理批次，尚未启动 Research 或邮件生成。",
  );

  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(guard.problems()).toEqual([]);
});
