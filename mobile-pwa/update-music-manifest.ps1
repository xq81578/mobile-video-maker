$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$MusicDir = Join-Path $Root "music"
$Manifest = Join-Path $MusicDir "manifest.json"
$Extensions = @(".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")

if (-not (Test-Path $MusicDir)) {
    New-Item -ItemType Directory -Force -Path $MusicDir | Out-Null
}

$Songs = Get-ChildItem -Path $MusicDir -File |
    Where-Object { $Extensions -contains $_.Extension.ToLowerInvariant() } |
    Sort-Object Name |
    ForEach-Object {
        [PSCustomObject]@{
            name = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
            file = $_.Name
        }
    }

$Songs | ConvertTo-Json -Depth 3 | Set-Content -Path $Manifest -Encoding UTF8
Write-Host "Updated $Manifest"
