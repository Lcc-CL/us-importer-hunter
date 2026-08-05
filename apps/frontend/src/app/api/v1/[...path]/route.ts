import { NextRequest, NextResponse } from "next/server";

const ALLOWED_PREFIXES = [
  "health",
  "acceptance",
  "import-sessions",
  "import-entity-decisions",
  "prospect-routing-runs",
  "prospect-routes",
  "prospect-batches",
  "suppressions",
  "umail-export-batches",
  "umail-result-imports",
  "discovery-tasks",
  "mvp",
  "companies",
  "research",
] as const;

const FORWARDED_RESPONSE_HEADERS = [
  "content-type",
  "content-disposition",
  "x-request-id",
] as const;

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const prefix = path[0] ?? "";
  if (!ALLOWED_PREFIXES.some((allowed) => allowed === prefix)) {
    return NextResponse.json(
      { code: "frontend_proxy_path_blocked", message: "API path is not available." },
      { status: 404 },
    );
  }

  const backend = (process.env.BACKEND_INTERNAL_URL ?? "").replace(/\/$/, "");
  if (!backend) {
    return NextResponse.json(
      {
        code: "frontend_proxy_not_configured",
        message: "Backend connection is not configured for this deployment.",
      },
      { status: 503 },
    );
  }

  const target = new URL(`${backend}/api/v1/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const requestId = request.headers.get("x-request-id");
  if (requestId) headers.set("x-request-id", requestId);

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer(),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const responseHeaders = new Headers();
    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      {
        code: "frontend_proxy_backend_unavailable",
        message: "Backend is temporarily unavailable. Retry shortly.",
      },
      { status: 503 },
    );
  }
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
