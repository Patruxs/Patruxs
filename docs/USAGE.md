# Animated profile guide

This repository powers the Patruxs GitHub profile. The synchronized dark and
light banners are self-contained SVGs with an animated dithered portrait and
terminal-style profile details.

Run every command from the repository root.

## Repository layout

```text
Patruxs/
├── README.md
├── dark.svg
├── light.svg
├── metrics.json
├── requirements.txt
├── assets/
│   ├── portrait.png
│   ├── animated-divider.gif
│   └── profile-summary-card-output/
├── scripts/
│   ├── fetch_data.py
│   └── generate_profile.py
└── .github/workflows/
    └── update-profile.yml
```

Both profile SVGs are produced by one generator run from the same profile data
and animation model. Only their palette and portrait treatment differ.

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

- `dark.svg` - the dark profile asset committed to the repository
- `light.svg` - the light profile asset committed to the repository
- `metrics.json` - deterministic generation and animation diagnostics
- `profile.html` - a local browser preview ignored by Git

Open `profile.html` in a browser to inspect the animation. Check both browser
color schemes before publishing.

## Customize the profile

Edit the public profile data near the top of
`scripts/generate_profile.py`:

- `INFO_LINES`
- `LOGO_MARKS`

Replace `assets/portrait.png` to change the portrait. A transparent-background
PNG produces the cleanest subject mask.

After either change, regenerate and review `profile.html`.

## GitHub Actions

The `Update profile` workflow:

1. Regenerates both profile SVGs and `metrics.json`.
2. Runs `scripts/fetch_data.py` to refresh the account uptime, every value in
   the System Info GitHub Stats block, and both themes of the three summary
   cards displayed by `README.md`.
3. Commits changed generated assets to `main`.

The workflow runs daily at 00:00 UTC and can also be started from the Actions
tab. The repository must allow GitHub Actions read and write access.

`ACCESS_TOKEN` or `SUMMARY_GITHUB_TOKEN` is optional. When present, it is used
for GitHub API requests; otherwise the workflow uses `github.token`.
Set the optional `BIRTHDAY` repository variable to a `YYYY-MM-DD` date when the
Uptime row should measure from a date other than GitHub account creation.

## Profile README

GitHub renders the root banner with:

```html
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./dark.svg"/>
    <img src="./light.svg" width="100%" alt="Patruxs animated terminal profile"/>
  </picture>
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
| Summary cards do not refresh | Check workflow permissions and the `Fetch live profile data and summary cards` logs |
