/**
 * Browser-quality guard: fails a test on React duplicate-key warnings,
 * unhandled page exceptions, or severe console errors.
 *
 * Attach at the start of a test, assert with `expect(guard.problems()).toEqual([])`
 * at the end.
 */

import type { Page } from "@playwright/test";

/** Noise that is not the app's fault and must not fail a run. */
const IGNORED = [
  /favicon/i,
  /Download the React DevTools/i,
  /net::ERR_ABORTED/i,
];

const DUPLICATE_KEY = [/two children with the same key/i, /unique "key" prop/i];

export interface ConsoleGuard {
  problems: () => string[];
  duplicateKeyWarnings: () => string[];
}

export function attachConsoleGuard(page: Page): ConsoleGuard {
  const collected: string[] = [];

  page.on("console", (message) => {
    const type = message.type();
    if (type !== "error" && type !== "warning") return;
    const text = message.text();
    if (IGNORED.some((pattern) => pattern.test(text))) return;
    // A React key warning arrives as a plain warning; keep it either way.
    if (type === "warning" && !DUPLICATE_KEY.some((p) => p.test(text))) return;
    collected.push(`[console.${type}] ${text}`);
  });

  page.on("pageerror", (error) => {
    collected.push(`[pageerror] ${error.message}`);
  });

  return {
    problems: () => [...collected],
    duplicateKeyWarnings: () =>
      collected.filter((entry) => DUPLICATE_KEY.some((p) => p.test(entry))),
  };
}
