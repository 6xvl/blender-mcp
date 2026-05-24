#!/usr/bin/env bash
# blender-mcp one-shot installer (macOS / Linux)
# Run:  curl -fsSL https://raw.githubusercontent.com/6xvl/blender-mcp/main/install.sh | bash
set -euo pipefail
repo="6xvl/blender-mcp"
raw="https://raw.githubusercontent.com/${repo}/main"

case "$(uname -s)" in
  Darwin) base="$HOME/Library/Application Support/Blender" ;;
  Linux)  base="$HOME/.config/blender" ;;
  *) echo "Unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac

echo "[1/4] Locating Blender addons folder…"
ver=$(ls -1 "$base" 2>/dev/null | sort -V | tail -n1 || true)
[ -z "$ver" ] && { echo "Blender config dir not found at $base" >&2; exit 1; }
addons="$base/$ver/scripts/addons"
mkdir -p "$addons"
curl -fsSL "$raw/addon/blender_mcp_addon.py" -o "$addons/blender_mcp_addon.py"
echo "  ✓ addon → $addons/blender_mcp_addon.py"

echo "[2/4] Installing uv tool blender-mcp…"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv tool install blender-mcp --force >/dev/null 2>&1

echo "[3/4] Patching server.py with BM_EXT toolset…"
case "$(uname -s)" in
  Darwin) srv="$HOME/Library/Application Support/uv/tools/blender-mcp/lib/python3.*/site-packages/blender_mcp/server.py" ;;
  Linux)  srv="$HOME/.local/share/uv/tools/blender-mcp/lib/python3.*/site-packages/blender_mcp/server.py" ;;
esac
srv_path=$(ls -1 $srv 2>/dev/null | head -n1 || true)
[ -z "$srv_path" ] && { echo "server.py not found after uv install; check 'uv tool dir'" >&2; exit 1; }
curl -fsSL "$raw/server/server.py" -o "$srv_path"
find "$(dirname "$srv_path")" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

bin="$(uv tool dir 2>/dev/null)/blender-mcp/bin/blender-mcp"
[ -x "$bin" ] || bin="$HOME/.local/bin/blender-mcp"

echo "[4/4] Done. MCP config snippet (paste into your client):"
cat <<EOF

  Claude Code   (~/.claude.json → mcpServers):
    "blender-mcp": { "type": "stdio", "command": "$bin", "args": [], "env": {} }

  Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json on macOS,
                  ~/.config/Claude/claude_desktop_config.json on Linux):
    same shape, under "mcpServers"

  Codex / Gemini CLI: add equivalent stdio server entry pointing to:
    $bin

Open Blender → Edit > Preferences > Add-ons → enable "Blender MCP"
N panel → BlenderMCP → Connect to Claude
EOF
