# Profile banner guide

This repository powers the **Patruxs** GitHub profile: dual-theme animated
banners, live stats, summary cards, and the profile `README.md`.

Run every command from the **repo root** unless noted.

---

## Repository layout

```text
Patruxs/
├── README.md                      # What GitHub shows on your profile
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
│   ├── fetch_data.py              # Apply YAML and refresh live GitHub data
│   ├── ascii_to_svg.py            # portrait.txt → SVG <tspan> block
│   ├── image_to_ascii.py          # Photo → ASCII portrait
│   └── README.md
│
├── docs/
│   └── USAGE.md                   # This guide
│
└── .github/workflows/
    └── update-profile.yml         # Daily banners and summary cards
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

# 3. Apply YAML and refresh live fields
export ACCESS_TOKEN=ghp_...          # optional, recommended for stats
python3 scripts/fetch_data.py

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
| **Uptime** | GitHub account `created_at`, or `BIRTHDAY` variable | Daily Action / `fetch_data.py` |
| **Lang** | Languages across **owned, non-fork** repos (by code size) | Daily Action / `fetch_data.py` |
| **GitHub Stats** | Repos, contributed repos, stars, commits, followers, LOC | Daily Action / `fetch_data.py` (needs token) |
| **Subject, Role, Origin, …** | `system_info.yaml` | You edit YAML, then run `fetch_data.py` |
| **Contact** | `system_info.yaml` | Same |
| **ASCII portrait** | `assets/portrait.txt` | Manual / `image_to_ascii.py` |

Leave live keys empty in YAML (`Uptime`, `Lang`). `GitHub Stats` is a section
with `kind: github_stats` - values are filled by `fetch_data.py`, not hand-edited.

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
    value: ""                    # live - all repo languages

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
python3 scripts/fetch_data.py
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

Then run `python3 scripts/fetch_data.py`.

---

## Scripts reference

Run from repo root:

| Command | Purpose |
|---------|---------|
| `python3 scripts/fetch_data.py` | Full live update (Uptime, Lang, Stats) |
| `python3 scripts/ascii_to_svg.py` | Build tspans from `assets/portrait.txt` |
| `python3 scripts/image_to_ascii.py PHOTO -o assets/portrait.txt` | Photo → ASCII |

### `fetch_data.py` environment

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
python3 scripts/fetch_data.py
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
   (or have an agent do it). `fetch_data.py` does **not** rewrite VISUAL.MAP.

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

## GitHub Actions

### Workflows

| Workflow | File | Schedule | What it does |
|----------|------|----------|--------------|
| **Update profile** | `update-profile.yml` | Daily 00:00 UTC | Refreshes banners and both summary-card themes, then publishes them to `main` |

The profile update supports **workflow_dispatch** (manual run from the Actions tab).

### Secrets and variables

Repo → **Settings → Secrets and variables → Actions**

| Name | Kind | Purpose |
|------|------|---------|
| `ACCESS_TOKEN` | Secret | Fine-grained or classic PAT for stats / private languages |
| `BIRTHDAY` | Variable | Optional Uptime start date (`YYYY-MM-DD`) |

Also set **Actions → General → Workflow permissions** to **Read and write**.

Suggested PAT scopes (see comments in `scripts/fetch_data.py`):

- Account: read followers / starring / watching  
- Repositories: contents, metadata, commit statuses (as needed for LOC)

### Manual profile refresh

**Actions → Update profile → Run workflow**

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
| `python-dateutil`, `requests`, `lxml` | `fetch_data.py` |
| `PyYAML` | `fetch_data.py` (optional fallback parser exists) |
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
| `python scripts/fetch_data.py` path errors | Run from **repo root**, not from `scripts/` |

---

## One-liners

```text
Banner        ->  edit system_info.yaml  ->  python3 scripts/fetch_data.py  ->  git push
Portrait      ->  edit assets/portrait.txt (or image_to_ascii.py)  ->  re-embed SVGs
Daily auto    ->  GitHub Action update-profile.yml (banners + summary cards)
```
