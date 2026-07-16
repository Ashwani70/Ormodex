import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Palette, Check, LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/ui-kit";

// ── Single fixed light theme. No customization, no theme picker. ──
// "Aurora" — a clean, professional light ERP look: soft off-white canvas,
// white cards, indigo primary, emerald accent and a dark slate sidebar.

export const THEMES = {
  aurora: {
    theme_id: "aurora",
    name: "Aurora Light",
    description: "Clean, enterprise light theme with a soft off-white canvas, white cards, blue primary and a dark slate sidebar.",
    icon: "dashboard",
    is_dark: false,
    radius: "14px",
    custom_colors: {
      primary: "#2563EB",
      secondary: "#0F172A",
      accent: "#2563EB",
      background: "#F8FAFC",
      text: "#111827",
      sidebar: "#0F172A",
    },
  },
};

// The one and only theme.
export const DEFAULT_THEME = THEMES.aurora;

// --- Color calculation helpers ---
export function isColorDark(hex) {
  hex = hex.replace(/^#/, "");
  if (hex.length === 3) {
    hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  }
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  const yiq = (r * 299 + g * 587 + b * 114) / 1000;
  return yiq < 128;
}

export function adjustColor(hex, percent) {
  hex = hex.replace(/^#/, "");
  if (hex.length === 3) {
    hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  }
  let r = parseInt(hex.substring(0, 2), 16);
  let g = parseInt(hex.substring(2, 4), 16);
  let b = parseInt(hex.substring(4, 6), 16);

  r = Math.min(255, Math.max(0, Math.round(r * (1 + percent))));
  g = Math.min(255, Math.max(0, Math.round(g * (1 + percent))));
  b = Math.min(255, Math.max(0, Math.round(b * (1 + percent))));

  const rs = r.toString(16).padStart(2, "0");
  const gs = g.toString(16).padStart(2, "0");
  const bs = b.toString(16).padStart(2, "0");

  return `#${rs}${gs}${bs}`;
}

export function hexToHslValues(hex) {
  hex = hex.replace(/^#/, "");
  if (hex.length === 3) {
    hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  }
  let r = parseInt(hex.substring(0, 2), 16) / 255;
  let g = parseInt(hex.substring(2, 4), 16) / 255;
  let b = parseInt(hex.substring(4, 6), 16) / 255;

  let max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h, s, l = (max + min) / 2;

  if (max === min) {
    h = s = 0;
  } else {
    let d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
      default: break;
    }
    h /= 6;
  }

  h = Math.round(h * 360);
  s = Math.round(s * 100);
  l = Math.round(l * 100);

  return `${h} ${s}% ${l}%`;
}

export function hexToRgbValues(hex) {
  hex = hex.replace(/^#/, "");
  if (hex.length === 3) {
    hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  }
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return `${r} ${g} ${b}`;
}

// Resolve a stored/persisted theme value down to one of the two fixed themes.
function resolveTheme(theme) {
  if (theme && THEMES[theme.theme_id]) return THEMES[theme.theme_id];
  // Any legacy value (gravity/template/slate/custom/etc.) falls back to Aurora.
  return DEFAULT_THEME;
}

// Apply the (single) Aurora theme.
//
// Aurora is a fixed LIGHT theme whose colors live entirely in index.css
// (:root). Previously this function wrote ~25 CSS variables inline on
// <html> from a per-theme color map — which OVERRODE the index.css tokens
// at runtime and, with any stale localStorage/DB value, re-introduced the
// old dark palette ("theme not working"). Since there is now exactly one
// theme, we let index.css be the single source of truth and only:
//   - clear any inline color overrides a previous build may have written
//   - keep the documentElement out of `.dark` mode
//
// `theme` is accepted (and resolved) for API compatibility but no longer
// drives colors.
const LEGACY_INLINE_VARS = [
  "--background", "--foreground", "--primary", "--primary-foreground",
  "--secondary", "--secondary-foreground", "--muted", "--muted-foreground",
  "--accent", "--accent-foreground", "--card", "--card-foreground",
  "--popover", "--popover-foreground", "--ring", "--border", "--input",
  "--zinc-50", "--zinc-800", "--zinc-900", "--zinc-950",
  "--sidebar-background", "--sidebar-foreground", "--sidebar-border",
];

export function applyTheme(theme) {
  const root = document.documentElement;
  resolveTheme(theme); // tolerate/normalize any stored value; result unused

  // Remove any inline overrides written by older builds so the index.css
  // :root tokens take effect.
  LEGACY_INLINE_VARS.forEach((v) => root.style.removeProperty(v));

  // Aurora is light — never apply the legacy dark class.
  root.classList.remove("dark");
}

const ICONS = { dashboard: LayoutDashboard };

export default function ThemeSettings() {
  const [themeId] = useState("aurora");
  const [loading, setLoading] = useState(true);

  // Single theme: ensure the DB/localStorage converge to "aurora" on mount.
  useEffect(() => {
    api.post("/theme-settings", { theme_id: "aurora" })
      .then(({ data }) => {
        localStorage.setItem("gew_theme_settings", JSON.stringify(data));
      })
      .catch(() => {
        // Non-fatal: the theme still applies locally even if the save fails.
      })
      .finally(() => setLoading(false));
  }, []);

  // Live preview whenever selection changes
  useEffect(() => {
    if (loading) return;
    applyTheme(THEMES[themeId]);
  }, [themeId, loading]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] font-mono text-sm text-muted-foreground">
        <div className="animate-spin mb-4">
          <Palette className="w-8 h-8 text-primary" />
        </div>
        LOADING THEME...
      </div>
    );
  }

  return (
    <div data-testid="theme-settings-page" className="space-y-6">
      <PageHeader
        eyebrow="System Configuration"
        title="Theme"
        description="Your console uses a single, clean light theme applied consistently across the application."
      />

      <div className="max-w-3xl">
        {Object.entries(THEMES).map(([id, t]) => {
          const Icon = ICONS[t.icon] || Palette;
          return (
            <div
              key={id}
              data-testid={`theme-${id}`}
              className="text-left p-5 border border-primary ring-1 ring-primary bg-card"
              style={{ borderRadius: t.radius }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Icon className="w-4 h-4 text-primary" />
                  <span className="font-bold text-sm text-foreground">{t.name}</span>
                </div>
                <Check className="w-4 h-4 text-primary" data-testid={`theme-${id}-active`} />
              </div>
              <p className="text-xs text-muted-foreground leading-normal mb-4">{t.description}</p>

              {/* Color swatches */}
              <div className="flex gap-1.5 items-center">
                {Object.values(t.custom_colors).map((color, i) => (
                  <span
                    key={i}
                    className="w-5 h-5 rounded-full border border-black/20"
                    style={{ backgroundColor: color }}
                  />
                ))}
                <span className="text-[10px] font-mono text-muted-foreground ml-auto uppercase">
                  {t.is_dark ? "Dark" : "Light"}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
