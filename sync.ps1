# Push D:\Projects\BlenderMCP source → live install paths.
# Run after editing addon/blender_mcp_addon.py or server/server.py.

$ErrorActionPreference = "Stop"
$src = "D:\Projects\BlenderMCP"

# Addon → Blender 5.1 user-addons
$addonDst = "$env:APPDATA\Blender Foundation\Blender\5.1\scripts\addons\blender_mcp_addon.py"
Copy-Item "$src\addon\blender_mcp_addon.py" $addonDst -Force
Write-Host "[OK] addon  -> $addonDst"

# Server → uv-tool install + ephemeral caches (kept synced so uvx-fallback also works)
$serverPaths = @(
    "$env:APPDATA\uv\tools\blender-mcp\Lib\site-packages\blender_mcp\server.py",
    "$env:LOCALAPPDATA\uv\cache\archive-v0\av3Q_1hQQlZbtTCS\blender_mcp\server.py",
    "$env:LOCALAPPDATA\uv\cache\archive-v0\yldWTfYPcvkqh8ph\Lib\site-packages\blender_mcp\server.py",
    "$env:LOCALAPPDATA\uv\cache\archive-v0\zlATC0VRJW1EK7nW\Lib\site-packages\blender_mcp\server.py"
)
foreach ($p in $serverPaths) {
    if (Test-Path $p) {
        Copy-Item "$src\server\server.py" $p -Force
        Write-Host "[OK] server -> $p"
    }
}

# Wipe __pycache__ everywhere so reload picks up changes
$pycacheRoots = @(
    "$env:APPDATA\Blender Foundation\Blender\5.1\scripts\addons\__pycache__",
    "$env:APPDATA\uv\tools\blender-mcp\Lib\site-packages\blender_mcp\__pycache__"
)
foreach ($r in $pycacheRoots) {
    if (Test-Path $r) {
        Remove-Item $r -Recurse -Force
        Write-Host "[OK] pycache wiped: $r"
    }
}
Get-ChildItem "$env:LOCALAPPDATA\uv\cache" -Recurse -Filter "__pycache__" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -like "*blender_mcp*" } |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force; Write-Host "[OK] pycache wiped: $($_.FullName)" }

Write-Host ""
Write-Host "Next: in Blender, F3 -> Reload Scripts.  Then /mcp reconnect blender-mcp."
