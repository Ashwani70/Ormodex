import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import {
  PageHeader,
  StatTile,
  SectionTitle,
  PrimaryButton,
  SecondaryButton,
  EmptyState,
} from "@/components/ui-kit";
import { toast } from "sonner";
import {
  Bot, Send, RefreshCw, AlertTriangle, TrendingUp, Package,
  Users, Clock, Upload, Zap, Eye, BarChart2, Search,
  Mic, MicOff, History, Plus, Trash2, Copy, CheckCheck,
  ChevronRight, Globe, Star, Sparkles, MessageSquare,
  ArrowRight, Shield, DollarSign,
} from "lucide-react";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const TABS = [
  { id: "chat", label: "AI Chat", icon: MessageSquare },
  { id: "insights", label: "Business Insights", icon: TrendingUp },
  { id: "fraud", label: "Fraud Alerts", icon: Shield },
  { id: "cashflow", label: "Cash Flow", icon: DollarSign },
  { id: "ocr", label: "Document OCR", icon: Eye },
];

const PROVIDER_LABELS = {
  auto: "Auto", openai: "GPT-4o", gemini: "Gemini 2.0",
  claude: "Claude Sonnet", groq: "Groq Llama", fallback: "Built-in",
};
const PROVIDER_COLORS = {
  openai: "text-green-400", gemini: "text-blue-400",
  claude: "text-orange-400", groq: "text-purple-400",
  fallback: "text-zinc-500", auto: "text-yellow-400",
};

// Markdown-lite renderer
function RenderMarkdown({ text }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("• ") || line.startsWith("- ") || line.startsWith("* ")) {
          return (
            <div key={i} className="flex items-start gap-2">
              <span className="text-yellow-400 mt-0.5 flex-shrink-0">▸</span>
              <span dangerouslySetInnerHTML={{ __html: line.slice(2).replace(/\*\*(.*?)\*\*/g, "<strong class='text-yellow-300'>$1</strong>") }} />
            </div>
          );
        }
        if (/^\d+\./.test(line)) {
          return (
            <div key={i} className="flex items-start gap-2">
              <span className="text-yellow-400 font-mono text-xs mt-0.5 flex-shrink-0 w-5">{line.match(/^\d+/)[0]}.</span>
              <span dangerouslySetInnerHTML={{ __html: line.replace(/^\d+\.\s*/, "").replace(/\*\*(.*?)\*\*/g, "<strong class='text-yellow-300'>$1</strong>") }} />
            </div>
          );
        }
        if (line.trim() === "") return <div key={i} className="h-1.5" />;
        return (
          <p key={i}
            dangerouslySetInnerHTML={{
              __html: line
                .replace(/\*\*(.*?)\*\*/g, "<strong class='text-yellow-300'>$1</strong>")
                .replace(/`(.*?)`/g, "<code class='bg-zinc-800 text-yellow-400 px-1 rounded text-xs font-mono'>$1</code>")
            }}
          />
        );
      })}
    </div>
  );
}

const QUICK_ACTIONS = [
  { label: "Today's Sales", query: "Show today's total sales and invoice count" },
  { label: "Pending Invoices", query: "Show all unpaid/pending invoices with amounts" },
  { label: "Generate GST Report", query: "Generate a GST summary report for this month" },
  { label: "Calculate Payroll", query: "Show payroll summary and total salary for this month" },
  { label: "Employee Attendance", query: "Show today's employee attendance status" },
  { label: "Low Stock Items", query: "Which products are below minimum stock level?" },
  { label: "Monthly Revenue", query: "Show this month's total revenue vs last month" },
  { label: "Create Purchase Order", query: "How do I create a new purchase order in the ERP?" },
];

const INSIGHT_ICONS = {
  SALES_SUMMARY: TrendingUp, TOP_CUSTOMER: Star,
  PENDING_APPROVALS: Clock, LOW_STOCK_ALERT: Package, UNPAID_INVOICES: AlertTriangle,
};
const SEVERITY_COLORS = {
  HIGH: "border-red-700 bg-red-950/30 text-red-400",
  MEDIUM: "border-yellow-700 bg-yellow-950/30 text-yellow-400",
  LOW: "border-blue-700 bg-blue-950/30 text-blue-400",
};

export default function AiAssistant() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("chat");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [sending, setSending] = useState(false);
  const [provider, setProvider] = useState("auto");
  const [availableProviders, setAvailableProviders] = useState([]);
  const [lastProvider, setLastProvider] = useState(null);
  const [insights, setInsights] = useState(null);
  const [fraudAlerts, setFraudAlerts] = useState(null);
  const [cashflow, setCashflow] = useState(null);
  const [ocrResult, setOcrResult] = useState(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [forecastMonths, setForecastMonths] = useState(3);
  const [sessions, setSessions] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [listening, setListening] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState(null);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Initial greeting
  useEffect(() => {
    setMessages([{
      role: "assistant",
      content: "**Hello! I am Gravity ERP AI Copilot** 🤖\n\nI can help you with:\n• Sales, invoices & GST compliance\n• Inventory & purchase management\n• HR, payroll & attendance\n• Business analytics & forecasting\n• Creating ERP records\n• Explaining ERP issues\n\nI support **Hindi** and **English**. What would you like to know?",
      timestamp: new Date(),
    }]);
    loadProviders();
    loadSessions();
  }, []);

  const loadProviders = async () => {
    try {
      const r = await api.get("/ai/providers");
      setAvailableProviders(r.data.available || []);
    } catch {}
  };

  const loadSessions = async () => {
    try {
      const r = await api.get("/ai/history");
      setSessions(r.data.sessions || []);
    } catch {}
  };

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
  }, [input, sending, sessionId, provider]);

  const startListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { toast.error("Voice not supported in this browser"); return; }
    const recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.continuous = false;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognition.onresult = (e) => sendMessage(e.results[0][0].transcript);
    recognition.start();
    recognitionRef.current = recognition;
  };

  const copyMessage = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const clearChat = () => {
    setMessages([{
      role: "assistant",
      content: "**New session started.** How can I help you?",
      timestamp: new Date(),
    }]);
    setSessionId(null);
    setLastProvider(null);
  };

  const deleteSession = async (sid) => {
    try {
      await api.delete(`/ai/chat/history/${sid}`);
      setSessions(prev => prev.filter(s => s.session_id !== sid));
      if (sid === sessionId) clearChat();
      toast.success("Session deleted");
    } catch { toast.error("Failed to delete session"); }
  };

  const loadInsights = async () => {
    try { const r = await api.get("/ai/business-insights"); setInsights(r.data); }
    catch { toast.error("Failed to load insights"); }
  };
  const loadFraud = async () => {
    try { const r = await api.get("/ai/fraud-alerts"); setFraudAlerts(r.data); }
    catch { toast.error("Failed to load fraud alerts"); }
  };
  const loadCashflow = async () => {
    try { const r = await api.get("/ai/cash-flow-forecast", { params: { months: forecastMonths } }); setCashflow(r.data); }
    catch { toast.error("Failed to load cash flow forecast"); }
  };
  const handleOcrUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setOcrLoading(true); setOcrResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("doc_type", "INVOICE");
      const r = await api.post("/ai/parse-document", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setOcrResult(r.data); toast.success("Document parsed successfully");
    } catch (e) { toast.error(e.response?.data?.detail || "OCR failed"); }
    finally { setOcrLoading(false); }
  };

  useEffect(() => {
    if (tab === "insights") loadInsights();
    if (tab === "fraud") loadFraud();
    if (tab === "cashflow") loadCashflow();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div data-testid="ai-assistant-page" className="space-y-5">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 border-b border-zinc-800 pb-5">
        <div>
          <div className="label-overline mb-2 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
            AI Intelligence Hub
          </div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight text-zinc-50 uppercase">
            Gravity Copilot
          </h1>
          <p className="mt-2 text-sm text-zinc-400 max-w-xl">
            Your AI-powered ERP assistant — natural language queries, business insights, fraud detection, document OCR, and voice commands in Hindi & English.
          </p>
        </div>

        {/* Provider status */}
        <div className="flex-shrink-0 bg-zinc-950 border border-zinc-800 p-4 min-w-52">
          <div className="font-mono text-[9px] uppercase tracking-widest text-zinc-500 mb-3">AI Providers</div>
          <div className="space-y-1.5">
            {[
              { key: "openai", label: "OpenAI GPT-4o" },
              { key: "gemini", label: "Google Gemini" },
              { key: "claude", label: "Anthropic Claude" },
              { key: "groq", label: "Groq Llama" },
            ].map(p => (
              <div key={p.key} className="flex items-center justify-between">
                <span className="text-xs text-zinc-400 font-mono">{p.label}</span>
                <span className={`text-[9px] font-mono px-1.5 py-0.5 border ${
                  availableProviders.includes(p.key)
                    ? "border-green-700 text-green-400 bg-green-950/20"
                    : "border-zinc-800 text-zinc-600"
                }`}>
                  {availableProviders.includes(p.key) ? "ACTIVE" : "NOT SET"}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-2 border-t border-zinc-800 flex items-center gap-2">
            <span className="text-[9px] font-mono text-zinc-600">Provider:</span>
            <select
              value={provider}
              onChange={e => setProvider(e.target.value)}
              className="flex-1 bg-black border border-zinc-700 text-xs font-mono text-white px-2 py-1 focus:border-yellow-400 focus:outline-none"
            >
              {["auto", "openai", "gemini", "claude", "groq"].map(p => (
                <option key={p} value={p}>{PROVIDER_LABELS[p]}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────── */}
      <div className="flex gap-px bg-zinc-800 border border-zinc-800 overflow-x-auto">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              data-testid={`tab-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`flex-shrink-0 flex items-center gap-2 px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors ${
                tab === t.id
                  ? "bg-yellow-400 text-black font-bold"
                  : "bg-zinc-950 text-zinc-400 hover:text-white hover:bg-zinc-900"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* ── AI Chat ──────────────────────────────────────────────────── */}
      {tab === "chat" && (
        <div className="flex gap-4" style={{ height: "calc(100vh - 360px)", minHeight: 480 }}>
          {/* Session history sidebar */}
          <div className={`flex-shrink-0 flex flex-col border border-zinc-800 bg-zinc-950 transition-all duration-200 ${showHistory ? "w-56" : "w-0 overflow-hidden border-0"}`}>
            {showHistory && (
              <>
                <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-black">
                  <span className="font-mono text-[9px] uppercase tracking-widest text-zinc-500">History</span>
                  <button onClick={clearChat} className="p-1 text-zinc-600 hover:text-yellow-400">
                    <Plus className="w-3 h-3" />
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto py-1">
                  {sessions.map(s => (
                    <div key={s.session_id} className="group flex items-center gap-1 px-2 py-1.5 hover:bg-zinc-900">
                      <button
                        className="flex-1 text-left text-[10px] text-zinc-400 truncate font-mono"
                        onClick={() => setSessionId(s.session_id)}
                        title={s.title}
                      >
                        {s.title || "Chat session"}
                      </button>
                      <button
                        onClick={() => deleteSession(s.session_id)}
                        className="opacity-0 group-hover:opacity-100 p-0.5 text-zinc-700 hover:text-red-400"
                      >
                        <Trash2 className="w-2.5 h-2.5" />
                      </button>
                    </div>
                  ))}
                  {sessions.length === 0 && (
                    <div className="px-3 py-4 text-[9px] font-mono text-zinc-700 uppercase">No history yet</div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Main chat area */}
          <div className="flex-1 flex flex-col border border-zinc-800 min-w-0">
            {/* Chat toolbar */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-black flex-shrink-0">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { setShowHistory(!showHistory); if (!showHistory) loadSessions(); }}
                  className={`flex items-center gap-1.5 px-2 py-1 text-[10px] font-mono border transition-colors ${
                    showHistory ? "border-yellow-400 text-yellow-400" : "border-zinc-700 text-zinc-500 hover:border-zinc-600"
                  }`}
                >
                  <History className="w-3 h-3" />
                  History
                </button>
                <button onClick={clearChat} className="flex items-center gap-1.5 px-2 py-1 text-[10px] font-mono border border-zinc-700 text-zinc-500 hover:border-zinc-600 hover:text-white transition-colors">
                  <Plus className="w-3 h-3" />
                  New Chat
                </button>
              </div>
              {lastProvider && (
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-[9px] text-zinc-600">via</span>
                  <span className={`font-mono text-[9px] ${PROVIDER_COLORS[lastProvider]}`}>{PROVIDER_LABELS[lastProvider]}</span>
                </div>
              )}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-zinc-950">
              {messages.map((msg, i) => (
                <div key={i} className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}>
                  {msg.role === "assistant" && (
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-5 h-5 bg-yellow-400 flex items-center justify-center flex-shrink-0">
                        <Bot className="w-3 h-3 text-black" />
                      </div>
                      <span className="text-[9px] text-zinc-600 font-mono uppercase tracking-wider">Gravity Copilot</span>
                      {msg.provider && (
                        <span className={`text-[8px] font-mono px-1 border border-zinc-800 ${PROVIDER_COLORS[msg.provider]}`}>
                          {PROVIDER_LABELS[msg.provider]}
                        </span>
                      )}
                    </div>
                  )}
                  <div className={`relative group max-w-2xl px-4 py-3 text-sm ${
                    msg.role === "user"
                      ? "bg-yellow-400 text-black font-medium"
                      : msg.error
                      ? "border border-red-800 bg-red-950/30 text-red-300"
                      : "border border-zinc-700 bg-zinc-900 text-zinc-200"
                  }`}>
                    {msg.role === "assistant" && !msg.error ? (
                      <RenderMarkdown text={msg.content} />
                    ) : (
                      <span>{msg.content}</span>
                    )}
                    {msg.role === "assistant" && !msg.error && (
                      <button
                        onClick={() => copyMessage(msg.content, i)}
                        className="absolute top-2 right-2 p-0.5 opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-yellow-400 transition-all"
                      >
                        {copiedIdx === i ? <CheckCheck className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
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
              {sending && (
                <div className="flex justify-start">
                  <div className="border border-zinc-700 bg-zinc-900 px-4 py-3">
                    <div className="flex gap-1">
                      <div className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Quick Actions */}
            <div className="flex-shrink-0 px-4 pt-3 pb-2 border-t border-zinc-800 flex flex-wrap gap-1.5">
              {QUICK_ACTIONS.slice(0, 4).map(a => (
                <button
                  key={a.label}
                  onClick={() => sendMessage(a.query)}
                  className="text-[9px] font-mono uppercase px-2 py-1 border border-zinc-700 text-zinc-400 hover:border-yellow-400 hover:text-yellow-400 transition-colors"
                >
                  {a.label}
                </button>
              ))}
            </div>

            {/* Input */}
            <div className="flex-shrink-0 flex gap-2 p-3 border-t border-zinc-800">
              {listening && (
                <div className="absolute bottom-20 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-2 bg-red-950/60 border border-red-800 text-red-400 text-xs font-mono">
                  <div className="w-2 h-2 bg-red-400 rounded-full animate-pulse" />
                  Listening... speak now (Hindi / English)
                </div>
              )}
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                placeholder="Ask anything in Hindi or English... (Enter to send)"
                className="flex-1 bg-black border border-zinc-700 text-white text-sm px-3 py-2.5 placeholder:text-zinc-600 focus:border-yellow-400 focus:outline-none"
                data-testid="chat-input"
              />
              <button
                onClick={listening ? () => { recognitionRef.current?.stop(); setListening(false); } : startListening}
                className={`px-3 border transition-colors ${
                  listening ? "border-red-500 bg-red-950/30 text-red-400 animate-pulse" : "border-zinc-700 text-zinc-500 hover:border-yellow-400 hover:text-yellow-400"
                }`}
                title="Voice input"
              >
                {listening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>
              <PrimaryButton onClick={() => sendMessage()} disabled={sending || !input.trim()} icon={Send} testid="send-btn">
                {sending ? "..." : "Send"}
              </PrimaryButton>
            </div>
          </div>

          {/* Quick Actions sidebar */}
          <div className="hidden xl:flex flex-col w-48 flex-shrink-0 border border-zinc-800 bg-zinc-950">
            <div className="px-3 py-2 border-b border-zinc-800 bg-black">
              <div className="font-mono text-[9px] uppercase tracking-widest text-zinc-500 flex items-center gap-1.5">
                <Zap className="w-2.5 h-2.5 text-yellow-400" />
                Quick Actions
              </div>
            </div>
            <div className="flex-1 overflow-y-auto py-2 space-y-0.5">
              {QUICK_ACTIONS.map(a => (
                <button
                  key={a.label}
                  onClick={() => sendMessage(a.query)}
                  className="w-full text-left flex items-center gap-2 px-3 py-2 text-[10px] text-zinc-400 hover:text-yellow-400 hover:bg-yellow-400/5 transition-colors"
                >
                  <ChevronRight className="w-2.5 h-2.5 flex-shrink-0 text-yellow-400" />
                  {a.label}
                </button>
              ))}
            </div>
            <div className="p-3 border-t border-zinc-800">
              <button
                onClick={() => navigate("/ai-assistant")}
                className="w-full flex items-center justify-center gap-1.5 py-2 bg-yellow-400/10 border border-yellow-400/30 text-yellow-400 text-[9px] font-mono uppercase tracking-wider hover:bg-yellow-400/20 transition-colors"
              >
                <Globe className="w-3 h-3" />
                Hindi / English
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Business Insights ─────────────────────────────────────── */}
      {tab === "insights" && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <SecondaryButton icon={RefreshCw} onClick={loadInsights}>Refresh</SecondaryButton>
          </div>
          {insights ? (
            insights.insights.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {insights.insights.map((ins, i) => {
                  const Icon = INSIGHT_ICONS[ins.type] || Zap;
                  return (
                    <div key={i} className={`border p-5 ${ins.priority === "HIGH" ? "border-yellow-700/50 bg-yellow-950/10" : "border-zinc-800 bg-zinc-900"}`}>
                      <div className="flex items-center gap-3 mb-3">
                        <div className="w-9 h-9 bg-yellow-400 flex items-center justify-center flex-shrink-0">
                          <Icon className="w-4.5 h-4.5 text-black" />
                        </div>
                        <div>
                          <div className="text-sm font-semibold text-white">{ins.title}</div>
                          {ins.priority === "HIGH" && (
                            <span className="text-[9px] font-mono text-yellow-400 uppercase">High Priority</span>
                          )}
                        </div>
                      </div>
                      <div className="font-display font-black text-4xl text-yellow-400">
                        {typeof ins.value === "number" && ins.value > 1000 ? `₹${inr(ins.value)}` : ins.value}
                      </div>
                      {ins.name && <div className="text-sm text-zinc-400 mt-1">{ins.name}</div>}
                      {ins.count && <div className="text-xs text-zinc-500 mt-1">{ins.count} transactions</div>}
                      {ins.trend !== undefined && (
                        <div className={`text-xs font-mono mt-2 ${ins.trend >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {ins.trend >= 0 ? "↑" : "↓"} {Math.abs(ins.trend).toFixed(1)}% vs last month
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState message="No insights generated — add some ERP data first" />
            )
          ) : (
            <EmptyState message="Click Refresh to load AI insights" action={<PrimaryButton onClick={loadInsights}>Load Insights</PrimaryButton>} />
          )}
        </div>
      )}

      {/* ── Fraud Alerts ──────────────────────────────────────────── */}
      {tab === "fraud" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              {fraudAlerts && (
                <div className="flex items-center gap-2">
                  <AlertTriangle className={`w-5 h-5 ${fraudAlerts.alert_count > 0 ? "text-red-400" : "text-green-400"}`} />
                  <span className="text-sm text-white">{fraudAlerts.alert_count} anomaly alerts detected</span>
                </div>
              )}
            </div>
            <SecondaryButton icon={Search} onClick={loadFraud}>Scan Now</SecondaryButton>
          </div>
          {fraudAlerts ? (
            fraudAlerts.alerts.length > 0 ? (
              <div className="space-y-3">
                {fraudAlerts.alerts.map((alert, i) => (
                  <div key={i} className={`border p-4 ${SEVERITY_COLORS[alert.severity] || "border-zinc-800 bg-zinc-900 text-zinc-400"}`}>
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[9px] font-mono uppercase font-bold">{alert.severity}</span>
                          <span className="text-[9px] font-mono text-zinc-500">{alert.type}</span>
                        </div>
                        <p className="text-sm">{alert.message}</p>
                        {alert.description && <p className="text-xs mt-1 opacity-75">{alert.description}</p>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="border border-green-800 bg-green-950/20 p-8 text-center">
                <div className="text-green-400 text-5xl mb-3">✓</div>
                <div className="text-green-400 font-display font-bold text-lg">No anomalies detected</div>
                <div className="text-xs text-zinc-500 mt-2 font-mono">All transactions appear normal</div>
              </div>
            )
          ) : (
            <EmptyState message="Click 'Scan Now' to run AI fraud detection" />
          )}
        </div>
      )}

      {/* ── Cash Flow Forecast ────────────────────────────────────── */}
      {tab === "cashflow" && (
        <div className="space-y-4">
          <div className="flex gap-3 items-center">
            <span className="label-overline">Forecast Months:</span>
            <select
              value={forecastMonths}
              onChange={e => setForecastMonths(parseInt(e.target.value))}
              className="bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400 focus:outline-none"
            >
              <option value={3}>3 months</option>
              <option value={6}>6 months</option>
              <option value={12}>12 months</option>
            </select>
            <PrimaryButton onClick={loadCashflow}>Generate Forecast</PrimaryButton>
          </div>
          {cashflow ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <StatTile label="Avg Monthly Sales" value={`₹${inr(cashflow.avg_monthly_sales)}`} accent />
                <StatTile label="Avg Monthly Expenses" value={`₹${inr(cashflow.avg_monthly_expenses)}`} />
                <StatTile label="Avg Net Cash" value={`₹${inr(cashflow.avg_monthly_sales - cashflow.avg_monthly_expenses)}`} />
              </div>
              <div className="border border-zinc-800 bg-zinc-950 p-5">
                <SectionTitle>Projected Cash Flow ({forecastMonths} months)</SectionTitle>
                <table className="w-full text-sm mt-3">
                  <thead>
                    <tr className="label-overline border-b border-zinc-800">
                      <th className="text-left py-2">Month</th>
                      <th className="text-right py-2">Proj. Sales</th>
                      <th className="text-right py-2">Proj. Expenses</th>
                      <th className="text-right py-2">Net Cash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cashflow.forecast.map((f, i) => (
                      <tr key={i} className="border-b border-zinc-900">
                        <td className="py-2 font-mono text-zinc-400">{f.month}</td>
                        <td className="py-2 text-right tabular text-green-400">₹{inr(f.projected_sales)}</td>
                        <td className="py-2 text-right tabular text-red-400">₹{inr(f.projected_expenses)}</td>
                        <td className={`py-2 text-right tabular font-bold ${f.projected_net_cash >= 0 ? "text-yellow-400" : "text-red-400"}`}>
                          {f.projected_net_cash >= 0 ? "+" : ""}₹{inr(f.projected_net_cash)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs text-zinc-700 mt-3 font-mono">* Based on 5% monthly sales growth, 2% expense growth from historical averages.</p>
              </div>
            </>
          ) : (
            <EmptyState message="Click 'Generate Forecast' to run AI cash flow prediction" />
          )}
        </div>
      )}

      {/* ── Document OCR ──────────────────────────────────────────── */}
      {tab === "ocr" && (
        <div className="space-y-4 max-w-2xl">
          <div>
            <SectionTitle><Eye className="w-4 h-4" /> AI Document Parser</SectionTitle>
            <p className="text-sm text-zinc-400 mt-1">Upload an invoice image (JPG, PNG) or PDF to automatically extract all fields using AI vision.</p>
          </div>
          <div
            className="border-2 border-dashed border-zinc-700 hover:border-yellow-400 transition-colors p-10 text-center cursor-pointer group"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="w-12 h-12 text-zinc-600 group-hover:text-yellow-400 mx-auto mb-3 transition-colors" />
            <div className="text-zinc-400 text-sm font-medium">Click to upload invoice / document</div>
            <div className="text-zinc-600 text-xs mt-1 font-mono">Supports: JPG, PNG, PDF</div>
            <input ref={fileInputRef} type="file" accept="image/*,.pdf" onChange={handleOcrUpload} className="hidden" data-testid="ocr-upload" />
          </div>

          {ocrLoading && (
            <div className="border border-yellow-800 bg-yellow-950/20 p-5 text-center">
              <div className="w-8 h-8 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <div className="text-yellow-400 font-mono text-sm">Parsing document with AI Vision...</div>
            </div>
          )}

          {ocrResult && (
            <div className="border border-zinc-700 bg-zinc-900 p-4">
              <div className="flex items-center justify-between mb-3">
                <SectionTitle>Extracted Data</SectionTitle>
                <span className={`text-[9px] font-mono px-2 py-0.5 border ${ocrResult.status === "PROCESSED" ? "border-green-700 text-green-400" : "border-yellow-700 text-yellow-400"}`}>
                  {ocrResult.status}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(ocrResult.extracted_data || {}).filter(([k]) => k !== "items").map(([key, val]) => (
                  <div key={key} className="flex justify-between py-1.5 border-b border-zinc-800">
                    <span className="text-zinc-500 font-mono text-xs">{key.replace(/_/g, " ")}</span>
                    <span className="text-white text-xs text-right ml-2">{String(val)}</span>
                  </div>
                ))}
              </div>
              {ocrResult.extracted_data?.items?.length > 0 && (
                <div className="mt-4">
                  <div className="label-overline mb-2">Line Items</div>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="label-overline border-b border-zinc-800">
                        <th className="text-left py-1">Description</th>
                        <th className="text-right py-1">Qty</th>
                        <th className="text-right py-1">Price</th>
                        <th className="text-right py-1">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ocrResult.extracted_data.items.map((item, i) => (
                        <tr key={i} className="border-b border-zinc-900">
                          <td className="py-1.5 text-white">{item.description}</td>
                          <td className="py-1.5 text-right tabular text-zinc-400">{item.quantity}</td>
                          <td className="py-1.5 text-right tabular text-zinc-400">₹{inr(item.unit_price)}</td>
                          <td className="py-1.5 text-right tabular text-yellow-400">₹{inr(item.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="mt-3 text-xs text-zinc-600 font-mono">
                Confidence: {ocrResult.extracted_data?.confidence > 0
                  ? `${(ocrResult.extracted_data.confidence * 100).toFixed(0)}%`
                  : "Set OPENAI_API_KEY for AI-powered OCR"}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
