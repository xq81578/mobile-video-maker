$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vendor = Join-Path $Root "vendor\ffmpeg"
$Core = Join-Path $Vendor "core"

New-Item -ItemType Directory -Force -Path $Core | Out-Null

$Files = @(
    @{
        Url = "https://cdn.jsdelivr.net/npm/@ffmpeg/ffmpeg@0.12.10/dist/umd/ffmpeg.js"
        Path = Join-Path $Vendor "ffmpeg.js"
    },
    @{
        Url = "https://cdn.jsdelivr.net/npm/@ffmpeg/ffmpeg@0.12.10/dist/umd/814.ffmpeg.js"
        Path = Join-Path $Vendor "814.ffmpeg.js"
    },
    @{
        Url = "https://cdn.jsdelivr.net/npm/@ffmpeg/util@0.12.1/dist/umd/index.js"
        Path = Join-Path $Vendor "util.js"
    },
    @{
        Url = "https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.10/dist/umd/ffmpeg-core.js"
        Path = Join-Path $Core "ffmpeg-core.js"
    },
    @{
        Url = "https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.10/dist/umd/ffmpeg-core.wasm"
        Path = Join-Path $Core "ffmpeg-core.wasm"
    }
)

foreach ($File in $Files) {
    Write-Host "Downloading $($File.Url)"
    Invoke-WebRequest -Uri $File.Url -OutFile $File.Path
}

Write-Host "Done. FFmpeg assets are ready in $Vendor"
