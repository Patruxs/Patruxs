# Scripts

| Script | Purpose |
|--------|---------|
| `generate_profile.py` | Build the self-contained animated profile from `assets/portrait.png` |

Run from the repo root:

```bash
python3 scripts/generate_profile.py
```

This writes the synchronized `profile-dark.svg` and `profile-light.svg`
banners, `metrics.json`, and the ignored local preview `profile.html`. See
[docs/USAGE.md](../docs/USAGE.md) for full instructions.
