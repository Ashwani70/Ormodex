import { useState, useEffect, useRef, useCallback } from "react";
import { useLocation } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  Bot, Send, X, ChevronRight, RefreshCw,
  Sparkles, Zap, MessageSquare, RotateCcw, Copy, CheckCheck,
  Globe, ChevronDown, Plus,
} from "lucide-react";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

// Markdown-lite renderer for AI responses
function RenderMarkdown({ text }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("**") && line.endsWith("**")) {
          return <p key={i} className="font-bold text-slate-900">{line.slice(2, -2)}</p>;
        }
        if (line.startsWith("• ") || line.startsWith("- ") || line.startsWith("* ")) {
          return (
            <div key={i} className="flex items-start gap-2">
              <span className="text-teal-600 mt-0.5 flex-shrink-0">▸</span>
              <span dangerouslySetInnerHTML={{ __html: line.slice(2).replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>") }} />
            </div>
          );
        }
        if (/^\d+\./.test(line)) {
          return (
            <div key={i} className="flex items-start gap-2">
              <span className="text-teal-600 font-mono text-xs mt-0.5 flex-shrink-0 w-4">{line.match(/^\d+/)[0]}.</span>
              <span dangerouslySetInnerHTML={{ __html: line.replace(/^\d+\.\s*/, "").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>") }} />
            </div>
          );
        }
        if (line.trim() === "") return <div key={i} className="h-1" />;
        return (
          <p key={i}
            dangerouslySetInnerHTML={{
              __html: line
                .replace(/\*\*(.*?)\*\*/g, "<strong class='text-teal-700'>$1</strong>")
                .replace(/`(.*?)`/g, "<code class='bg-slate-100 text-teal-700 px-1 rounded text-xs'>$1</code>")
            }}
          />
        );
      })}
    </div>
  );
}

const PROVIDER_LABELS = {
  auto: "Auto",
  gemini: "Gemini 3.5",
  claude: "Claude",
  fallback: "Built-in",
};

const PROVIDER_COLORS = {
  gemini: "text-blue-600",
  claude: "text-orange-600",
  fallback: "text-slate-400",
  auto: "text-teal-600",
};

export default function AiCopilotPanel({ isOpen, onClose }) {
  const location = useLocation();

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [provider, setProvider] = useState("auto");
  const [lastProvider, setLastProvider] = useState(null);
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [showProviders, setShowProviders] = useState(false);
  const [availableProviders, setAvailableProviders] = useState([]);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load suggestions on route change
  useEffect(() => {
    if (!isOpen) return;
    api.get("/ai/suggestions", { params: { module: location.pathname } })
      .then(r => setSuggestions(r.data.suggestions || []))
      .catch(() => {});
  }, [location.pathname, isOpen]);

  // Load available providers
  useEffect(() => {
    if (!isOpen) return;
    api.get("/ai/providers")
      .then(r => setAvailableProviders(r.data.available || []))
      .catch(() => {});
  }, [isOpen]);

  // Initial greeting
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([{
        role: "assistant",
        content: "**Hello! I'm Gravity Copilot** ✨\n\nI can help you with:\n• Sales, invoices & GST queries\n• Inventory & purchase orders\n• HR, payroll & attendance\n• Business insights & reports\n• Create records & take actions\n\nWhat would you like to know?",
        timestamp: new Date(),
      }]);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 300);
    }
  }, [isOpen]);

  const sendMessage = useCallback(async (text) => {
    const msg = (text || input).trim();
    if (!msg || sending) return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: msg, timestamp: new Date() }]);
    setSending(true);

    try {
      const r = await api.post("/ai/chat", {
        message: msg,
        session_id: sessionId,
        provider,
        context: location.pathname,
      });
      setSessionId(r.data.session_id);
      setLastProvider(r.data.provider);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: r.data.reply,
        provider: r.data.provider,
        timestamp: new Date(),
      }]);
    } catch (e) {
      // Surface the backend's actual error detail instead of a generic
      // message — a timeout, a 403 (module access), and a 500 all mean
      // different things and the user should be able to tell them apart.
      const detail =
        e.code === "ECONNABORTED"
          ? "The request timed out. The AI provider may be slow to respond right now."
          : !e.response
          ? "Could not reach the server. Check your connection and try again."
          : formatApiErrorDetail(e.response.data?.detail);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: detail,
        error: true,
        retryText: msg,
        timestamp: new Date(),
      }]);
    } finally {
      setSending(false);
    }
  }, [input, sending, sessionId, provider, location.pathname]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const copyMessage = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const clearChat = () => {
    setMessages([{
      role: "assistant",
      content: "**Chat cleared.** How can I help you?",
      timestamp: new Date(),
    }]);
    setSessionId(null);
    setLastProvider(null);
  };

  return (
    <div
      className={`flex flex-col h-full bg-slate-50 border-l border-slate-200 transition-all duration-300 ease-in-out ${
        isOpen ? "w-[380px] opacity-100" : "w-0 opacity-0 overflow-hidden"
      }`}
      style={{ minWidth: isOpen ? 380 : 0 }}
    >
      {isOpen && (
        <>
          {/* ── Header ─────────────────────────────────────────────── */}
          <div className="flex-shrink-0 border-b border-slate-200 px-4 py-3 bg-white">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-teal-500 to-violet-600 flex items-center justify-center flex-shrink-0 relative">
                  <Bot className="w-4 h-4 text-white" />
                  <div className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-emerald-500 rounded-full border-2 border-white" />
                </div>
                <div>
                  <div className="text-sm font-bold text-slate-900 leading-none">Gravity Copilot</div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <Sparkles className="w-2.5 h-2.5 text-teal-600" />
                    <span className="font-mono text-[9px] uppercase tracking-widest text-teal-600">
                      AI Assistant
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                {/* Provider selector */}
                <div className="relative">
                  <button
                    onClick={() => setShowProviders(!showProviders)}
                    className="flex items-center gap-1 px-2 py-1 rounded-md border border-slate-200 hover:border-teal-500 transition-colors text-[10px] font-mono"
                  >
                    <span className={PROVIDER_COLORS[provider]}>{PROVIDER_LABELS[provider]}</span>
                    <ChevronDown className="w-2.5 h-2.5 text-slate-400" />
                  </button>
                  {showProviders && (
                    <div className="absolute right-0 top-7 z-50 bg-white border border-slate-200 rounded-lg shadow-xl w-32 overflow-hidden">
                      {["auto", "gemini", "claude"].map(p => (
                        <button
                          key={p}
                          onClick={() => { setProvider(p); setShowProviders(false); }}
                          className={`w-full text-left px-3 py-2 text-xs font-mono transition-colors hover:bg-slate-50 ${
                            provider === p ? "text-teal-600 font-semibold" : "text-slate-500"
                          } ${availableProviders.includes(p) || p === "auto" ? "" : "opacity-40"}`}
                        >
                          {PROVIDER_LABELS[p]}
                          {availableProviders.includes(p) && <span className="ml-1 text-emerald-500">●</span>}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={clearChat}
                  className="p-1.5 text-slate-400 hover:text-teal-600 transition-colors"
                  title="New chat"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 text-slate-400 hover:text-red-500 transition-colors"
                  title="Close"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Context bar */}
            <div className="mt-2 flex items-center gap-1.5 px-2 py-1 rounded-md bg-slate-50 border border-slate-200">
              <Zap className="w-2.5 h-2.5 text-teal-600 flex-shrink-0" />
              <span className="text-[9px] font-mono uppercase tracking-wider text-slate-500 truncate">
                Context: {location.pathname === "/" ? "Dashboard" : location.pathname.replace(/\//g, " › ").trim()}
              </span>
              {lastProvider && (
                <>
                  <span className="text-slate-300 ml-auto">|</span>
                  <span className={`text-[9px] font-mono flex-shrink-0 ${PROVIDER_COLORS[lastProvider]}`}>
                    via {PROVIDER_LABELS[lastProvider]}
                  </span>
                </>
              )}
            </div>
          </div>

          {/* ── Messages ─────────────────────────────────────────────── */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 copilot-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}>
                {msg.role === "assistant" && (
                  <div className="flex items-center gap-1.5 mb-1">
                    <div className="w-4 h-4 rounded bg-gradient-to-br from-teal-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                      <Bot className="w-2.5 h-2.5 text-white" />
                    </div>
                    <span className="text-[9px] font-mono text-slate-400 uppercase tracking-wider">
                      Gravity Copilot
                    </span>
                  </div>
                )}
                <div
                  className={`relative group max-w-[95%] px-3 py-2.5 text-xs leading-relaxed rounded-xl ${
                    msg.role === "user"
                      ? "bg-teal-600 text-white font-medium rounded-br-sm shadow-sm"
                      : msg.error
                      ? "border border-red-200 bg-red-50 text-red-700 rounded-bl-sm"
                      : "border border-slate-200 bg-white text-slate-700 rounded-bl-sm shadow-sm"
                  }`}
                >
                  {msg.role === "assistant" && !msg.error ? (
                    <RenderMarkdown text={msg.content} />
                  ) : (
                    <span>{msg.content}</span>
                  )}

                  {/* Copy button */}
                  {msg.role === "assistant" && !msg.error && (
                    <button
                      onClick={() => copyMessage(msg.content, i)}
                      className="absolute top-1.5 right-1.5 p-0.5 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-teal-600 transition-all"
                    >
                      {copiedIdx === i ? (
                        <CheckCheck className="w-3 h-3 text-emerald-500" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                    </button>
                  )}

                  {msg.error && msg.retryText && (
                    <button
                      onClick={() => sendMessage(msg.retryText)}
                      disabled={sending}
                      className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-red-700 hover:text-red-800 disabled:opacity-50"
                    >
                      <RotateCcw className="w-3 h-3" /> Retry
                    </button>
                  )}
                </div>
                {msg.timestamp && (
                  <span className="text-[8px] text-slate-400 font-mono mt-0.5 px-1">
                    {msg.timestamp.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                )}
              </div>
            ))}

            {/* Typing indicator */}
            {sending && (
              <div className="flex items-start gap-2">
                <div className="w-4 h-4 rounded bg-gradient-to-br from-teal-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-2.5 h-2.5 text-white" />
                </div>
                <div className="border border-slate-200 bg-white rounded-xl rounded-bl-sm px-3 py-2.5 shadow-sm">
                  <div className="flex gap-1 items-center">
                    <div className="w-1.5 h-1.5 bg-teal-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <div className="w-1.5 h-1.5 bg-teal-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <div className="w-1.5 h-1.5 bg-teal-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* ── Suggestions ─────────────────────────────────────────── */}
          {suggestions.length > 0 && messages.length <= 2 && (
            <div className="flex-shrink-0 px-3 pt-2 pb-1 border-t border-slate-200">
              <div className="font-mono text-[9px] uppercase tracking-widest text-slate-400 mb-1.5">
                Quick prompts
              </div>
              <div className="space-y-1 max-h-28 overflow-y-auto">
                {suggestions.slice(0, 4).map((s, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(s)}
                    className="w-full text-left text-[10px] text-slate-600 hover:text-teal-700 px-2 py-1.5 rounded-md border border-slate-200 hover:border-teal-400 hover:bg-teal-50 transition-all flex items-center gap-2"
                  >
                    <ChevronRight className="w-2.5 h-2.5 flex-shrink-0 text-teal-600" />
                    <span className="truncate">{s}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── Input ─────────────────────────────────────────────────── */}
          <div className="flex-shrink-0 border-t border-slate-200 p-3 bg-white">
            <div className="flex gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything... (Enter to send)"
                rows={1}
                className="flex-1 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 text-xs px-3 py-2 placeholder:text-slate-400 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 focus:outline-none resize-none leading-relaxed"
                style={{ maxHeight: 80, overflowY: "auto" }}
                disabled={sending}
              />
              <div className="flex flex-col gap-1">
                {/* Send button */}
                <button
                  onClick={() => sendMessage()}
                  disabled={sending || !input.trim()}
                  className="w-8 h-8 rounded-lg flex items-center justify-center bg-teal-600 hover:bg-teal-700 disabled:bg-slate-200 disabled:text-slate-400 text-white transition-colors"
                  title="Send"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            <div className="mt-1.5 flex items-center justify-between">
              <span className="text-[8px] font-mono text-slate-400 uppercase tracking-widest">
                Hindi + English supported
              </span>
              <Globe className="w-2.5 h-2.5 text-slate-400" />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
