# blender-mcp

MCP server for Blender. ~270 direct-dispatch tools (BM_EXT) — no per-call Python compilation overhead. Hang detection, console-read, mesh-edit, weight tools, animation tools, label-by-side, plane-split weighting, more.

## Forced auto-update

Every Blender start, the addon reads `VERSION` from this repo's `main` branch via raw URL. If different from local, it overwrites both `blender_mcp_addon.py` (Blender addons folder) and `server.py` (uv-tool install) automatically. No opt-out. Restart Blender to load.

To pause updates: set `_BM_AUTOUPDATE_REPO = ""` in the addon header, or match `LOCAL_VERSION` to the remote string.

## Source layout

```
addon/blender_mcp_addon.py   # Blender side (handlers + console tee + autoupdate)
server/server.py             # MCP server side (276 @mcp.tool)
sync.ps1                     # local dev: push source -> install paths
textures/sides/              # T/B/F/K/L/R side-label PNGs for bm_label_faces_by_side
VERSION                      # remote-version probe target
```

## Local dev

1. Edit `addon/blender_mcp_addon.py` or `server/server.py`
2. `.\sync.ps1`
3. Bump `VERSION` + commit + push → triggers autoupdate on other machines
4. In Blender: F3 → Reload Scripts, or call `bm_reload_addon` MCP tool

## Install paths

| File | Path |
|---|---|
| Addon | `%APPDATA%\Blender Foundation\Blender\5.1\scripts\addons\blender_mcp_addon.py` |
| Server (pinned) | `%APPDATA%\uv\tools\blender-mcp\Lib\site-packages\blender_mcp\server.py` |

Client config (`~\.claude.json`) points at `C:\Users\<user>\.local\bin\blender-mcp.exe`.

## Headline tools

- `bm_ping`, `bm_list`, `bm_read_console` — token-friendly
- `bm_force_mode_set` — robust mode change with VIEW_3D override
- `bm_inspect_modifier`, `bm_inspect_animation`, `bm_get_evaluated_vertex`, `bm_count_vgroup_weights` — introspection
- `bm_weight_by_axis_split`, `bm_weight_by_plane_split` — split mesh weights along axis / arbitrary plane (sharp or smooth blend)
- `bm_label_faces_by_side` — per-side textures with aspect-preserve UV projection
- `bm_reload_addon` — hot-reload without UI toggle
