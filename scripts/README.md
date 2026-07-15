# Scripts

| Script | Purpose |
|--------|---------|
| `today.py` | Live refresh: Uptime, Lang, GitHub Stats → `dark.svg` / `light.svg` |
| `update_system_info.py` | Apply `system_info.yaml` structure + light live fill |
| `ascii_to_svg.py` | `assets/portrait.txt` → SVG tspans |
| `image_to_ascii.py` | Photo → ASCII portrait |

Run from the **repo root**:

```bash
python3 scripts/today.py
python3 scripts/update_system_info.py
python3 scripts/ascii_to_svg.py
python3 scripts/image_to_ascii.py photo.jpg -o assets/portrait.txt
```

See [docs/USAGE.md](../docs/USAGE.md) for full docs.
