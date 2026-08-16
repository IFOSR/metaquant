import { cookies } from "next/headers";

import {
  LOCALE_COOKIE,
  resolveLocale,
  translate,
  type Locale,
  type MessageKey,
} from "./i18n";

export type ServerT = (
  key: MessageKey,
  params?: Record<string, string | number>,
) => string;

export async function getServerLocale(): Promise<Locale> {
  const store = await cookies();
  return resolveLocale(store.get(LOCALE_COOKIE)?.value);
}

export async function getServerT(): Promise<ServerT> {
  const locale = await getServerLocale();
  return (key, params) => translate(locale, key, params);
}
