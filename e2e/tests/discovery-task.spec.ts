import { expect, test } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

test("one-sentence manual CSV discovery survives a page refresh", async ({
  page,
}) => {
  const guard = attachConsoleGuard(page);
  await page.goto("/");

  const panel = page.getByTestId("discovery-task-panel");
  await panel.getByTestId("discovery-prompt").fill("帮我找 20 家北美五金进口商");
  await panel.getByTestId("discovery-csv-file").setInputFiles({
    name: "discovery-candidates.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      [
        "company_name,source_url,website,region,product_description,import_evidence",
        "E2E Atlas Hardware,https://evidence.example/atlas,https://atlas-e2e.example,US,Hand tools,BOL-ATLAS-1",
        "E2E Harbor Supply,https://evidence.example/harbor,https://harbor-e2e.example,US,Industrial supplies,BOL-HARBOR-1",
      ].join("\n"),
    ),
  });
  await panel.getByTestId("create-manual-csv-discovery-task").click();

  const result = panel.getByTestId("discovery-task-result");
  await expect(result.getByText("已完成", { exact: true })).toBeVisible();
  await expect(result.getByText("E2E Atlas Hardware")).toBeVisible();
  await expect(result.getByText("E2E Harbor Supply")).toBeVisible();
  await expect(result.getByText(/manual_csv/).first()).toBeVisible();
  await expect(page).toHaveURL(/task_id=[0-9a-f-]{36}/);

  await page.reload({ waitUntil: "networkidle" });
  const restored = page.getByTestId("discovery-task-result");
  await expect(restored.getByText("已完成", { exact: true })).toBeVisible();
  await expect(restored.getByText("E2E Atlas Hardware")).toBeVisible();
  await expect(restored.getByText("E2E Harbor Supply")).toBeVisible();

  expect(guard.duplicateKeyWarnings()).toEqual([]);
  expect(guard.problems()).toEqual([]);
});
