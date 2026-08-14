"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const TOKEN_KEY = "quant-access-token";

export function storeAccessToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function readAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export default function LoginPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!token.trim()) {
      setError("An access token is required.");
      return;
    }
    storeAccessToken(token.trim());
    router.push("/");
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">FR-701 / Authentication</span>
          <h1>Sign in with a scoped access token.</h1>
          <p className="lede">
            Roles and capabilities are derived from the token, never hard-coded
            in the client. Paper and live environments stay gated.
          </p>
        </div>
      </div>
      <form className="panel" onSubmit={submit}>
        <label className="context-select" htmlFor="access-token">
          <span>Access token</span>
          <input
            id="access-token"
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Bearer token issued by the identity provider"
          />
        </label>
        {error ? (
          <div className="freshness-banner" role="alert">
            <span>{error}</span>
          </div>
        ) : null}
        <button className="button button-primary" type="submit">
          Continue
        </button>
      </form>
    </div>
  );
}
