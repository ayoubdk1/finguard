# Design System Master File — FinGuard

> **LOGIC:** When building a specific page, first check `design-system/finguard/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** FinGuard — Personal Finance, Double-Entry Ledger & Fraud Intelligence Platform
**Generated:** 2026-11-15
**Category:** Fintech / Personal Finance & Security Web App
**Style:** Minimalism & Swiss Style (High-Precision Financial Intelligence)
**Design Dials:** Motion 5/10 (Standard) | Density 7/10 (Dashboard Precision)

---

## 1. Global Design Tokens

### Color Palette (Dark Mode Default & Light Mode Support)

| Role | Dark Theme (Default) | Light Theme (`[data-theme="light"]`) | CSS Variable |
|------|----------------------|--------------------------------------|--------------|
| **Primary (Brand Emerald/Gold)** | `#10B981` | `#059669` | `--color-primary` |
| **Primary Hover** | `#059669` | `#047857` | `--color-primary-hover` |
| **On Primary** | `#020617` | `#FFFFFF` | `--color-on-primary` |
| **Secondary (Trust Gold)** | `#F59E0B` | `#D97706` | `--color-secondary` |
| **On Secondary** | `#0F172A` | `#FFFFFF` | `--color-on-secondary` |
| **Accent / Tech** | `#38BDF8` | `#0284C7` | `--color-accent` |
| **Background (App Canvas)** | `#0B1120` | `#F8FAFC` | `--color-background` |
| **Surface / Sidebar** | `#0F172A` | `#0F172A` | `--color-sidebar` |
| **Foreground (Primary Text)** | `#F8FAFC` | `#0F172A` | `--color-foreground` |
| **Card Surface** | `#151F32` | `#FFFFFF` | `--color-card` |
| **Card Elevated / Hover** | `#1E293B` | `#F1F5F9` | `--color-card-elevated` |
| **Card Foreground** | `#F8FAFC` | `#0F172A` | `--color-card-foreground` |
| **Muted Surface** | `#1E293B` | `#F1F5F9` | `--color-muted` |
| **Muted Foreground** | `#94A3B8` | `#475569` | `--color-muted-foreground` |
| **Border / Divider** | `#26334D` | `#E2E8F0` | `--color-border` |
| **Border Subtle** | `#1E293B` | `#F1F5F9` | `--color-border-subtle` |
| **Success** | `#10B981` | `#059669` | `--color-success` |
| **Warning** | `#F59E0B` | `#D97706` | `--color-warning` |
| **Destructive / Danger** | `#EF4444` | `#DC2626` | `--color-destructive` |
| **Focus Ring** | `#10B981` | `#059669` | `--color-ring` |

### Typography

- **Heading & UI Font:** `'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif`
- **Monospace / Financial Figures & IDs:** `'IBM Plex Mono', monospace`
- **Numeric Discipline:** All currency amounts, balances, risk scores, and timestamps use `font-variant-numeric: tabular-nums`
- **Google Fonts Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
```

### Spacing & Radius Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` (`0.25rem`) | Tight inline gaps, badge padding |
| `--space-sm` | `8px` (`0.5rem`) | Icon-to-text gaps, compact list spacing |
| `--space-md` | `16px` (`1rem`) | Standard control & card inner spacing |
| `--space-lg` | `24px` (`1.5rem`) | Panel padding, grid gaps |
| `--space-xl` | `32px` (`2rem`) | Page horizontal gutters, section breaks |
| `--space-2xl` | `48px` (`3rem`) | Major layout separations |
| `--radius-sm` | `6px` | Badges, code pills, small buttons |
| `--radius-md` | `10px` | Inputs, selects, standard buttons |
| `--radius-lg` | `14px` | Cards, panels, tables |
| `--radius-xl` | `18px` | Modals, hero callouts |

### Elevation & Shadows

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(2, 6, 23, 0.08)` | Subtle surface separation |
| `--shadow-md` | `0 4px 12px rgba(2, 6, 23, 0.16)` | Cards, stat tiles, active controls |
| `--shadow-lg` | `0 12px 28px rgba(2, 6, 23, 0.28)` | Elevated cards, popovers |
| `--shadow-xl` | `0 24px 48px rgba(2, 6, 23, 0.45)` | Modal dialogs |

---

## 2. Component Specifications

- **Buttons**: Crisp `10px` radius, `font-weight: 600`, inline SVG icon alignment (`display: inline-flex; align-items: center; gap: 8px`), `200ms cubic-bezier(0.16, 1, 0.3, 1)` transitions, visible `:focus-visible` ring (`2px solid var(--color-ring)`).
- **Stat & Account Cards**: `14px` radius, `1px solid var(--color-border)`, subtle top highlight, tabular numeric displays, status badge pills with semantic icon indicators.
- **Data Tables**: Sticky/clean uppercase headers (`11px`, `letter-spacing: 0.08em`), monospace UUID truncation pills, right-aligned or tabular-num financial amounts, semantic status pills (`POSTED`, `PROCESSED`, `PUBLISHED`, `PENDING`, `DEAD`), hover row highlighting.
- **Forms & Inputs**: Clear accessible `<label>` above every control, `10px` border radius, `1px solid var(--color-border)`, high-contrast focus ring, inline alert banners (`role="alert"`).
- **Modals**: Blurred backdrop (`backdrop-filter: blur(6px)`), `18px` radius, clear step indicator (Form → Review → Receipt), keyboard & click-outside dismissable.

---

## 3. Strict Anti-Patterns & Pre-Delivery Checklist

- [x] **No Emojis or ASCII Glyphs as Icons**: Replace all Unicode symbols (`▦`, `▤`, `⇄`, `≡`, `◇`, `◉`, `◎`, `↻`, `✓`, `×`) with crisp 24×24 SVG vector icons (Lucide / Heroicons style, `stroke-width="1.75"`, `aria-hidden="true"` on decorative icons).
- [x] **Contrast & Readability**: Maintain >= 4.5:1 text contrast ratio across both Dark and Light themes.
- [x] **Interactive States**: Every interactive element has `cursor: pointer`, hover elevation/color transition (150–250ms), and disabled protection (`cursor: not-allowed; opacity: 0.55`).
- [x] **Responsive Breakpoints**: Fluid layouts across `375px` (mobile), `768px` (tablet), `1024px` (laptop), and `1440px` (desktop).
- [x] **Preserve All Functionality & Tests**: Keep all existing API contracts, props, form labels, headings, and ARIA roles intact so all unit and integration tests pass.
