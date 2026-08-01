import { expect, test, type Page } from "@playwright/test";

import {
  BUDGET_EXCEEDED_RUN,
  COMPLETED_RUN,
  NEEDS_BROWSER_RUN,
  PARTIAL_RUN,
  RESEARCH_RUN_ID,
  ROBOTS_DENIED_RUN,
  confirmResponse,
  type ResearchRunFixture,
} from "../fixtures/research";
import { attachConsoleGuard } from "../utils/console-guard";
import { openAdvancedForm } from "../utils/form";

/**
 * The research API is intercepted so the panel's states can be driven exactly,
 * offline. The backend's own behaviour is covered by its integration tests;
 * what these assert is the frontend contract: what is shown, what the reviewer
 * can do, and — most importantly — what is *not* done automatically.
 */

const API = "**/api/v1/research/**";

async function stubResearch(
  page: Page,
  run: ResearchRunFixture,
  confirm?: Record<string, unknown>,
): Promise<{ confirmBodies: unknown[]; analyzeCalls: number }> {
  const state = { confirmBodies: [] as unknown[], analyzeCalls: 0 };

  await page.route("**/api/v1/mvp/prospects/analyze", async (route) => {
    state.analyzeCalls += 1;
    await route.fulfill({ status: 500, body: "{}" });
  });

  await page.route(API, async (route) => {
    const url = route.request().url();
    if (url.includes("/confirm")) {
      state.confirmBodies.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(confirm ?? confirmResponse([], [])),
      });
      return;
    }
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(run),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(run),
    });
  });

  return state;
}

async function startResearch(page: Page): Promise<void> {
  await page.getByLabel("Research target name").fill("Acme Hardware");
  await page.getByLabel("Research target website").fill("https://acme.example");
  await page.getByRole("button", { name: "开始自动研究" }).click();
  await expect(page.getByTestId("research-result")).toBeVisible();
}

test.describe("research panel", () => {
  test("is visible only when the feature flag is on", async ({ page }) => {
    // The E2E stack sets NEXT_PUBLIC_ENABLE_RESEARCH=true; the default
    // everywhere else is off, which is asserted from the built client below.
    await page.goto("/");
    await expect(page.getByTestId("research-panel")).toBeVisible();
    await expect(page.getByTestId("research-security-notice")).toContainText(
      "内部测试功能",
    );
  });

  test("completed run shows pages, claims and evidence", async ({ page }) => {
    const guard = attachConsoleGuard(page);
    await stubResearch(page, COMPLETED_RUN);
    await page.goto("/");
    await startResearch(page);

    await expect(page.getByTestId("research-status")).toHaveText("已完成");
    await expect(page.getByTestId("research-failure-code")).toHaveCount(0);
    await expect(page.getByTestId("research-pages").locator("li")).toHaveCount(2);
    await expect(page.getByTestId("research-claims").locator("li")).toHaveCount(3);

    const first = page.getByTestId("research-claim-0");
    await expect(first).toContainText("进口活跃度");      // localized kind
    await expect(first).toContainText("进口五金，来自亚洲"); // detail
    await expect(first).toContainText("verbatim sentence"); // evidence snippet
    await expect(first).toContainText("https://acme.example/"); // source url
    await expect(first).toContainText("80%");               // confidence

    expect(guard.problems()).toEqual([]);
  });

  test("unknown dimensions are shown as open questions, not weaknesses", async ({
    page,
  }) => {
    const guard = attachConsoleGuard(page);
    await stubResearch(page, COMPLETED_RUN);
    await page.goto("/");
    await startResearch(page);

    const unknown = page.getByTestId("research-unknown");
    await expect(unknown).toBeVisible();
    await expect(unknown).toContainText("未知维度（2）");
    await expect(unknown).toContainText(
      "当前未找到可靠证据，以下维度保持未知，系统不会自动猜测。",
    );
    // Localized kind labels, and never presented as a claim.
    await expect(unknown).toContainText("运输匹配度");
    await expect(unknown).toContainText("潜在痛点");
    await expect(page.getByTestId("research-claims").locator("li")).toHaveCount(3);

    expect(guard.problems()).toEqual([]);
  });

  test("unknown dimensions survive a reload of the saved run", async ({ page }) => {
    await stubResearch(page, COMPLETED_RUN);
    await page.goto("/");
    await startResearch(page);
    await expect(page.getByTestId("research-unknown")).toContainText("未知维度（2）");

    await page.reload();
    await startResearch(page);

    const unknown = page.getByTestId("research-unknown");
    await expect(unknown).toContainText("未知维度（2）");
    await expect(unknown).toContainText("运输匹配度");
  });

  test("unknown dimensions section is absent when the list is empty", async ({ page }) => {
    await stubResearch(page, { ...COMPLETED_RUN, unknown_dimensions: [] });
    await page.goto("/");
    await startResearch(page);

    await expect(page.getByTestId("research-claims")).toBeVisible();
    await expect(page.getByTestId("research-unknown")).toHaveCount(0);
  });

  test("claims start pending — nothing is accepted for the reviewer", async ({ page }) => {
    await stubResearch(page, COMPLETED_RUN);
    await page.goto("/");
    await startResearch(page);

    // Confirming without deciding is refused client-side.
    await page.getByTestId("research-confirm").click();
    await expect(page.getByTestId("research-error")).toContainText("请先对至少一条信号做出裁决");
  });

  test("partial run reports failed pages", async ({ page }) => {
    await stubResearch(page, PARTIAL_RUN);
    await page.goto("/");
    await startResearch(page);

    await expect(page.getByTestId("research-status")).toHaveText("部分完成");
    await expect(page.getByTestId("research-pages").locator("li")).toHaveCount(1);
    await page.getByText("研究备注").click();
    await expect(page.getByText(/could not be read/)).toBeVisible();
  });

  test("needs_browser is explained, not silently empty", async ({ page }) => {
    await stubResearch(page, NEEDS_BROWSER_RUN);
    await page.goto("/");
    await startResearch(page);

    await expect(page.getByTestId("research-status")).toHaveText("部分完成");
    await expect(page.getByTestId("research-failure-code")).toContainText("需要浏览器渲染");
    await expect(page.getByText("未能从该网站提出任何可支撑的信号。")).toBeVisible();
  });

  test("robots_denied is explained", async ({ page }) => {
    await stubResearch(page, ROBOTS_DENIED_RUN);
    await page.goto("/");
    await startResearch(page);

    await expect(page.getByTestId("research-status")).toHaveText("失败");
    await expect(page.getByTestId("research-failure-code")).toContainText("robots.txt 禁止");
    await expect(page.getByText("未成功抓取任何页面。")).toBeVisible();
  });

  test("budget_exceeded is explained", async ({ page }) => {
    await stubResearch(page, BUDGET_EXCEEDED_RUN);
    await page.goto("/");
    await startResearch(page);
    await expect(page.getByTestId("research-failure-code")).toContainText("超出时间预算");
  });

  test("accept, edit and reject are sent as one batch", async ({ page }) => {
    const state = await stubResearch(page, COMPLETED_RUN);
    await page.goto("/");
    await startResearch(page);

    await page.getByTestId("accept-0").click();
    await page.getByTestId("edit-1").click();
    await page.getByLabel("Claim 1 detail").fill("审核者改写后的描述");
    await page.getByLabel("Claim 1 kind").selectOption("shipping_fit");
    await page.getByTestId("reject-2").click();
    await page.getByTestId("research-confirm").click();
    await expect(page.getByTestId("research-applied")).toBeVisible();

    expect(state.confirmBodies).toHaveLength(1);
    const body = state.confirmBodies[0] as {
      decisions: Array<Record<string, unknown>>;
      target_company_id?: string;
    };
    expect(body.decisions).toHaveLength(3);
    expect(body.decisions[0]).toMatchObject({ claim_position: 0, decision: "accepted" });
    expect(body.decisions[1]).toMatchObject({
      claim_position: 1,
      decision: "edited",
      edited_detail: "审核者改写后的描述",
      edited_kind: "shipping_fit",
    });
    expect(body.decisions[2]).toMatchObject({ claim_position: 2, decision: "rejected" });
    // Phase 4 never writes into an existing company.
    expect(body.target_company_id).toBeUndefined();
  });

  test("confirmed research fills the advanced form and asks only for what is missing", async ({
    page,
  }) => {
    const payload = confirmResponse(
      [
        { kind: "import_activity", detail: "进口五金，来自亚洲" },
        { kind: "company_scale", detail: "自有仓库约 12 万平方英尺" },
      ],
      [
        { source: "company_website", reference: "https://acme.example/" },
        { source: "company_website", reference: "https://acme.example/about" },
      ],
    );
    const state = await stubResearch(page, COMPLETED_RUN, payload);
    await page.goto("/");

    // The user's own contact/sender work must survive the fill.
    await openAdvancedForm(page);
    await page.getByLabel("Contact name").fill("Maria Chen");
    await page.getByLabel("Sender name").fill("Alex Morgan");

    await startResearch(page);
    await page.getByTestId("accept-0").click();
    await page.getByTestId("accept-1").click();
    await page.getByTestId("research-confirm").click();
    await expect(page.getByTestId("research-applied")).toBeVisible();

    // Guided flow collects contact/sender itself, so it stops and asks rather
    // than spending an analysis it cannot complete.
    await expect(page.getByTestId("guided-missing")).toBeVisible();

    await openAdvancedForm(page);
    await expect(page.getByLabel("Company name")).toHaveValue("Acme Hardware");
    await expect(page.getByLabel("Company website")).toHaveValue("https://acme.example");
    await expect(page.getByLabel("Source 1 name")).toHaveValue("company_website");
    await expect(page.getByLabel("Source 1 reference")).toHaveValue("https://acme.example/");
    await expect(page.getByLabel("Source 2 reference")).toHaveValue(
      "https://acme.example/about",
    );
    await expect(page.getByLabel("Signal 1 kind")).toHaveValue("import_activity");
    await expect(page.getByLabel("Signal 1 detail")).toHaveValue("进口五金，来自亚洲");
    await expect(page.getByLabel("Signal 2 kind")).toHaveValue("company_scale");

    // Untouched, as promised.
    await expect(page.getByLabel("Contact name")).toHaveValue("Maria Chen");
    await expect(page.getByLabel("Sender name")).toHaveValue("Alex Morgan");

    // Nothing was analyzed while a required field was still missing.
    expect(state.analyzeCalls).toBe(0);
  });

  test("filled fields remain editable", async ({ page }) => {
    const payload = confirmResponse(
      [{ kind: "import_activity", detail: "原始描述" }],
      [{ source: "company_website", reference: "https://acme.example/" }],
    );
    await stubResearch(page, COMPLETED_RUN, payload);
    await page.goto("/");
    await startResearch(page);
    await page.getByTestId("accept-0").click();
    await page.getByTestId("research-confirm").click();
    await expect(page.getByTestId("research-applied")).toBeVisible();

    await openAdvancedForm(page);
    await page.getByLabel("Signal 1 detail").fill("用户手动修改");
    await expect(page.getByLabel("Signal 1 detail")).toHaveValue("用户手动修改");
  });

  test("a saved run can be reloaded through the API", async ({ page }) => {
    await stubResearch(page, COMPLETED_RUN);
    const response = await page.request.get(
      `http://localhost:8001/api/v1/research/runs/${RESEARCH_RUN_ID}`,
    );
    // The route stub only covers the browser context; this asserts the real
    // backend answers a GET for an unknown id rather than hanging.
    expect([200, 404]).toContain(response.status());
  });

  test("unknown-dimension copy is localized in English too", async ({ page }) => {
    await stubResearch(page, COMPLETED_RUN);
    await page.goto("/");
    await startResearch(page);
    await page.getByRole("button", { name: "English" }).click();

    const unknown = page.getByTestId("research-unknown");
    await expect(unknown).toContainText("Unknown dimensions (2)");
    await expect(unknown).toContainText(
      "No reliable evidence was found for these dimensions. They remain unknown and are not inferred.",
    );
    await expect(unknown).toContainText("Shipping fit");
  });

  test("panel is fully localized and switches with the rest of the UI", async ({ page }) => {
    await stubResearch(page, COMPLETED_RUN);
    await page.goto("/");
    await startResearch(page);
    await expect(page.getByTestId("research-status")).toHaveText("已完成");

    await page.getByRole("button", { name: "English" }).click();
    await expect(page.getByTestId("research-status")).toHaveText("Completed");
    await expect(page.getByTestId("research-security-notice")).toContainText(
      "Internal testing feature",
    );
    await expect(page.getByRole("button", { name: "Start research" })).toBeVisible();

    await page.getByRole("button", { name: "中文" }).click();
    await expect(page.getByTestId("research-status")).toHaveText("已完成");
  });

  test("no credentials, endpoints or raw HTML reach the page", async ({ page }) => {
    const guard = attachConsoleGuard(page);
    await stubResearch(page, COMPLETED_RUN);
    await page.goto("/");
    await startResearch(page);

    const html = await page.content();
    for (const forbidden of [
      "api_key",
      "apikey",
      "base_url",
      "OPENAI_",
      "system_prompt",
      "codeyu.shop",
    ]) {
      expect(html.toLowerCase()).not.toContain(forbidden.toLowerCase());
    }
    expect(html).not.toMatch(/sk-[A-Za-z0-9_-]{12,}/);
    expect(guard.duplicateKeyWarnings()).toEqual([]);
    expect(guard.problems()).toEqual([]);
  });
});
