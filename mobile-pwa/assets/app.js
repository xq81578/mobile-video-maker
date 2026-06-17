(function () {
  "use strict";

  const LOCAL_CORE_BASE = "./vendor/ffmpeg/core";
  const OUTPUT_NAME = "output.mp4";
  const AUDIO_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"];

  const state = {
    images: [],
    audio: null,
    ffmpeg: null,
    ffmpegLoaded: false,
    loadingFfmpeg: false,
    generating: false,
    installPrompt: null,
    outputBlob: null,
    outputUrl: "",
    audioPreviewUrl: "",
    objectUrls: new Set(),
  };

  const els = {
    imageInput: document.getElementById("imageInput"),
    audioInput: document.getElementById("audioInput"),
    audioLabel: document.getElementById("audioLabel"),
    musicSelect: document.getElementById("musicSelect"),
    imageList: document.getElementById("imageList"),
    imageCount: document.getElementById("imageCount"),
    audioPreview: document.getElementById("audioPreview"),
    secondsInput: document.getElementById("secondsInput"),
    transitionDurationInput: document.getElementById("transitionDurationInput"),
    resolutionInput: document.getElementById("resolutionInput"),
    transitionInput: document.getElementById("transitionInput"),
    fontSizeInput: document.getElementById("fontSizeInput"),
    centerGapInput: document.getElementById("centerGapInput"),
    resetButton: document.getElementById("resetButton"),
    generateButton: document.getElementById("generateButton"),
    ffmpegState: document.getElementById("ffmpegState"),
    statusText: document.getElementById("statusText"),
    progressBar: document.getElementById("progressBar"),
    previewVideo: document.getElementById("previewVideo"),
    downloadButton: document.getElementById("downloadButton"),
    installButton: document.getElementById("installButton"),
    template: document.getElementById("imageItemTemplate"),
  };

  function setStatus(text) {
    els.statusText.textContent = text;
  }

  function setProgress(percent) {
    const value = Math.max(0, Math.min(100, percent));
    els.progressBar.style.width = `${value}%`;
  }

  function canGenerate() {
    return state.images.length > 0 && Boolean(state.audio);
  }

  function updateActions() {
    els.generateButton.disabled = state.generating || !canGenerate();
  }

  function setBusy(isBusy) {
    state.generating = isBusy;
    els.generateButton.disabled = isBusy || !canGenerate();
    els.imageInput.disabled = isBusy;
    els.audioInput.disabled = isBusy;
    els.musicSelect.disabled = isBusy;
  }

  function createObjectUrl(blob) {
    const url = URL.createObjectURL(blob);
    state.objectUrls.add(url);
    return url;
  }

  function revokeObjectUrl(url) {
    if (url && state.objectUrls.has(url)) {
      URL.revokeObjectURL(url);
      state.objectUrls.delete(url);
    }
  }

  function getExtension(file, fallback) {
    const match = file.name.toLowerCase().match(/\.([a-z0-9]+)$/);
    return match ? match[1] : fallback;
  }

  function encodePath(path) {
    return path
      .split("/")
      .map((part) => encodeURIComponent(part))
      .join("/");
  }

  function escapeFilterText(text) {
    return text.replace(/[\\'":%]/g, "\\$&");
  }

  function readSettings() {
    const seconds = Number(els.secondsInput.value);
    const transitionDuration = Number(els.transitionDurationInput.value);
    const [width, height] = els.resolutionInput.value.split("x").map(Number);
    const fontSize = Number(els.fontSizeInput.value);
    const centerGap = Number(els.centerGapInput.value);

    if (!Number.isFinite(seconds) || seconds <= 0) {
      throw new Error("每张时长必须大于 0。");
    }
    if (!Number.isFinite(transitionDuration) || transitionDuration <= 0) {
      throw new Error("转场时长必须大于 0。");
    }
    if (els.transitionInput.value !== "none" && transitionDuration >= seconds) {
      throw new Error("转场时长必须小于每张图片时长。");
    }
    if (!width || !height) {
      throw new Error("分辨率格式不正确。");
    }
    if (!Number.isFinite(fontSize) || fontSize <= 0) {
      throw new Error("文字字号必须大于 0。");
    }
    if (!Number.isFinite(centerGap) || centerGap < 0) {
      throw new Error("中线间距不能小于 0。");
    }

    return {
      seconds,
      transitionDuration,
      width,
      height,
      transition: els.transitionInput.value,
      fontSize,
      centerGap,
    };
  }

  function renderImages() {
    els.imageList.textContent = "";
    els.imageCount.textContent = `${state.images.length} 张图片`;

    state.images.forEach((item, index) => {
      const node = els.template.content.firstElementChild.cloneNode(true);
      const img = node.querySelector("img");
      const topText = node.querySelector(".top-text");
      const bottomText = node.querySelector(".bottom-text");
      const up = node.querySelector(".move-up");
      const down = node.querySelector(".move-down");
      const remove = node.querySelector(".remove");

      img.src = item.url;
      img.alt = item.file.name;
      topText.value = item.topText;
      bottomText.value = item.bottomText;
      up.disabled = index === 0;
      down.disabled = index === state.images.length - 1;

      topText.addEventListener("input", () => {
        item.topText = topText.value;
      });
      bottomText.addEventListener("input", () => {
        item.bottomText = bottomText.value;
      });
      up.addEventListener("click", () => moveImage(index, -1));
      down.addEventListener("click", () => moveImage(index, 1));
      remove.addEventListener("click", () => removeImage(index));

      els.imageList.appendChild(node);
    });

    updateActions();
  }

  function isAudioFile(file) {
    const lower = file.toLowerCase();
    return AUDIO_EXTENSIONS.some((extension) => lower.endsWith(extension));
  }

  function normalizeSong(file) {
    const decoded = decodeURIComponent(file);
    return {
      name: decoded.replace(/\.[^.]+$/, ""),
      file: decoded,
    };
  }

  function renderMusicOptions(songs) {
    els.musicSelect.textContent = "";

    if (!Array.isArray(songs) || songs.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "music 文件夹暂无音乐";
      els.musicSelect.appendChild(option);
      return;
    }

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "请选择背景音乐";
    els.musicSelect.appendChild(placeholder);

    songs.forEach((song, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = song.name || song.file;
      option.dataset.file = song.file || "";
      els.musicSelect.appendChild(option);
    });
  }

  async function discoverMusicFromDirectory() {
    const response = await fetch("./music/", { cache: "no-cache" });
    if (!response.ok) {
      throw new Error("当前托管不支持读取 music 目录。");
    }

    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    const songs = Array.from(doc.querySelectorAll("a"))
      .map((link) => link.getAttribute("href") || "")
      .map((href) => href.split("?")[0].split("#")[0])
      .filter((href) => href && !href.includes("/") && isAudioFile(href))
      .map(normalizeSong)
      .sort((left, right) => left.name.localeCompare(right.name, "zh-CN"));

    if (songs.length === 0) {
      throw new Error("music 目录里没有可识别的音乐文件。");
    }
    return songs;
  }

  async function discoverMusicFromManifest() {
    const response = await fetch("./music/manifest.json", { cache: "no-cache" });
    if (!response.ok) {
      throw new Error("没有找到音乐清单。");
    }
    return response.json();
  }

  async function loadMusicOptions() {
    try {
      const songs = await discoverMusicFromDirectory();
      renderMusicOptions(songs);
    } catch (directoryError) {
      console.warn(directoryError);
      try {
        const songs = await discoverMusicFromManifest();
        renderMusicOptions(songs);
      } catch (manifestError) {
        console.warn(manifestError);
        els.musicSelect.textContent = "";
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "音乐读取失败";
        els.musicSelect.appendChild(option);
      }
    }
  }

  async function chooseBuiltInMusic() {
    const selected = els.musicSelect.selectedOptions[0];
    const file = selected ? selected.dataset.file : "";
    if (!file) {
      return;
    }

    setStatus("正在读取背景音乐...");
    const response = await fetch(`./music/${encodePath(file)}`);
    if (!response.ok) {
      throw new Error(`无法读取音乐：${file}`);
    }
    const blob = await response.blob();
    setAudioFile(new File([blob], file, { type: blob.type || "audio/mpeg" }));
    els.audioInput.value = "";
    els.audioLabel.textContent = "从手机选择";
    setStatus(state.images.length ? "素材已选择，可以生成视频。" : "请继续选择图片。");
    updateActions();
  }

  function moveImage(index, direction) {
    const target = index + direction;
    if (target < 0 || target >= state.images.length) {
      return;
    }
    const [item] = state.images.splice(index, 1);
    state.images.splice(target, 0, item);
    renderImages();
  }

  function removeImage(index) {
    const [item] = state.images.splice(index, 1);
    revokeObjectUrl(item.url);
    renderImages();
  }

  function resetOutput() {
    if (els.previewVideo.src) {
      revokeObjectUrl(els.previewVideo.src);
      els.previewVideo.removeAttribute("src");
      els.previewVideo.load();
    }
    revokeObjectUrl(state.outputUrl);
    state.outputBlob = null;
    state.outputUrl = "";
    els.previewVideo.hidden = true;
    els.downloadButton.hidden = true;
  }

  function setAudioFile(file) {
    revokeObjectUrl(state.audioPreviewUrl);
    state.audio = file;
    state.audioPreviewUrl = createObjectUrl(file);
    els.audioPreview.src = state.audioPreviewUrl;
    els.audioPreview.hidden = false;
  }

  function resetAudio() {
    revokeObjectUrl(state.audioPreviewUrl);
    state.audioPreviewUrl = "";
    state.audio = null;
    els.audioPreview.removeAttribute("src");
    els.audioPreview.load();
    els.audioPreview.hidden = true;
  }

  function formatLocalTimestamp(date) {
    const pad = (value) => String(value).padStart(2, "0");
    return [
      date.getFullYear(),
      pad(date.getMonth() + 1),
      pad(date.getDate()),
      "-",
      pad(date.getHours()),
      pad(date.getMinutes()),
      pad(date.getSeconds()),
    ].join("");
  }

  async function saveGeneratedVideo() {
    if (!state.outputBlob) {
      setStatus("还没有可保存的视频。");
      return;
    }

    const fileName = `随身影集-${formatLocalTimestamp(new Date())}.mp4`;
    const file = new File([state.outputBlob], fileName, { type: "video/mp4" });

    try {
      if (window.showSaveFilePicker) {
        const handle = await window.showSaveFilePicker({
          suggestedName: fileName,
          types: [
            {
              description: "MP4 视频",
              accept: { "video/mp4": [".mp4"] },
            },
          ],
        });
        const writable = await handle.createWritable();
        await writable.write(state.outputBlob);
        await writable.close();
        setStatus("视频已保存。");
        return;
      }

      if (navigator.canShare && navigator.canShare({ files: [file] }) && navigator.share) {
        await navigator.share({
          files: [file],
          title: "随身影集",
          text: "保存生成的视频",
        });
        setStatus("已打开系统保存/分享面板。");
        return;
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setStatus("已取消保存。");
        return;
      }
      console.warn(error);
    }

    const anchor = document.createElement("a");
    anchor.href = state.outputUrl;
    anchor.download = fileName;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();

    setTimeout(() => {
      if (state.outputUrl) {
        window.open(state.outputUrl, "_blank", "noopener");
      }
    }, 300);
    setStatus("已触发下载；如果没有反应，请用系统浏览器打开这个页面。");
  }

  async function loadFfmpeg() {
    if (state.ffmpegLoaded || state.loadingFfmpeg) {
      return;
    }
    if (!window.FFmpegWASM || !window.FFmpegUtil) {
      throw new Error("没有找到本地 ffmpeg.wasm 文件，请检查 vendor/ffmpeg。");
    }

    state.loadingFfmpeg = true;
    const { FFmpeg } = window.FFmpegWASM;
    const { toBlobURL } = window.FFmpegUtil;
    const ffmpeg = new FFmpeg();

    ffmpeg.on("log", ({ message }) => {
      if (message) {
        console.debug(message);
      }
    });
    ffmpeg.on("progress", ({ progress }) => {
      if (state.generating && Number.isFinite(progress)) {
        setProgress(Math.round(progress * 100));
      }
    });

    els.ffmpegState.textContent = "FFmpeg 加载中";
    setStatus("正在准备视频引擎，首次打开会稍慢。");

    try {
      await ffmpeg.load({
        coreURL: await toBlobURL(`${LOCAL_CORE_BASE}/ffmpeg-core.js`, "text/javascript"),
        wasmURL: await toBlobURL(`${LOCAL_CORE_BASE}/ffmpeg-core.wasm`, "application/wasm"),
      });

      state.ffmpeg = ffmpeg;
      state.ffmpegLoaded = true;
      els.ffmpegState.textContent = "FFmpeg 已就绪";
      setStatus(canGenerate() ? "素材已选择，可以生成视频。" : "请选择图片和音乐。");
      updateActions();
    } finally {
      state.loadingFfmpeg = false;
    }
  }

  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = () => {
        URL.revokeObjectURL(url);
        resolve(image);
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error(`无法读取图片：${file.name}`));
      };
      image.src = url;
    });
  }

  async function renderImageToPng(item, settings) {
    const image = await loadImage(item.file);
    const canvas = document.createElement("canvas");
    canvas.width = settings.width;
    canvas.height = settings.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("当前浏览器不支持 Canvas。");
    }

    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, settings.width, settings.height);

    const scale = Math.min(settings.width / image.naturalWidth, settings.height / image.naturalHeight);
    const drawWidth = image.naturalWidth * scale;
    const drawHeight = image.naturalHeight * scale;
    const drawX = (settings.width - drawWidth) / 2;
    const drawY = (settings.height - drawHeight) / 2;
    ctx.drawImage(image, drawX, drawY, drawWidth, drawHeight);

    drawCaption(ctx, item.topText, settings.width / 2, settings.height / 2 - settings.centerGap, settings, "top");
    drawCaption(ctx, item.bottomText, settings.width / 2, settings.height / 2 + settings.centerGap, settings, "bottom");

    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((result) => {
        if (result) {
          resolve(result);
        } else {
          reject(new Error("图片预处理失败。"));
        }
      }, "image/png");
    });

    return new Uint8Array(await blob.arrayBuffer());
  }

  function drawCaption(ctx, text, centerX, baseY, settings, placement) {
    const value = text.trim();
    if (!value) {
      return;
    }

    const maxWidth = Math.floor(settings.width * 0.86);
    const fontSize = settings.fontSize;
    const lineHeight = Math.round(fontSize * 1.22);
    ctx.font = `700 ${fontSize}px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = placement === "top" ? "bottom" : "top";

    const lines = wrapText(ctx, value, maxWidth);
    const totalHeight = lines.length * lineHeight;
    const paddingX = Math.round(fontSize * 0.34);
    const paddingY = Math.round(fontSize * 0.18);
    const widest = Math.max(...lines.map((line) => ctx.measureText(line).width));
    const boxWidth = Math.min(settings.width - 24, widest + paddingX * 2);
    const boxHeight = totalHeight + paddingY * 2;
    const boxX = centerX - boxWidth / 2;
    const boxY = placement === "top" ? baseY - boxHeight : baseY;

    ctx.fillStyle = "rgba(0, 0, 0, 0.48)";
    roundRect(ctx, boxX, boxY, boxWidth, boxHeight, 8);
    ctx.fill();

    ctx.lineWidth = Math.max(3, Math.round(fontSize * 0.06));
    ctx.strokeStyle = "rgba(0, 0, 0, 0.95)";
    ctx.fillStyle = "#ffffff";

    lines.forEach((line, index) => {
      const y =
        placement === "top"
          ? baseY - paddingY - (lines.length - 1 - index) * lineHeight
          : baseY + paddingY + index * lineHeight;
      ctx.strokeText(line, centerX, y);
      ctx.fillText(line, centerX, y);
    });
  }

  function wrapText(ctx, text, maxWidth) {
    const lines = [];
    let current = "";
    for (const char of Array.from(text)) {
      const candidate = current + char;
      if (current && ctx.measureText(candidate).width > maxWidth) {
        lines.push(current);
        current = char;
      } else {
        current = candidate;
      }
    }
    if (current) {
      lines.push(current);
    }
    return lines.slice(0, 4);
  }

  function roundRect(ctx, x, y, width, height, radius) {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + width, y, x + width, y + height, r);
    ctx.arcTo(x + width, y + height, x, y + height, r);
    ctx.arcTo(x, y + height, x, y, r);
    ctx.arcTo(x, y, x + width, y, r);
    ctx.closePath();
  }

  async function writeInputs(ffmpeg, settings) {
    for (let index = 0; index < state.images.length; index += 1) {
      setStatus(`正在预处理第 ${index + 1} 张图片...`);
      const data = await renderImageToPng(state.images[index], settings);
      await ffmpeg.writeFile(`image${index}.png`, data);
    }

    const audioExt = getExtension(state.audio, "mp3");
    const audioName = `audio.${audioExt}`;
    await ffmpeg.writeFile(audioName, new Uint8Array(await state.audio.arrayBuffer()));
    return audioName;
  }

  function buildFfmpegArgs(settings, audioName) {
    const count = state.images.length;
    const totalDuration = settings.seconds * count;
    const useTransition = settings.transition !== "none" && count > 1;
    const stillDuration = useTransition ? settings.seconds + settings.transitionDuration : settings.seconds;
    const args = ["-y"];

    for (let index = 0; index < count; index += 1) {
      args.push("-loop", "1", "-t", stillDuration.toFixed(3), "-i", `image${index}.png`);
    }
    args.push("-stream_loop", "-1", "-i", audioName);

    const filters = [];
    for (let index = 0; index < count; index += 1) {
      filters.push(`[${index}:v]fps=30,format=yuv420p,settb=AVTB[v${index}]`);
    }

    if (count === 1) {
      filters.push("[v0]null[outv]");
    } else if (!useTransition) {
      filters.push(`${Array.from({ length: count }, (_, index) => `[v${index}]`).join("")}concat=n=${count}:v=1:a=0[outv]`);
    } else {
      let previous = "v0";
      for (let index = 1; index < count; index += 1) {
        const output = index === count - 1 ? "outv" : `x${index}`;
        const offset = settings.seconds * index;
        filters.push(
          `[${previous}][v${index}]xfade=transition=${escapeFilterText(settings.transition)}:` +
            `duration=${settings.transitionDuration.toFixed(3)}:offset=${offset.toFixed(3)}[${output}]`
        );
        previous = output;
      }
    }

    args.push(
      "-filter_complex",
      filters.join(";"),
      "-map",
      "[outv]",
      "-map",
      `${count}:a:0`,
      "-t",
      totalDuration.toFixed(3),
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "23",
      "-pix_fmt",
      "yuv420p",
      "-c:a",
      "aac",
      "-b:a",
      "160k",
      "-movflags",
      "+faststart",
      OUTPUT_NAME
    );

    return args;
  }

  async function cleanupFfmpegFiles(ffmpeg, audioName) {
    const names = [...state.images.map((_, index) => `image${index}.png`), audioName, OUTPUT_NAME];
    await Promise.all(
      names.map(async (name) => {
        try {
          await ffmpeg.deleteFile(name);
        } catch (_error) {
          // 文件可能因为前一步失败不存在。
        }
      })
    );
  }

  async function generateVideo() {
    if (!canGenerate()) {
      setStatus("请先选择图片和音乐。");
      return;
    }

    resetOutput();
    setBusy(true);
    setProgress(0);
    let audioName = "";

    try {
      if (!state.ffmpegLoaded) {
        await loadFfmpeg();
      }
      const settings = readSettings();
      audioName = await writeInputs(state.ffmpeg, settings);
      const args = buildFfmpegArgs(settings, audioName);
      setStatus("正在合成视频，请保持页面在前台打开。");
      await state.ffmpeg.exec(args);
      const data = await state.ffmpeg.readFile(OUTPUT_NAME);
      const blob = new Blob([data.buffer], { type: "video/mp4" });
      const url = createObjectUrl(blob);
      state.outputBlob = blob;
      state.outputUrl = url;
      els.previewVideo.src = url;
      els.previewVideo.hidden = false;
      els.downloadButton.hidden = false;
      setProgress(100);
      setStatus("视频生成完成，可以预览或保存。");
    } catch (error) {
      console.error(error);
      setStatus(error instanceof Error ? error.message : "生成失败，请检查素材格式。");
    } finally {
      if (audioName && state.ffmpeg) {
        await cleanupFfmpegFiles(state.ffmpeg, audioName);
      }
      setBusy(false);
    }
  }

  function resetAll() {
    state.images.forEach((item) => revokeObjectUrl(item.url));
    state.images = [];
    resetAudio();
    els.imageInput.value = "";
    els.audioInput.value = "";
    els.audioLabel.textContent = "从手机选择";
    els.secondsInput.value = "4";
    els.transitionDurationInput.value = "0.6";
    els.resolutionInput.value = "720x1280";
    els.transitionInput.value = "fade";
    els.fontSizeInput.value = "54";
    els.centerGapInput.value = "14";
    resetOutput();
    setProgress(0);
    setStatus("请选择图片和音乐。");
    renderImages();
  }

  function bindEvents() {
    els.imageInput.addEventListener("change", () => {
      const files = Array.from(els.imageInput.files || []);
      files.forEach((file) => {
        state.images.push({
          id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
          file,
          url: createObjectUrl(file),
          topText: "十年前",
          bottomText: "现在",
        });
      });
      els.imageInput.value = "";
      renderImages();
      setStatus(state.audio ? "素材已选择，可以生成视频。" : "请继续选择背景音乐。");
    });

    els.audioInput.addEventListener("change", () => {
      const [file] = Array.from(els.audioInput.files || []);
      if (!file) {
        return;
      }
      setAudioFile(file);
      els.musicSelect.value = "";
      els.audioLabel.textContent = file.name;
      setStatus(state.images.length ? "素材已选择，可以生成视频。" : "请继续选择图片。");
      updateActions();
    });

    els.musicSelect.addEventListener("change", async () => {
      try {
        await chooseBuiltInMusic();
      } catch (error) {
        console.error(error);
        setStatus(error instanceof Error ? error.message : "音乐读取失败。");
      }
    });

    els.generateButton.addEventListener("click", generateVideo);
    els.downloadButton.addEventListener("click", saveGeneratedVideo);
    els.resetButton.addEventListener("click", resetAll);

    els.installButton.addEventListener("click", async () => {
      if (!state.installPrompt) {
        return;
      }
      state.installPrompt.prompt();
      await state.installPrompt.userChoice;
      state.installPrompt = null;
      els.installButton.hidden = true;
    });
  }

  function registerPwa() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("./sw.js").catch((error) => {
        console.warn("Service Worker 注册失败", error);
      });
    }

    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      state.installPrompt = event;
      els.installButton.hidden = false;
    });
  }

  bindEvents();
  registerPwa();
  loadMusicOptions();
  window.setTimeout(() => {
    loadFfmpeg().catch((error) => {
      console.warn(error);
      els.ffmpegState.textContent = "FFmpeg 待加载";
      setStatus("请选择图片和音乐。");
    });
  }, 600);
  renderImages();
  updateActions();
})();
