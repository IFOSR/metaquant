"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useI18n } from "../../components/i18n-provider";

const TOKEN_KEY = "quant-access-token";

export function storeAccessToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function readAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!token.trim()) {
      setError(t("login.tokenRequired"));
      return;
    }
    storeAccessToken(token.trim());
    router.push("/");
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("login.eyebrow")}</span>
          <h1>{t("login.title")}</h1>
          <p className="lede">
            {t("login.lede")}
          </p>
        </div>
      </div>
      <form className="panel" onSubmit={submit}>
        <label className="context-select" htmlFor="access-token">
          <span>{t("login.tokenLabel")}</span>
          <input
            id="access-token"
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder={t("login.tokenPlaceholder")}
          />
        </label>
        {error ? (
          <div className="freshness-banner" role="alert">
            <span>{error}</span>
          </div>
        ) : null}
        <button className="button button-primary" type="submit">
          {t("login.continue")}
        </button>
      </form>
    </div>
  );
}
