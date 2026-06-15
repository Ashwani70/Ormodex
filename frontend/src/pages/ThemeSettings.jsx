import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import { Palette, Check, Moon, LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/ui-kit";

// ── Two fixed themes only. No customization. ──
// 1. Gravity Brand  — the current high-contrast industrial dark theme.
// 2. Blue Template  — the corporate blue ERP dashboard template look.

export const THEMES = {
  gravity: {
    theme_id: "gravity",
    name: "Gravity Brand",
    description: "High-contrast industrial dark theme with signal yellow accents and deep midnight background.",
    icon: "moon",
    is_dark: true,
    radius: "0px",
    custom_colors: {
      primary: "#FACC15",
      secondary: "#171717",
      accent: "#22C55E",
      background: "#0B0B0B",
      text: "#FFFFFF",
      sidebar: "#09090B",
    },
  },
  template: {
    theme_id: "template",
    name: "Blue Template",
    description: "Clean corporate ERP dashboard with a royal blue sidebar, soft light background and white cards.",
    icon: "dashboard",
    is_dark: false,
    radius: "12px",
    custom_colors: {
      primary: "#1D4ED8",
      secondary: "#1E3A8A",
      accent: "#3B82F6",
      background: "#EFF3FB",
      text: "#0F172A",
      sidebar: "#1E3A8A",
    },
  },
  slate: {
    theme_id: "slate",
    name: "Slate Template",
    description: "Clean corporate ERP dashboard with a dark slate sidebar, soft light background and white cards.",
    icon: "dashboard",
    is_dark: false,
    radius: "12px",
    custom_colors: {
      primary: "#6366F1",
      secondary: "#0F172A",
      accent: "#10B981",
      background: "#F8FAFC",
      text: "#0F172A",
      sidebar: "#0F172A",
    },
  },
};

// Default theme is the company brand.
export const DEFAULT_THEME = THEMES.gravity;

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
  // Legacy values (custom/light_premium/etc.) fall back to the default brand.
  return DEFAULT_THEME;
}

// Apply variables directly to documentElement styling
export function applyTheme(theme) {
  const root = document.documentElement;
  const activeTheme = resolveTheme(theme);

  root.style.setProperty("--radius", activeTheme.radius);

  const colors = activeTheme.custom_colors;
  const isDark = activeTheme.is_dark !== false;

  // Set HSL base colors
  root.style.setProperty("--background", hexToHslValues(colors.background));
  root.style.setProperty("--foreground", hexToHslValues(colors.text));
  root.style.setProperty("--primary", hexToHslValues(colors.primary));
  root.style.setProperty("--primary-foreground", isColorDark(colors.primary) ? "0 0% 100%" : "0 0% 0%");
  root.style.setProperty("--secondary", hexToHslValues(colors.secondary));
  root.style.setProperty("--secondary-foreground", isColorDark(colors.secondary) ? "0 0% 100%" : "0 0% 0%");
  root.style.setProperty("--muted", hexToHslValues(isDark ? colors.secondary : adjustColor(colors.background, -0.05)));
  root.style.setProperty("--muted-foreground", isDark ? "0 0% 64%" : "0 0% 40%");
  root.style.setProperty("--accent", hexToHslValues(colors.accent));
  root.style.setProperty("--accent-foreground", isColorDark(colors.accent) ? "0 0% 100%" : "0 0% 0%");
  root.style.setProperty("--card", hexToHslValues(isDark ? colors.secondary : "#FFFFFF"));
  root.style.setProperty("--card-foreground", hexToHslValues(colors.text));
  root.style.setProperty("--popover", hexToHslValues(isDark ? colors.secondary : "#FFFFFF"));
  root.style.setProperty("--popover-foreground", hexToHslValues(colors.text));
  root.style.setProperty("--ring", hexToHslValues(colors.primary));

  // Dynamic borders
  const borderVal = adjustColor(colors.background, isDark ? 0.3 : -0.08);
  root.style.setProperty("--border", hexToHslValues(borderVal));
  root.style.setProperty("--input", hexToHslValues(borderVal));

  // Dynamic neutral fallbacks
  root.style.setProperty("--zinc-50", hexToRgbValues(isDark ? colors.text : colors.background));
  root.style.setProperty("--zinc-950", hexToRgbValues(isDark ? colors.background : colors.text));
  root.style.setProperty("--zinc-800", hexToRgbValues(adjustColor(colors.background, isDark ? 0.3 : -0.12)));
  root.style.setProperty("--zinc-900", hexToRgbValues(adjustColor(colors.background, isDark ? 0.15 : -0.06)));

  // Set sidebar colors
  const sidebarBg = colors.sidebar || (isDark ? colors.secondary : "#1E293B");
  root.style.setProperty("--sidebar-background", hexToHslValues(sidebarBg));
  const sidebarFg = isColorDark(sidebarBg) ? "#FFFFFF" : "#0F172A";
  root.style.setProperty("--sidebar-foreground", hexToHslValues(sidebarFg));
  const sidebarBorder = adjustColor(sidebarBg, isColorDark(sidebarBg) ? 0.15 : -0.1);
  root.style.setProperty("--sidebar-border", hexToHslValues(sidebarBorder));

  // Dark class toggle
  if (isDark) {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

const ICONS = { moon: Moon, dashboard: LayoutDashboard };

export default function ThemeSettings() {
  const { user } = useAuth();
  const [themeId, setThemeId] = useState("gravity");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Load the user's saved theme on mount
  useEffect(() => {
    api.get("/theme-settings")
      .then((res) => {
        const id = THEMES[res.data?.theme_id] ? res.data.theme_id : "gravity";
        setThemeId(id);
      })
      .catch(() => {
        toast.error("Failed to load theme settings from server.");
      })
      .finally(() => setLoading(false));
  }, []);

  // Live preview whenever selection changes
  useEffect(() => {
    if (loading) return;
    applyTheme(THEMES[themeId]);
  }, [themeId, loading]);

  const selectTheme = async (id) => {
    if (saving || id === themeId) {
      setThemeId(id);
      return;
    }
    setThemeId(id);
    setSaving(true);
    try {
      const { data } = await api.post("/theme-settings", { theme_id: id });
      localStorage.setItem("gew_theme_settings", JSON.stringify(data));
      toast.success(`${THEMES[id].name} applied.`);
    } catch (err) {
      toast.error("Failed to save theme to database.");
    } finally {
      setSaving(false);
    }
  };

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
        description="Choose the look of your console. Your selection is saved and applied across the application."
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl">
        {Object.entries(THEMES).map(([id, t]) => {
          const isActive = themeId === id;
          const Icon = ICONS[t.icon] || Palette;
          return (
            <button
              key={id}
              onClick={() => selectTheme(id)}
              data-testid={`theme-${id}`}
              disabled={saving}
              className={`text-left p-5 border transition-all disabled:opacity-60 ${
                isActive
                  ? "border-primary ring-1 ring-primary bg-card"
                  : "border-border bg-card/40 hover:border-primary/60"
              }`}
              style={{ borderRadius: t.radius }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Icon className="w-4 h-4 text-primary" />
                  <span className="font-bold text-sm text-foreground">{t.name}</span>
                </div>
                {isActive && <Check className="w-4 h-4 text-primary" data-testid={`theme-${id}-active`} />}
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
            </button>
          );
        })}
      </div>
    </div>
  );
}
