# Profile banner guide

This repo powers the GitHub profile page for **Patruxs**: animated banners,
live stats, contribution snake, and the profile README.

## Layout

```text
Patruxs/
├── README.md                 # Profile page (what GitHub shows)
├── dark.svg / light.svg      # Theme banners
├── snake.svg / snake-dark.svg
├── system_info.yaml          # Edit static SYSTEM.INFO fields here
├── requirements.txt
├── assets/
│   └── portrait.txt          # ASCII art source for VISUAL.MAP
├── scripts/
│   ├── today.py              # Live: Uptime, Lang, GitHub Stats
│   ├── update_system_info.py # Apply system_info.yaml → SVGs
│   ├── ascii_to_svg.py       # portrait.txt → SVG tspans
│   └── image_to_ascii.py     # photo → portrait.txt
├── docs/
│   └── USAGE.md              # This file
└── .github/workflows/
    ├── update-banners.yml    # Daily live field refresh
    └── snake.yml             # Contribution snake
```

## Quick start

```bash
# Install deps (once)
pip install -r requirements.txt

# Edit static text
#   open system_info.yaml

# Apply static fields + refresh Uptime / Lang
python3 scripts/update_system_info.py

# Or full live refresh (Uptime, all languages, GitHub Stats)
export ACCESS_TOKEN=ghp_...   # optional but recommended
python3 scripts/today.py

# Preview
#   open dark.svg / light.svg in a browser

git add system_info.yaml dark.svg light.svg
git commit -m "Update profile banner"
git push
```

## What updates automatically

| Field | Source | Workflow |
|-------|--------|----------|
| **Uptime** | Account age or `BIRTHDAY` var | `update-banners.yml` (daily) |
| **Lang** | Languages across owned non-fork repos | same |
| **GitHub Stats** | Repos, stars, commits, followers, LOC | same (needs token) |
| **Snake** | Contribution graph | `snake.yml` (every 12h) |

Static rows (Subject, Role, Contact, …) come from `system_info.yaml` only.

## Edit static SYSTEM.INFO

Open `system_info.yaml`:

```yaml
host: patruxs@devos

fields:
  - key: Subject
    value: Your Name
  - key: Role
    value: Backend Engineer · Fullstack Engineer
  - key: Lang
    value: ""          # filled live by today.py — leave empty

sections:
  - title: Contact
    fields:
      - key: Grid.Mail
        value: you@email.com
  - title: GitHub Stats
    kind: github_stats # live ids; values filled by today.py
```

Then:

```bash
python3 scripts/update_system_info.py
```

### Line types

| YAML | Renders as |
|------|------------|
| `host:` | Purple header |
| `key` + `value` | `. Key: ........ Value` |
| empty key/value | Spacer |
| `Grid.Mail` | Nested key styling |
| `Lang` | Multi-line live languages |
| `sections[].title` | `- Section` header |
| `kind: github_stats` | Live stats block |

## ASCII portrait (VISUAL.MAP)

1. Put art in `assets/portrait.txt`, **or** generate from a photo:

```bash
python3 scripts/image_to_ascii.py path/to/photo.jpg -o assets/portrait.txt
```

2. Optional: emit tspans for manual SVG editing:

```bash
python3 scripts/ascii_to_svg.py
# writes assets/portrait_tspan.txt
```

3. Re-apply portrait into the banners (agent/script or paste tspans into SVG).

`update_system_info.py` only rewrites the SYSTEM.INFO panel, not the portrait.

## GitHub Actions setup

### Secrets / variables

| Name | Type | Purpose |
|------|------|---------|
| `ACCESS_TOKEN` | Secret | PAT for private repos + reliable GraphQL stats |
| `BIRTHDAY` | Variable | Optional `YYYY-MM-DD` for Uptime (else account created_at) |

Repo → **Settings → Secrets and variables → Actions**

Workflow permissions: **Read and write**.

### Manual run

**Actions → Update profile banners → Run workflow**

## Profile README

`README.md` should stay at the repo root with:

```markdown
![Patruxs](./dark.svg#gh-dark-mode-only)
![Patruxs](./light.svg#gh-light-mode-only)
```

Repo name must be `USERNAME/USERNAME` for the profile README to appear.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| SVG unchanged | Hard-refresh browser |
| GitHub shows old banner | Wait ~1 min or hard-refresh profile |
| Stats stay `0` | Set `ACCESS_TOKEN` secret (PAT) |
| Push races in CI | Workflow already rebases/retries |

## One-liner

```text
Edit system_info.yaml  →  python3 scripts/update_system_info.py  →  git push
Live stats               →  python3 scripts/today.py             →  git push
```
