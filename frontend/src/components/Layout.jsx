import { useState, useRef, useEffect, useCallback } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import AiCopilotPanel from "@/components/AiCopilotPanel";
import VoiceAssistant from "@/components/VoiceAssistant";
import NotificationPanel from "@/components/NotificationPanel";
import {
  Menu, Bot, Search, X, Activity, LogOut,
  ChevronDown, User, Settings, Hammer,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";

// Global search hook
function useGlobalSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const navigate = useNavigate();

  const QUICK_LINKS = [
    { label: "Dashboard", path: "/", icon: "📊" },
    { label: "GST Invoices", path: "/invoices", icon: "🧾" },
    { label: "Purchase Orders", path: "/purchase-orders", icon: "🛒" },
    { label: "Customers", path: "/customers", icon: "👥" },
    { label: "Employees", path: "/hr/employees", icon: "👤" },
    { label: "Payroll", path: "/hr/payroll", icon: "💰" },
    { label: "Attendance", path: "/hr/attendance", icon: "📅" },
    { label: "Products / Inventory", path: "/products", icon: "📦" },
    { label: "GST Accounting", path: "/gst", icon: "🏛️" },
    { label: "Expenses", path: "/expenses", icon: "💳" },
    { label: "Reports", path: "/reports", icon: "📈" },
    { label: "MIS Reports", path: "/mis-reports", icon: "📉" },
    { label: "Accounting", path: "/accounting", icon: "📒" },
    { label: "Ledger & Bank", path: "/ledger", icon: "🏦" },
    { label: "Leads / CRM", path: "/leads", icon: "🎯" },
    { label: "Sales Orders", path: "/sales-orders", icon: "📝" },
    { label: "Suppliers", path: "/suppliers", icon: "🏭" },
    { label: "Gravity AI Copilot", path: "/ai-assistant", icon: "🤖" },
    { label: "Users", path: "/users", icon: "⚙️" },
    { label: "Theme", path: "/admin/theme-settings", icon: "🎨" },
  ];

  const search = (q) => {
    setQuery(q);
    if (!q.trim()) { setResults([]); return; }
    const filtered = QUICK_LINKS.filter(l =>
      l.label.toLowerCase().includes(q.toLowerCase())
    );
    setResults(filtered.slice(0, 6));
  };

  const go = (path) => {
    navigate(path);
    setQuery("");
    setResults([]);
  };

  return { query, results, searching, search, go, setQuery, setResults };
}

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { query, results, search, go, setQuery, setResults } = useGlobalSearch();
  const searchRef = useRef(null);
  const profileRef = useRef(null);
  const searchInputRef = useRef(null);

  // Keyboard shortcut: Ctrl+K or Cmd+K to open search
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => searchInputRef.current?.focus(), 100);
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
        setQuery("");
        setResults([]);
        setProfileOpen(false);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setSearchOpen(false);
        setQuery("");
        setResults([]);
      }
      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setProfileOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Voice → Copilot panel bridge
  const handleVoiceToChat = useCallback((text) => {
    setCopilotOpen(true);
    // Delay to ensure panel is open before attempting to send
    window.__gravityCopilotSendMessage?.(text);
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="h-screen bg-background text-foreground flex overflow-hidden">

      {/* ── Mobile sidebar overlay ───────────────────────────── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/80 z-30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ─────────────────────────────────────────── */}
      <div
        className={`
          fixed lg:relative z-40 inset-y-0 left-0
          w-64 flex-shrink-0 flex flex-col h-full
          transform transition-transform duration-200 ease-in-out
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0
        `}
      >
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} scrollable />
      </div>

      {/* ── Main column ─────────────────────────────────────── */}
      <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden">

        {/* ── Enhanced Topbar ──────────────────────────────── */}
        <header className="flex-shrink-0 z-20 border-b border-border bg-card/95 backdrop-blur-sm text-card-foreground">
          <div className="flex items-center justify-between px-3 sm:px-4 py-2.5 gap-2">

            {/* Left: mobile toggle + status */}
            <div className="flex items-center gap-3 min-w-0">
              <button
                data-testid="sidebar-toggle"
                className="lg:hidden p-1.5 border border-border text-muted-foreground hover:text-primary hover:border-primary transition-colors flex-shrink-0"
                onClick={() => setSidebarOpen(true)}
              >
                <Menu className="w-4 h-4" />
              </button>
              <div className="hidden sm:flex items-center gap-2">
                <div className="w-1.5 h-1.5 bg-green-500 rounded-full pulse-yellow flex-shrink-0" />
                <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                  System: Operational
                </span>
              </div>
            </div>

            {/* Center: Search bar */}
            <div className="flex-1 max-w-md" ref={searchRef}>
              <div className="relative">
                <button
                  onClick={() => { setSearchOpen(true); setTimeout(() => searchInputRef.current?.focus(), 50); }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 bg-muted/40 border border-border hover:border-zinc-500 text-muted-foreground hover:text-foreground transition-colors text-xs"
                  id="global-search-btn"
                >
                  <Search className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="flex-1 text-left truncate">Search ERP modules...</span>
                  <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-muted border border-border text-[9px] font-mono text-muted-foreground">
                    Ctrl+K
                  </kbd>
                </button>

                {/* Search dropdown */}
                {searchOpen && (
                  <div className="absolute top-0 left-0 right-0 z-50 bg-card border border-border shadow-2xl">
                    <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
                      <Search className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                      <input
                        ref={searchInputRef}
                        type="text"
                        value={query}
                        onChange={e => search(e.target.value)}
                        placeholder="Search modules, pages..."
                        className="flex-1 bg-transparent text-foreground text-sm placeholder:text-muted-foreground focus:outline-none"
                        autoFocus
                      />
                      <button onClick={() => { setSearchOpen(false); setQuery(""); setResults([]); }}>
                        <X className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground" />
                      </button>
                    </div>
                    {results.length > 0 ? (
                      <div className="py-1">
                        {results.map((r) => (
                          <button
                            key={r.path}
                            onClick={() => { go(r.path); setSearchOpen(false); }}
                            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-foreground/80 hover:text-foreground hover:bg-muted transition-colors text-left"
                          >
                            <span className="text-base">{r.icon}</span>
                            <span>{r.label}</span>
                          </button>
                        ))}
                      </div>
                    ) : query ? (
                      <div className="px-4 py-3 text-xs text-muted-foreground font-mono">No results for "{query}"</div>
                    ) : (
                      <div className="px-4 py-2">
                        <div className="text-[9px] font-mono uppercase text-muted-foreground tracking-widest mb-1">Quick links</div>
                        {["/", "/invoices", "/products", "/hr/payroll", "/gst", "/ai-assistant"].map(path => {
                          const link = [
                            { label: "Dashboard", path: "/", icon: "📊" },
                            { label: "GST Invoices", path: "/invoices", icon: "🧾" },
                            { label: "Products", path: "/products", icon: "📦" },
                            { label: "Payroll", path: "/hr/payroll", icon: "💰" },
                            { label: "GST Accounting", path: "/gst", icon: "🏛️" },
                            { label: "AI Copilot", path: "/ai-assistant", icon: "🤖" },
                          ].find(l => l.path === path);
                          return link ? (
                            <button key={path} onClick={() => { go(path); setSearchOpen(false); }}
                              className="w-full flex items-center gap-2 px-1 py-1.5 text-xs text-muted-foreground hover:text-primary transition-colors text-left">
                              <span>{link.icon}</span><span>{link.label}</span>
                            </button>
                          ) : null;
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Right: Notifications + AI toggle + Profile */}
            <div className="flex items-center gap-1 flex-shrink-0">
              {/* Date/time — hidden on small screens */}
              <div className="hidden lg:block font-mono text-[10px] uppercase tracking-wider text-muted-foreground mr-2">
                {new Date().toLocaleString("en-IN", {
                  day: "2-digit", month: "short", year: "numeric",
                  hour: "2-digit", minute: "2-digit",
                })}
              </div>

              {/* Notifications */}
              <NotificationPanel />

              {/* AI Copilot toggle */}
              <button
                onClick={() => setCopilotOpen(!copilotOpen)}
                id="ai-copilot-toggle"
                className={`flex items-center gap-1.5 px-2.5 py-1.5 border text-xs font-mono uppercase tracking-wider transition-all ${
                  copilotOpen
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:border-primary hover:text-primary"
                }`}
                title="Toggle AI Copilot Panel"
              >
                <Bot className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Copilot</span>
                {copilotOpen && <div className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse" />}
              </button>

              {/* User profile */}
              <div className="relative" ref={profileRef}>
                <button
                  onClick={() => setProfileOpen(!profileOpen)}
                  className="flex items-center gap-2 px-2 py-1.5 border border-border hover:border-muted-foreground/50 transition-colors"
                  id="user-profile-btn"
                >
                  <div className="w-6 h-6 bg-primary text-primary-foreground font-bold flex items-center justify-center text-xs flex-shrink-0">
                    {user?.name?.[0]?.toUpperCase() || "?"}
                  </div>
                  <span className="hidden sm:block text-xs font-mono text-muted-foreground max-w-20 truncate">
                    {user?.name?.split(" ")[0]}
                  </span>
                  <ChevronDown className="w-3 h-3 text-zinc-500" />
                </button>

                {/* Profile dropdown */}
                {profileOpen && (
                  <div className="absolute right-0 top-10 z-50 w-52 bg-card border border-border shadow-2xl text-card-foreground">
                    <div className="px-4 py-3 border-b border-border">
                      <div className="text-sm font-semibold text-foreground">{user?.name || "—"}</div>
                      <div className="text-[10px] font-mono uppercase text-primary mt-0.5">{user?.role}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5 truncate">{user?.email}</div>
                    </div>
                    <div className="py-1">
                      <button
                        onClick={() => { navigate("/my-portal"); setProfileOpen(false); }}
                        className="w-full flex items-center gap-3 px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      >
                        <User className="w-3.5 h-3.5" />
                        My Portal
                      </button>
                      {user?.role === "admin" && (
                        <button
                          onClick={() => { navigate("/admin/theme-settings"); setProfileOpen(false); }}
                          className="w-full flex items-center gap-3 px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        >
                          <Settings className="w-3.5 h-3.5" />
                          Theme
                        </button>
                      )}
                    </div>
                    <div className="border-t border-border py-1">
                      <button
                        onClick={handleLogout}
                        className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                      >
                        <LogOut className="w-3.5 h-3.5" />
                        Sign out
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* ── Content + Copilot ────────────────────────────── */}
        <div className="flex-1 flex overflow-hidden">
          {/* Main content */}
          <main
            className="flex-1 overflow-y-auto overflow-x-hidden scroll-smooth"
            style={{ scrollBehavior: "smooth" }}
          >
            <div className="p-4 sm:p-5 lg:p-6 min-h-full">
              <Outlet />
            </div>
          </main>

          {/* AI Copilot Panel — right side */}
          <AiCopilotPanel
            isOpen={copilotOpen}
            onClose={() => setCopilotOpen(false)}
          />
        </div>
      </div>

      {/* ── Floating Voice Assistant ─────────────────────── */}
      <VoiceAssistant onSendToChat={(text) => {
        setCopilotOpen(true);
        handleVoiceToChat(text);
      }} />
    </div>
  );
}
