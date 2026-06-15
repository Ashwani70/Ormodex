import { useState, useEffect, useRef, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Bot, Send, X, ChevronRight, Mic, MicOff, RefreshCw,
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
          return <p key={i} className="font-bold text-white">{line.slice(2, -2)}</p>;
        }
        if (line.startsWith("• ") || line.startsWith("- ") || line.startsWith("* ")) {
          return (
            <div key={i} className="flex items-start gap-2">
              <span className="text-yellow-400 mt-0.5 flex-shrink-0">▸</span>
              <span dangerouslySetInnerHTML={{ __html: line.slice(2).replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>") }} />
            </div>
          );
        }
        if (/^\d+\./.test(line)) {
          return (
            <div key={i} className="flex items-start gap-2">
              <span className="text-yellow-400 font-mono text-xs mt-0.5 flex-shrink-0 w-4">{line.match(/^\d+/)[0]}.</span>
              <span dangerouslySetInnerHTML={{ __html: line.replace(/^\d+\.\s*/, "").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>") }} />
            </div>
          );
        }
        if (line.trim() === "") return <div key={i} className="h-1" />;
        return (
          <p key={i}
            dangerouslySetInnerHTML={{
              __html: line
                .replace(/\*\*(.*?)\*\*/g, "<strong class='text-yellow-300'>$1</strong>")
                .replace(/`(.*?)`/g, "<code class='bg-zinc-800 text-yellow-400 px-1 rounded text-xs'>$1</code>")
            }}
          />
        );
      })}
    </div>
  );
}

const PROVIDER_LABELS = {
  auto: "Auto",
  openai: "GPT-4o",
  gemini: "Gemini",
  claude: "Claude",
  groq: "Groq",
  fallback: "Built-in",
};

const PROVIDER_COLORS = {
  openai: "text-green-400",
  gemini: "text-blue-400",
  claude: "text-orange-400",
  groq: "text-purple-400",
  fallback: "text-zinc-500",
  auto: "text-yellow-400",
};

export default function AiCopilotPanel({ isOpen, onClose }) {
  const location = useLocation();
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [provider, setProvider] = useState("auto");
  const [lastProvider, setLastProvider] = useState(null);
  const [listening, setListening] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [showProviders, setShowProviders] = useState(false);
  const [availableProviders, setAvailableProviders] = useState([]);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);

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
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Sorry, I encountered an error. Please try again.",
        error: true,
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

  const startListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toast.error("Voice not supported in this browser");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-IN"; // supports both English and Hindi

    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = () => { setListening(false); toast.error("Voice recognition failed"); };
    recognition.onresult = async (event) => {
      const transcript = event.results[0][0].transcript;
      setListening(false);
      // Try voice command routing first
      try {
        const r = await api.post("/ai/voice-command", {
          transcript,
          current_module: location.pathname,
        });
        if (r.data.intent === "navigate" && r.data.route) {
          toast.success(`Navigating to ${r.data.route}`);
          navigate(r.data.route);
          onClose?.();
        } else if (r.data.intent === "chat") {
          sendMessage(r.data.message || transcript);
        } else if (r.data.intent === "action") {
          sendMessage(`Please ${r.data.action?.replace(/_/g, " ")}: ${transcript}`);
        } else {
          sendMessage(transcript);
        }
      } catch {
        sendMessage(transcript);
      }
    };

    recognition.start();
    recognitionRef.current = recognition;
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setListening(false);
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
      className={`flex flex-col h-full bg-zinc-950 border-l border-zinc-800 transition-all duration-300 ease-in-out ${
        isOpen ? "w-[380px] opacity-100" : "w-0 opacity-0 overflow-hidden"
      }`}
      style={{ minWidth: isOpen ? 380 : 0 }}
    >
      {isOpen && (
        <>
          {/* ── Header ─────────────────────────────────────────────── */}
          <div className="flex-shrink-0 border-b border-zinc-800 px-4 py-3 bg-black">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 bg-yellow-400 flex items-center justify-center flex-shrink-0 relative">
                  <Bot className="w-4 h-4 text-black" />
                  <div className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-green-500 rounded-full border border-black" />
                </div>
                <div>
                  <div className="text-sm font-bold text-white leading-none">Gravity Copilot</div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <Sparkles className="w-2.5 h-2.5 text-yellow-400" />
                    <span className="font-mono text-[9px] uppercase tracking-widest text-yellow-400">
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
                    className="flex items-center gap-1 px-2 py-1 border border-zinc-700 hover:border-yellow-400 transition-colors text-[10px] font-mono"
                  >
                    <span className={PROVIDER_COLORS[provider]}>{PROVIDER_LABELS[provider]}</span>
                    <ChevronDown className="w-2.5 h-2.5 text-zinc-400" />
                  </button>
                  {showProviders && (
                    <div className="absolute right-0 top-7 z-50 bg-zinc-900 border border-zinc-700 shadow-xl w-32">
                      {["auto", "openai", "gemini", "claude", "groq"].map(p => (
                        <button
                          key={p}
                          onClick={() => { setProvider(p); setShowProviders(false); }}
                          className={`w-full text-left px-3 py-2 text-xs font-mono transition-colors hover:bg-zinc-800 ${
                            provider === p ? "text-yellow-400" : "text-zinc-400"
                          } ${availableProviders.includes(p) || p === "auto" ? "" : "opacity-40"}`}
                        >
                          {PROVIDER_LABELS[p]}
                          {availableProviders.includes(p) && <span className="ml-1 text-green-500">●</span>}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={clearChat}
                  className="p-1.5 text-zinc-600 hover:text-yellow-400 transition-colors"
                  title="New chat"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors"
                  title="Close"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Context bar */}
            <div className="mt-2 flex items-center gap-1.5 px-2 py-1 bg-zinc-900 border border-zinc-800">
              <Zap className="w-2.5 h-2.5 text-yellow-400 flex-shrink-0" />
              <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500 truncate">
                Context: {location.pathname === "/" ? "Dashboard" : location.pathname.replace(/\//g, " › ").trim()}
              </span>
              {lastProvider && (
                <>
                  <span className="text-zinc-700 ml-auto">|</span>
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
                    <div className="w-4 h-4 bg-yellow-400 flex items-center justify-center flex-shrink-0">
                      <Bot className="w-2.5 h-2.5 text-black" />
                    </div>
                    <span className="text-[9px] font-mono text-zinc-600 uppercase tracking-wider">
                      Gravity Copilot
                    </span>
                  </div>
                )}
                <div
                  className={`relative group max-w-[95%] px-3 py-2.5 text-xs leading-relaxed ${
                    msg.role === "user"
                      ? "bg-yellow-400 text-black font-medium"
                      : msg.error
                      ? "border border-red-800 bg-red-950/60 text-red-300"
                      : "border border-zinc-800 bg-zinc-900/80 text-zinc-200"
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
                      className="absolute top-1.5 right-1.5 p-0.5 opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-yellow-400 transition-all"
                    >
                      {copiedIdx === i ? (
                        <CheckCheck className="w-3 h-3 text-green-400" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                    </button>
                  )}
                </div>
                {msg.timestamp && (
                  <span className="text-[8px] text-zinc-700 font-mono mt-0.5 px-1">
                    {msg.timestamp.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                )}
              </div>
            ))}

            {/* Typing indicator */}
            {sending && (
              <div className="flex items-start gap-2">
                <div className="w-4 h-4 bg-yellow-400 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-2.5 h-2.5 text-black" />
                </div>
                <div className="border border-zinc-800 bg-zinc-900 px-3 py-2.5">
                  <div className="flex gap-1 items-center">
                    <div className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <div className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <div className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* ── Suggestions ─────────────────────────────────────────── */}
          {suggestions.length > 0 && messages.length <= 2 && (
            <div className="flex-shrink-0 px-3 pt-2 pb-1 border-t border-zinc-900">
              <div className="font-mono text-[9px] uppercase tracking-widest text-zinc-600 mb-1.5">
                Quick prompts
              </div>
              <div className="space-y-1 max-h-28 overflow-y-auto">
                {suggestions.slice(0, 4).map((s, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(s)}
                    className="w-full text-left text-[10px] text-zinc-400 hover:text-yellow-400 px-2 py-1.5 border border-zinc-800 hover:border-yellow-400/50 hover:bg-yellow-400/5 transition-all flex items-center gap-2"
                  >
                    <ChevronRight className="w-2.5 h-2.5 flex-shrink-0 text-yellow-400" />
                    <span className="truncate">{s}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── Input ─────────────────────────────────────────────────── */}
          <div className="flex-shrink-0 border-t border-zinc-800 p-3 bg-black">
            {/* Voice indicator */}
            {listening && (
              <div className="mb-2 flex items-center gap-2 px-3 py-1.5 bg-red-950/40 border border-red-800">
                <div className="w-2 h-2 bg-red-400 rounded-full animate-pulse" />
                <span className="text-xs text-red-400 font-mono">Listening... speak now</span>
              </div>
            )}
            <div className="flex gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything... (Enter to send)"
                rows={1}
                className="flex-1 bg-zinc-900 border border-zinc-700 text-white text-xs px-3 py-2 placeholder:text-zinc-600 focus:border-yellow-400 focus:outline-none resize-none leading-relaxed"
                style={{ maxHeight: 80, overflowY: "auto" }}
                disabled={sending}
              />
              <div className="flex flex-col gap-1">
                {/* Voice button */}
                <button
                  onClick={listening ? stopListening : startListening}
                  className={`w-8 h-8 flex items-center justify-center border transition-all ${
                    listening
                      ? "border-red-500 bg-red-950/40 text-red-400 animate-pulse"
                      : "border-zinc-700 hover:border-yellow-400 text-zinc-400 hover:text-yellow-400"
                  }`}
                  title={listening ? "Stop listening" : "Voice input (Hindi/English)"}
                >
                  {listening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                </button>
                {/* Send button */}
                <button
                  onClick={() => sendMessage()}
                  disabled={sending || !input.trim()}
                  className="w-8 h-8 flex items-center justify-center bg-yellow-400 hover:bg-yellow-300 disabled:bg-zinc-800 disabled:text-zinc-600 text-black transition-colors"
                  title="Send"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            <div className="mt-1.5 flex items-center justify-between">
              <span className="text-[8px] font-mono text-zinc-700 uppercase tracking-widest">
                Hindi + English supported
              </span>
              <Globe className="w-2.5 h-2.5 text-zinc-700" />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
