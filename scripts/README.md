# Scripts

| Script | Purpose |
|--------|---------|
| `generate_profile.py` | Optionally rebuild the animated profile from a local portrait image |
| `fetch_data.py` | Refresh live System Info values and the summary cards used by `README.md` |

Run from the repo root:

```bash
python3 scripts/fetch_data.py
```

The fetch script updates the synchronized `assets/dark.svg` and
`assets/light.svg` banners in place. See
[docs/USAGE.md](../docs/USAGE.md) for optional banner regeneration instructions.
