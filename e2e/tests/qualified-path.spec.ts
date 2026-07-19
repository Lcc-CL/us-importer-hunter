import { expect, test } from "@playwright/test";

import {
  QUALIFIED_EXPECTATION,
  qualifiedProspect,
} from "../fixtures/prospects";
import { attachConsoleGuard } from "../utils/console-guard";
import {
  draftCountForCompany,
  latestAssessmentForCompany,
  latestDraftForCompany,
  signalCountForCompany,
} from "../utils/db";
import { PROVIDER_MODE } from "../utils/env";
import { companyIdFromUrl, fillProspectForm, submitAnalysis } from "../utils/form";

test.describe("qualified path", () => {
  test("company → Chinese signals → QUALIFIED → decision maker → draft → approve → reload", async ({
    page,
  }) => {
    test.skip(PROVIDER_MODE !== "fake", "fake-provider run only");
    const guard = attachConsoleGuard(page);
    const payload = qualifiedProspect();

    await page.goto("/");
    await fillProspectForm(page, payload);
    await submitAnalysis(page);

    // --- workflow reached completion ---
    await expect(page.getByText("已完成")).toBeVisible({ timeout: 90_000 });
    const companyId = await companyIdFromUrl(page);

    // --- qualification is visible and explainable ---
    await expect(page.getByRole("heading", { name: "资格评估" })).toBeVisible();
    await expect(page.getByText("70.5")).toBeVisible();
    await expect(page.getByText("判定依据")).toBeVisible();

    // The four dimensions that the v0.1.1 P0 fix restored must all be scored,
    // i.e. none of them may report "unknown".
    for (const dimension of [
      "shipping_fit",
      "cargo_value_potential",
      "company_scale",
      "logistics_complexity",
    ]) {
      await expect(
        page.getByText(`no ${dimension} signal observed`),
      ).toHaveCount(0);
    }

    // --- decision maker selected (the name also appears inside the draft
    // body, so target the card heading specifically) ---
    await expect(page.getByText("联系人 · 决策人")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: payload.contact.name }),
    ).toBeVisible();

    // --- draft generated, and it is a draft ---
    await expect(page.getByText("版本 1")).toBeVisible();
    await expect(
      page.getByText("草稿模式：当前版本只生成和审批邮件草稿，不会自动发送。"),
    ).toBeVisible();

    // --- approve ---
    await page.getByLabel("审批人姓名").fill("E2E Approver");
    await page.getByRole("button", { name: "批准草稿" }).click();
    await expect(page.getByText("批准人：E2E Approver")).toBeVisible();

    // --- reload restores the approved state ---
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByText("批准人：E2E Approver")).toBeVisible();
    await expect(page.getByText("70.5")).toBeVisible();

    // --- database is the source of truth ---
    const assessment = latestAssessmentForCompany(companyId);
    expect(assessment).not.toBeNull();
    expect(assessment!.score).toBe(QUALIFIED_EXPECTATION.score);
    expect(assessment!.completeness).toBe(QUALIFIED_EXPECTATION.completeness);
    expect(assessment!.decision).toBe(QUALIFIED_EXPECTATION.decision);

    // pain_point is stored (8 signals submitted) yet contributes no score:
    // the total is exactly the seven scoring dimensions plus contactability.
    expect(signalCountForCompany(companyId)).toBe(8);

    const draft = latestDraftForCompany(companyId);
    expect(draft).not.toBeNull();
    expect(draft!.approvalStatus).toBe("approved");
    expect(draft!.provider).toBe("fake");
    expect(draft!.promptVersion).toBeTruthy();

    expect(guard.duplicateKeyWarnings()).toEqual([]);
    expect(guard.problems()).toEqual([]);
  });

  test("@real generates one draft through the configured live provider", async ({
    page,
  }) => {
    test.skip(PROVIDER_MODE !== "openai", "real-provider run only");
    const guard = attachConsoleGuard(page);
    const payload = qualifiedProspect();

    await page.goto("/");
    await fillProspectForm(page, payload);
    await submitAnalysis(page);

    await expect(page.getByText("已完成")).toBeVisible({ timeout: 120_000 });
    const companyId = await companyIdFromUrl(page);

    await expect(page.getByText("版本 1")).toBeVisible();

    const assessment = latestAssessmentForCompany(companyId);
    expect(assessment!.decision).toBe("qualified");

    const draft = latestDraftForCompany(companyId);
    expect(draft).not.toBeNull();
    expect(draft!.provider).toBe("openai");
    expect(draft!.model).toBeTruthy();
    expect(draft!.promptVersion).toBeTruthy();
    expect(draftCountForCompany(companyId)).toBe(1);

    expect(guard.problems()).toEqual([]);
  });
});
