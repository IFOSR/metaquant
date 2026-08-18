"use client";

import {
  createContext,
  useContext,
  type ReactNode,
} from "react";

import { translate, type MessageKey } from "../lib/i18n";

interface I18nContextValue {
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  return (
    <I18nContext.Provider value={{ t: translate }}>{children}</I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return value;
}
