# Blender MCP Server

**Connect AI assistants like Claude, Codex, and Gemini to Blender.**

[![GitHub](https://img.shields.io/badge/github-6xvl%2Fblender--mcp-blue?logo=github)](https://github.com/6xvl/blender-mcp)
![Blender](https://img.shields.io/badge/blender-3.0+-orange?logo=blender)
![Platform](https://img.shields.io/badge/platform-win%20%7C%20macOS%20%7C%20linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What is This?

An MCP server that lets AI inspect your Blender scene, model, rig, animate, weight-paint, UV-unwrap, render, and export — all driven by ~270 direct-dispatch tools (no per-call Python compilation overhead). Forced auto-update keeps every machine on the same version.

## Setup

### 1. Install the plugin + server

**Windows — PowerShell:**
```powershell
iwr https://raw.githubusercontent.com/6xvl/blender-mcp/main/install.ps1 | iex
```

**macOS / Linux — Bash:**
```bash
curl -fsSL https://raw.githubusercontent.com/6xvl/blender-mcp/main/install.sh | bash
```

The installer drops the addon into Blender's addons folder, installs `uv`, runs `uv tool install blender-mcp`, and patches the installed `server.py` with this fork's expanded toolset.

### 2. Activate in Blender

- **Edit → Preferences → Add-ons** → search **"Blender MCP"** → tick it.
- Press **N** in the 3D viewport → **BlenderMCP** tab → **Connect to Claude**.

Status flips to *"Running on port 9876"*. Blender side is done.

### 3. Connect your AI

**Claude Code:**
```bash
claude mcp add blender-mcp -- blender-mcp
```

**Codex CLI:**
```bash
codex mcp add blender-mcp -- blender-mcp
```

**Gemini CLI:**
```bash
gemini mcp add blender-mcp blender-mcp --trust
```

Verify by asking the assistant to call `bm_ping`. Expected response: `{"ok": true, "scene": "Scene", "frame": 0}`.

<details>
<summary><strong>Other MCP clients (Claude Desktop, Cursor, Windsurf, manual config)</strong></summary>

### Generic JSON snippet

Add to your client's MCP config:

```json
{
  "mcpServers": {
    "blender-mcp": {
      "command": "blender-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

If `blender-mcp` isn't on PATH, use the absolute path printed by the installer (e.g. `C:\Users\<you>\.local\bin\blender-mcp.exe` on Windows, `~/.local/bin/blender-mcp` on macOS/Linux).

### Per-client config file

| Client | Config file |
|---|---|
| **Claude Code** | `~/.claude.json` → `mcpServers` |
| **Claude Desktop (Windows)** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Claude Desktop (macOS)** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Claude Desktop (Linux)** | `~/.config/Claude/claude_desktop_config.json` |
| **Codex CLI** | `~/.codex/config.toml` → `[mcp_servers.blender-mcp]` |
| **Gemini CLI** | `~/.gemini/settings.json` → `mcpServers` |
| **Cursor** | Settings → MCP → Add Server |
| **Windsurf** | Settings → MCP servers → JSON config |

### Manual install (no installer script)

```bash
# 1. Install uv if missing
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
iwr https://astral.sh/uv/install.ps1 | iex             # Windows PowerShell

# 2. Install the MCP server
uv tool install blender-mcp

# 3. Patch server.py with this fork's expanded toolset
#    Find the install dir:
uv tool dir
#    Then overwrite the file at: <UV_TOOL_DIR>/blender-mcp/lib/python*/site-packages/blender_mcp/server.py
curl -fsSL https://raw.githubusercontent.com/6xvl/blender-mcp/main/server/server.py \
  -o "<that-path>"

# 4. Drop the addon into Blender's addons folder
#    Win:   %APPDATA%\Blender Foundation\Blender\<ver>\scripts\addons\
#    mac:   ~/Library/Application Support/Blender/<ver>/scripts/addons/
#    linux: ~/.config/blender/<ver>/scripts/addons/
curl -fsSL https://raw.githubusercontent.com/6xvl/blender-mcp/main/addon/blender_mcp_addon.py \
  -o "<addons-dir>/blender_mcp_addon.py"
```

### Windows quirks

If PATH lookup fails, pass the full binary path:

```json
{
  "mcpServers": {
    "blender-mcp": {
      "command": "C:\\Users\\YOU\\.local\\bin\\blender-mcp.exe",
      "args": []
    }
  }
}
```

</details>

---

## What Can You Do?

Ask things like: *"List every armature and its bones"*, *"Bend the elbow 90° on Forearm_R at frame 30"*, *"Apply a 45° diagonal cut to Right_Arm and split weights between Bicep_R and Forearm_R"*, *"Render the camera view at frame 20 to disk"*, *"Export the rig and all animations as FBX for Roblox"*, *"Label each side of this mesh with Top/Bottom/Front/Back/Left/Right textures"*.

### Tool categories

| Category | Examples |
|---|---|
| **Inspect** | `bm_list`, `bm_ping`, `bm_read_console`, `bm_inspect_modifier`, `bm_inspect_animation`, `bm_count_vgroup_weights` |
| **Transform** | `bm_set_transform`, `bm_apply_transforms`, `bm_set_origin`, `bm_translate`, `bm_rotate`, `bm_scale` |
| **Mesh edit** | `bm_rotate_verts`, `bm_translate_verts`, `bm_mirror_verts`, `bm_pca_align`, `bm_mesh_separate`, `bm_bisect_plane`, `bm_subdivide` |
| **Rig + skin** | `bm_add_armature`, `bm_auto_weights`, `bm_smooth_weights`, `bm_weight_by_axis_split`, `bm_weight_by_plane_split`, `bm_paint_weight_to_bone` |
| **Animate** | `bm_keyframe_bone`, `bm_keyframe_object`, `bm_set_frame`, `bm_push_to_nla`, `bm_keyframe_material_emission` |
| **Materials / UV** | `bm_create_material`, `bm_label_faces_by_side`, `bm_color_faces_by_side`, `bm_uv_unwrap`, `bm_resize_texture` |
| **Modifiers** | `bm_add_modifier`, `bm_apply_modifier`, `bm_add_armature_modifier`, `bm_add_softbody`, `bm_add_cloth`, `bm_add_fluid` |
| **Export** | `bm_export_fbx`, `bm_export_format` (OBJ/GLB/GLTF/DAE) |
| **Maintenance** | `bm_force_mode_set`, `bm_reload_addon` |

Full tool catalog with signatures + docstrings: **[docs/tools_blender_mcp.md](docs/tools_blender_mcp.md)** (auto-generated from `server.py`). Once connected, call `bm_list` for scene objects and ask your assistant for tool details.

---

## Forced Auto-Update

Every Blender startup, the addon reads `VERSION` from this repo's `main` branch via raw URL. If different from local, both `blender_mcp_addon.py` and `server.py` are atomically replaced. No opt-out by default. Restart Blender to load the new code.

To disable on a machine:

```python
# top of blender_mcp_addon.py
_BM_AUTOUPDATE_REPO = ""   # empty disables the probe
```

To publish an update from a fork:

```bash
# edit addon/blender_mcp_addon.py or server/server.py
echo "1.0.1" > VERSION
git add -A && git commit -m "feat: …" && git push
# next Blender startup on any installed machine pulls the new files
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `bm_ping` returns *"Could not connect to Blender"* | N panel → BlenderMCP → **Connect to Claude**. Then `/mcp` reconnect on the client side. |
| Tool returns `{"error": "timeout", …}` | A bpy op is blocking the main thread. Run `bm_force_mode_set OBJECT` and retry. If persistent, toggle the addon off+on. |
| Tab missing in N panel | Window → Toggle System Console for tracebacks. Reload Scripts (F3 → "Reload Scripts"). |
| `bm_set_mode` errors with "context is incorrect" | Use `bm_force_mode_set` — it overrides the VIEW_3D context. |
| Auto-update didn't run | Network issue, `_BM_AUTOUPDATE_REPO` was emptied, or local `VERSION` already matches. Check `bm_read_console mode=summary` for autoupdate log lines. |

---

## Local Development

```
D:\Projects\BlenderMCP\
├── addon\blender_mcp_addon.py    # Blender side (handlers + console tee + autoupdate)
├── server\server.py              # MCP server side (276 @mcp.tool)
├── sync.ps1                      # push source → live install paths + wipe pycache
├── install.ps1 / install.sh      # public one-shot installers
├── textures\sides\               # T/B/F/K/L/R label PNGs for bm_label_faces_by_side
├── VERSION                       # auto-update probe target
├── LICENSE
└── README.md
```

Workflow:

```powershell
# 1. Edit either source file
# 2. Push to all live install paths + clear pycache
.\sync.ps1
# 3. Call the hot-reload MCP tool from your client — no UI toggle needed
bm_reload_addon
# 4. /mcp reconnect (socket restart)
```

---

[Report Issues](https://github.com/6xvl/blender-mcp/issues) | MIT Licensed
