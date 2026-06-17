# 手机本地 AI 出视频 PWA

这是独立于桌面版的新实现：网页本身可以部署到 GitHub Pages、Cloudflare Pages、Netlify 等静态托管平台；图片、音乐和视频合成都在手机浏览器本地完成，不需要电脑常开，也不需要购买服务器。

## 目录结构

```text
mobile-pwa/
  index.html
  assets/
    app.js
    styles.css
  vendor/
    ffmpeg/
      ffmpeg.js
      814.ffmpeg.js
      util.js
      core/
        ffmpeg-core.js
        ffmpeg-core.wasm
  music/
    manifest.json
    your-song.mp3
```

`vendor/ffmpeg` 下的 FFmpeg 文件体积较大，没有直接提交到项目里。部署前先执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\download-ffmpeg-assets.ps1
```

下载完成后，直接把整个 `mobile-pwa` 文件夹发布为静态站点即可。

## 使用方式

1. 手机浏览器打开静态站点地址。
2. 选择图片和背景音乐。
3. 调整图片顺序、每张图的上下文字和视频参数。
4. 点击“加载 FFmpeg”。首次打开会下载几十 MB 的 wasm 核心，后续会被浏览器和 PWA 缓存。
5. 点击“生成视频”，页面保持在前台，完成后下载 MP4。

## 内置背景音乐

把常用音乐放到 `music` 文件夹，然后更新音乐清单：

```powershell
powershell -ExecutionPolicy Bypass -File .\update-music-manifest.ps1
```

本地用 `python -m http.server` 预览时，网页会优先自动读取 `music` 目录里的音乐文件。部分静态托管平台不会开放目录索引，这时才会回退读取 `music/manifest.json`，新增或删除音乐后再重新生成清单。

## 部署建议

第一版建议使用 GitHub Pages。原因是 `ffmpeg-core.wasm` 通常超过 25 MiB，而 Cloudflare Pages 免费版单个静态资源限制为 25 MiB，可能无法直接托管这个 wasm 文件。

仓库根目录已经提供 `.github/workflows/deploy-mobile-pwa.yml`。推送到 GitHub 后，在仓库设置里把 Pages 的 Build and deployment Source 设为 `GitHub Actions`，之后每次推送 `main` 或 `master` 都会自动发布 `mobile-pwa` 目录。

部署流程会自动运行 `mobile-pwa/scripts/generate-music-manifest.mjs`，把 `music` 文件夹里的音乐写入 `music/manifest.json`。本地开发仍然会优先读取目录，线上 GitHub Pages 会使用这个清单。

如果使用 Cloudflare Pages，可以把大文件放到 R2 或其他静态文件服务，再把 `assets/app.js` 中的 `LOCAL_CORE_BASE` 改成对应地址。

## 当前限制

- 第一版使用单线程 ffmpeg.wasm，兼容性优先，速度会比电脑原生 FFmpeg 慢。
- 建议先使用 `720 x 1280`，图片数量控制在 20 张以内。
- 生成时不要锁屏或切后台，手机浏览器可能会暂停计算。
- 如果手机浏览器不支持某种图片或音频格式，需要先转换格式再使用。
