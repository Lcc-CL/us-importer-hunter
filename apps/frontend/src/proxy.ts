import { createHash, timingSafeEqual } from "node:crypto";

import { NextRequest, NextResponse } from "next/server";

/**
 * Access passcode for the whole frontend, including the /api/v1 proxy.
 *
 * HTTP Basic auth keeps it simple: the browser prompts once, then resends the
 * credentials on every same-origin page load and fetch, so the API proxy is
 * covered without any client code. Any username is accepted; only the
 * password is checked against FRONTEND_ACCESS_PASSWORD (server-only, read at
 * runtime — never give it a NEXT_PUBLIC_ prefix).
 *
 * Unset in production fails closed; unset in development stays open so
 * `npm run dev` and the E2E stack keep working without extra setup.
 */
const REALM = "US Importer Hunter";

function digest(value: string): Buffer {
  return createHash("sha256").update(value, "utf8").digest();
}

function passwordFromBasicAuth(header: string | null): string | null {
  if (!header) return null;
  const [scheme, encoded] = header.split(" ", 2);
  if (scheme?.toLowerCase() !== "basic" || !encoded) return null;
  const decoded = Buffer.from(encoded, "base64").toString("utf8");
  const separator = decoded.indexOf(":");
  return separator === -1 ? null : decoded.slice(separator + 1);
}

export function proxy(request: NextRequest): NextResponse | undefined {
  const expected = process.env.FRONTEND_ACCESS_PASSWORD ?? "";
  if (!expected) {
    if (process.env.NODE_ENV !== "production") return undefined;
    return NextResponse.json(
      {
        code: "frontend_access_not_configured",
        message: "Access passcode is not configured for this deployment.",
      },
      { status: 503 },
    );
  }

  const supplied = passwordFromBasicAuth(request.headers.get("authorization"));
  // Compare fixed-length digests so the check is constant-time regardless of
  // the supplied length.
  if (supplied !== null && timingSafeEqual(digest(supplied), digest(expected))) {
    return undefined;
  }

  return NextResponse.json(
    { code: "frontend_access_denied", message: "Access passcode required." },
    {
      status: 401,
      headers: { "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"` },
    },
  );
}

export const config = {
  // Everything except build assets; the favicon stays public so the browser
  // does not raise a second prompt for it.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
