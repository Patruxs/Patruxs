# Scripts

| Script | Purpose |
|--------|---------|
| `generate_profile.py` | Build the self-contained animated profile from `assets/portrait.png` |
| `fetch_data.py` | Refresh live System Info values and the summary cards used by `README.md` |

Run from the repo root:

```bash
python3 scripts/generate_profile.py
python3 scripts/fetch_data.py
```

This writes the synchronized `dark.svg` and `light.svg` banners,
`metrics.json`, and the ignored local preview `profile.html`. See
[docs/USAGE.md](../docs/USAGE.md) for full instructions.
