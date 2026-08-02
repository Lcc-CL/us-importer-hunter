import { expect, test } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

test("bulk CSV raw intake survives refresh without starting downstream work", async ({
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
        "公司名称,邮箱",
        "D5A1 E2E Atlas,a@example.com",
        "D5A1 E2E Atlas,a@example.com",
        "BrokenOnly",
      ].join("\n"),
    ),
  });
  await panel
    .getByTestId("bulk-import-mapping")
    .fill('{"company_name":"公司名称","contact_email":"邮箱"}');
  await panel.getByTestId("bulk-import-upload").click();

  const result = panel.getByTestId("bulk-import-result");
  await expect(result.getByText("导入完成，部分行无效")).toBeVisible();
  await expect(
    result.getByText("总行数", { exact: true }).locator("..").getByText("3", { exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/import_session_id=[0-9a-f-]{36}/);

  await page.reload({ waitUntil: "networkidle" });
  const restored = page.getByTestId("bulk-import-result");
  await expect(restored.getByText("导入完成，部分行无效")).toBeVisible();
  await expect(restored.getByTestId("bulk-import-rows").locator("tr")).toHaveCount(3);

  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(guard.problems()).toEqual([]);
});
