import { useState, useRef, useEffect } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import AiCopilotPanel from "@/components/AiCopilotPanel";
import NotificationPanel from "@/components/NotificationPanel";
import KeyboardShortcutsHelp from "@/components/KeyboardShortcutsHelp";
import GlobalSearch from "@/components/GlobalSearch";
import WarehousePicker from "@/components/WarehousePicker";
import { useKeyboardShortcuts, isInputFocused } from "@/hooks/useKeyboardShortcuts";
import { useGlobalBackNavigation } from "@/hooks/useGlobalBackNavigation";
import {
  Menu, Bot, Search, Activity, LogOut,
  ChevronDown, User, Settings, Hammer, Keyboard,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useModalStackRegistration } from "@/context/ModalStackContext";
import { isAdminRole } from "@/lib/navItems";

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [warehousePickerOpen, setWarehousePickerOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const profileRef = useRef(null);

  const openSearch = () => setSearchOpen(true);
  const closeSearch = () => setSearchOpen(false);

  // Global "Back Navigation": Esc / Alt+Left / Cmd+[ / mouse back button →
  // previous page, or Dashboard if there's nothing behind this one. Mounted
  // once here since Layout wraps every authenticated module.
  useGlobalBackNavigation({ fallbackPath: "/" });

  // The profile dropdown / shortcuts-help panel aren't <Modal> instances, but
  // they're still "overlays that Escape should close first" — register them
  // the same way so back-nav backs off while open. GlobalSearch registers
  // itself (it owns its own open state + Radix Dialog's built-in Escape).
  useModalStackRegistration(profileOpen || shortcutsOpen);

  // Navigation + help shortcuts (G+letter, ?, Ctrl+/)
  useKeyboardShortcuts({
    onToggleHelp: () => setShortcutsOpen((v) => !v),
    onOpenSearch: openSearch,
    onToggleCopilot: () => setCopilotOpen((v) => !v),
    onOpenWarehousePicker: () => setWarehousePickerOpen(true),
  });

  // Ctrl+K → search; Escape → close profile/shortcuts; F11 → fullscreen; F12 → Settings
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        openSearch();
      }
      if (e.key === "Escape" && (profileOpen || shortcutsOpen)) {
        e.stopPropagation();
        setProfileOpen(false);
        setShortcutsOpen(false);
      }
      // F11 → browser/OS fullscreen toggle (generic, works on every page)
      if (e.key === "F11") {
        e.preventDefault();
        if (document.fullscreenElement) {
          document.exitFullscreen?.();
        } else {
          document.documentElement.requestFullscreen?.();
        }
      }
      // F12 → open Settings (generic navigation shortcut; DevTools still
      // opens too in most browsers since we don't stop propagation here)
      if (e.key === "F12" && !isInputFocused()) {
        navigate("/admin/theme-settings");
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileOpen, shortcutsOpen]);

  // Close profile dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setProfileOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
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
          w-[280px] flex-shrink-0 flex flex-col h-full
          transform transition-transform duration-200 ease-in-out
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0
        `}
      >
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} onHelp={() => setShortcutsOpen(true)} scrollable />
      </div>

      {/* ── Main column ─────────────────────────────────────── */}
      <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden">

        {/* ── Topbar ────────────────────────────────────────── */}
        <header className="flex-shrink-0 z-20 bg-card text-card-foreground" style={{ borderBottom: "1px solid hsl(var(--border))" }}>
          <div className="flex items-center justify-between px-4 sm:px-5 py-3 gap-3">

            {/* Left: mobile toggle */}
            <div className="flex items-center gap-3 min-w-0">
              <button
                data-testid="sidebar-toggle"
                className="lg:hidden p-1.5 rounded-lg border border-border text-muted-foreground hover:text-primary hover:border-primary transition-colors flex-shrink-0"
                onClick={() => setSidebarOpen(true)}
              >
                <Menu className="w-4 h-4" />
              </button>
            </div>

            {/* Center: Search bar — opens the GlobalSearch command palette */}
            <div className="flex-1 max-w-md">
              <button
                onClick={openSearch}
                className="w-full flex items-center gap-2 px-3 py-1.5 bg-muted/40 border border-border hover:border-zinc-500 text-muted-foreground hover:text-foreground transition-colors text-xs"
                id="global-search-btn"
                style={{ borderRadius: "var(--radius-md)" }}
              >
                <Search className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="flex-1 text-left truncate">Search everything…</span>
                <div className="hidden sm:flex items-center gap-1">
                  <kbd className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-muted border border-border text-[9px] font-mono text-muted-foreground" style={{ borderRadius: "var(--radius-sm)" }}>
                    Ctrl+K
                  </kbd>
                  <span
                    onClick={(e) => { e.stopPropagation(); setShortcutsOpen(true); }}
                    className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-muted border border-border text-[9px] font-mono text-muted-foreground hover:border-primary hover:text-primary cursor-pointer transition-colors"
                    style={{ borderRadius: "var(--radius-sm)" }}
                    title="Keyboard shortcuts (?)"
                  >
                    ?
                  </span>
                </div>
              </button>
            </div>

            {/* Right: Notifications + AI toggle + Profile */}
            <div className="flex items-center gap-1 flex-shrink-0">
              {/* Date/time — hidden on small screens */}
                         {/* Keyboard shortcuts help */}
              <button
                onClick={() => setShortcutsOpen(true)}
                title="Keyboard shortcuts (?)"
                className="hidden sm:flex w-8 h-8 items-center justify-center border border-border text-muted-foreground hover:border-primary hover:text-primary transition-colors bg-background"
                style={{ borderRadius: "var(--radius-md)" }}
              >
                <Keyboard className="w-3.5 h-3.5" />
              </button>

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
                style={{ borderRadius: "var(--radius-md)" }}
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
                  className="flex items-center gap-2 px-2 py-1.5 border border-border hover:border-muted-foreground/50 transition-colors bg-background"
                  style={{ borderRadius: "var(--radius-md)" }}
                  id="user-profile-btn"
                >
                  <div className="w-6 h-6 bg-primary text-primary-foreground font-bold flex items-center justify-center text-[10px] flex-shrink-0" style={{ borderRadius: "50%" }}>
                    {user?.name?.[0]?.toUpperCase() || "?"}
                  </div>
                  <span className="hidden sm:block text-[11px] font-mono text-muted-foreground max-w-20 truncate">
                    {user?.name?.split(" ")[0]}
                  </span>
                  <ChevronDown className="w-3 h-3 text-zinc-500" />
                </button>

                {/* Profile dropdown */}
                {profileOpen && (
                  <div className="absolute right-0 top-10 z-50 w-52 bg-card border border-border shadow-2xl text-card-foreground" style={{ borderRadius: "var(--radius-md)", overflow: "hidden" }}>
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
                      {isAdminRole(user?.role) && (
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
            {/* Keyed on pathname so React remounts this wrapper per route,
                replaying the fade/slide-in animation — the "smooth page
                transition when navigating back" requirement. */}
            <div key={location.pathname} className="page-transition p-4 sm:p-5 lg:p-6 min-h-full">
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

      {/* Keyboard shortcuts help overlay */}
      <KeyboardShortcutsHelp
        open={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />

      {/* Global search command palette (Ctrl+K) */}
      <GlobalSearch open={searchOpen} onClose={closeSearch} />
      <WarehousePicker open={warehousePickerOpen} onClose={() => setWarehousePickerOpen(false)} />
    </div>
  );
}
