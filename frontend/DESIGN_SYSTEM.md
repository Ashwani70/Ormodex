# Aurora Design System

A single design system powers every screen — masters, invoices, stock, reports,
and dashboards. New modules inherit it automatically through this chain:

```
Tokens (index.css) → Tailwind config → ui-kit.jsx → Modules
```

**Live reference:** visit `/design-system` in the app (admin only) to see every
primitive and its states rendered together.

## Principles

- Clean and professional, information-dense without feeling crowded
- Optimized for data entry and large tables
- Accessible: strong contrast, visible focus states
- Consistent spacing and interaction patterns

## How to build a screen

1. Import primitives from `@/components/ui-kit` — `PageHeader`, `Card`,
   `StatTile`, `PrimaryButton`/`SecondaryButton`/`SuccessButton`,
   `Input`/`Select`/`Textarea`/`Field`, `Badge`/`StatusBadge`, `EmptyState`,
   `Spinner`/`Skeleton`/`SkeletonTable`.
2. Use Tailwind **semantic** classes that map to tokens: `bg-background`,
   `bg-surface`, `bg-card`, `text-foreground`, `text-muted-foreground`,
   `border-border`, `bg-primary`, `text-primary`, `bg-accent`.
3. For radius/shadow use the CSS vars: `var(--radius-sm|md|lg)`,
   `var(--shadow-sm|md)`.

## Component states

Every shared component supports the states it needs:

| Component | States |
|-----------|--------|
| Buttons   | default · hover · disabled · `loading` (spinner) |
| Inputs    | default · focus (3px ring) · `error` · disabled |
| Field     | label · `required` · `hint` · `error` message |
| Tables    | sticky header · zebra · hover · `SkeletonTable` loading |
| Data views| `EmptyState` for no-data |
| Toasts    | success · warning · error · info (5s auto-dismiss) |

## Guardrails — do not

These are flagged by ESLint (`no-restricted-syntax`, currently `warn`):

❌ Hard-coded colors in style props
```jsx
style={{ background: "#4F46E5" }}
```

✅ Use a token
```jsx
className="bg-primary"
// or
style={{ background: "var(--primary-color)" }}
```

❌ Custom shadows
```jsx
style={{ boxShadow: "0 2px 8px rgba(0,0,0,0.2)" }}
```

✅ Use a shadow token
```jsx
style={{ boxShadow: "var(--shadow-sm)" }}
```

Prefer Tailwind's `rounded-lg`/`rounded-md` or `var(--radius-*)` over raw pixel
radii so the whole app stays on one radius scale.

## Tokens

All tokens live in `src/index.css` under `:root`. The HSL set drives Tailwind
semantic colors (via `tailwind.config.js`); a parallel hex set (`--primary-color`,
`--surface`, `--border-color`, `--sidebar-*`, `--radius-*`, `--shadow-*`,
`--space-*`) is available for raw CSS and inline `var()` use. Font is Inter.
