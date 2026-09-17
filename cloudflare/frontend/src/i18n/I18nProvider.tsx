import { createContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { messages, type MessageKey } from "./messages";
import type { Locale, TranslationValues } from "./types";

const STORAGE_KEY = "heatsafe-locale";

export type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey, values?: TranslationValues) => string;
};

export const I18nContext = createContext<I18nContextValue | null>(null);

function initialLocale(): Locale {
  if (typeof window === "undefined") return "zh-CN";
  return window.localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "zh-CN";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18nContextValue>(() => ({
    locale,
    setLocale,
    t: (key, values = {}) => Object.entries(values).reduce(
      (text, [name, replacement]) => text.replaceAll(`{${name}}`, String(replacement)),
      messages[locale][key],
    ),
  }), [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
