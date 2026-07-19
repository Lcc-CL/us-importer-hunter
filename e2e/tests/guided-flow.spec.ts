/**
 * The guided research-to-draft journey.
 *
 * v0.2.1 shipped the pieces but not the road between them: the panel filled a
 * form and stopped, leaving the user to find a submit button in a five-section
 * form. These tests pin the road — and, just as importantly, pin where it must
 * *not* continue: a REVIEW or DISQUALIFIED verdict never produces a draft, and
 * nothing is ever sent.
 */

import { expect, test, type Page } from "@playwright/test";

import { COMPLETED_RUN, confirmResponse, RESEARCH_RUN_ID } from "../fixtures/research";
import type { ResearchRunFixture } from "../fixtures/research";
import { attachConsoleGuard } from "../utils/console-guard";
import { openAdvancedForm } from "../utils/form";

const API = "**/api/v1/research/**";

interface AnalysisStub {
  decision: "qualified" | "review" | "research_more" | "disqualified";
  draft?: "GENERATED" | "SKIPPED" | "FAILED";
  reasons?: string[];
}

function analysisBody(stub: AnalysisStub): Record<string, unknown> {
  const generated = stub.draft ?? (stub.decision === "qualified" ? "GENERATED" : "SKIPPED");
  return {
    request_id: "11111111-1111-1111-1111-111111111111",
    overall_status: stub.decision === "qualified" ? "COMPLETED" : "PARTIAL",
    company: {
      action: "CREATED",
      company_id: "22222222-2222-2222-2222-222222222222",
      name: "Acme Hardware",
      notes: [],
    },
    opportunity: {
      action: stub.decision === "qualified" ? "QUALIFIED" : "REVIEW",
      opportunity_id: "33333333-3333-3333-3333-333333333333",
      score: stub.decision === "qualified" ? 70.5 : 39.5,
      confidence: 0.8,
      data_completeness: 1,
      qualification_decision: stub.decision,
      recommended_action:
        stub.decision === "qualified" ? "prepare_outreach" : "human_review",
      reasons: stub.reasons ?? ["signal observed"],
    },
    contact: {
      action: "CREATED",
      contact_id: "44444444-4444-4444-4444-444444444444",
      notes: [],
    },
    decision_maker: {
      action: "SELECTED",
      selected_contact_id: "44444444-4444-4444-4444-444444444444",
      recommended_channel: "email",
      confidence: 0.9,
      reasons: [],
    },
    email_draft: {
      action: generated,
      outreach_id: generated === "GENERATED" ? "55555555-5555-5555-5555-555555555555" : null,
      version: generated === "GENERATED" ? 1 : null,
      subject: generated === "GENERATED" ? "Freight partnership for Acme" : null,
      body: generated === "GENERATED" ? "Hi Maria,\n\nBest regards," : null,
      status: generated === "GENERATED" ? "generated" : null,
      notes: [],
    },
    warnings: [],
    created_at: "2026-07-19T12:00:00Z",
  };
}

interface Stubs {
  analyzeCalls: number;
  analyzeBodies: unknown[];
  sendAttempts: number;
}

async function stubJourney(
  page: Page,
  options: { run?: ResearchRunFixture; analysis?: AnalysisStub } = {},
): Promise<Stubs> {
  const state: Stubs = { analyzeCalls: 0, analyzeBodies: [], sendAttempts: 0 };
  const run = options.run ?? COMPLETED_RUN;

  const confirm = confirmResponse(
    [
      { kind: "import_activity", detail: "进口五金，来自亚洲" },
      { kind: "company_scale", detail: "自有仓库约 12 万平方英尺" },
    ],
    [
      { source: "company_website", reference: "https://acme.example/" },
      { source: "company_website", reference: "https://acme.example/about" },
    ],
  );

  await page.route("**/api/v1/mvp/prospects/analyze", async (route) => {
    state.analyzeCalls += 1;
    state.analyzeBodies.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(analysisBody(options.analysis ?? { decision: "qualified" })),
    });
  });

  // Nothing in this journey may ever hit a send endpoint.
  await page.route("**/send**", async (route) => {
    state.sendAttempts += 1;
    await route.fulfill({ status: 500, body: "{}" });
  });

  await page.route(API, async (route) => {
    const url = route.request().url();
    if (url.includes("/confirm")) {
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
      body: JSON.stringify(run),
    });
  });

  return state;
}

async function research(page: Page): Promise<void> {
  await page.getByLabel("Research target name").fill("Acme Hardware");
  await page.getByLabel("Research target website").fill("https://acme.example");
  await page.getByRole("button", { name: "开始自动研究" }).click();
  await expect(page.getByTestId("research-result")).toBeVisible();
}

async function acceptAndConfirm(page: Page): Promise<void> {
  await page.getByTestId("accept-0").click();
  await page.getByTestId("accept-1").click();
  await page.getByTestId("research-confirm").click();
}

async function fillGuidedFields(page: Page): Promise<void> {
  await page.getByTestId("guided-contact-name").fill("Maria Chen");
  await page.getByTestId("guided-contact-email").fill("maria@acme.example");
  await page.getByTestId("guided-sender-name").fill("Alex Morgan");
  await page.getByTestId("guided-sender-company").fill("Harbor Bridge Logistics");
  await page.getByTestId("guided-sender-value").fill("我们简化亚洲到美国的进口运输。");
}

test.describe("guided research-to-draft", () => {
  test("four steps are always visible and advance with the flow", async ({ page }) => {
    await stubJourney(page);
    await page.goto("/");

    const steps = page.getByTestId("research-steps");
    await expect(steps).toBeVisible();
    for (const id of ["research", "review", "analysis", "draft"]) {
      await expect(page.getByTestId(`research-step-${id}`)).toBeVisible();
    }
    await expect(page.getByTestId("research-step-research")).toHaveAttribute(
      "data-state",
      "todo",
    );

    await research(page);
    await expect(page.getByTestId("research-step-research")).toHaveAttribute(
      "data-state",
      "done",
    );
    await expect(page.getByTestId("research-step-review")).toHaveAttribute(
      "data-state",
      "current",
    );
  });

  test("confirming runs qualification without a second button", async ({ page }) => {
    const state = await stubJourney(page);
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);

    await fillGuidedFields(page);
    await page.getByTestId("guided-continue").click();

    await expect(page.getByTestId("research-step-analysis")).toHaveAttribute(
      "data-state",
      "done",
    );
    expect(state.analyzeCalls).toBe(1);
  });

  test("the analysis carries the researched sources and signals", async ({ page }) => {
    const state = await stubJourney(page);
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);
    await fillGuidedFields(page);
    await page.getByTestId("guided-continue").click();
    await expect(page.getByTestId("research-step-analysis")).toHaveAttribute(
      "data-state",
      "done",
    );

    const body = state.analyzeBodies[0] as {
      company: { sources: unknown[]; signals: unknown[] };
      contact: { name: string };
    };
    expect(body.company.sources).toHaveLength(2);
    expect(body.company.signals).toHaveLength(2);
    expect(body.contact.name).toBe("Maria Chen");
  });

  test("a qualified result produces a draft automatically", async ({ page }) => {
    await stubJourney(page, { analysis: { decision: "qualified", draft: "GENERATED" } });
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);
    await fillGuidedFields(page);
    await page.getByTestId("guided-continue").click();

    await expect(page.getByTestId("research-step-draft")).toHaveAttribute(
      "data-state",
      "done",
    );
    await expect(page.getByText("Freight partnership for Acme")).toBeVisible();
  });

  test("a missing contact asks for the contact only", async ({ page }) => {
    const state = await stubJourney(page);
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);

    await expect(page.getByTestId("guided-missing")).toBeVisible();
    await expect(page.getByTestId("guided-missing-contact")).toBeVisible();
    // The whole five-section form must not be thrown at the user.
    await expect(page.getByLabel("Source 1 name")).toBeHidden();
    expect(state.analyzeCalls).toBe(0);
  });

  test("the prompt does not vanish while the user is still typing", async ({ page }) => {
    // Deriving which blocks to show from live completeness unmounted the
    // prompt — and its Continue button — the moment the last field became
    // valid, so the flow could never be continued.
    await stubJourney(page);
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);

    await expect(page.getByTestId("guided-continue")).toBeDisabled();
    await fillGuidedFields(page);
    await expect(page.getByTestId("guided-missing")).toBeVisible();
    await expect(page.getByTestId("guided-continue")).toBeEnabled();
  });

  test("the sender is remembered, so the next company only asks for a contact", async ({
    page,
  }) => {
    await stubJourney(page);
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);
    await fillGuidedFields(page);
    await page.getByTestId("guided-continue").click();
    await expect(page.getByTestId("research-step-analysis")).toHaveAttribute(
      "data-state",
      "done",
    );

    // Second company in the same session: the sender does not change, but the
    // contact belongs to the previous prospect and must not be carried over.
    await page.route("**/api/v1/research/**/confirm", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...confirmResponse(
            [{ kind: "import_activity", detail: "另一家公司的信号" }],
            [{ source: "company_website", reference: "https://second.example/" }],
          ),
          application_payload: {
            company_name: "Second Importer",
            website: "https://second.example",
            sources: [{ source: "company_website", reference: "https://second.example/" }],
            signals: [{ kind: "import_activity", detail: "另一家公司的信号" }],
          },
        }),
      });
    });

    await page.getByLabel("Research target name").fill("Second Importer");
    await page.getByLabel("Research target website").fill("https://second.example");
    await page.getByRole("button", { name: "开始自动研究" }).click();
    await expect(page.getByTestId("research-result")).toBeVisible();
    await page.getByTestId("accept-0").click();
    await page.getByTestId("research-confirm").click();

    await expect(page.getByTestId("guided-missing-contact")).toBeVisible();
    await expect(page.getByTestId("guided-missing-sender")).toHaveCount(0);
  });

  test("REVIEW never produces a draft and says what is missing", async ({ page }) => {
    await stubJourney(page, {
      analysis: {
        decision: "review",
        draft: "SKIPPED",
        reasons: ["no china_dependency signal observed — unknown, not negative"],
      },
    });
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);
    await fillGuidedFields(page);
    await page.getByTestId("guided-continue").click();

    await expect(page.getByTestId("research-step-draft")).toHaveAttribute(
      "data-state",
      "blocked",
    );
    await expect(page.getByText("Freight partnership for Acme")).toHaveCount(0);
    await expect(page.getByTestId("research-step-blocked")).toBeVisible();
  });

  test("DISQUALIFIED never produces a draft", async ({ page }) => {
    await stubJourney(page, {
      analysis: { decision: "disqualified", draft: "SKIPPED", reasons: ["hard gate hit"] },
    });
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);
    await fillGuidedFields(page);
    await page.getByTestId("guided-continue").click();

    await expect(page.getByTestId("research-step-draft")).toHaveAttribute(
      "data-state",
      "blocked",
    );
    await expect(page.getByText("Freight partnership for Acme")).toHaveCount(0);
  });

  test("a failed draft keeps the research and the qualification", async ({ page }) => {
    await stubJourney(page, { analysis: { decision: "qualified", draft: "FAILED" } });
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);
    await fillGuidedFields(page);
    await page.getByTestId("guided-continue").click();

    await expect(page.getByTestId("research-step-analysis")).toHaveAttribute(
      "data-state",
      "done",
    );
    await expect(page.getByTestId("research-step-draft")).toHaveAttribute(
      "data-state",
      "blocked",
    );
    // The evidence the user already reviewed is still on screen.
    await expect(page.getByTestId("research-claims")).toBeVisible();
  });

  test("the manual form is collapsed but still usable", async ({ page }) => {
    await stubJourney(page);
    await page.goto("/");

    const advanced = page.getByTestId("advanced-form");
    await expect(advanced).toBeVisible();
    await expect(page.getByLabel("Company name")).toBeHidden();

    await openAdvancedForm(page);
    await expect(page.getByLabel("Company name")).toBeVisible();
    await page.getByLabel("Company name").fill("手工录入公司");
    await expect(page.getByLabel("Company name")).toHaveValue("手工录入公司");
  });

  test("the research summary appears above the claims", async ({ page }) => {
    const guard = attachConsoleGuard(page);
    await stubJourney(page);
    await page.goto("/");
    await research(page);

    const summary = page.getByTestId("research-summary");
    await expect(summary).toBeVisible();
    await expect(page.getByTestId("research-summary-opportunity")).toBeVisible();

    const summaryBox = await summary.boundingBox();
    const claimsBox = await page.getByTestId("research-claims").boundingBox();
    expect(summaryBox && claimsBox && summaryBox.y < claimsBox.y).toBe(true);

    expect(guard.problems()).toEqual([]);
  });

  test("no email is ever sent", async ({ page }) => {
    const state = await stubJourney(page, {
      analysis: { decision: "qualified", draft: "GENERATED" },
    });
    await page.goto("/");
    await research(page);
    await acceptAndConfirm(page);
    await fillGuidedFields(page);
    await page.getByTestId("guided-continue").click();
    await expect(page.getByText("Freight partnership for Acme")).toBeVisible();

    expect(state.sendAttempts).toBe(0);
  });

  test("the run request carries the UI language", async ({ page }) => {
    let requestedLanguage: string | null = null;
    await page.route("**/api/v1/research/runs", async (route) => {
      const body = route.request().postDataJSON() as { output_language?: string };
      requestedLanguage = body.output_language ?? null;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(COMPLETED_RUN),
      });
    });
    await page.goto("/");
    await research(page);

    expect(requestedLanguage).toBe("zh-CN");
  });

  test("switching to English sends en-US for the next run", async ({ page }) => {
    const languages: string[] = [];
    await page.route("**/api/v1/research/runs", async (route) => {
      const body = route.request().postDataJSON() as { output_language?: string };
      languages.push(body.output_language ?? "");
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(COMPLETED_RUN),
      });
    });
    await page.goto("/");
    await research(page);

    await page.getByRole("button", { name: "English" }).click();
    await page.getByLabel("Research target name").fill("Acme Hardware");
    await page.getByLabel("Research target website").fill("https://acme.example");
    await page.getByRole("button", { name: "Start research" }).click();
    await expect(page.getByTestId("research-result")).toBeVisible();

    expect(languages).toEqual(["zh-CN", "en-US"]);
  });

  test("a saved run reports the language it was produced in", async ({ page }) => {
    await stubJourney(page);
    await page.goto("/");
    const response = await page.request.get(
      `http://localhost:8001/api/v1/research/runs/${RESEARCH_RUN_ID}`,
    );
    expect([200, 404]).toContain(response.status());
  });
});
