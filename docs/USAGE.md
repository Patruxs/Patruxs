# Animated profile guide

This repository powers the Patruxs GitHub profile. The banner is one
self-contained SVG with an animated dithered portrait, automatic dark and
light themes, and terminal-style profile details.

Run every command from the repository root.

## Repository layout

```text
Patruxs/
├── README.md
├── profile.svg
├── metrics.json
├── requirements.txt
├── assets/
│   ├── portrait.png
│   ├── animated-divider.gif
│   └── profile-summary-card-output/
├── scripts/
│   └── generate_profile.py
└── .github/workflows/
    └── update-profile.yml
```

`profile.svg` contains both color schemes. The SVG chooses its palette through
`prefers-color-scheme`, so separate dark and light banner files are not needed.

## Rebuild the banner

Install the dependencies once:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then generate all outputs:

```bash
python3 scripts/generate_profile.py
```

The command reads `assets/portrait.png` and writes:

- `profile.svg` - the profile asset committed to the repository
- `metrics.json` - deterministic generation and animation diagnostics
- `profile.html` - a local browser preview ignored by Git

Open `profile.html` in a browser to inspect the animation. Check both browser
color schemes before publishing.

## Customize the profile

Edit the public profile data near the top of
`scripts/generate_profile.py`:

- `HANDLE`
- `PROFILE_ROWS`
- `LOGO_MARKS`

Replace `assets/portrait.png` to change the portrait. A transparent-background
PNG produces the cleanest subject mask.

After either change, regenerate and review `profile.html`.

## GitHub Actions

The `Update profile` workflow:

1. Regenerates `profile.svg` and `metrics.json`.
2. Refreshes both themes of the GitHub profile summary cards on scheduled and
   manually dispatched runs.
3. Commits changed generated assets to `main`.

The workflow runs daily at 00:00 UTC and can also be started from the Actions
tab. The repository must allow GitHub Actions read and write access.

`ACCESS_TOKEN` or `SUMMARY_GITHUB_TOKEN` is optional. When present, it is used
by the summary-card action; otherwise the workflow uses `github.token`.

## Profile README

GitHub renders the root banner with:

```html
<p align="center">
  <img src="./profile.svg" width="100%" alt="Patruxs animated terminal profile"/>
</p>
```

The special repository name `USERNAME/USERNAME` is required for GitHub to show
the repository README on a user profile.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | Install `requirements.txt` in the active environment |
| Portrait clipping looks wrong | Use a transparent PNG with visible head and shoulders |
| Banner looks unchanged | Rebuild it, then hard-refresh after GitHub updates its image cache |
| Animation does not run locally | Preview through a browser instead of an editor's static SVG viewer |
| Summary cards do not refresh | Check workflow permissions and the summary-card action logs |
