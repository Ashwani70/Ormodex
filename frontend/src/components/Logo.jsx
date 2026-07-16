import { useNavigate } from "react-router-dom";

/**
 * Single source of truth for ORMODEX branding across the app.
 *
 * Future branding changes only need to touch this file. The logo image lives at
 * a fixed public path (see LOGO_SRC); drop the official PNG/SVG there and it
 * appears everywhere this component is used — login, sidebar, navbar, splash,
 * loading, about, etc.
 *
 * The image lazy-loads and falls back to a styled text wordmark if it fails to
 * load (or hasn't been uploaded yet), so nothing ever renders a broken image.
 */

// Central asset path. Replace the file at this path to rebrand everywhere.
export const LOGO_SRC = "/ormodex-logo.png";
export const LOGO_MARK_SRC = "/ormodex-mark.png"; // square icon-only variant (favicon-style)

export const BRAND = {
  name: "ORMODEX",
  tagline: "TECH & SOFTWARE SOLUTIONS",
  // Brand colours sampled from the logo (kept here for charts/accents that opt in;
  // the global theme is unchanged this pass).
  colors: {
    green: "#3fbf3f",
    blue: "#1e6fe0",
    navy: "#0f1e3d",
    white: "#ffffff",
  },
};

const SIZES = {
  xs: { img: 20, name: "text-sm", tag: "text-[7px]" },
  sm: { img: 28, name: "text-base", tag: "text-[8px]" },
  md: { img: 36, name: "text-lg", tag: "text-[9px]" },
  lg: { img: 48, name: "text-2xl", tag: "text-[10px]" },
  xl: { img: 72, name: "text-4xl", tag: "text-xs" },
};

// Styled text wordmark used as the fallback when the image is missing/broken.
function TextWordmark({ size = "md", showTagline }) {
  const s = SIZES[size] || SIZES.md;
  return (
    <span className="inline-flex flex-col leading-none select-none">
      <span className={`font-display font-black tracking-tight ${s.name}`}>
        <span style={{ color: BRAND.colors.green }}>OR</span>
        <span style={{ color: BRAND.colors.navy }}>MO</span>
        <span style={{ color: BRAND.colors.blue }}>DE</span>
        <span style={{ color: BRAND.colors.green }}>X</span>
      </span>
      {showTagline && (
        <span className={`font-mono uppercase tracking-[0.3em] text-muted-foreground mt-1 ${s.tag}`}>
          {BRAND.tagline}
        </span>
      )}
    </span>
  );
}

/**
 * Props:
 *  - variant: "full" (image wordmark) | "mark" (square icon-only) | "text" (styled text)
 *  - size: xs|sm|md|lg|xl
 *  - showTagline: render the tagline under the wordmark (text/fallback only)
 *  - clickable: navigate to "/" (dashboard) on click
 *  - className: extra classes on the wrapper
 *  - alt: image alt text
 */
export default function Logo({
  variant = "full",
  size = "md",
  showTagline = false,
  clickable = false,
  className = "",
  alt = "ORMODEX",
}) {
  const navigate = useNavigate();
  const s = SIZES[size] || SIZES.md;

  const onActivate = clickable ? () => navigate("/") : undefined;
  const wrapperCls =
    `inline-flex items-center gap-2 ${clickable ? "cursor-pointer" : ""} ${className}`;

  const content =
    variant === "text" ? (
      <TextWordmark size={size} showTagline={showTagline} />
    ) : (
      <img
        src={variant === "mark" ? LOGO_MARK_SRC : LOGO_SRC}
        alt={alt}
        loading="lazy"
        decoding="async"
        // Reserve height to prevent layout shift; width auto-scales.
        style={{ height: s.img, width: "auto", maxWidth: variant === "mark" ? s.img : undefined }}
        className="object-contain"
        onError={(e) => {
          // Swap to the text wordmark if the asset is missing, so we never show
          // a broken-image icon. Done by hiding the img and unhiding a sibling.
          const el = e.currentTarget;
          el.style.display = "none";
          const fb = el.nextElementSibling;
          if (fb) fb.style.display = "inline-flex";
        }}
      />
    );

  return (
    <span
      className={wrapperCls}
      onClick={onActivate}
      onKeyDown={clickable ? (e) => { if (e.key === "Enter") onActivate?.(); } : undefined}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      aria-label={clickable ? "Go to dashboard" : undefined}
    >
      {content}
      {/* Hidden fallback sibling for the image onError swap. */}
      {variant !== "text" && (
        <span style={{ display: "none" }}>
          <TextWordmark size={size} showTagline={showTagline} />
        </span>
      )}
    </span>
  );
}
