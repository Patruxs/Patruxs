# Profile banner guide

This repository powers the **Patruxs** GitHub profile: dual-theme animated
banners, live stats, contribution snake, and the profile `README.md`.

Run every command from the **repo root** unless noted.

---

## Repository layout

```text
Patruxs/
├── README.md                      # What GitHub shows on your profile
├── snake.svg / snake-dark.svg     # Contribution snake
├── system_info.yaml               # Static SYSTEM.INFO text (edit this)
├── requirements.txt
├── .gitignore
│
├── assets/
│   ├── dark.svg / light.svg       # Theme banners (VISUAL.MAP + SYSTEM.INFO)
│   ├── portrait.txt               # ASCII portrait source for VISUAL.MAP
│   └── profile-summary-card-output/
│       ├── github/                 # Light profile summary cards
│       └── github_dark/            # Dark profile summary cards
│
├── scripts/
│   ├── today.py                   # Live refresh: Uptime, Lang, GitHub Stats
│   ├── update_system_info.py      # Apply system_info.yaml → SVGs
│   ├── ascii_to_svg.py            # portrait.txt → SVG <tspan> block
│   ├── image_to_ascii.py          # Photo → ASCII portrait
│   └── README.md
│
├── docs/
│   └── USAGE.md                   # This guide
│
└── .github/workflows/
    ├── update-banners.yml         # Daily live-field refresh
    ├── summary-cards.yml          # Daily light/dark summary cards
    └── snake.yml                  # Contribution snake every 12h
```

Profile assets stay under `assets/` and use paths relative to `README.md`, such
as `./assets/dark.svg`.

---

## Quick start

```bash
# 1. Dependencies (once)
pip install -r requirements.txt

# 2. Edit static fields
#    open system_info.yaml

# 3a. Apply YAML + light live fill (Uptime, Lang)
python3 scripts/update_system_info.py

# 3b. Or full live refresh (Uptime, all languages, GitHub Stats)
export ACCESS_TOKEN=ghp_...          # optional, recommended for stats
python3 scripts/today.py

# 4. Preview
#    open assets/dark.svg and assets/light.svg in a browser

# 5. Publish
git add system_info.yaml assets/dark.svg assets/light.svg
git commit -m "Update profile banner"
git push
```

---

## What is live vs static

| Area | Source | Updates how |
|------|--------|-------------|
| **Uptime** | GitHub account `created_at`, or `BIRTHDAY` variable | Daily Action / `today.py` |
| **Lang** | Languages across **owned, non-fork** repos (by code size) | Daily Action / `today.py` |
| **GitHub Stats** | Repos, contributed repos, stars, commits, followers, LOC | Daily Action / `today.py` (needs token) |
| **Snake** | Contribution graph | `snake.yml` every 12 hours |
| **Subject, Role, Origin, …** | `system_info.yaml` | You edit YAML, then run `update_system_info.py` |
| **Contact** | `system_info.yaml` | Same |
| **ASCII portrait** | `assets/portrait.txt` | Manual / `image_to_ascii.py` |

Leave live keys empty in YAML (`Uptime`, `Lang`). `GitHub Stats` is a section
with `kind: github_stats` - values are filled by `today.py`, not hand-edited.

### Lang display

Languages are ranked by total bytes, packed into multiple monospaced lines,
right-justified with filler dots:

```text
. Lang: ................TypeScript · Java · HTML · CSS
. .............Python · JavaScript · Go · SCSS · Shell
. ........................PowerShell · HCL · Batchfile
. ......................Go Template · PHP · Ruby · Lua
. ..........................................Dockerfile
```

---

## Edit static SYSTEM.INFO

### 1. Open `system_info.yaml`

Current shape:

```yaml
host: patruxs@devos

fields:
  - key: Uptime
    value: ""                    # live

  - key: Subject
    value: Patrick

  - key: Role
    value: Backend Engineer · Fullstack Engineer

  - key: Origin
    value: Vietnam · Remote

  - key: Education
    value: Software Engineering

  - key: Status
    value: Building · Learning · Shipping

  - key: Lang
    value: ""                    # live — all repo languages

sections:
  - title: Contact
    fields:
      - key: Grid.Mail
        value: laithuanphat.work@gmail.com
      - key: Grid.Portfolio
        value: github.com/Patruxs
      - key: Grid.LinkedIn
        value: linkedin.com/in/patruxs
      - key: Grid.Github
        value: Patruxs

  - title: GitHub Stats
    kind: github_stats           # live block
```

### 2. Apply changes

```bash
python3 scripts/update_system_info.py
```

This rebuilds the SYSTEM.INFO panel in both theme SVGs and refreshes Uptime + Lang.

### Line types

| YAML | Renders as |
|------|------------|
| `host:` | Purple terminal header |
| `key` + `value` | `. Key: ........ Value` (right-justified) |
| empty `key` and `value` | Blank spacer |
| `Grid.Mail` (nested key) | `. Grid.Mail: .... value` |
| `Lang` | Multi-line live language list |
| `sections[].title` | `- Contact` style header |
| `kind: github_stats` | Live Repos / Commits / LOC rows |

### Add a static row

Under `fields:`:

```yaml
  - key: Focus
    value: APIs · Distributed systems
```

Then run `python3 scripts/update_system_info.py`.

---

## Scripts reference

Run from repo root:

| Command | Purpose |
|---------|---------|
| `python3 scripts/today.py` | Full live update (Uptime, Lang, Stats) |
| `python3 scripts/update_system_info.py` | YAML structure + Uptime/Lang |
| `python3 scripts/ascii_to_svg.py` | Build tspans from `assets/portrait.txt` |
| `python3 scripts/image_to_ascii.py PHOTO -o assets/portrait.txt` | Photo → ASCII |

### `today.py` environment

| Variable | Required | Meaning |
|----------|----------|---------|
| `USER_NAME` | No | GitHub login (default: `Patruxs`) |
| `ACCESS_TOKEN` | Recommended | PAT for GraphQL stats + private repos |
| `BIRTHDAY` | No | `YYYY-MM-DD` for Uptime; else account created_at |

Example:

```bash
export USER_NAME=Patruxs
export ACCESS_TOKEN=ghp_xxxxxxxx
export BIRTHDAY=2002-07-05   # optional
python3 scripts/today.py
```

Without `ACCESS_TOKEN`, Uptime and Lang still update (public APIs). GitHub Stats
need a token for reliable results.

---

## ASCII portrait (VISUAL.MAP)

### From existing art

1. Edit `assets/portrait.txt` (monospace ASCII block).
2. Optionally generate SVG tspans:

```bash
python3 scripts/ascii_to_svg.py
# → assets/portrait_tspan.txt
```

3. Paste/update the portrait `<tspan>` block inside `assets/dark.svg` and `assets/light.svg`
   (or have an agent do it). `update_system_info.py` does **not** rewrite VISUAL.MAP.

### From a photo

```bash
python3 scripts/image_to_ascii.py path/to/photo.jpg -o assets/portrait.txt

# Useful flags:
#   --cols 92 --rows 53
#   --gamma 0.90
#   --no-crop / --no-dither / --no-subject-aware
```

Then open `assets/portrait.txt`, tweak if needed, and re-embed into the SVGs.

---

## Contribution snake

Generated by `.github/workflows/snake.yml` (every 12 hours + manual).

Files:

- `snake.svg` - light theme  
- `snake-dark.svg` - dark theme  

Referenced from `README.md`:

```markdown
![Snake animation](./snake.svg#gh-light-mode-only)
![Snake animation](./snake-dark.svg#gh-dark-mode-only)
```

---

## GitHub Actions

### Workflows

| Workflow | File | Schedule | What it does |
|----------|------|----------|--------------|
| **Update profile banners** | `update-banners.yml` | Daily 00:00 UTC | Runs `scripts/today.py`, commits SVG changes |
| **Profile summary cards** | `summary-cards.yml` | Daily 00:30 UTC | Regenerates both themes under `assets/profile-summary-card-output/` and publishes them to `main` |
| **Generate snake animation** | `snake.yml` | Every 12 hours | Platane/snk → `snake.svg` / `snake-dark.svg` |

All three support **workflow_dispatch** (manual run from the Actions tab).

### Secrets and variables

Repo → **Settings → Secrets and variables → Actions**

| Name | Kind | Purpose |
|------|------|---------|
| `ACCESS_TOKEN` | Secret | Fine-grained or classic PAT for stats / private languages |
| `BIRTHDAY` | Variable | Optional Uptime start date (`YYYY-MM-DD`) |

Also set **Actions → General → Workflow permissions** to **Read and write**.

Suggested PAT scopes (see comments in `scripts/today.py`):

- Account: read followers / starring / watching  
- Repositories: contents, metadata, commit statuses (as needed for LOC)

### Manual banner refresh

**Actions → Update profile banners → Run workflow**

---

## Profile README

Keep `README.md` at the root. Minimal pattern:

```markdown
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/dark.svg"/>
  <img src="./assets/light.svg" alt="Patruxs"/>
</picture>

## My stats:
...

## Commits
![Snake animation](./snake.svg#gh-light-mode-only)
![Snake animation](./snake-dark.svg#gh-dark-mode-only)
```

The special repo name **`USERNAME/USERNAME`** is required for GitHub to show this
as your profile README.

---

## Dependencies

```bash
pip install -r requirements.txt
```

| Package | Used by |
|---------|---------|
| `python-dateutil`, `requests`, `lxml` | `today.py` |
| `PyYAML` | `update_system_info.py` (optional fallback parser exists) |
| `numpy`, `Pillow` | `image_to_ascii.py` |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| Banner looks unchanged | Hard-refresh the browser / profile page |
| GitHub still shows old SVG | Wait ~1 minute; hard-refresh; check Actions succeeded |
| Stats stay `0` | Add `ACCESS_TOKEN` secret (PAT), re-run workflow |
| Lang missing languages | Owned **non-fork** repos only; private needs PAT |
| YAML parse / SVG XML error | Check indentation and quotes in `system_info.yaml` |
| `python scripts/today.py` path errors | Run from **repo root**, not from `scripts/` |

---

## One-liners

```text
Static text   →  edit system_info.yaml  →  python3 scripts/update_system_info.py  →  git push
Live fields   →  python3 scripts/today.py                                        →  git push
Portrait      →  edit assets/portrait.txt  (or image_to_ascii.py)  →  re-embed SVGs →  git push
Daily auto    →  GitHub Action update-banners.yml (Uptime + Lang + Stats)
Snake auto    →  GitHub Action snake.yml
```
