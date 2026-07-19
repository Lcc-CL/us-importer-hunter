/**
 * Pre-flight: the stack must be up, pointed at the throwaway database, and
 * running the provider mode the caller asked for. Failing here beats a
 * confusing failure three specs later.
 */

import { getRuntimeStatus } from "./utils/api";
import { databaseExists } from "./utils/db";
import { API_BASE_URL, APP_BASE_URL, E2E_DB, PROVIDER_MODE } from "./utils/env";

export default async function globalSetup(): Promise<void> {
  const runtime = await getRuntimeStatus().catch((error: unknown) => {
    throw new Error(
      `E2E backend unreachable at ${API_BASE_URL}. Start it with \`make e2e-up\`.\n${String(error)}`,
    );
  });

  if (runtime.provider !== PROVIDER_MODE) {
    throw new Error(
      `Provider mismatch: stack reports "${runtime.provider}" but the run expects ` +
        `"${PROVIDER_MODE}". Restart with E2E_PROVIDER=${PROVIDER_MODE}.`,
    );
  }

  if (!databaseExists(E2E_DB)) {
    throw new Error(`Throwaway database ${E2E_DB} is missing — run \`make e2e-up\`.`);
  }

  const frontend = await fetch(APP_BASE_URL).catch(() => null);
  if (!frontend || !frontend.ok) {
    throw new Error(`E2E frontend unreachable at ${APP_BASE_URL}.`);
  }

  // Never print the key itself — only whether the mode is satisfiable.
  console.log(
    `E2E ready · provider=${runtime.provider} · model=${runtime.model} · db=${E2E_DB}`,
  );
}
