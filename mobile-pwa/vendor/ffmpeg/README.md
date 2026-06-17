# ffmpeg.wasm 资源目录

这个目录用于放置浏览器版 FFmpeg 运行文件。为了让手机端不依赖第三方 CDN，部署前请把下面文件放到对应位置：

```text
vendor/ffmpeg/ffmpeg.js
vendor/ffmpeg/814.ffmpeg.js
vendor/ffmpeg/util.js
vendor/ffmpeg/core/ffmpeg-core.js
vendor/ffmpeg/core/ffmpeg-core.wasm
```

推荐使用和 ffmpeg.wasm 官方示例一致的 `0.12.x` 版本。文件来源可以是 npm 包，也可以先从 CDN 下载后放进本目录。

示例下载地址：

```text
https://cdn.jsdelivr.net/npm/@ffmpeg/ffmpeg@0.12.10/dist/umd/ffmpeg.js
https://cdn.jsdelivr.net/npm/@ffmpeg/ffmpeg@0.12.10/dist/umd/814.ffmpeg.js
https://cdn.jsdelivr.net/npm/@ffmpeg/util@0.12.1/dist/umd/index.js
https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.10/dist/umd/ffmpeg-core.js
https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.10/dist/umd/ffmpeg-core.wasm
```

如果后续要改成多线程版本，还需要 `@ffmpeg/core-mt` 的 `ffmpeg-core.worker.js`，并且托管平台要能配置 `Cross-Origin-Opener-Policy` 和 `Cross-Origin-Embedder-Policy`。当前第一版使用单线程核心，兼容性更稳。
