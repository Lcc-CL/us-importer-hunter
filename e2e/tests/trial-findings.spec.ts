/**
 * The three things the internal trial found.
 *
 * 1. The sender vanished on every reload, so it was retyped for every company.
 * 2. Valid purchasing contacts were not always chosen, and the screen said
 *    nothing about why.
 * 3. All three companies stopped at REVIEW with no explanation, so a
 *    salesperson read "REVIEW" as "weak prospect" when the real cause was that
 *    a website cannot prove customs activity.
 */

import { expect, test, type Page } from "@playwright/test";

import { COMPLETED_RUN, confirmResponse } from "../fixtures/research";
import { attachConsoleGuard } from "../utils/console-guard";
import { openAdvancedForm } from "../utils/form";

const API = "**/api/v1/research/**";
const SENDER_KEY = "sender_profile_v1";

async function stubResearch(page: Page): Promise<void> {
  const confirm = confirmResponse(
    [{ kind: "import_activity", detail: "进口五金，来自亚洲" }],
    [{ source: "company_website", reference: "https://acme.example/" }],
  );
  await page.route("**/api/v1/mvp/prospects/analyze", async (route) => {
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
}

async function researchAndConfirm(page: Page): Promise<void> {
  await page.getByLabel("Research target name").fill("Acme Hardware");
  await page.getByLabel("Research target website").fill("https://acme.example");
  await page.getByRole("button", { name: "开始自动研究" }).click();
  await expect(page.getByTestId("research-result")).toBeVisible();
  await page.getByTestId("accept-0").click();
  await page.getByTestId("research-confirm").click();
}

function storedProfile(page: Page): Promise<string | null> {
  return page.evaluate((key) => window.localStorage.getItem(key), SENDER_KEY);
}

test.describe("sender profile persistence", () => {
  test("starts empty", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");
    expect(await storedProfile(page)).toBeNull();

    await openAdvancedForm(page);
    await expect(page.getByLabel("Sender name")).toHaveValue("");
  });

  test("is written as the user types", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");
    await openAdvancedForm(page);
    await page.getByLabel("Sender name").fill("Alex Morgan");
    await page.getByLabel("Sender company").fill("Harbor Bridge Logistics");
    await page.getByLabel("Value proposition").fill("我们简化亚洲到美国的进口运输。");

    await expect.poll(async () => storedProfile(page)).toContain("Alex Morgan");
    const raw = (await storedProfile(page)) ?? "";
    expect(raw).toContain("sender_company");
    expect(raw).toContain("value_proposition");
  });

  test("comes back after a reload", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");
    await openAdvancedForm(page);
    await page.getByLabel("Sender name").fill("Alex Morgan");
    await page.getByLabel("Sender company").fill("Harbor Bridge Logistics");
    await page.getByLabel("Value proposition").fill("我们简化亚洲到美国的进口运输。");
    await expect.poll(async () => storedProfile(page)).toContain("Alex Morgan");

    await page.reload({ waitUntil: "networkidle" });
    await openAdvancedForm(page);
    await expect(page.getByLabel("Sender name")).toHaveValue("Alex Morgan");
    await expect(page.getByLabel("Value proposition")).toHaveValue(
      "我们简化亚洲到美国的进口运输。",
    );
  });

  test("is reused for the next company", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");
    await openAdvancedForm(page);
    await page.getByLabel("Sender name").fill("Alex Morgan");
    await page.getByLabel("Sender company").fill("Harbor Bridge Logistics");
    await page.getByLabel("Value proposition").fill("价值主张");
    await expect.poll(async () => storedProfile(page)).toContain("Alex Morgan");

    await page.reload({ waitUntil: "networkidle" });
    await researchAndConfirm(page);

    // Only the contact is asked for; the sender is already known.
    await expect(page.getByTestId("guided-missing-contact")).toBeVisible();
    await expect(page.getByTestId("guided-missing-sender")).toHaveCount(0);
  });

  test("an edit made this session is not reverted by the saved profile", async ({
    page,
  }) => {
    await stubResearch(page);
    await page.goto("/");
    // Seeded once, not through addInitScript: that would rewrite storage on
    // every navigation and mask whether the app persisted the edit.
    await page.evaluate(
      ([key, value]) => window.localStorage.setItem(key, value),
      [
        SENDER_KEY,
        JSON.stringify({
          sender_name: "保存的姓名",
          sender_company: "保存的公司",
          value_proposition: "保存的价值主张",
        }),
      ] as const,
    );

    await page.reload({ waitUntil: "networkidle" });
    await openAdvancedForm(page);
    await expect(page.getByLabel("Sender company")).toHaveValue("保存的公司");

    // A deliberate edit must win over the stored value, not be reverted.
    await page.getByLabel("Sender company").fill("本次新公司");
    await expect.poll(async () => storedProfile(page)).toContain("本次新公司");

    await page.reload({ waitUntil: "networkidle" });
    await openAdvancedForm(page);
    await expect(page.getByLabel("Sender company")).toHaveValue("本次新公司");
    await expect(page.getByLabel("Sender name")).toHaveValue("保存的姓名");
  });

  test("clearing removes it from the browser", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");
    await openAdvancedForm(page);
    await page.getByLabel("Sender name").fill("Alex Morgan");
    await page.getByLabel("Sender company").fill("Harbor Bridge Logistics");
    await page.getByLabel("Value proposition").fill("价值主张");
    await expect.poll(async () => storedProfile(page)).toContain("Alex Morgan");

    await researchAndConfirm(page);
    await page.getByTestId("sender-clear").click();

    await expect.poll(async () => storedProfile(page)).toBeNull();
    await openAdvancedForm(page);
    await expect(page.getByLabel("Sender name")).toHaveValue("");
  });

  test("collapsing the advanced editor does not lose it", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");
    await openAdvancedForm(page);
    await page.getByLabel("Sender name").fill("Alex Morgan");

    await page.getByTestId("advanced-form").locator("summary").click();
    await openAdvancedForm(page);
    await expect(page.getByLabel("Sender name")).toHaveValue("Alex Morgan");
  });

  test("the contact is never stored as a global profile", async ({ page }) => {
    await stubResearch(page);
    await page.goto("/");
    await openAdvancedForm(page);
    await page.getByLabel("Contact name").fill("Maria Chen");
    await page.getByLabel("Contact email").fill("maria@acme.example");
    await page.getByLabel("Sender name").fill("Alex Morgan");
    await expect.poll(async () => storedProfile(page)).toContain("Alex Morgan");

    // A contact belongs to one company; it must never become a default.
    const raw = (await storedProfile(page)) ?? "";
    expect(raw).not.toContain("Maria Chen");
    expect(raw).not.toContain("maria@acme.example");

    const everything = await page.evaluate(() => JSON.stringify(window.localStorage));
    expect(everything).not.toContain("maria@acme.example");
    expect(everything.toLowerCase()).not.toContain("api_key");
    expect(everything.toLowerCase()).not.toContain("base_url");
  });
});

const REVIEW_DETAIL = {
    company: {
      company_id: "22222222-2222-2222-2222-222222222222",
      name: "Acme Hardware",
      website: "https://acme.example",
      verified: false,
      sources: ["company_website"],
      signals: ["import_activity: 进口五金"],
    },
    latest_assessment: {
      opportunity_id: "33333333-3333-3333-3333-333333333333",
      score: 44,
      confidence: 0.35,
      data_completeness: 0.65,
      qualification_decision: "review",
      recommended_action: "human_review",
      reasons: ["no china_dependency signal observed — unknown, not negative"],
      scoring_version: "mvp-explainable-scoring-v1",
      policy_version: "mvp-qualification-policy-v1",
      assessed_at: "2026-07-19T12:00:00Z",
      explanation: {
        dimensions: [
          {
            dimension: "shipping_fit",
            status: "assessed",
            weight: 15,
            earned_score: 12,
            score_contribution: 0.27,
            evidence_status: "present",
            unknown_reason: null,
            needs_import_evidence: false,
            reasons: ["signal observed"],
          },
          {
            dimension: "import_activity",
            status: "unknown",
            weight: 20,
            earned_score: 0,
            score_contribution: 0,
            evidence_status: "absent",
            unknown_reason: "unknown",
            needs_import_evidence: true,
            reasons: ["no import_activity signal observed — unknown, not negative"],
          },
          {
            dimension: "china_dependency",
            status: "unknown",
            weight: 15,
            earned_score: 0,
            score_contribution: 0,
            evidence_status: "absent",
            unknown_reason: "unknown",
            needs_import_evidence: true,
            reasons: ["no china_dependency signal observed — unknown, not negative"],
          },
        ],
        evidence_obtained: ["shipping_fit"],
        missing_key_evidence: ["import_activity", "china_dependency"],
        import_evidence_missing: ["import_activity", "china_dependency"],
        unreachable_weight: 35,
        hard_gate_hits: [],
        next_action: "IMPORT_EVIDENCE_REQUIRED",
      },
    },
    qualification_decision: "review",
    contacts: [],
    decision_maker: { selected_contact_id: null, rankings: [] },
    latest_email_draft: null,
    draft_history: [],
  };

test.describe("qualification explanation", () => {
  async function stubDetail(page: Page): Promise<void> {
    await page.route("**/api/v1/mvp/prospects/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(REVIEW_DETAIL),
      });
    });
  }

  test("separates obtained evidence from what is still missing", async ({ page }) => {
    await stubDetail(page);
    await page.goto("/?company_id=22222222-2222-2222-2222-222222222222");

    const card = page.getByTestId("qualification-explanation");
    await expect(card).toBeVisible();
    await expect(page.getByTestId("qual-obtained")).toContainText("运输匹配度");
    await expect(page.getByTestId("qual-missing")).toContainText("进口活跃度");
    await expect(page.getByTestId("qual-missing")).toContainText("中国供应链依赖");
  });

  test("says the gap is the source, not the company", async ({ page }) => {
    await stubDetail(page);
    await page.goto("/?company_id=22222222-2222-2222-2222-222222222222");

    const notice = page.getByTestId("qual-import-notice");
    await expect(notice).toContainText("官网研究无法可靠证明该进口维度");
    await expect(notice).toContainText("不代表该公司是低质量客户");
    await expect(notice).toContainText("35");
  });

  test("recommends import evidence without calling it qualified", async ({ page }) => {
    await stubDetail(page);
    await page.goto("/?company_id=22222222-2222-2222-2222-222222222222");

    await expect(page.getByTestId("qual-next-action")).toContainText("补充进口数据证据");
    // The verdict itself is untouched.
    await expect(page.getByTestId("qualification-explanation")).not.toContainText(
      "QUALIFIED",
    );
    await expect(page.getByTestId("qual-why-review")).toBeVisible();
  });

  test("the explanation is localized", async ({ page }) => {
    await stubDetail(page);
    await page.goto("/?company_id=22222222-2222-2222-2222-222222222222");
    await page.getByRole("button", { name: "English" }).click();

    await expect(page.getByTestId("qual-obtained")).toContainText("Evidence obtained");
    await expect(page.getByTestId("qual-import-notice")).toContainText(
      "does not mean this is a low-quality prospect",
    );
  });
});

test.describe("company source display", () => {
  /** A detail payload whose sources repeat — the shape that crashed the page. */
  function detailWithSources(sources: unknown[]): Record<string, unknown> {
    return {
      ...REVIEW_DETAIL,
      company: { ...REVIEW_DETAIL.company, sources },
    };
  }

  async function stubDetailWith(page: Page, sources: unknown[]): Promise<void> {
    await page.route("**/api/v1/mvp/prospects/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(detailWithSources(sources)),
      });
    });
  }

  test("one site seen twice renders once, with a count", async ({ page }) => {
    const guard = attachConsoleGuard(page);
    await stubDetailWith(page, [{ source: "company_website", reference_count: 2 }]);
    await page.goto("/?company_id=22222222-2222-2222-2222-222222222222");

    const chips = page.getByTestId("company-sources").locator("span");
    await expect(chips).toHaveCount(1);
    await expect(chips.first()).toHaveText("company_website × 2");

    expect(guard.duplicateKeyWarnings()).toEqual([]);
    expect(guard.problems()).toEqual([]);
  });

  test("distinct sources are all shown", async ({ page }) => {
    const guard = attachConsoleGuard(page);
    await stubDetailWith(page, [
      { source: "importyeti", reference_count: 1 },
      { source: "company_website", reference_count: 3 },
    ]);
    await page.goto("/?company_id=22222222-2222-2222-2222-222222222222");

    const chips = page.getByTestId("company-sources").locator("span");
    await expect(chips).toHaveCount(2);
    await expect(chips.nth(0)).toHaveText("importyeti");
    await expect(chips.nth(1)).toHaveText("company_website × 3");

    expect(guard.problems()).toEqual([]);
  });

  test("a legacy payload that still repeats a name cannot crash the page", async ({
    page,
  }) => {
    // Rows written before the API deduplicated, or an older deployment.
    const guard = attachConsoleGuard(page);
    await stubDetailWith(page, [
      { source: "company_website", reference_count: 1 },
      { source: "company_website", reference_count: 1 },
      { source: "importyeti", reference_count: 1 },
    ]);
    await page.goto("/?company_id=22222222-2222-2222-2222-222222222222");

    const chips = page.getByTestId("company-sources").locator("span");
    await expect(chips).toHaveCount(2);
    await expect(chips.first()).toHaveText("company_website × 2");

    expect(guard.duplicateKeyWarnings()).toEqual([]);
    expect(guard.problems()).toEqual([]);
  });
});
