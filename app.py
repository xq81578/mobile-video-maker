from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk


APP_TITLE = "图片配乐视频生成器"
THUMBNAIL_SIZE = (128, 96)
THUMBNAIL_CARD_WIDTH = 154
DEFAULT_FONT_FILE = r"C\:/Windows/Fonts/msyhbd.ttc"
IMAGE_TYPES = [
    ("图片文件", "*.jpg *.jpeg *.jfif *.png *.webp *.bmp"),
    ("所有文件", "*.*"),
]
AUDIO_TYPES = [
    ("音频文件", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"),
    ("所有文件", "*.*"),
]
TRANSITIONS = {
    "无转场": "none",
    "淡入淡出": "fade",
    "向左滑动": "slideleft",
    "向右滑动": "slideright",
    "圆形展开": "circleopen",
    "溶解": "dissolve",
}


def find_ffmpeg() -> str | None:
    local_ffmpeg = Path(__file__).resolve().parent / "tools" / "ffmpeg.exe"
    if local_ffmpeg.exists():
        return str(local_ffmpeg)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    winget_packages = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    matches = list(winget_packages.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"))
    return str(matches[0]) if matches else None


def escape_drawtext_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("'", r"\'")
        .replace(":", r"\:")
        .replace("%", r"\%")
    )


def build_ffmpeg_command(
    ffmpeg: str,
    images: list[str],
    audio: str,
    output: str,
    seconds_per_image: float,
    transition: str,
    transition_duration: float,
    width: int,
    height: int,
    top_text: str = "",
    bottom_text: str = "",
    font_size: int = 64,
    center_gap: int = 16,
    image_texts: list[tuple[str, str]] | None = None,
) -> tuple[list[str], float]:
    total_duration = seconds_per_image * len(images)
    use_transition = transition != "none" and len(images) > 1
    still_duration = seconds_per_image + transition_duration if use_transition else seconds_per_image

    command = [ffmpeg, "-y"]
    for image in images:
        command.extend(["-loop", "1", "-t", f"{still_duration:.3f}", "-i", image])
    command.extend(["-stream_loop", "-1", "-i", audio])

    video_filters: list[str] = []
    for index in range(len(images)):
        current_top_text, current_bottom_text = (
            image_texts[index] if image_texts is not None else (top_text, bottom_text)
        )
        image_filter = (
            f"[{index}:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1,fps=30,format=yuv420p,settb=AVTB"
        )
        drawtext_common = (
            f":fontfile='{DEFAULT_FONT_FILE}'"
            f":fontsize={font_size}:fontcolor=white"
            ":borderw=3:bordercolor=black"
            ":box=1:boxcolor=black@0.48:boxborderw=12"
            ":x=(w-text_w)/2"
        )
        if current_top_text:
            image_filter += (
                f",drawtext=text='{escape_drawtext_text(current_top_text)}'"
                f"{drawtext_common}:y=h/2-text_h-{center_gap}"
            )
        if current_bottom_text:
            image_filter += (
                f",drawtext=text='{escape_drawtext_text(current_bottom_text)}'"
                f"{drawtext_common}:y=h/2+{center_gap}"
            )
        video_filters.append(f"{image_filter}[v{index}]")

    if len(images) == 1:
        video_filters.append("[v0]null[outv]")
    elif transition == "none":
        inputs = "".join(f"[v{index}]" for index in range(len(images)))
        video_filters.append(f"{inputs}concat=n={len(images)}:v=1:a=0[outv]")
    else:
        previous = "v0"
        for index in range(1, len(images)):
            output_label = "outv" if index == len(images) - 1 else f"x{index}"
            offset = seconds_per_image * index
            video_filters.append(
                f"[{previous}][v{index}]"
                f"xfade=transition={transition}:duration={transition_duration:.3f}:"
                f"offset={offset:.3f}[{output_label}]"
            )
            previous = output_label

    audio_index = len(images)
    command.extend(
        [
            "-filter_complex",
            ";".join(video_filters),
            "-map",
            "[outv]",
            "-map",
            f"{audio_index}:a:0",
            "-t",
            f"{total_duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            output,
        ]
    )
    return command, total_duration


class VideoMakerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x820")
        self.root.minsize(760, 700)

        self.images: list[str] = []
        self.image_texts: list[tuple[str, str]] = []
        self.thumbnail_images: list[ImageTk.PhotoImage] = []
        self.thumbnail_cards: list[tk.Frame] = []
        self.selected_image_index: int | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.exporting = False

        self.audio_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd() / "output.mp4"))
        self.seconds_var = tk.StringVar(value="4")
        self.transition_var = tk.StringVar(value="淡入淡出")
        self.transition_duration_var = tk.StringVar(value="0.6")
        self.resolution_var = tk.StringVar(value="1080x1920")
        self.top_text_var = tk.StringVar(value="十年前")
        self.bottom_text_var = tk.StringVar(value="现在")
        self.loading_image_text = False
        self.font_size_var = tk.StringVar(value="64")
        self.center_gap_var = tk.StringVar(value="16")
        self.status_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)

        self._build_ui()
        self.top_text_var.trace_add("write", self._save_selected_image_text)
        self.bottom_text_var.trace_add("write", self._save_selected_image_text)
        self._refresh_gallery()
        self._refresh_ffmpeg_status()
        self.root.after(100, self._process_events)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        ttk.Label(outer, text=APP_TITLE, font=("", 18, "bold")).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 12)
        )

        content = ttk.Frame(outer)
        content.grid(row=1, column=0, sticky=tk.NSEW)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        images_frame = ttk.LabelFrame(content, text="图片（按列表顺序播放）", padding=10)
        images_frame.grid(row=0, column=0, sticky=tk.NSEW)
        images_frame.columnconfigure(0, weight=1)
        images_frame.rowconfigure(0, weight=1)

        self.gallery_canvas = tk.Canvas(images_frame, height=155, highlightthickness=0, bg="white")
        self.gallery_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        gallery_scrollbar = ttk.Scrollbar(
            images_frame, orient=tk.HORIZONTAL, command=self.gallery_canvas.xview
        )
        gallery_scrollbar.grid(row=1, column=0, sticky=tk.EW, pady=(6, 0))
        self.gallery_canvas.configure(xscrollcommand=gallery_scrollbar.set)

        self.gallery_inner = tk.Frame(self.gallery_canvas, bg="white")
        self.gallery_window = self.gallery_canvas.create_window(
            (0, 0), window=self.gallery_inner, anchor=tk.NW
        )
        self.gallery_inner.bind("<Configure>", self._update_gallery_scrollregion)
        self.gallery_canvas.bind("<Configure>", self._resize_gallery_window)

        image_actions = ttk.Frame(images_frame)
        image_actions.grid(row=0, column=1, rowspan=2, sticky=tk.N, padx=(10, 0))
        ttk.Button(image_actions, text="添加图片", command=self._add_images).pack(fill=tk.X)
        ttk.Button(image_actions, text="上移", command=lambda: self._move_selected(-1)).pack(
            fill=tk.X, pady=(8, 0)
        )
        ttk.Button(image_actions, text="下移", command=lambda: self._move_selected(1)).pack(
            fill=tk.X, pady=(8, 0)
        )
        ttk.Button(image_actions, text="移除选中", command=self._remove_selected).pack(
            fill=tk.X, pady=(8, 0)
        )
        ttk.Button(image_actions, text="清空", command=self._clear_images).pack(
            fill=tk.X, pady=(8, 0)
        )

        settings = ttk.LabelFrame(content, text="导出设置", padding=10)
        settings.grid(row=1, column=0, sticky=tk.EW, pady=(12, 0))
        settings.columnconfigure(1, weight=1)

        self._add_path_row(settings, 0, "背景音乐", self.audio_var, self._choose_audio)
        self._add_path_row(
            settings,
            1,
            "输出文件",
            self.output_var,
            self._choose_output,
            extra_text="打开目录",
            extra_command=self._open_output_directory,
        )

        ttk.Label(settings, text="每张图片时长").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(settings, textvariable=self.seconds_var, width=10).grid(
            row=2, column=1, sticky=tk.W, pady=(8, 0)
        )
        ttk.Label(settings, text="秒").grid(row=2, column=1, sticky=tk.W, padx=(86, 0), pady=(8, 0))

        ttk.Label(settings, text="转场方式").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Combobox(
            settings,
            textvariable=self.transition_var,
            values=list(TRANSITIONS),
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky=tk.W, pady=(8, 0))

        ttk.Label(settings, text="转场时长").grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(settings, textvariable=self.transition_duration_var, width=10).grid(
            row=4, column=1, sticky=tk.W, pady=(8, 0)
        )
        ttk.Label(settings, text="秒").grid(row=4, column=1, sticky=tk.W, padx=(86, 0), pady=(8, 0))

        ttk.Label(settings, text="视频分辨率").grid(row=5, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Combobox(
            settings,
            textvariable=self.resolution_var,
            values=["1920x1080", "1080x1920", "1280x720", "720x1280"],
            state="readonly",
            width=18,
        ).grid(row=5, column=1, sticky=tk.W, pady=(8, 0))

        ttk.Label(settings, text="选中图片：上方文字").grid(row=6, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(settings, textvariable=self.top_text_var, width=20).grid(
            row=6, column=1, sticky=tk.W, pady=(8, 0)
        )

        ttk.Label(settings, text="选中图片：下方文字").grid(row=7, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(settings, textvariable=self.bottom_text_var, width=20).grid(
            row=7, column=1, sticky=tk.W, pady=(8, 0)
        )

        ttk.Label(settings, text="文字字号").grid(row=8, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(settings, textvariable=self.font_size_var, width=10).grid(
            row=8, column=1, sticky=tk.W, pady=(8, 0)
        )

        ttk.Label(settings, text="距离中线").grid(row=9, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(settings, textvariable=self.center_gap_var, width=10).grid(
            row=9, column=1, sticky=tk.W, pady=(8, 0)
        )
        ttk.Label(settings, text="像素").grid(row=9, column=1, sticky=tk.W, padx=(86, 0), pady=(8, 0))

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky=tk.EW, pady=(12, 0))
        footer.columnconfigure(0, weight=1)

        ttk.Progressbar(footer, variable=self.progress_var, maximum=100).grid(
            row=0, column=0, sticky=tk.EW
        )
        self.export_button = ttk.Button(footer, text="生成视频", command=self._start_export)
        self.export_button.grid(row=0, column=1, padx=(12, 0))
        ttk.Label(footer, textvariable=self.status_var).grid(row=1, column=0, columnspan=2, sticky=tk.W)

    def _add_path_row(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: object,
        extra_text: str | None = None,
        extra_command: object | None = None,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=(0 if row == 0 else 8, 0))
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky=tk.EW, padx=(10, 10), pady=(0 if row == 0 else 8, 0)
        )
        ttk.Button(parent, text="选择", command=command).grid(
            row=row, column=2, pady=(0 if row == 0 else 8, 0)
        )
        if extra_text and extra_command:
            ttk.Button(parent, text=extra_text, command=extra_command).grid(
                row=row, column=3, padx=(8, 0), pady=(0 if row == 0 else 8, 0)
            )

    def _refresh_ffmpeg_status(self) -> None:
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            self.status_var.set(f"FFmpeg 已就绪：{ffmpeg}")
        else:
            self.status_var.set("尚未检测到 FFmpeg，请按 README.md 安装后再生成视频。")

    def _add_images(self) -> None:
        files = filedialog.askopenfilenames(title="选择图片", filetypes=IMAGE_TYPES)
        first_new_index: int | None = None
        for file in files:
            if file not in self.images:
                if first_new_index is None:
                    first_new_index = len(self.images)
                self.images.append(file)
                self.image_texts.append(("十年前", "现在"))
        if first_new_index is not None:
            self.selected_image_index = first_new_index
            self._load_selected_image_text()
        self._refresh_gallery()

    def _refresh_gallery(self) -> None:
        self._ensure_image_texts()
        for widget in self.gallery_inner.winfo_children():
            widget.destroy()
        self.thumbnail_images.clear()
        self.thumbnail_cards.clear()

        if not self.images:
            tk.Label(
                self.gallery_inner,
                text="点击“添加图片”导入素材；单击选中，双击放大查看",
                bg="white",
                fg="#666666",
                padx=24,
                pady=55,
            ).pack()
            return

        for index, image_path in enumerate(self.images):
            selected = index == self.selected_image_index
            card = tk.Frame(
                self.gallery_inner,
                width=THUMBNAIL_CARD_WIDTH,
                height=140,
                bg="#dceeff" if selected else "#f4f4f4",
                highlightbackground="#2389da" if selected else "#cccccc",
                highlightthickness=2 if selected else 1,
                cursor="hand2",
            )
            card.pack(side=tk.LEFT, padx=(0 if index == 0 else 8, 0), pady=4)
            card.pack_propagate(False)
            self.thumbnail_cards.append(card)

            try:
                thumbnail = self._load_thumbnail(image_path)
                self.thumbnail_images.append(thumbnail)
                image_label = tk.Label(card, image=thumbnail, bg=card["bg"], cursor="hand2")
            except OSError:
                image_label = tk.Label(
                    card,
                    text="图片读取失败",
                    bg=card["bg"],
                    fg="#aa0000",
                    cursor="hand2",
                )
            image_label.pack(padx=8, pady=(8, 4))

            name = Path(image_path).name
            text_label = tk.Label(
                card,
                text=f"{index + 1:02d}. {name}",
                bg=card["bg"],
                anchor=tk.W,
                justify=tk.LEFT,
                wraplength=136,
                cursor="hand2",
            )
            text_label.pack(fill=tk.X, padx=8)
            for widget in (card, image_label, text_label):
                self._bind_thumbnail_events(widget, index)

    def _load_thumbnail(self, image_path: str) -> ImageTk.PhotoImage:
        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            background = Image.new("RGBA", THUMBNAIL_SIZE, "#e8e8e8")
            position = (
                (THUMBNAIL_SIZE[0] - image.width) // 2,
                (THUMBNAIL_SIZE[1] - image.height) // 2,
            )
            background.alpha_composite(image, position)
        return ImageTk.PhotoImage(background.convert("RGB"))

    def _bind_thumbnail_events(self, widget: tk.Widget, index: int) -> None:
        widget.bind("<Button-1>", lambda _event, i=index: self._select_thumbnail(i))
        widget.bind("<Double-Button-1>", lambda _event, i=index: self._preview_thumbnail(i))

    def _select_thumbnail(self, index: int) -> None:
        self.selected_image_index = index
        self._load_selected_image_text()
        self.status_var.set(f"已选中第 {index + 1} 张图片")
        self._update_thumbnail_selection()

    def _preview_thumbnail(self, index: int) -> None:
        self.selected_image_index = index
        self._load_selected_image_text()
        self._update_thumbnail_selection()
        self._show_image_preview(self.images[index])

    def _save_selected_image_text(self, *_args: object) -> None:
        if self.loading_image_text or self.selected_image_index is None:
            return
        if not 0 <= self.selected_image_index < len(self.image_texts):
            return
        self.image_texts[self.selected_image_index] = (
            self.top_text_var.get(),
            self.bottom_text_var.get(),
        )

    def _ensure_image_texts(self) -> None:
        while len(self.image_texts) < len(self.images):
            self.image_texts.append(("十年前", "现在"))
        if len(self.image_texts) > len(self.images):
            del self.image_texts[len(self.images) :]

    def _load_selected_image_text(self) -> None:
        if self.selected_image_index is None:
            return
        self._ensure_image_texts()
        top_text, bottom_text = self.image_texts[self.selected_image_index]
        self.loading_image_text = True
        try:
            self.top_text_var.set(top_text)
            self.bottom_text_var.set(bottom_text)
        finally:
            self.loading_image_text = False

    def _update_thumbnail_selection(self) -> None:
        for index, card in enumerate(self.thumbnail_cards):
            selected = index == self.selected_image_index
            background = "#dceeff" if selected else "#f4f4f4"
            card.configure(
                bg=background,
                highlightbackground="#2389da" if selected else "#cccccc",
                highlightthickness=2 if selected else 1,
            )
            for child in card.winfo_children():
                child.configure(bg=background)

    def _move_selected(self, direction: int) -> None:
        if self.selected_image_index is None or not self.images:
            messagebox.showinfo(APP_TITLE, "请先点击选择一张图片。")
            return
        old_index = self.selected_image_index
        new_index = old_index + direction
        if not 0 <= new_index < len(self.images):
            return
        self.images[old_index], self.images[new_index] = self.images[new_index], self.images[old_index]
        self.image_texts[old_index], self.image_texts[new_index] = (
            self.image_texts[new_index],
            self.image_texts[old_index],
        )
        self.selected_image_index = new_index
        self.status_var.set(f"已将图片移动到第 {new_index + 1} 位")
        self._refresh_gallery()

    def _show_image_preview(self, image_path: str) -> None:
        try:
            with Image.open(image_path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                max_size = (self.root.winfo_screenwidth() - 180, self.root.winfo_screenheight() - 180)
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                preview_image = ImageTk.PhotoImage(image)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"无法打开图片：\n{exc}")
            return

        preview = tk.Toplevel(self.root)
        preview.title(Path(image_path).name)
        preview.transient(self.root)
        ttk.Label(preview, image=preview_image).pack(padx=12, pady=12)
        preview.preview_image = preview_image
        preview.bind("<Escape>", lambda _event: preview.destroy())
        preview.lift()
        preview.after_idle(preview.focus_force)

    def _update_gallery_scrollregion(self, _event: tk.Event) -> None:
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))

    def _resize_gallery_window(self, event: tk.Event) -> None:
        self.gallery_canvas.itemconfigure(self.gallery_window, height=event.height)

    def _remove_selected(self) -> None:
        if self.selected_image_index is None or not self.images:
            messagebox.showinfo(APP_TITLE, "请先点击选择一张图片。")
            return
        del self.images[self.selected_image_index]
        del self.image_texts[self.selected_image_index]
        if self.images:
            self.selected_image_index = min(self.selected_image_index, len(self.images) - 1)
            self._load_selected_image_text()
        else:
            self.selected_image_index = None
        self._refresh_gallery()

    def _clear_images(self) -> None:
        self.images.clear()
        self.image_texts.clear()
        self.selected_image_index = None
        self._refresh_gallery()

    def _choose_audio(self) -> None:
        file = filedialog.askopenfilename(title="选择背景音乐", filetypes=AUDIO_TYPES)
        if file:
            self.audio_var.set(file)

    def _choose_output(self) -> None:
        file = filedialog.asksaveasfilename(
            title="保存视频",
            defaultextension=".mp4",
            filetypes=[("MP4 视频", "*.mp4")],
        )
        if file:
            self.output_var.set(file)

    def _open_output_directory(self) -> None:
        output = self.output_var.get().strip()
        directory = Path(output).expanduser().parent if output else Path.cwd()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(directory)
            else:
                subprocess.Popen(["xdg-open", str(directory)])
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"无法打开输出目录：\n{exc}")

    def _validate_export(self) -> tuple[float, float, int, int, int, int] | None:
        if not self.images:
            messagebox.showerror(APP_TITLE, "请至少添加一张图片。")
            return None
        if not self.audio_var.get() or not Path(self.audio_var.get()).is_file():
            messagebox.showerror(APP_TITLE, "请选择有效的背景音乐文件。")
            return None
        if not self.output_var.get():
            messagebox.showerror(APP_TITLE, "请选择输出文件。")
            return None
        try:
            seconds = float(self.seconds_var.get())
            transition_duration = float(self.transition_duration_var.get())
            width, height = map(int, self.resolution_var.get().split("x"))
            font_size = int(self.font_size_var.get())
            center_gap = int(self.center_gap_var.get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "时长、分辨率或文字设置格式不正确。")
            return None
        if seconds <= 0:
            messagebox.showerror(APP_TITLE, "每张图片时长必须大于 0 秒。")
            return None
        if self.transition_var.get() != "无转场" and not 0 < transition_duration < seconds:
            messagebox.showerror(APP_TITLE, "转场时长必须大于 0，且小于每张图片时长。")
            return None
        if font_size <= 0:
            messagebox.showerror(APP_TITLE, "文字字号必须大于 0。")
            return None
        if center_gap < 0:
            messagebox.showerror(APP_TITLE, "距离中线不能小于 0。")
            return None
        return seconds, transition_duration, width, height, font_size, center_gap

    def _start_export(self) -> None:
        if self.exporting:
            return
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            messagebox.showerror(APP_TITLE, "未检测到 FFmpeg，请先按照 README.md 安装。")
            return
        values = self._validate_export()
        if not values:
            return
        self._ensure_image_texts()
        seconds, transition_duration, width, height, font_size, center_gap = values
        output = str(Path(self.output_var.get()).with_suffix(".mp4"))
        try:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"无法创建输出目录：\n{exc}")
            return

        command, total_duration = build_ffmpeg_command(
            ffmpeg=ffmpeg,
            images=self.images.copy(),
            audio=self.audio_var.get(),
            output=output,
            seconds_per_image=seconds,
            transition=TRANSITIONS[self.transition_var.get()],
            transition_duration=transition_duration,
            width=width,
            height=height,
            top_text=self.top_text_var.get().strip(),
            bottom_text=self.bottom_text_var.get().strip(),
            font_size=font_size,
            center_gap=center_gap,
            image_texts=[(top.strip(), bottom.strip()) for top, bottom in self.image_texts],
        )
        self.output_var.set(output)
        self.exporting = True
        self.export_button.configure(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_var.set("正在生成视频...")
        threading.Thread(
            target=self._run_export,
            args=(command, total_duration, output),
            daemon=True,
        ).start()

    def _run_export(self, command: list[str], total_duration: float, output: str) -> None:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
            )
            output_lines: list[str] = []
            assert process.stdout is not None
            for line in process.stdout:
                line = line.strip()
                output_lines.append(line)
                if line.startswith("out_time_ms="):
                    try:
                        microseconds = int(line.partition("=")[2])
                    except ValueError:
                        # 部分 FFmpeg 版本在开始或结束阶段可能返回 N/A。
                        continue
                    percent = min(100, microseconds / 1_000_000 / total_duration * 100)
                    self.events.put(("progress", percent))
            return_code = process.wait()
            if return_code == 0:
                self.events.put(("done", output))
            else:
                details = "\n".join(output_lines[-20:])
                self.events.put(("error", details or f"FFmpeg 退出码：{return_code}"))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _process_events(self) -> None:
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "progress":
                    self.progress_var.set(float(value))
                    self.status_var.set(f"正在生成视频：{float(value):.0f}%")
                elif event == "done":
                    self._finish_export()
                    self.progress_var.set(100)
                    self.status_var.set(f"生成完成：{value}")
                    messagebox.showinfo(APP_TITLE, f"视频生成完成：\n{value}")
                elif event == "error":
                    self._finish_export()
                    self.status_var.set("生成失败，请检查素材或 FFmpeg 配置。")
                    messagebox.showerror(APP_TITLE, f"视频生成失败：\n\n{value}")
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)

    def _finish_export(self) -> None:
        self.exporting = False
        self.export_button.configure(state=tk.NORMAL)


def main() -> None:
    root = tk.Tk()
    VideoMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
