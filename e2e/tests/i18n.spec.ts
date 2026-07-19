import { expect, test } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";
import { openAdvancedForm } from "../utils/form";

test.describe("i18n", () => {
  test("defaults to Chinese, switches to English, and survives reload", async ({
    page,
  }) => {
    const guard = attachConsoleGuard(page);

    // --- default is Simplified Chinese ---
    await page.goto("/");
    await expect(page.getByText("潜在客户分析工作台")).toBeVisible();
    // The manual form's own heading sits inside the collapsed Advanced
    // section now, so localization is checked where it is actually shown.
    await expect(page.getByText("高级编辑 / 手动补充")).toBeVisible();
    await openAdvancedForm(page);
    await expect(page.getByText("分析一家美国进口商")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");

    // --- switch to English ---
    await page.getByRole("button", { name: "English" }).click();
    await expect(page.getByText("Prospect analysis workspace")).toBeVisible();
    await openAdvancedForm(page);
    await expect(page.getByText("Analyze a US importer")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");

    // --- the choice persists across a reload ---
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByText("Prospect analysis workspace")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");

    // --- and back again ---
    await page.getByRole("button", { name: "中文" }).click();
    await expect(page.getByText("潜在客户分析工作台")).toBeVisible();
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByText("潜在客户分析工作台")).toBeVisible();

    expect(guard.duplicateKeyWarnings()).toEqual([]);
    expect(guard.problems()).toEqual([]);
  });

  test("signal-kind dropdown shows localized labels and submits English enums", async ({
    page,
  }) => {
    const guard = attachConsoleGuard(page);
    await page.goto("/");
    await openAdvancedForm(page);
    await page.getByRole("button", { name: "添加信号" }).click();

    const select = page.getByLabel("Signal 1 kind");
    await expect(select).toHaveJSProperty("tagName", "SELECT");

    const values = await select.locator("option").evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value),
    );
    for (const canonical of [
      "import_activity",
      "china_dependency",
      "shipping_fit",
      "cargo_value_potential",
      "company_scale",
      "growth_signal",
      "logistics_complexity",
      "pain_point",
    ]) {
      expect(values).toContain(canonical);
    }
    // Legacy aliases must not be offered for new input.
    for (const legacy of ["cargo_value", "growth", "complexity"]) {
      expect(values).not.toContain(legacy);
    }

    const labels = await select.locator("option").allTextContents();
    expect(labels).toContain("进口活跃度");
    expect(labels).toContain("货值潜力");

    await page.getByRole("button", { name: "English" }).click();
    const englishLabels = await page
      .getByLabel("Signal 1 kind")
      .locator("option")
      .allTextContents();
    expect(englishLabels).toContain("Import activity");
    expect(englishLabels).toContain("Cargo value potential");

    expect(guard.problems()).toEqual([]);
  });
});
