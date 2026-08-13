import { describe, expect, it } from "vitest";

import { isLocalDemoRequest } from "../lib/local-demo-origin";

function headers(values: Record<string, string>): Headers {
  return new Headers(values);
}

describe("isLocalDemoRequest", () => {
  it.each([
    ["localhost:3000", {}],
    ["127.0.0.1:3000", {}],
    ["127.42.7.9", {}],
    ["[::1]:3000", {}],
    ["localhost:3000", { "x-forwarded-host": "127.0.0.1:3000" }],
    ["localhost:3000", { forwarded: 'for=127.0.0.1;host="[::1]:3000"' }],
  ])("accepts loopback Host and forwarded hosts", (host, forwarded) => {
    expect(isLocalDemoRequest(headers({ host, ...forwarded }))).toBe(true);
  });

  it.each([
    [{ host: "quant.example.com" }],
    [{ host: "localhost:3000", "x-forwarded-host": "quant.example.com" }],
    [{ host: "localhost:3000", "x-forwarded-host": "localhost, quant.example.com" }],
    [{ host: "localhost:3000", forwarded: "for=10.0.0.2;host=quant.example.com" }],
  ])("rejects any non-loopback Host or forwarded host", (values) => {
    expect(isLocalDemoRequest(headers(values))).toBe(false);
  });

  it("rejects requests without a Host header", () => {
    expect(isLocalDemoRequest(new Headers())).toBe(false);
  });
});
