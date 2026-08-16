import type { NextRequest } from "next/server";

import {
  buildProxyTarget,
  isAllowedQuantApiPath,
} from "../../../../lib/proxy-url";
import { isLocalDemoRequest } from "../../../../lib/local-demo-origin";

const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "idempotency-key",
  "if-match",
] as const;

const FORWARDED_RESPONSE_HEADERS = [
  "content-type",
  "etag",
  "location",
  "retry-after",
] as const;

async function proxy(request: NextRequest, path: string[]) {
  if (!isLocalDemoRequest(request.headers)) {
    return Response.json(
      {
        type: "about:blank",
        title: "Local demo proxy only",
        status: 403,
        detail:
          "The shared static-token proxy accepts requests only through a loopback host.",
        code: "LOCAL_DEMO_PROXY_ONLY",
      },
      {
        status: 403,
        headers: { "Content-Type": "application/problem+json" },
      },
    );
  }

  if (!isAllowedQuantApiPath(path)) {
    return Response.json(
      {
        type: "about:blank",
        title: "Resource not found",
        status: 404,
        detail: "The resource does not exist or is not available through this proxy.",
        code: "RESOURCE_NOT_FOUND",
      },
      {
        status: 404,
        headers: { "Content-Type": "application/problem+json" },
      },
    );
  }

  const upstream = process.env.QUANT_API_UPSTREAM_URL;
  const accessToken = process.env.QUANT_API_ACCESS_TOKEN;
  if (!upstream || !accessToken) {
    return Response.json(
      {
        type: "about:blank",
        title: "Quant API proxy is not configured",
        status: 503,
        detail:
          "Set QUANT_API_UPSTREAM_URL and QUANT_API_ACCESS_TOKEN on the Next.js server.",
        code: "QUANT_API_PROXY_NOT_CONFIGURED",
      },
      {
        status: 503,
        headers: { "Content-Type": "application/problem+json" },
      },
    );
  }

  const headers = new Headers({ Authorization: `Bearer ${accessToken}` });
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const target = buildProxyTarget(upstream, path, request.nextUrl.search);
  let response: Response;
  try {
    response = await fetch(target, {
      method: request.method,
      headers,
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : await request.arrayBuffer(),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return Response.json(
      {
        type: "about:blank",
        title: "Quant API upstream unavailable",
        status: 504,
        detail: "The upstream Quant API did not respond in time.",
        code: "QUANT_API_UPSTREAM_UNAVAILABLE",
      },
      {
        status: 504,
        headers: { "Content-Type": "application/problem+json" },
      },
    );
  }
  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = response.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
