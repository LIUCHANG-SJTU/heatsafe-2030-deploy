import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { I18nProvider } from "./I18nProvider";
import { useI18n } from "./useI18n";

function Probe() {
  const { locale, setLocale, t } = useI18n();
  return <div>
    <span>{locale}</span>
    <strong>{t("map.gridCount", { count: 400 })}</strong>
    <button onClick={() => setLocale("en")}>EN</button>
  </div>;
}

describe("I18nProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = "";
  });

  it("defaults to zh-CN and updates the document language", () => {
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByText("zh-CN")).toBeInTheDocument();
    expect(screen.getByText("400 个分析格网")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("zh-CN");
  });

  it("switches immediately and persists the English locale", () => {
    render(<I18nProvider><Probe /></I18nProvider>);
    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByText("en")).toBeInTheDocument();
    expect(screen.getByText("400 analysis grids")).toBeInTheDocument();
    expect(localStorage.getItem("heatsafe-locale")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
  });

  it("restores a persisted locale", () => {
    localStorage.setItem("heatsafe-locale", "en");
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByText("en")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
  });
});
