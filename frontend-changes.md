# Frontend Changes

## Code Quality Tooling — Prettier Setup

This document records the frontend changes made to introduce code quality tooling.

---

### New Files

#### `frontend/package.json`
Introduces Node.js package management for the frontend. Declares Prettier 3.x as a dev
dependency and exposes three npm scripts:

| Script | Command | Purpose |
|---|---|---|
| `format` | `prettier --write "**/*.{js,css,html}"` | Auto-format all frontend files in place |
| `format:check` | `prettier --check "**/*.{js,css,html}"` | Check formatting without modifying files (CI-safe) |
| `lint` | alias for `format:check` | Convenience alias |

#### `frontend/.prettierrc`
Prettier configuration that enforces consistent style across JS, CSS, and HTML:

| Option | Value | Rationale |
|---|---|---|
| `printWidth` | 100 | Matches the existing line-length convention in the codebase |
| `tabWidth` | 4 | Consistent with existing indentation throughout all three files |
| `useTabs` | false | Spaces throughout |
| `semi` | true | Explicit semicolons in JS |
| `singleQuote` | true | Single quotes in JS string literals |
| `trailingComma` | `"es5"` | Trailing commas in objects/arrays/parameters where valid in ES5 |
| `bracketSpacing` | true | Spaces inside object braces: `{ key: value }` |
| `arrowParens` | `"always"` | Parentheses around single arrow-function parameters: `(x) => x` |
| `endOfLine` | `"lf"` | Unix line endings for cross-platform consistency |

#### `scripts/check-frontend.sh`
Shell script for running frontend quality checks from the repository root.

```
./scripts/check-frontend.sh         # check formatting (exits non-zero on violations)
./scripts/check-frontend.sh --fix   # auto-format all frontend files in place
```

Automatically installs npm dependencies (`node_modules`) if they are missing. Errors clearly
if Node.js / npx is not available.

---

### Modified Files

All three existing frontend files were reformatted to be fully compliant with the Prettier
configuration above. No logic, structure, or visual output was changed.

#### `frontend/script.js`
- Removed extra blank lines between `setupEventListeners` sections
- Added trailing commas to multi-line object literals and function call arguments (e.g., `fetch` body, `JSON.stringify`)
- Added parentheses around single-parameter arrow functions (`forEach`, `querySelectorAll` callbacks)
- Expanded the `sources.map(...)` chain onto multiple lines for readability within the 100-character print width
- Normalized spacing around the `markedRenderer.link` function declaration

#### `frontend/style.css`
- Split the `*,*::before,*::after` universal selector onto separate lines
- Expanded multi-value `transition` shorthand into multi-line form (`.sources-content a`, `.message-content a`) — Prettier's standard CSS shorthand expansion
- Expanded `0%, 80%, 100%` `@keyframes bounce` selector onto separate lines
- Split the `.no-courses, .loading, .error` grouped selector across lines
- Separated single-line heading size declarations (`h1`, `h2`, `h3`) into individual rule blocks
- Split the long `font-family` value in `body` across two lines to respect `printWidth: 100`
- Normalized blank lines between rule blocks throughout

#### `frontend/index.html`
- Changed `<!DOCTYPE html>` to lowercase `<!doctype html>` (Prettier HTML convention)
- Added self-closing slash to void elements: `<meta ... />`, `<link ... />`, `<input ... />`
- Reformatted multi-attribute elements (`<input>`, `<button>`, `<svg>`) to one attribute per line when attributes exceed the print width
- Wrapped long `data-question` attribute values onto new lines for readability
- Normalized indentation (4 spaces) consistently throughout

---

### How to Use

**One-time setup** (requires Node.js):
```bash
cd frontend
npm install
```

**Check formatting** (useful in CI):
```bash
# from repo root:
./scripts/check-frontend.sh

# or from frontend/:
npm run format:check
```

**Auto-format** (fix all violations):
```bash
# from repo root:
./scripts/check-frontend.sh --fix

# or from frontend/:
npm run format
```
