// Nexcent-style isometric hero artwork — a person beside a large dashboard screen,
// drawn as inline SVG so it ships without binary assets and inherits the green theme.
// Soft, flat, friendly. Floats gently via the parent's animate-float.
export default function HeroIllustration({ className = "" }) {
  return (
    <svg
      viewBox="0 0 560 460"
      className={className}
      role="img"
      aria-label="Illustration of a person working with the Ormodex dashboard"
    >
      <defs>
        <linearGradient id="screenG" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#E8F5E9" />
          <stop offset="1" stopColor="#F5F7FA" />
        </linearGradient>
        <linearGradient id="barG" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#4CAF4F" />
          <stop offset="1" stopColor="#7AC77B" />
        </linearGradient>
      </defs>

      {/* soft ground shadow */}
      <ellipse cx="300" cy="420" rx="210" ry="26" fill="#263238" opacity="0.06" />

      {/* floating accent dots */}
      <circle cx="70" cy="70" r="6" fill="#7AC77B" opacity="0.7" />
      <circle cx="500" cy="120" r="9" fill="#4CAF4F" opacity="0.5" />
      <circle cx="120" cy="360" r="5" fill="#4CAF4F" opacity="0.5" />
      <path d="M470 330l14 0M477 323l0 14" stroke="#7AC77B" strokeWidth="3" strokeLinecap="round" />

      {/* ── Isometric monitor ─────────────────────────────── */}
      <g>
        {/* monitor body (isometric block) */}
        <path d="M170 110 L470 70 L470 250 L170 290 Z" fill="#263238" />
        <path d="M170 110 L470 70 L470 78 L170 118 Z" fill="#37474F" />
        {/* screen */}
        <path d="M186 128 L454 92 L454 236 L186 272 Z" fill="url(#screenG)" />

        {/* screen content: header bar */}
        <path d="M198 140 L442 110 L442 122 L198 152 Z" fill="#FFFFFF" />
        <circle cx="210" cy="146" r="3.4" fill="#4CAF4F" />

        {/* KPI cards */}
        <path d="M200 162 L268 153 L268 186 L200 195 Z" fill="#FFFFFF" />
        <path d="M278 151 L346 142 L346 175 L278 184 Z" fill="#FFFFFF" />
        <path d="M356 140 L424 131 L424 164 L356 173 Z" fill="#FFFFFF" />
        <path d="M206 168 L236 164 L236 169 L206 173 Z" fill="#CFD8DC" />
        <path d="M206 178 L252 172 L252 182 L206 188 Z" fill="#4CAF4F" />
        <path d="M284 157 L314 153 L314 158 L284 162 Z" fill="#CFD8DC" />
        <path d="M284 167 L326 161 L326 171 L284 177 Z" fill="#7AC77B" />
        <path d="M362 146 L392 142 L392 147 L362 151 Z" fill="#CFD8DC" />
        <path d="M362 156 L402 150 L402 160 L362 166 Z" fill="#4CAF4F" />

        {/* bar chart */}
        <path d="M200 205 L424 178 L424 246 L200 263 Z" fill="#FFFFFF" />
        {[
          [214, 30], [232, 46], [250, 36], [268, 54], [286, 42], [304, 58], [322, 48],
        ].map(([x, h], i) => (
          <path
            key={i}
            d={`M${x} ${250 - i * 2.2} L${x + 12} ${248 - i * 2.2} L${x + 12} ${248 - i * 2.2 - h} L${x} ${250 - i * 2.2 - h} Z`}
            fill="url(#barG)"
          />
        ))}
      </g>

      {/* monitor stand */}
      <path d="M300 250 L320 247 L320 300 L300 303 Z" fill="#37474F" />
      <path d="M276 300 L344 290 L344 300 L276 310 Z" fill="#263238" />

      {/* ── Person ────────────────────────────────────────── */}
      <g>
        {/* legs */}
        <path d="M96 330 q-4 40 2 70 l14 0 q2 -34 6 -62 Z" fill="#263238" />
        <path d="M120 326 q6 38 18 66 l13 -4 q-12 -32 -16 -64 Z" fill="#37474F" />
        {/* shoes */}
        <path d="M92 398 l18 0 q6 0 6 6 l-26 2 Z" fill="#4CAF4F" />
        <path d="M134 388 l16 6 q5 2 3 8 l-25 -8 Z" fill="#4CAF4F" />
        {/* body / shirt */}
        <path d="M92 250 q26 -12 52 0 q8 40 0 84 q-28 10 -56 0 q-6 -44 4 -84 Z" fill="#4CAF4F" />
        {/* arm holding tablet */}
        <path d="M140 270 q34 6 52 26 l-10 12 q-26 -16 -46 -22 Z" fill="#3d9140" />
        {/* tablet */}
        <path d="M176 296 l40 -10 l10 26 l-40 10 Z" fill="#263238" />
        <path d="M182 298 l30 -7 l7 18 l-30 7 Z" fill="#E8F5E9" />
        {/* head */}
        <circle cx="118" cy="226" r="22" fill="#FFCCBC" />
        {/* hair */}
        <path d="M97 222 q2 -26 24 -26 q22 0 22 24 q-10 -12 -24 -10 q-14 2 -22 12 Z" fill="#263238" />
        {/* neck */}
        <path d="M110 246 l16 0 l0 10 l-16 0 Z" fill="#FFAB91" />
      </g>

      {/* small gear accent */}
      <g transform="translate(250 360)" fill="#CFD8DC">
        <circle r="13" />
        <circle r="6" fill="#F5F7FA" />
        {[0, 60, 120, 180, 240, 300].map((a) => (
          <rect key={a} x="-2.5" y="-17" width="5" height="6" transform={`rotate(${a})`} />
        ))}
      </g>
    </svg>
  );
}
