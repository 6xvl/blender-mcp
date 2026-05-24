# blender-mcp

> **MCP server for Blender.** ~270 direct-dispatch tools, hang detection, console capture, and forced auto-update. Drop it in, point your MCP client at it, drive Blender from any assistant.

[![GitHub](https://img.shields.io/badge/github-6xvl%2Fblender--mcp-blue?logo=github)](https://github.com/6xvl/blender-mcp)
![Blender](https://img.shields.io/badge/blender-3.0+-orange?logo=blender)
![Platform](https://img.shields.io/badge/platform-win%20%7C%20macOS%20%7C%20linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Install (one line)

Pick your shell. The installer downloads the addon, sets up the MCP server via [uv](https://docs.astral.sh/uv/), patches it, and prints the client-config snippet.

**Windows — PowerShell**

```powershell
iwr https://raw.githubusercontent.com/6xvl/blender-mcp/main/install.ps1 | iex
```

**macOS / Linux — Bash**

```bash
curl -fsSL https://raw.githubusercontent.com/6xvl/blender-mcp/main/install.sh | bash
```

That's it. Skip to **[Activate in Blender](#activate-in-blender)** next.

---

## What's in it

| Category | Examples |
|---|---|
| **Inspect** | `bm_list`, `bm_ping`, `bm_read_console` (token-friendly), `bm_inspect_modifier`, `bm_inspect_animation`, `bm_count_vgroup_weights` |
| **Transform** | `bm_set_transform`, `bm_apply_transforms`, `bm_set_origin`, `bm_translate`, `bm_rotate`, `bm_scale` |
| **Mesh edit** | `bm_rotate_verts`, `bm_translate_verts`, `bm_mirror_verts`, `bm_pca_align`, `bm_mesh_separate`, `bm_bisect_plane`, `bm_subdivide` |
| **Rig + skin** | `bm_add_armature`, `bm_auto_weights`, `bm_smooth_weights`, `bm_weight_by_axis_split`, `bm_weight_by_plane_split` |
| **Animate** | `bm_keyframe_bone`, `bm_keyframe_object`, `bm_set_frame`, `bm_push_to_nla`, `bm_keyframe_material_emission` |
| **Materials / UV** | `bm_create_material`, `bm_label_faces_by_side`, `bm_color_faces_by_side`, `bm_uv_unwrap`, `bm_resize_texture` |
| **Modifiers** | `bm_add_modifier`, `bm_apply_modifier`, `bm_add_armature_modifier`, `bm_add_softbody`, `bm_add_cloth`, `bm_add_fluid` |
| **Export** | `bm_export_fbx`, `bm_export_format` (OBJ/GLB/GLTF/DAE) |
| **Maintenance** | `bm_force_mode_set`, `bm_reload_addon` |

Full list: [tools_blender_mcp.md](https://github.com/6xvl/claude-identity/blob/main/skills/blender/references/tools_blender_mcp.md) (if you use the matching Claude skill) — or just `bm_list` once connected.

---

## Activate in Blender

After running the installer:

1. **Open Blender** (any version 3.0+).
2. **Edit → Preferences → Add-ons.**
3. Search **"Blender MCP"** → tick the checkbox.
4. Close Preferences. In the 3D viewport press **N** to open the sidebar.
5. Click the **BlenderMCP** tab → **Connect to Claude** (starts the socket on `localhost:9876`).

You'll see *"Running on port 9876"*. Blender side is done.

---

## Wire it into your MCP client

The installer prints the exact JSON snippet at the end. Generic shape:

```json
"blender-mcp": {
  "type": "stdio",
  "command": "<path printed by installer>",
  "args": [],
  "env": {}
}
```

| Client | Config file |
|---|---|
| **Claude Code** | `~/.claude.json` → `mcpServers` block |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` (Win) / `~/Library/Application Support/Claude/claude_desktop_config.json` (mac) / `~/.config/Claude/claude_desktop_config.json` (linux) |
| **Codex CLI** | `~/.codex/config.toml` → `[mcp_servers.blender-mcp]` |
| **Gemini CLI** | `~/.gemini/settings.json` → `mcpServers` |
| **Cursor / Windsurf / others** | any client that speaks stdio MCP — same shape |

Restart the client, then verify with:

```
bm_ping
```

Expected: `{"ok": true, "scene": "Scene", "frame": 0}`.

---

## Forced auto-update

Every time Blender starts, the addon hits `https://raw.githubusercontent.com/6xvl/blender-mcp/main/VERSION` and compares with its local `LOCAL_VERSION` constant. If different, it downloads fresh `blender_mcp_addon.py` + `server.py` and overwrites the install files in-place.

- **Pure stdlib** (urllib) — no `requests` dependency
- **Timeout 5 s** on the version probe — fails open if offline
- **Atomic write** via `.tmp` + `os.replace`
- **No opt-out by default**

To disable for a machine:

```python
# top of blender_mcp_addon.py
_BM_AUTOUPDATE_REPO = ""   # empty disables the probe
```

To publish an update from your fork:

```bash
# edit addon/blender_mcp_addon.py or server/server.py
echo "1.0.1" > VERSION
git add -A && git commit -m "feat: …" && git push
# next Blender startup on any machine pulls the new files
```

---

## Manual install

Use this if the one-liner fails or you want to know what it did.

```bash
# 1. Install uv (skip if you already have it)
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
# OR
iwr https://astral.sh/uv/install.ps1 | iex             # Windows

# 2. Install the MCP server
uv tool install blender-mcp

# 3. Patch server.py with this fork's expanded toolset
#    Find the path with:  uv tool dir
#    Then download:
curl -fsSL https://raw.githubusercontent.com/6xvl/blender-mcp/main/server/server.py \
  -o "<UV_TOOL_DIR>/blender-mcp/lib/python*/site-packages/blender_mcp/server.py"

# 4. Drop the addon into Blender's addons folder
#    Win:   %APPDATA%\Blender Foundation\Blender\<ver>\scripts\addons\
#    mac:   ~/Library/Application Support/Blender/<ver>/scripts/addons/
#    linux: ~/.config/blender/<ver>/scripts/addons/
curl -fsSL https://raw.githubusercontent.com/6xvl/blender-mcp/main/addon/blender_mcp_addon.py \
  -o "<BLENDER_ADDONS_DIR>/blender_mcp_addon.py"
```

---

## Local development

If you're hacking on the fork itself:

```
D:\Projects\BlenderMCP\
├── addon\blender_mcp_addon.py    # Blender side
├── server\server.py              # MCP server side
├── sync.ps1                      # push source → live install paths + wipe pycache
├── install.ps1 / install.sh      # public one-shot installers
├── textures\sides\               # T/B/F/K/L/R label PNGs for bm_label_faces_by_side
├── VERSION                       # auto-update probe target
└── README.md
```

Workflow:

```powershell
# 1. Edit either source file
# 2. Push to all live install paths + clear pycache
.\sync.ps1
# 3. In Blender call the hot-reload tool — no UI toggle needed
bm_reload_addon
# 4. /mcp reconnect in your client (socket restart)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `bm_ping` returns *"Could not connect to Blender"* | Blender open? N panel → BlenderMCP → **Connect to Claude**. Then `/mcp` reconnect on the client side. |
| Tool returns `{"error": "timeout", …}` | A bpy op blocked the main thread. Switch to OBJECT mode (`bm_force_mode_set ... OBJECT`) and retry. If persistent, toggle the addon off+on. |
| Tab missing in N panel | Check System Console (Window menu) for tracebacks. Reload Scripts (F3 → "Reload Scripts"). |
| `bm_set_mode` errors with "context is incorrect" | Use `bm_force_mode_set` instead — it overrides VIEW_3D context. |
| Auto-update didn't run | Update header `_BM_AUTOUPDATE_REPO` empty / no network / `VERSION` matches. Check `bm_read_console mode=summary` for the autoupdate log lines. |

---

## License

MIT.
