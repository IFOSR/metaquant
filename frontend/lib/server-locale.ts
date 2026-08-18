import { translate, type MessageKey } from "./i18n";

export type ServerT = (
  key: MessageKey,
  params?: Record<string, string | number>,
) => string;

export async function getServerT(): Promise<ServerT> {
  return translate;
}
