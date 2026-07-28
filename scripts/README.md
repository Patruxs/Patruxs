# Scripts

| Script | Purpose |
|--------|---------|
| `fetch_data.py` | Apply `system_info.yaml`, refresh GitHub data, and merge `projects.json` when present |
| `ascii_to_svg.py` | `assets/portrait.txt` → SVG tspans |
| `image_to_ascii.py` | Photo → ASCII portrait |

Run from the **repo root**:

```bash
python3 scripts/fetch_data.py
python3 scripts/ascii_to_svg.py
python3 scripts/image_to_ascii.py photo.jpg -o assets/portrait.txt
```

See [docs/USAGE.md](../docs/USAGE.md) for full docs.
