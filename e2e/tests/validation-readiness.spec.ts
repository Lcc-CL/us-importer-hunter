/**
 * Two things that had to be true before real salespeople touch this.
 *
 * 1. One contact and one sender. They used to be stored twice — once in the
 *    guided prompt, once in the advanced form — so filling one left the other
 *    still asking, and the analysis read whichever copy happened to be wired
 *    up. These tests hold the two views to a single source of truth.
 *
 * 2. The panel says which extractor ran. The Fake extractor quotes real
 *    sentences from the real page, so a demo run is convincing enough for a
 *    tester to judge "AI research quality" from a model that never ran.
 */

import { expect, test, type Page } from "@playwright/test";

import { COMPLETED_RUN, confirmResponse } from "../fixtures/research";
import { attachConsoleGuard } from "../utils/console-guard";
import { openAdvancedForm } from "../utils/form";
import { PROVIDER_MODE } from "../utils/env";

const API = "**/api/v1/research/**";

async function stubResearch(page: Page): Promise<{ analyzeBodies: unknown[] }> {
  const state = { analyzeBodies: [] as unknown[] };
  const confirm = confirmResponse(
    [{ kind: "import_activity", detail: "进口五金，来自亚洲" }],
    [{ source: "company_website", reference: "https://acme.example/" }],
  );

  await page.route("**/api/v1/mvp/prospects/analyze", async (route) => {
    state.analyzeBodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 500, body: "{}" });
  });

  await page.route(API, async (route) => {
    if (route.request().url().includes("/confirm")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(confirm),
      });
      return;
    }
    await route.fulfill({
      status: route.request().method() === "POST" ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify(COMPLETED_RUN),
    });
  });
  return state;
}

async function researchAndConfirm(page: Page): Promise<void> {
  await page.getByLabel("Research target name").fill("Acme Hardware");
  await page.getByLabel("Research target website").fill("https://acme.example");
  await page.getByRole("button", { name: "开始自动研究" }).click();
  await expect(page.getByTestId("research-result")).toBeVisible();
  await page.getByTestId("accept-0").click();
  await page.getByTestId("research-confirm").click();
}

test.describe("unified contact and sender state", () => {
  test("what the guided prompt collects appears in the advanced editor", async ({
    page,
  }) => {
    await stubResearch(page);
    await page.goto("/");
    await researchAndConfirm(page);

    await page.getByTestId("guided-contact-name").fill("Maria Chen");
    await page.getByTestId("guided-contact-email").fill("maria@acme.example");
    await page.getByTestId("guided-sender-name").fill("Alex Morgan");

    await openAdvancedForm(page);
    await expect(page.getByLabel("Contact name")).toHaveValue("Maria Chen");
    await expect(page.getByLabel("Contact email")).toHaveValue("maria@acme.example");
    await expect(page.getByLabel("Sender name")).toHaveValue("Alex Morgan");
  });

  test("a contact filled in the advanced editor is not asked for again", async ({
    page,
  }) => {
    await stubResearch(page);
    await page.goto("/");

    await openAdvancedForm(page);
    await page.getByLabel("Contact name").fill("Maria Chen");
    await page.getByLabel("Contact email").fill("maria@acme.example");
    await page.getByLabel("Contact source").fill("company_website");
    await page.getByLabel("Sender name").fill("Alex Morgan");
    await page.getByLabel("Sender company").fill("Harbor Bridge Logistics");
    await page.getByLabel("Value proposition").fill("我们简化亚洲到美国的进口运输。");

    await researchAndConfirm(page);

    // Everything it needs is already known, so it never stops to ask.
    await expect(page.getByTestId("guided-missing")).toHaveCount(0);
  });

  test("the sender syncs in both directions", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");

    await openAdvancedForm(page);
    await page.getByLabel("Sender company").fill("Harbor Bridge Logistics");

    await researchAndConfirm(page);
    await expect(page.getByTestId("guided-sender-company")).toHaveValue(
      "Harbor Bridge Logistics",
    );

    await page.getByTestId("guided-sender-company").fill("改名后的公司");
    await openAdvancedForm(page);
    await expect(page.getByLabel("Sender company")).toHaveValue("改名后的公司");
  });

  test("a partly filled contact only needs the rest", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");

    await openAdvancedForm(page);
    await page.getByLabel("Contact name").fill("Maria Chen");

    await researchAndConfirm(page);

    // The name survives; the prompt exists because reachability is still absent.
    await expect(page.getByTestId("guided-contact-name")).toHaveValue("Maria Chen");
    await expect(page.getByTestId("guided-continue")).toBeDisabled();

    await page.getByTestId("guided-contact-email").fill("maria@acme.example");
    await page.getByTestId("guided-contact-source").fill("company_website");
    await page.getByTestId("guided-sender-name").fill("Alex Morgan");
    await page.getByTestId("guided-sender-company").fill("Harbor Bridge Logistics");
    await page.getByTestId("guided-sender-value").fill("我们简化亚洲到美国的进口运输。");
    await expect(page.getByTestId("guided-continue")).toBeEnabled();
  });

  test("there is only one contact, not a copy per view", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");
    await researchAndConfirm(page);

    await page.getByTestId("guided-contact-name").fill("Maria Chen");
    await openAdvancedForm(page);
    await page.getByLabel("Contact name").fill("Maria Chen 修改后");

    // The edit replaced the value; it did not create a second contact.
    await expect(page.getByTestId("guided-contact-name")).toHaveValue("Maria Chen 修改后");
    await expect(page.getByLabel("Contact name")).toHaveCount(1);
  });

  test("the analysis carries whichever values were entered last", async ({ page }) => {
    const state = await stubResearch(page);
    await page.goto("/");
    await researchAndConfirm(page);

    await page.getByTestId("guided-contact-name").fill("Maria Chen");
    await page.getByTestId("guided-contact-email").fill("maria@acme.example");
    await page.getByTestId("guided-contact-source").fill("company_website");
    await page.getByTestId("guided-sender-name").fill("Alex Morgan");
    await page.getByTestId("guided-sender-company").fill("Harbor Bridge Logistics");
    await page.getByTestId("guided-sender-value").fill("初版价值主张");

    // A last-second correction in the other view must win.
    await openAdvancedForm(page);
    await page.getByLabel("Value proposition").fill("最终价值主张");

    await page.getByTestId("guided-continue").click();
    await expect.poll(() => state.analyzeBodies.length).toBe(1);

    const body = state.analyzeBodies[0] as {
      contact: { name: string };
      sender: { value_proposition: string };
    };
    expect(body.contact.name).toBe("Maria Chen");
    expect(body.sender.value_proposition).toBe("最终价值主张");
  });

  test("collapsing and reopening the advanced editor keeps the data", async ({
    page,
  }) => {
    await stubResearch(page);
    await page.goto("/");

    await openAdvancedForm(page);
    await page.getByLabel("Contact name").fill("Maria Chen");
    await page.getByTestId("advanced-form").locator("summary").click();
    await openAdvancedForm(page);

    await expect(page.getByLabel("Contact name")).toHaveValue("Maria Chen");
  });
});

test.describe("research provider notice", () => {
  test("demo mode is spelled out, not just coloured", async ({ page }) => {
    test.skip(PROVIDER_MODE !== "fake", "only meaningful on the fake stack");
    const guard = attachConsoleGuard(page);
    await page.goto("/");

    const notice = page.getByTestId("research-provider-fake");
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("演示模式");
    await expect(notice).toContainText("不能作为真实 AI 研究质量样本");
    await expect(page.getByTestId("research-provider-real")).toHaveCount(0);

    expect(guard.problems()).toEqual([]);
  });

  test("the notice is localized", async ({ page }) => {
    test.skip(PROVIDER_MODE !== "fake", "only meaningful on the fake stack");
    await page.goto("/");
    await page.getByRole("button", { name: "English" }).click();

    const notice = page.getByTestId("research-provider-fake");
    await expect(notice).toContainText("Demo mode");
    await expect(notice).toContainText("not a sample of real AI research quality");
  });

  test("real mode names the provider and model instead", async ({ page }) => {
    await page.route("**/api/v1/health/runtime", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          provider: "openai",
          model: "gpt-5.6-terra",
          research_provider: "openai",
          research_model: "gpt-5.6-terra",
          environment: "development",
        }),
      });
    });
    await page.goto("/");

    const real = page.getByTestId("research-provider-real");
    await expect(real).toBeVisible();
    await expect(real).toContainText("真实 AI");
    await expect(real).toContainText("gpt-5.6-terra");
    await expect(page.getByTestId("research-provider-fake")).toHaveCount(0);
  });

  test("the notice survives a reload", async ({ page }) => {
    test.skip(PROVIDER_MODE !== "fake", "only meaningful on the fake stack");
    await page.goto("/");
    await expect(page.getByTestId("research-provider-fake")).toBeVisible();

    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByTestId("research-provider-fake")).toBeVisible();
  });

  test("no credential or endpoint reaches the page", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("research-panel")).toBeVisible();

    const html = (await page.content()).toLowerCase();
    for (const forbidden of ["api_key", "apikey", "base_url", "sk-", "codeyu.shop"]) {
      expect(html).not.toContain(forbidden);
    }
  });
});
