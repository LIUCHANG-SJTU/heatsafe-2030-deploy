import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getAgentStatus } from "./agentApi";
import { AgentDrawer } from "./AgentDrawer";
import { streamAgent } from "./agentStream";
import { I18nProvider } from "../i18n/I18nProvider";

vi.mock("./agentApi", () => ({ getAgentStatus: vi.fn() }));
vi.mock("./agentStream", () => ({ streamAgent: vi.fn() }));

describe("AgentDrawer streaming contract", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(getAgentStatus).mockResolvedValue({ enabled: true } as never);
    vi.mocked(streamAgent).mockImplementation(async (_messages, _context, onEvent) => {
      onEvent({ type: "token", data: { text: "ABC " } });
      onEvent({ type: "token", data: { text: "DEF" } });
      return {
        request_id: "r1", answer: "ABC DEF", evidence: [], tool_trace: [], map_actions: [],
        validation: { status: "PASS", errors: [] }, answer_mode: "GROUNDED",
        provider: "mock", model: "mock", latency_ms: 1,
      };
    });
  });

  it("replaces the streamed draft with the done answer exactly once", async () => {
    render(<I18nProvider><AgentDrawer open onClose={vi.fn()} selectedGridId="GRID-1" activeLayer="risk_score" onMapAction={vi.fn()} /></I18nProvider>);
    fireEvent.change(screen.getByLabelText("向 HeatSafe 提问"), { target: { value: "test" } });
    fireEvent.click(screen.getByLabelText("发送问题"));
    await waitFor(() => expect(screen.getAllByText("ABC DEF")).toHaveLength(1));
  });

  it("localizes suggestions, context, placeholder, and request locale", async () => {
    localStorage.setItem("heatsafe-locale", "en");
    render(<I18nProvider><AgentDrawer open onClose={vi.fn()} selectedGridId="GRID-1" activeLayer="risk_score" onMapAction={vi.fn()} /></I18nProvider>);
    expect(screen.getByText("What actions should be prioritized for this grid?")).toBeInTheDocument();
    expect(screen.getByText("SELECTED GRID")).toBeInTheDocument();
    expect(screen.getByText("Heat Risk")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ask HeatSafe"), { target: { value: "What should we do?" } });
    fireEvent.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(streamAgent).toHaveBeenCalled());
    expect(vi.mocked(streamAgent).mock.calls.at(-1)?.[1]).toMatchObject({ locale: "en", selected_grid_id: "GRID-1" });
  });

  it("presents provider-none operation as intentional evidence-grounded mode", async () => {
    vi.mocked(getAgentStatus).mockResolvedValue({ enabled: false } as never);
    vi.mocked(streamAgent).mockImplementation(async () => ({
      request_id: "r2",
      answer: "当前模型服务暂时不可用，以下为 HeatSafe REAL 数据摘要。格网 M4B-R-5EEC8B7710-G-R16-C13 的相对风险为 90.2 [E1]，主要贡献项为 hazard。该格网人口约为 1589.3 人 [E3]，有效陆地绿地比例为 0.2 [E5]。",
      evidence: [], tool_trace: [], map_actions: [],
      validation: { status: "PASS", errors: [] }, answer_mode: "DETERMINISTIC_FALLBACK",
      provider: "deterministic", model: "fallback-v1", latency_ms: 1,
    }));
    render(<I18nProvider><AgentDrawer open onClose={vi.fn()} selectedGridId="M4B-R-5EEC8B7710-G-R16-C13" activeLayer="risk_score" onMapAction={vi.fn()} /></I18nProvider>);
    await waitFor(() => expect(screen.getByText("证据约束 · 可追溯")).toBeInTheDocument());
    expect(screen.getByText("格网 R16-C13")).toHaveAttribute("title", "M4B-R-5EEC8B7710-G-R16-C13");
    fireEvent.change(screen.getByLabelText("向 HeatSafe 提问"), { target: { value: "为什么风险高？" } });
    fireEvent.click(screen.getByLabelText("发送问题"));
    await waitFor(() => expect(screen.getByText(/当前为证据约束决策模式/)).toBeInTheDocument());
    expect(document.body.textContent).toContain("最大加权贡献项为热危险度");
    expect(document.body.textContent).toContain("约 1,589 人");
    expect(document.body.textContent).toContain("20.0%");
    expect(document.body.textContent).not.toContain("模型服务暂时不可用");
    expect(document.body.textContent).not.toContain("M4B-R-5EEC8B7710-G-R16-C13 的相对风险");
  });
});
