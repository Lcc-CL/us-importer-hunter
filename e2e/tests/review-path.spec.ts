import { expect, test } from "@playwright/test";

import { REVIEW_EXPECTATION, reviewProspect } from "../fixtures/prospects";
import { attachConsoleGuard } from "../utils/console-guard";
import { draftCountForCompany, latestAssessmentForCompany } from "../utils/db";
import { PROVIDER_MODE } from "../utils/env";
import { companyIdFromUrl, fillProspectForm, submitAnalysis } from "../utils/form";

test.describe("review path", () => {
  test("thin evidence → REVIEW, no draft, explainable reasons shown", async ({
    page,
  }) => {
    test.skip(PROVIDER_MODE !== "fake", "fake-provider run only");
    const guard = attachConsoleGuard(page);
    const payload = reviewProspect();

    await page.goto("/");
    await fillProspectForm(page, payload);
    await submitAnalysis(page);

    // Not qualified, so the run completes partially rather than fully.
    await expect(page.getByText("部分完成")).toBeVisible({ timeout: 90_000 });
    const companyId = await companyIdFromUrl(page);

    // --- decision is REVIEW and says so in the UI ---
    await expect(page.getByRole("heading", { name: "资格评估" })).toBeVisible();
    await expect(page.getByText("人工复核").first()).toBeVisible();
    await expect(page.getByText("37.5")).toBeVisible();

    // --- the reasons are explainable: unmeasured dimensions are named, and
    // framed as unknown rather than negative ---
    await expect(page.getByText("判定依据")).toBeVisible();
    await expect(
      page.getByText("no shipping_fit signal observed — unknown, not negative"),
    ).toBeVisible();
    await expect(
      page.getByText(/no cargo_value_potential signal observed/),
    ).toBeVisible();

    // --- no draft was generated, and the UI says why ---
    await expect(page.getByText("版本 1")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "批准草稿" })).toHaveCount(0);
    await expect(page.getByText("工作流备注")).toBeVisible();

    // --- database confirms: REVIEW, and zero drafts ---
    const assessment = latestAssessmentForCompany(companyId);
    expect(assessment).not.toBeNull();
    expect(assessment!.score).toBe(REVIEW_EXPECTATION.score);
    expect(assessment!.completeness).toBe(REVIEW_EXPECTATION.completeness);
    expect(assessment!.decision).toBe(REVIEW_EXPECTATION.decision);
    expect(draftCountForCompany(companyId)).toBe(0);

    expect(guard.duplicateKeyWarnings()).toEqual([]);
    expect(guard.problems()).toEqual([]);
  });
});
