# blender-mcp one-shot installer (Windows / PowerShell)
# Run:  iwr https://raw.githubusercontent.com/6xvl/blender-mcp/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
$repo  = "6xvl/blender-mcp"
$raw   = "https://raw.githubusercontent.com/$repo/main"

Write-Host "[1/4] Locating Blender addons folder…"
$cands = Get-ChildItem "$env:APPDATA\Blender Foundation\Blender" -Directory -ErrorAction SilentlyContinue |
         Sort-Object Name -Descending
if (-not $cands) { throw "Blender config dir not found at $env:APPDATA\Blender Foundation\Blender" }
$addonsDir = Join-Path $cands[0].FullName "scripts\addons"
New-Item -ItemType Directory -Force $addonsDir | Out-Null
$addonPath = Join-Path $addonsDir "blender_mcp_addon.py"
Invoke-WebRequest "$raw/addon/blender_mcp_addon.py" -OutFile $addonPath
Write-Host "  ✓ addon → $addonPath"

Write-Host "[2/4] Installing uv tool blender-mcp…"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    iwr https://astral.sh/uv/install.ps1 | iex
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
}
uv tool install blender-mcp --force 2>&1 | Out-Null

Write-Host "[3/4] Patching server.py with BM_EXT toolset…"
$serverDst = "$env:APPDATA\uv\tools\blender-mcp\Lib\site-packages\blender_mcp\server.py"
Invoke-WebRequest "$raw/server/server.py" -OutFile $serverDst
# Wipe pycache
Get-ChildItem -Path (Split-Path $serverDst) -Filter __pycache__ -Recurse -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

Write-Host "[4/4] Done. MCP config snippet (paste into your client):"
$bin = "$env:USERPROFILE\.local\bin\blender-mcp.exe"
@"

  Claude Code   (~/.claude.json → mcpServers):
    "blender-mcp": { "type": "stdio", "command": "$($bin -replace '\\','\\\\')", "args": [], "env": {} }

  Claude Desktop (%APPDATA%\Claude\claude_desktop_config.json):
    same shape, under "mcpServers"

  Codex / Gemini CLI: add equivalent stdio server entry pointing to:
    $bin

Open Blender → Edit > Preferences > Add-ons → enable "Blender MCP"
N panel → BlenderMCP → Connect to Claude
"@ | Write-Host
