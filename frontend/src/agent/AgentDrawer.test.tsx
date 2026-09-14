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
});
