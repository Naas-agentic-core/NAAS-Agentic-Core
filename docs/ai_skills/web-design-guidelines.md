---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with Web Interface Guidelines.

> **Project context:** The frontend lives in `frontend/`. It uses **Next.js** (no Tailwind),
> custom CSS variables defined in `frontend/app/globals.css`, **RTL layout** (`direction: rtl`),
> and Arabic fonts (`Cairo`, `IBM Plex Sans Arabic`). All UI work must respect these constraints.

---

## Project Design Tokens

Always use CSS variables from `frontend/app/globals.css` — never hard-code colours or shadows.

### Colour Tokens

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--primary-color` | `#2563eb` | `#60a5fa` | Primary actions, links |
| `--primary-hover` | `#1d4ed8` | `#3b82f6` | Hover state on primary |
| `--secondary-color` | `#475569` | `#94a3b8` | Secondary text, icons |
| `--bg-color` | `#f8fafc` | `#0f172a` | Page background |
| `--surface-color` | `#ffffff` | `#1e293b` | Cards, panels |
| `--text-color` | `#0f172a` | `#f1f5f9` | Body text |
| `--text-secondary` | `#64748b` | `#cbd5e1` | Captions, metadata |
| `--border-color` | `#e2e8f0` | `#334155` | Borders, dividers |
| `--success-color` | `#10b981` | `#34d399` | Success states |
| `--warning-color` | `#f59e0b` | `#fbbf24` | Warnings |
| `--error-color` | `#ef4444` | `#f87171` | Errors, destructive |

### Shadow Tokens

| Token | Value | Use |
|-------|-------|-----|
| `--shadow-sm` | `0 1px 2px 0 rgb(0 0 0 / 0.05)` | Subtle elevation |
| `--shadow` | `0 4px 6px -1px rgb(0 0 0 / 0.1)` | Cards, dropdowns |

### Typography

- **Font family:** `'Cairo', 'IBM Plex Sans Arabic', sans-serif`
- **Direction:** `rtl` (right-to-left) — all new components must respect this
- **Line height:** `1.6` base

---

## How It Works

1. Read the specified files (or prompt user for files/pattern)
2. Check against all rules below
3. Output findings in `file:line` format

If no files are specified, ask the user which files to review.

---

## Core Rules

### Layout & RTL

- `direction: rtl` must be set on `body` — never override to `ltr` without explicit justification
- Use logical CSS properties (`margin-inline-start`, `padding-inline-end`) instead of `margin-left`/`margin-right` where possible
- Flex/grid layouts must be tested in RTL — `row` direction reverses visually
- Icons that imply direction (arrows, chevrons) must be mirrored in RTL

### Colour Usage

- Never hard-code hex/rgb values — always use `var(--token-name)`
- Dark mode is toggled via `[data-theme='dark']` on the root — do not use `prefers-color-scheme` media queries directly; use the theme attribute
- Ensure sufficient contrast: text on background must meet WCAG 2.1 AA (4.5:1 for normal text, 3:1 for large text)

### Spacing & Sizing

- Use `rem` for font sizes and spacing (not `px`) to respect user font preferences
- Minimum touch target size: `44px × 44px` (WCAG 2.5.5)
- Use `100dvh` instead of `100vh` for full-height containers (mobile viewport fix — already in `.app-container`)

### Components

- Buttons must have visible focus styles (`:focus-visible` outline, not just `:focus`)
- Interactive elements must not rely on colour alone to convey state — add text or icon
- Loading states must be communicated to screen readers (`aria-busy="true"`, `aria-live` regions)
- Empty states must include a descriptive message, not just a blank area

---

## Accessibility Baseline (WCAG 2.1 AA)

Every component must pass these checks:

| Rule | Requirement |
|------|-------------|
| Images | `alt` attribute on all `<img>` — empty `alt=""` for decorative images |
| Buttons | Visible label or `aria-label` — never icon-only without accessible name |
| Form inputs | Associated `<label>` or `aria-label` on every input |
| Focus order | Tab order follows visual reading order (RTL: right to left) |
| Colour contrast | 4.5:1 for body text, 3:1 for large text and UI components |
| Keyboard navigation | All interactive elements reachable and operable by keyboard |
| Error messages | Linked to their input via `aria-describedby` |
| Page language | `<html lang="ar">` for Arabic content |
| Headings | Logical hierarchy — no skipping levels (h1 → h2 → h3) |
| Live regions | Dynamic content updates announced via `aria-live` |

---

## Common Pitfalls

| Avoid | Why | Instead |
|-------|-----|---------|
| `margin-left` / `margin-right` | Breaks RTL | `margin-inline-start` / `margin-inline-end` |
| Hard-coded `#hex` colours | Breaks dark mode | `var(--token-name)` |
| `onClick` on `<div>` | Not keyboard accessible | Use `<button>` |
| `100vh` for full height | Broken on mobile browsers | `100dvh` |
| `placeholder` as label | Disappears on input | Visible `<label>` element |
| `display: none` for hidden content | Removed from accessibility tree | `visibility: hidden` or `aria-hidden` depending on intent |
| Colour-only status indicators | Fails for colour-blind users | Add text or icon alongside colour |

---

## Output Format

Report findings as:

```
file:line  RULE  description
```

Example:

```
app/components/Button.jsx:14  ACCESSIBILITY  Button has no accessible name — add aria-label or visible text
app/page.tsx:32               COLOUR         Hard-coded #2563eb — use var(--primary-color)
app/layout.tsx:8              RTL            margin-left used — replace with margin-inline-start
```

Severity levels: `ERROR` (blocks merge), `WARNING` (should fix), `INFO` (suggestion).
