import { NextRequest, NextResponse } from "next/server";

import { isPublicMailRoute } from "@/lib/mail-routes";

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
  "mail-campaigns",
  "companies",
] as const;

const FORWARDED_RESPONSE_HEADERS = [
  "content-type",
  "content-disposition",
  "x-request-id",
  "cache-control",
  "content-security-policy",
  "referrer-policy",
] as const;

function getBackendBaseUrl(): string {
  const configured = (process.env.BACKEND_INTERNAL_URL ?? "").trim();
  if (configured) return configured.replace(/\/$/, "");

  // Host-based `npm run dev` commonly runs beside FastAPI on port 8000. Docker
  // and production must provide the service URL explicitly because localhost
  // inside the frontend container is not the backend container.
  return process.env.NODE_ENV === "production" ? "" : "http://localhost:8000";
}

// Public form and webhook payloads are small. Stop reading oversized bodies
// even when the caller omits Content-Length or uses chunked encoding.
async function readPublicMailBody(request: NextRequest): Promise<ArrayBuffer | null> {
  const limit = 8192;
  const buffer = new Uint8Array(limit);
  const reader = request.body?.getReader();
  if (!reader) return buffer.buffer.slice(0, 0);

  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return buffer.buffer.slice(0, size);
      if (size + value.byteLength > limit) {
        await reader.cancel();
        return null;
      }
      buffer.set(value, size);
      size += value.byteLength;
    }
  } finally {
    reader.releaseLock();
  }
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const prefix = path[0] ?? "";
  const publicMail = isPublicMailRoute(request.nextUrl.pathname, request.method);
  if (!publicMail && !ALLOWED_PREFIXES.some((allowed) => allowed === prefix)) {
    return NextResponse.json(
      { code: "frontend_proxy_path_blocked", message: "API path is not available." },
      { status: 404 },
    );
  }

  const backend = getBackendBaseUrl();
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
  if (publicMail && prefix === "mail-feedback") {
    const key = request.headers.get("x-mail-feedback-key");
    if (key) headers.set("x-mail-feedback-key", key);
  }

  try {
    let body: ArrayBuffer | undefined;
    if (request.method !== "GET" && request.method !== "HEAD") {
      const incoming = publicMail ? await readPublicMailBody(request) : await request.arrayBuffer();
      if (incoming === null) {
        return NextResponse.json({ message: "Request body is too large." }, { status: 413 });
      }
      body = incoming;
    }
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
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
