/** Shared runtime knobs for the E2E harness. */

export const API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8001";
export const APP_BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3001";

/** Which provider the stack under test was started with. */
export type ProviderMode = "fake" | "openai";

export const PROVIDER_MODE: ProviderMode =
  process.env.E2E_PROVIDER === "openai" ? "openai" : "fake";

/** Name of the throwaway database the stack under test is pointed at. */
export const E2E_DB = process.env.E2E_DB ?? "importer_hunter_e2e";

/** The dev database, which the harness must never touch. */
export const DEV_DB = "importer_hunter";
