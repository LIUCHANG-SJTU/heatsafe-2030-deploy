import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Send, X } from "lucide-react";
import { streamAgent } from "./agentStream";
import { getAgentStatus } from "./agentApi";
import type { AgentContext, AgentEvidence, AgentMapAction, AgentMessage, AgentResponse } from "./types";
import { AgentEvidence as EvidenceCards, evidenceIdsInText } from "./AgentEvidence";
import { useI18n } from "../i18n/useI18n";

type Props = { open: boolean; onClose: () => void; selectedGridId: string | null; activeLayer: string; focusedHotspotId?: string | null; onMapAction: (action: AgentMapAction) => void };

export function AgentDrawer({ open, onClose, selectedGridId, activeLayer, focusedHotspotId, onMapAction }: Props) {
  const { locale, t } = useI18n();
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [answer, setAnswer] = useState<AgentResponse | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [providerEnabled, setProviderEnabled] = useState(false);
  const previousLocale = useRef(locale);
  useEffect(() => { if (!open) return; getAgentStatus().then((status) => setProviderEnabled(status.enabled)).catch(() => setProviderEnabled(false)); }, [open]);
  useEffect(() => {
    if (previousLocale.current === locale) return;
    previousLocale.current = locale;
    setMessages([{ role: "assistant", content: t("agent.languageChanged") }]);
    setAnswer(null); setDraft(""); setInput("");
  }, [locale, t]);
  const suggestions = useMemo(() => selectedGridId
    ? [t("agent.suggestionGridAction"), t("agent.suggestionGridWhy"), t("agent.suggestionGridCompare"), t("agent.suggestionEffect")]
    : [t("agent.suggestionHotspotAction"), t("agent.suggestionHotspots"), t("agent.suggestionQuery"), t("agent.suggestionMethod")], [selectedGridId, t]);
  if (!open) return null;
  const send = async (text = input) => {
    const content = text.trim(); if (!content || streaming) return;
    const next = [...messages, { role: "user" as const, content }].slice(-12);
    setMessages(next); setInput(""); setAnswer(null); setDraft(""); setStreaming(true);
    try {
      let tokenStarted = false;
      const response = await streamAgent(next, { locale, selected_grid_id: selectedGridId, active_layer: activeLayer, focused_hotspot_id: focusedHotspotId, agent_highlighted_grid_ids: [] }, (event) => {
        if (event.type === "status" && !tokenStarted) setDraft(event.data.message);
        if (event.type === "token") { setDraft((value) => tokenStarted ? value + event.data.text : event.data.text); tokenStarted = true; }
      });
      setDraft(""); setAnswer(response); setMessages((current) => [...current, { role: "assistant" as const, content: response.answer }].slice(-12));
      response.map_actions.forEach(onMapAction);
    } catch (error) {
      setAnswer({ request_id: "", answer: t("agent.unavailable"), evidence: [], tool_trace: [], map_actions: [], validation: { status: "FAIL", errors: [] }, answer_mode: "DETERMINISTIC_FALLBACK", provider: "error", model: "", latency_ms: 0 });
    } finally { setStreaming(false); }
  };
  return <aside className="agent-drawer" role="dialog" aria-label={t("agent.title")}><div className="agent-drawer-header"><div><span className="eyebrow">{t("agent.eyebrow")}</span><h2><Bot size={19} />{t("agent.title")}</h2><span className="agent-badge">{providerEnabled ? t("agent.realProvider") : t("agent.fallbackProvider")}</span></div><button className="icon-button" aria-label={t("agent.close")} onClick={onClose}><X size={18} /></button></div><div className="agent-context"><span>{t("agent.selectedGrid")}<b>{selectedGridId || t("agent.noGrid")}</b></span><span>{t("agent.layer")}<b>{t(`layers.${activeLayer}` as Parameters<typeof t>[0])}</b></span></div><div className="agent-suggestions">{suggestions.map((suggestion) => <button key={suggestion} onClick={() => send(suggestion)} disabled={streaming}>{suggestion}</button>)}</div><div className="agent-conversation">{messages.map((message, index) => <div className={`agent-message ${message.role}`} key={`${message.role}-${index}`}>{message.content}</div>)}{streaming && <div className="agent-message assistant" role="status">{draft || t("agent.loading")}</div>}{answer && !streaming && <EvidenceCards items={answer.evidence as AgentEvidence[]} citedEvidenceIds={evidenceIdsInText(answer.answer)} onGridClick={(id) => onMapAction({ action: "select_grid", grid_ids: [id] })} />}</div><form className="agent-composer" onSubmit={(event) => { event.preventDefault(); void send(); }}><input value={input} onChange={(event) => setInput(event.target.value)} placeholder={t("agent.placeholder")} aria-label={t("agent.ask")} maxLength={4000} /><button type="submit" aria-label={t("agent.send")} disabled={!input.trim() || streaming}><Send size={17} /></button></form><button className="agent-clear" onClick={() => { setMessages([]); setAnswer(null); setDraft(""); }}>{t("agent.clear")}</button></aside>;
}
