import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

import { I18nProvider } from "../components/i18n-provider";
import type { Locale } from "../lib/i18n";

/**
 * Render a component inside I18nProvider. Tests assert on the English
 * dictionary, so the default locale is "en".
 */
export function renderWithI18n(
  ui: ReactElement,
  locale: Locale = "en",
  options?: Omit<RenderOptions, "wrapper">,
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return <I18nProvider initialLocale={locale}>{children}</I18nProvider>;
  }
  return render(ui, { wrapper: Wrapper, ...options });
}
