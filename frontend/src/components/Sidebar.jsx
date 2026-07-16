import { useState, useEffect } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { LogOut, Settings, HelpCircle } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { ALL_NAV_ITEMS, isVisibleToRole } from "@/lib/navItems";
import { LOGO_MARK_SRC, BRAND } from "@/components/Logo";
import { useImageBlob } from "@/components/ImageUploader";

export default function Sidebar({ open, onClose, onHelp }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const role = user?.role || "employee";

  const [company, setCompany] = useState(null);
  // Authenticated blob-fetch, not a raw <img src="{API}/files/...">: the
  // /files endpoint accepts the access_token COOKIE for exactly this use
  // case, but in dev the cookie is SameSite=Lax and frontend/backend are
  // different origins, so a bare <img> tag never sends it and 401s — the
  // logo saves correctly but silently fails to render everywhere except the
  // Company Master page's own uploader (which already blob-fetches via axios).
  const logoSrc = useImageBlob(company?.logo_url);

  useEffect(() => {
    api.get("/company/active")
      .then((res) => setCompany(res.data))
      .catch(() => {});
  }, []);

  const firstName = (user?.name || "").trim().split(" ")[0] || "User";
  const initials = (user?.name || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();

  // Flat nav: every section header and every link is always rendered, in order.
  const visibleItems = ALL_NAV_ITEMS.filter((it) => isVisibleToRole(it, user));

  return (
    <aside
      data-testid="app-sidebar"
      className="h-full w-full flex flex-col"
      style={{
        background: "hsl(var(--sidebar-background))",
        borderRight: "1px solid hsl(var(--sidebar-border))",
        color: "hsl(var(--sidebar-foreground))",
      }}
    >
      {/* ── Brand / Logo — click returns to dashboard ────── */}
      <div
        className="flex items-center gap-3 px-5 py-4 cursor-pointer"
        style={{ borderBottom: "1px solid hsl(var(--sidebar-border))" }}
        onClick={() => navigate("/")}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter") navigate("/"); }}
        aria-label="Go to dashboard"
      >
        <div
          className="w-9 h-9 flex items-center justify-center overflow-hidden flex-shrink-0"
          style={{
            background: "var(--background)",
            borderRadius: "10px",
            // eslint-disable-next-line no-restricted-syntax
            boxShadow: "var(--shadow-sm)",
          }}
        >
          {logoSrc ? (
            <img src={logoSrc} alt="Logo" className="w-full h-full object-contain p-0.5" />
          ) : (
            // Static ORMODEX mark; falls back to initials if the asset is absent.
            <img
              src={LOGO_MARK_SRC}
              alt={BRAND.name}
              loading="lazy"
              className="w-full h-full object-contain p-0.5"
              onError={(e) => {
                const el = e.currentTarget; el.style.display = "none";
                const fb = el.nextElementSibling; if (fb) fb.style.display = "flex";
              }}
            />
          )}
          {!company?.logo_url && (
            <span
              className="w-full h-full items-center justify-center text-white font-black text-sm tracking-tight"
              style={{ display: "none", background: "linear-gradient(135deg, var(--primary-color), #14b8a6)" }}
            >
              {(company?.name || "OX").slice(0, 2).toUpperCase()}
            </span>
          )}
        </div>
        <div className="min-w-0">
          <div className="font-bold text-sm leading-tight truncate" style={{ color: "var(--text)" }}>
            {company?.name || BRAND.name}
          </div>
          <div className="text-[10px] font-medium" style={{ color: "var(--primary-color)" }}>
            ERP Platform
          </div>
        </div>
        {/* Close (mobile) — stop propagation so it doesn't trigger brand nav */}
        <button
          onClick={(e) => { e.stopPropagation(); onClose?.(); }}
          className="ml-auto lg:hidden p-1 rounded text-muted-foreground hover:text-foreground"
        >
          ×
        </button>
      </div>

      {/* ── Nav — permanent flat list, always scrollable, no collapsing ──── */}
      <nav className="flex-1 overflow-y-auto py-3 px-3">
        {visibleItems.map((item, i) => {
          if (item.section) {
            return (
              <div
                key={`s-${i}-${item.section}`}
                className="px-2 pt-4 pb-1.5"
              >
                <span
                  className="text-[10px] font-semibold uppercase tracking-[0.12em]"
                  style={{ color: "var(--text-muted)" }}
                >
                  {item.section}
                </span>
              </div>
            );
          }

          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              data-testid={`nav-${item.to.replace(/^\//, "").replace(/\//g, "-").replace(/\?/, "-").replace(/=/, "-") || "dashboard"}`}
              onClick={() => onClose?.()}
              className={({ isActive }) => {
                const isItActive = item.to.includes("?")
                  ? (location.pathname + location.search) === item.to
                  : isActive && !location.search;
                return `group flex items-center gap-3 px-3 py-3 my-0.5 rounded-lg text-sm font-medium transition-colors duration-150 ${
                  isItActive ? "active-nav-item" : "inactive-nav-item"
                }`;
              }}
              style={({ isActive }) => {
                const isItActive = item.to.includes("?")
                  ? (location.pathname + location.search) === item.to
                  : isActive && !location.search;
                return isItActive
                  ? {
                      background: "var(--sidebar-active-soft)",
                      color: "var(--primary-color)",
                      fontWeight: 600,
                    }
                  : {
                      color: "var(--sidebar-text)",
                    };
              }}
            >
              {({ isActive }) => {
                const isItActive = item.to.includes("?")
                  ? (location.pathname + location.search) === item.to
                  : isActive && !location.search;
                return (
                  <>
                    <span
                      className="w-7 h-7 flex items-center justify-center rounded-md flex-shrink-0 transition-colors duration-150"
                      style={isItActive
                        ? { background: "var(--primary-color)", color: "var(--primary-foreground)" }
                        : { background: "transparent", color: "var(--sidebar-text)" }
                      }
                    >
                      <Icon className="w-3.5 h-3.5" strokeWidth={2} />
                    </span>
                    <span className="truncate">{item.label}</span>
                    {isItActive && (
                      <span
                        className="ml-auto w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={{ background: "var(--primary-color)" }}
                      />
                    )}
                  </>
                );
              }}
            </NavLink>
          );
        })}
      </nav>

      {/* ── Bottom utility links ────────────────────────── */}
      <div style={{ borderTop: "1px solid hsl(var(--sidebar-border))" }}>
        <div className="px-3 py-2">
          <button
            onClick={() => { navigate("/admin/theme-settings"); onClose?.(); }}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium transition-colors hover:bg-muted"
            style={{ color: "var(--sidebar-text)" }}
          >
            <span className="w-7 h-7 flex items-center justify-center rounded-md" style={{ background: "var(--muted)" }}>
              <Settings className="w-3.5 h-3.5" />
            </span>
            Settings
          </button>
          <button
            className="w-full flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium transition-colors hover:bg-muted"
            style={{ color: "var(--sidebar-text)" }}
            onClick={() => { onHelp?.(); onClose?.(); }}
          >
            <span className="w-7 h-7 flex items-center justify-center rounded-md" style={{ background: "var(--muted)" }}>
              <HelpCircle className="w-3.5 h-3.5" />
            </span>
            Help
          </button>

        </div>

        {/* User card — click to open the account/security profile page */}
        <div
          data-testid="sidebar-user-card"
          role="button"
          tabIndex={0}
          onClick={() => navigate("/profile")}
          onKeyDown={(e) => { if (e.key === "Enter") navigate("/profile"); }}
          className="mx-3 mb-3 rounded-xl px-3 py-2.5 flex items-center gap-3 cursor-pointer transition-colors hover:brightness-95"
          style={{ background: "var(--primary-soft)", border: "1px solid rgba(13,148,136,0.15)" }}
        >
          <div
            className="w-9 h-9 flex items-center justify-center text-white font-bold text-sm rounded-full flex-shrink-0"
            // eslint-disable-next-line no-restricted-syntax
            style={{ background: "linear-gradient(135deg, var(--primary-color), var(--primary-color-light, #14b8a6))" }}
          >
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold truncate" style={{ color: "var(--text)" }}>
              {user?.name || "—"}
            </div>
            <div className="text-[10px] truncate" style={{ color: "var(--text-muted)" }}>
              {user?.email || user?.role}
            </div>
          </div>
          <button
            data-testid="logout-btn"
            title="Sign out"
            onClick={async (e) => {
              e.stopPropagation();
              try { await logout(); } catch (_) {}
              navigate("/login");
            }}
            className="p-1.5 rounded-lg transition-colors hover:bg-red-50 hover:text-red-500"
            style={{ color: "var(--text-muted)" }}
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="px-5 pb-2 text-[9px] text-center" style={{ color: "var(--text-muted)" }}>
          v2.3.1 — Stable Release
        </div>
      </div>
    </aside>
  );
}
