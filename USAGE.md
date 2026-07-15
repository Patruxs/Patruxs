# How to use this profile banner

This project builds the animated GitHub profile header (`dark.svg` + `light.svg`).

## Quick start

```bash
# 1. Edit your system info
#    open system_info.yaml in any editor

# 2. Apply changes to both SVGs
python3 update_system_info.py

# 3. Preview
#    open dark.svg or light.svg in a browser
```

Then commit and push to your profile repo so GitHub shows the update.

---

## Files you care about

| File | What it is |
|------|------------|
| `system_info.yaml` | **Edit this** - name, role, skills, contact, etc. |
| `update_system_info.py` | Script that writes SYSTEM.INFO into the SVGs |
| `portrait.txt` | ASCII portrait used in VISUAL.MAP |
| `dark.svg` | Banner for dark GitHub theme |
| `light.svg` | Banner for light GitHub theme |
| `README.md` | Your GitHub profile page (shows the banners) |

---

## Update SYSTEM.INFO (right panel)

### 1. Open `system_info.yaml`

Change any field you want:

```yaml
host: patruxs@devos

fields:
  - key: Subject
    value: Your Name

  - key: Role
    value: Backend Engineer · Spring Boot

  # blank line
  - key: ""
    value: ""

  - key: Lang
    value: Java

sections:
  - title: Contact
    fields:
      - key: Grid.Mail
        value: you@email.com
      - key: Grid.Github
        value: YourGithub

  - title: Live Stats
    note: See live GitHub stats badges below in README ↓
```

### 2. Run the updater

```bash
python3 update_system_info.py
```

You need Python 3. Install PyYAML if needed:

```bash
pip install pyyaml
```

### 3. Check the result

Open `dark.svg` and `light.svg` in a browser. The right panel (SYSTEM.INFO) should show your new text.

### 4. Publish

```bash
git add system_info.yaml dark.svg light.svg
git commit -m "Update profile SYSTEM.INFO"
git push
```

---

## Line types in `system_info.yaml`

| YAML | Shows as |
|------|----------|
| `host: name@devos` | Purple header at the top |
| `key` + `value` | `. Key: ........ Value` |
| empty `key` and `value` | Blank spacer row |
| `Core.Lang` / `Grid.Mail` | Nested keys (`Core.Lang`) |
| `sections[].title` | Green section title (`- Contact`) |
| `sections[].note` | Free text under a section |

---

## Update the ASCII portrait (left panel)

1. Edit `portrait.txt` (keep a monospace block of ASCII art).
2. Rebuild the SVGs so VISUAL.MAP uses the new art  
   (or ask your agent / re-run your portrait patch script if you have one).

Right now, **only SYSTEM.INFO is automated** via `update_system_info.py`.  
Portrait updates are done by changing `portrait.txt` and regenerating the banner ASCII block.

---

## GitHub profile setup

In `README.md` you should have:

```markdown
![Banner](./dark.svg#gh-dark-mode-only)
![Banner](./light.svg#gh-light-mode-only)
```

- Dark mode on GitHub → `dark.svg`
- Light mode on GitHub → `light.svg`

Repo name must match your username (`Patruxs/Patruxs`) for the profile README to show.

---

## Common edits

**Change name / role**

```yaml
fields:
  - key: Subject
    value: New Name
  - key: Role
    value: Full Stack Developer
```

Then:

```bash
python3 update_system_info.py
```

**Change email**

```yaml
sections:
  - title: Contact
    fields:
      - key: Grid.Mail
        value: new@email.com
```

Then run the script again.

**Add a skill row**

Under `fields:`:

```yaml
  - key: Core.Cloud
    value: AWS, Docker
```

Then run the script again.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: yaml` | `pip install pyyaml` |
| SVG looks unchanged | Hard-refresh the browser, or re-open the file |
| GitHub still shows old banner | Wait a minute, or hard-refresh the profile page |
| XML / parse error | Re-check quotes and indentation in `system_info.yaml` |

---

## One-liner reminder

```text
Edit system_info.yaml  →  python3 update_system_info.py  →  git push
```
