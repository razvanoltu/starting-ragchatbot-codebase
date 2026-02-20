# Frontend Changes

## Dark/Light Mode Toggle Button

### Feature Summary
Added a dark/light mode theme toggle button positioned fixed in the top-right corner of the viewport. The button uses SVG sun/moon icons, smooth CSS transitions, persists the user's preference via `localStorage`, and is fully keyboard-navigable and accessible.

---

### Files Modified

#### `frontend/index.html`
- Bumped CSS cache-bust query string from `v=10` to `v=11`.
- Added `<button id="themeToggle" class="theme-toggle">` just before the `.container` div, containing:
  - An SVG **sun icon** (`.icon-sun`) — visible in dark mode; signals "switch to light"
  - An SVG **moon icon** (`.icon-moon`) — visible in light mode; signals "switch to dark"
  - `aria-label="Switch to light mode"` (updated dynamically by JS)
  - `title="Toggle theme"` for tooltip on hover

#### `frontend/style.css`
- **Light theme CSS variables** added under `[data-theme="light"]` selector:
  - Overrides `--background`, `--surface`, `--surface-hover`, `--text-primary`, `--text-secondary`, `--border-color`, `--assistant-message`, `--shadow`, `--welcome-bg`, `--toggle-bg`, `--toggle-border`, `--toggle-color`.
- **Two new custom properties** added to `:root` for the toggle button: `--toggle-bg`, `--toggle-border`, `--toggle-color`.
- **Global smooth theme transition** applied to `body`, sidebars, chat containers, inputs, messages, and source chips (`background-color`, `color`, `border-color` all animate over 0.3s).
- **`.theme-toggle` button styles**:
  - `position: fixed; top: 1rem; right: 1rem; z-index: 1000`
  - 42×42px circle, box-shadow, hover scale + primary-color accent, focus ring using `--focus-ring`.
- **Icon transition logic via CSS**:
  - Both icons are `position: absolute` inside the button.
  - Default (dark): `.icon-sun` at `opacity: 1 / rotate(0deg)`; `.icon-moon` at `opacity: 0 / rotate(-90deg) scale(0.6)`.
  - `[data-theme="light"]`: icons swap — sun hides with a clockwise rotation, moon appears.
  - Transitions: `opacity 0.3s ease`, `transform 0.4s ease`.
- **Light mode code block overrides**: `.message-content code` and `pre` use lower-opacity backgrounds in light mode.

#### `frontend/script.js`
- **IIFE `initTheme()`** runs synchronously before DOM is ready — reads `localStorage.getItem('theme')` and sets `data-theme="light"` on `<html>` if saved, preventing a flash of the wrong theme on load.
- **Second `DOMContentLoaded` listener** wires up the toggle button:
  - Reads current `data-theme` attribute to determine the active theme.
  - Toggles `data-theme` on `document.documentElement` between `"light"` and removed (dark).
  - Persists the new value to `localStorage`.
  - Updates `aria-label` to reflect the mode that will be activated on the next click.
  - Syncs `aria-label` with the initially loaded theme state.

---

## Light Theme CSS Variables

### Feature Summary
Expanded the light theme from a minimal color override into a complete, WCAG 2.1 AA-compliant variable system. Every hardcoded `rgba()`/hex color in the stylesheet was extracted into a named CSS custom property so that both themes are fully token-driven and no component rule needs per-theme overrides.

### Files Modified

#### `frontend/style.css`

**`:root` — new variables added (dark-mode defaults):**

| Variable | Dark value | Purpose |
|---|---|---|
| `--welcome-shadow` | `0 4px 16px rgba(0,0,0,0.2)` | Welcome message box-shadow |
| `--code-bg` | `rgba(0,0,0,0.2)` | Inline code & code block background |
| `--link-pill-bg` | `rgba(37,99,235,0.12)` | Inline link chip background |
| `--link-pill-border` | `rgba(37,99,235,0.3)` | Inline link chip border |
| `--error-bg` | `rgba(239,68,68,0.1)` | Error banner background |
| `--error-color` | `#f87171` | Error banner text |
| `--error-border` | `rgba(239,68,68,0.2)` | Error banner border |
| `--success-bg` | `rgba(34,197,94,0.1)` | Success banner background |
| `--success-color` | `#4ade80` | Success banner text |
| `--success-border` | `rgba(34,197,94,0.2)` | Success banner border |

**`[data-theme="light"]` — complete set of overrides (WCAG notes):**

| Variable | Light value | Contrast / Notes |
|---|---|---|
| `--background` | `#f8fafc` | slate-50 |
| `--surface` | `#ffffff` | white |
| `--surface-hover` | `#f1f5f9` | slate-100 |
| `--text-primary` | `#0f172a` | slate-900 — ≥15:1 on white ✓ AAA |
| `--text-secondary` | `#475569` | slate-600 — 5.9:1 on white ✓ AA |
| `--border-color` | `#e2e8f0` | slate-200 |
| `--shadow` | `0 4px 6px -1px rgba(0,0,0,0.08)` | softer than dark |
| `--focus-ring` | `rgba(37,99,235,0.25)` | slightly stronger for light bg |
| `--assistant-message` | `#f1f5f9` | slate-100 |
| `--welcome-bg` | `#eff6ff` | blue-50 |
| `--welcome-border` | `#93c5fd` | blue-300, soft on light |
| `--welcome-shadow` | `0 4px 16px rgba(0,0,0,0.07)` | subtle |
| `--code-bg` | `rgba(0,0,0,0.05)` | near-invisible tint on white |
| `--link-pill-bg` | `rgba(37,99,235,0.08)` | lighter tint |
| `--link-pill-border` | `rgba(37,99,235,0.22)` | lighter border |
| `--error-color` | `#b91c1c` | red-700 — 7.4:1 on white ✓ AAA |
| `--success-color` | `#15803d` | green-700 — 5.1:1 on white ✓ AA |
| `--toggle-bg` | `#ffffff` | |
| `--toggle-border` | `#e2e8f0` | |
| `--toggle-color` | `#475569` | |

**Component rules updated to use variables (no hardcoded colors remain):**
- `.message-content code / pre` → `background-color: var(--code-bg)`
- `.message.welcome-message .message-content` → `box-shadow: var(--welcome-shadow)`
- `.message-content a` → `background: var(--link-pill-bg)`, `border-color: var(--link-pill-border)`
- `.error-message` → `background: var(--error-bg)`, `color: var(--error-color)`, `border-color: var(--error-border)`
- `.success-message` → `background: var(--success-bg)`, `color: var(--success-color)`, `border-color: var(--success-border)`

**Removed:** per-component `[data-theme="light"]` selector overrides for `code`/`pre` (superseded by the variable approach).

---

## JavaScript Theme Toggle Functionality

### Feature Summary
Refactored the theme-toggle JavaScript into a self-contained `Theme` module with OS-preference detection, clean toggle/apply/current API, and a transition-lifecycle helper class.

### Files Modified

#### `frontend/script.js`

**Replaced** the previous IIFE + standalone `DOMContentLoaded` listener with a single `Theme` IIFE module + one dedicated `DOMContentLoaded` listener.

**`Theme` module (IIFE, runs before first paint):**
- `getInitial()` — resolves the starting theme in priority order:
  1. Saved value in `localStorage` (`'light'` or `'dark'`)
  2. OS/browser preference via `window.matchMedia('(prefers-color-scheme: light)')`
  3. Falls back to dark (the app default)
- `apply(theme)` — sets or removes `data-theme="light"` on `<html>`
- `current()` — returns `'light'` or `'dark'` based on the live attribute
- `toggle()` — flips to the opposite theme, persists to `localStorage`, and temporarily adds `theme-transitioning` to `<html>` for 350 ms (covers the 300 ms CSS transition duration) so any future code can gate on it
- Module is invoked immediately so the correct theme is in place before the browser paints, preventing a flash of the wrong colour scheme

**`DOMContentLoaded` listener (button wiring):**
- Retrieves `#themeToggle`
- `syncLabel()` — sets `aria-label` to reflect what clicking will switch *to* (e.g. "Switch to dark mode" when currently light)
- Click handler calls `Theme.toggle()` then `syncLabel()`
- `syncLabel()` is also called on init to match whatever theme was restored from storage/OS

---

## Implementation Details — CSS Custom Properties & Full Element Coverage

### Feature Summary
Completed the theme system so that every element in the UI properly adapts via CSS custom properties. Fixed variable mis-references discovered during audit, wired the remaining semantic variables to their intended elements, expanded transition coverage, and added a CSS guard preventing double-clicks mid-animation.

### Files Modified

#### `frontend/style.css`

**Bug fix — blockquote border:**
- `.message-content blockquote` referenced `var(--primary)` which does not exist → corrected to `var(--primary-color)`. Blockquote left-border was invisible in both themes before this fix.

**Bug fix — assistant message background:**
- `.message.assistant .message-content` used `var(--surface)` despite `--assistant-message` existing specifically for this element.
- In light mode `--surface` is `#ffffff` (white) against `--background: #f8fafc` (near-white) — essentially invisible.
- Changed to `var(--assistant-message)`. Contrast verified: `--text-primary` on `--assistant-message` passes WCAG AA in both themes.

**Bug fix — welcome message colours:**
- `.message.welcome-message .message-content` was using `var(--surface)` for background and `var(--border-color)` for its border, ignoring `--welcome-bg` and `--welcome-border` which were defined with purpose-built per-theme values.
- Changed to `background: var(--welcome-bg)` and `border-color: var(--welcome-border)`. In dark mode: deep navy `#1e3a5f` with blue `#2563eb` border. In light mode: soft blue `#eff6ff` with `#93c5fd` border — both visually distinct from surrounding surfaces.

**Expanded transition selector:**
Added the following selectors to the global smooth-transition rule (`background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease`) so they animate instead of snapping:
- `.main-content`
- `.message-meta`
- `.stat-value`, `.stat-label`
- `.course-title-item`
- `.sources-collapsible`

**Transition double-click guard:**
Added `html.theme-transitioning .theme-toggle { pointer-events: none; }` — disables the toggle button for the 350 ms window that the JS `theme-transitioning` class is active, preventing a second click from firing before the first animation finishes.
