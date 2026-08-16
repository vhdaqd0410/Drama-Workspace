from __future__ import annotations

import os
import shutil
import subprocess
import threading
import tkinter as tk
import winsound
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import tkinterdnd2

from core.analyzer import build_rename_plan
from core.preview import render_preview
from core.task import run_rename_task
from utils.config import load_config, save_config
from utils.fileutil import parse_dropped_path


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def next_pause_state(paused: bool) -> tuple[bool, str]:
    return (not paused, "继续" if not paused else "暂停")


def build_progress_text(processed: int, total: int) -> str:
    if total <= 0:
        return "已完成 0/0 个文件"
    percent = round(processed / total * 100, 1)
    return f"已完成 {processed}/{total} 个文件 ({percent:.1f}%)"


# ---------------------------------------------------------------------------
# 深色主题配色
# ---------------------------------------------------------------------------

DARK_COLORS = {
    "bg": "#1a1b26",
    "fg": "#c0caf5",
    "entry_bg": "#1f2335",
    "button_bg": "#3b4261",
    "select_bg": "#7aa2f7",
    "accent": "#7aa2f7",
    "border": "#292e42",
    "green": "#9ece6a",
    "red": "#f7768e",
}

LIGHT_COLORS = {
    "bg": "#f6f8fa",
    "fg": "#1f2328",
    "entry_bg": "#ffffff",
    "button_bg": "#d0d7de",
    "select_bg": "#0969da",
    "accent": "#0969da",
    "border": "#d0d7de",
    "green": "#1a7f37",
    "red": "#cf222e",
}


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------


class MainWindow:
    def __init__(self, root: tkinterdnd2.Tk | None = None) -> None:
        self.root = root or tkinterdnd2.Tk()
        self.root.title("拆集重命名 2.0")
        self.root.geometry("760x640")
        self.root.minsize(680, 540)

        self._apply_theme("dark")

        self.status_var = tk.StringVar(value="准备就绪。可选择目录或拖拽文件夹到下方区域。")
        self.path_var = tk.StringVar(value="")
        self.output_dir_var = tk.StringVar(value="")

        self.is_renaming = False
        self.paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.rename_pairs: list[tuple[Path, Path]] = []
        self.total_files = 0
        self.success_count = 0
        self.error_count = 0
        self.processed_count = 0
        self.cancel_requested = False
        self.last_output_dir: Path | None = None
        self.rename_thread: threading.Thread | None = None

        self._build_ui()
        self._enable_drag_drop()
        self._restore_last_directory()
        self._bind_shortcuts()

    # ------------------------------------------------------------------
    # 主题
    # ------------------------------------------------------------------

    def _apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.colors = DARK_COLORS if theme == "dark" else LIGHT_COLORS
        self.root.configure(bg=self.colors["bg"])
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=self.colors["bg"], foreground=self.colors["fg"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["fg"])
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("TButton", background=self.colors["button_bg"])
        style.map("TButton", background=[("active", self.colors["select_bg"])])
        style.configure("TEntry", fieldbackground=self.colors["entry_bg"], foreground=self.colors["fg"])
        style.configure("TRadiobutton", background=self.colors["bg"], foreground=self.colors["fg"])
        style.configure("TProgressbar", background=self.colors["select_bg"])
        style.configure("Theme.TButton", background=self.colors["button_bg"], padding=2)
        style.configure("Accent.TButton", background=self.colors["accent"],
                        foreground="#ffffff", font=("微软雅黑", 9, "bold"))
        style.map("Accent.TButton", background=[("active", self.colors["select_bg"])])
        style.configure("Drop.TFrame", background=self.colors["entry_bg"], relief="solid", borderwidth=1)
        style.configure("Separator.TFrame", background=self.colors["border"])

    def _toggle_theme(self) -> None:
        new_theme = "light" if self.theme == "dark" else "dark"
        self._apply_theme(new_theme)
        self.theme_btn.configure(text="🌙" if new_theme == "dark" else "☀️")
        self._refresh_widget_colors()

    def _refresh_widget_colors(self) -> None:
        colors = self.colors
        for child in self.root.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=colors["bg"], fg=colors["fg"])
            elif isinstance(child, tk.Text):
                child.configure(bg=colors["entry_bg"], fg=colors["fg"],
                                insertbackground=colors["fg"])
            elif isinstance(child, tk.Frame):
                if child is self.drop_frame:
                    child.configure(bg=colors["entry_bg"],
                                    highlightbackground=colors["accent"])
                else:
                    child.configure(bg=colors["bg"])
                for sub in child.winfo_children():
                    if isinstance(sub, tk.Label):
                        sub.configure(bg=child.cget("bg"), fg=colors["fg"])
        self.root.configure(bg=colors["bg"])

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        colors = self.colors
        FONT = ("Microsoft YaHei UI", 9)
        FONT_BOLD = ("Microsoft YaHei UI", 9, "bold")
        MONO = ("Cascadia Code", 9) if os.name == "nt" else ("Menlo", 10)

        # 标题栏
        title_frame = tk.Frame(self.root, bg=colors["bg"], height=44)
        title_frame.pack(fill="x", padx=24, pady=(12, 8))
        title_frame.pack_propagate(False)
        tk.Label(title_frame, text="拆集重命名 2.0", font=("微软雅黑", 15, "bold"),
                 bg=colors["bg"], fg=colors["accent"]).pack(side=tk.LEFT)
        self.theme_btn = ttk.Button(title_frame, text="☀️", width=3,
                                     style="Theme.TButton", command=self._toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT)

        # 分隔线
        sep = tk.Frame(self.root, bg=colors["border"], height=1)
        sep.pack(fill="x", padx=24)

        # 目录区域
        dir_section = ttk.Frame(self.root)
        dir_section.pack(fill="x", padx=24, pady=(12, 0))

        ttk.Label(dir_section, text="📁 当前目录", font=FONT_BOLD).pack(anchor="w")
        ttk.Entry(dir_section, textvariable=self.path_var, state="readonly",
                  font=FONT).pack(fill="x", pady=(4, 8))

        ttk.Label(dir_section, text="📤 输出目录", font=FONT_BOLD).pack(anchor="w")
        out_row = ttk.Frame(dir_section)
        out_row.pack(fill="x")
        ttk.Entry(out_row, textvariable=self.output_dir_var, font=FONT).pack(
            side=tk.LEFT, fill="x", expand=True)
        ttk.Button(out_row, text="选择", command=self.choose_output_directory).pack(
            side=tk.LEFT, padx=(8, 0))

        # 拖拽区域
        self.drop_frame = tk.Frame(self.root, bg=colors["entry_bg"],
                                    highlightbackground=colors["accent"],
                                    highlightthickness=1, cursor="hand2")
        self.drop_frame.pack(fill="x", padx=24, pady=(12, 4), ipady=28)
        self.drop_label = tk.Label(
            self.drop_frame,
            text="📂  拖拽文件夹到此处，或点击下方「选择目录」",
            font=("微软雅黑", 11),
            bg=colors["entry_bg"],
            fg=colors["fg"],
            cursor="hand2",
        )
        self.drop_label.pack(expand=True)

        # 状态
        self.status_var.set("准备就绪。拖拽目录或点击按钮开始。")
        info_label = ttk.Label(self.root, textvariable=self.status_var, wraplength=650)
        info_label.pack(pady=(4, 0))

        # 预览 & 进度
        self.preview_text = tk.Text(self.root, height=5, wrap="word",
                                     bg=colors["entry_bg"], fg=colors["fg"],
                                     insertbackground=colors["fg"],
                                     font=MONO, borderwidth=0)
        self.preview_text.pack(fill="both", expand=True, padx=24, pady=(8, 0))
        self.preview_text.insert(tk.END, "预览区域 — 选择目录后将显示重命名计划")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(self.root, mode="determinate", variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x", padx=24, pady=(4, 0))

        # 日志
        self.log_text = tk.Text(self.root, height=3, wrap="word",
                                 bg=colors["entry_bg"], fg=colors["fg"],
                                 insertbackground=colors["fg"],
                                 font=MONO, borderwidth=0)
        self.log_text.pack(fill="both", expand=True, padx=24, pady=(4, 0))
        self.log_text.insert(tk.END, "日志：\n")

        # 摘要
        self.summary_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.summary_var, wraplength=500, font=FONT).pack(
            anchor="w", padx=24, pady=(4, 2))

        # 按钮
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=(4, 12))

        self.btn_select = ttk.Button(button_frame, text="选择目录", command=self.choose_directory)
        self.btn_select.pack(side=tk.LEFT, padx=4)
        self.btn_scan = ttk.Button(button_frame, text="扫描", command=self.scan_directory)
        self.btn_scan.pack(side=tk.LEFT, padx=4)
        self.run_button = ttk.Button(button_frame, text="▶ 执行重命名", command=self.execute_rename,
                                      style="Accent.TButton")
        self.run_button.pack(side=tk.LEFT, padx=4)
        self.pause_button = ttk.Button(button_frame, text="⏸ 暂停", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side=tk.LEFT, padx=4)
        self.cancel_button = ttk.Button(button_frame, text="✕ 取消", command=self.cancel_rename, state="disabled")
        self.cancel_button.pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text="💾 日志", command=self.save_log).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text="退出", command=self.root.destroy).pack(side=tk.LEFT, padx=4)

        self._busy_buttons = [self.btn_select, self.btn_scan, self.run_button]

    # ------------------------------------------------------------------
    # 拖拽
    # ------------------------------------------------------------------

    def _enable_drag_drop(self) -> None:
        try:
            self.drop_frame.drop_target_register("DND_Files")
            self.drop_frame.dnd_bind("<<Drop>>", self._handle_drop)
            self.root.drop_target_register("DND_Files")
            self.root.dnd_bind("<<Drop>>", self._handle_drop)
        except (AttributeError, tk.TclError):
            self.drop_label.configure(text="📂  点击「选择目录」按钮选择文件夹")

    # ------------------------------------------------------------------
    # 目录记忆
    # ------------------------------------------------------------------

    def _restore_last_directory(self) -> None:
        cfg = load_config()
        last_dir = cfg.get("last_directory")
        if last_dir and Path(last_dir).exists():
            self.path_var.set(last_dir)
        last_out = cfg.get("last_output_dir")
        if last_out:
            self.output_dir_var.set(last_out)

    def _persist_directory(self) -> None:
        save_config({
            "last_directory": self.path_var.get(),
            "last_output_dir": self.output_dir_var.get(),
        })

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _e: self.choose_directory())
        self.root.bind("<Control-O>", lambda _e: self.choose_directory())
        self.root.bind("<Control-Return>", lambda _e: self.execute_rename())
        self.root.bind("<Escape>", lambda _e: self.cancel_rename() if self.is_renaming else None)

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------

    def choose_directory(self) -> None:
        path = filedialog.askdirectory(title="选择剧集目录")
        if path:
            self._set_input_dir(Path(path))

    def choose_output_directory(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir_var.set(path)
            self._persist_directory()

    def _set_input_dir(self, folder: Path) -> None:
        self.path_var.set(str(folder))
        self._persist_directory()
        self.drop_label.configure(text=f"📂  {folder.name}")
        self.status_var.set(f"已选择目录：{folder}")

        # 先扫描获取文件数
        output_dir = Path(self.output_dir_var.get()).expanduser() if self.output_dir_var.get() else None
        items = build_rename_plan(folder, output_dir=output_dir, mode="split_merge")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, render_preview(items))
        self.summary_var.set(f"检测到 {len(items)} 个可处理文件")

        if items:
            self._show_countdown_dialog(len(items))
        else:
            self.status_var.set(f"已扫描目录：{folder}，但没有匹配到可处理的集数文件。")

    def _handle_drop(self, event: tk.Event) -> None:
        dropped_path = parse_dropped_path(event.data)
        if dropped_path is None:
            messagebox.showwarning("提示", "请拖入一个存在的文件夹。")
            return
        if dropped_path.is_file():
            dropped_path = dropped_path.parent
        self._set_input_dir(dropped_path)

    def _show_countdown_dialog(self, file_count: int) -> None:
        """显示倒计时确认弹窗，5 秒后自动执行重命名。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("拆集重命名")
        dlg.geometry("400x180")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg=self.colors["bg"])

        countdown = tk.IntVar(value=5)

        tk.Label(dlg, text=f"检测到 {file_count} 个可处理文件",
                 font=("微软雅黑", 12, "bold"), bg=self.colors["bg"], fg=self.colors["fg"]).pack(pady=(20, 6))
        countdown_label = tk.Label(dlg, textvariable=countdown,
                                    font=("微软雅黑", 24, "bold"),
                                    bg=self.colors["bg"], fg=self.colors["select_bg"])
        countdown_label.pack(pady=(4, 4))
        info_label = tk.Label(dlg, text="秒后自动开始重命名",
                               font=("微软雅黑", 10), bg=self.colors["bg"], fg=self.colors["fg"])
        info_label.pack()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=(12, 0))

        def do_rename() -> None:
            dlg.destroy()
            self.root.after(200, self.execute_rename)

        def do_cancel() -> None:
            dlg.destroy()
            self.status_var.set("已取消，可点击「执行重命名」手动开始。")

        ttk.Button(btn_frame, text=f"立即开始 ({countdown.get()})",
                   command=do_rename).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="仅预览",
                   command=do_cancel).pack(side=tk.LEFT, padx=8)

        def tick() -> None:
            if not dlg.winfo_exists():
                return
            remaining = countdown.get() - 1
            if remaining <= 0:
                do_rename()
                return
            countdown.set(remaining)
            btn_frame.winfo_children()[0].configure(text=f"立即开始 ({remaining})")
            dlg.after(1000, tick)

        dlg.after(1000, tick)
        self.root.wait_window(dlg)

    def scan_directory(self) -> None:
        folder = Path(self.path_var.get())
        if not folder.exists():
            messagebox.showwarning("提示", "请先选择目录。")
            return

        output_dir = Path(self.output_dir_var.get()).expanduser() if self.output_dir_var.get() else None
        items = build_rename_plan(folder, output_dir=output_dir, mode="split_merge")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, render_preview(items))
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, "日志：\n")
        self.log_text.insert(tk.END, f"扫描完成，发现 {len(items)} 个可处理文件。\n")
        self.log_text.see(tk.END)
        self.progress_var.set(0.0)
        self.summary_var.set(f"扫描结果：{len(items)} 个可处理文件")
        if items:
            self.status_var.set(f"已扫描目录：{folder}，共检测到 {len(items)} 个可处理文件。")
        else:
            self.status_var.set(f"已扫描目录：{folder}，但没有匹配到可处理的集数文件。")

    def execute_rename(self) -> None:
        if self.is_renaming:
            return

        folder = Path(self.path_var.get())
        if not folder.exists():
            messagebox.showwarning("提示", "请先选择目录。")
            return

        output_dir = Path(self.output_dir_var.get()).expanduser() if self.output_dir_var.get() else None
        items = build_rename_plan(folder, output_dir=output_dir, mode="split_merge")
        if not items:
            messagebox.showinfo("提示", "当前目录没有可执行的重命名项。")
            return

        conflicts = [item.target for item in items if item.target.exists() and item.target != item.source]
        if conflicts:
            conflict_names = "\n".join(str(item) for item in conflicts[:10])
            messagebox.showwarning("提示", f"存在目标冲突，无法继续执行：\n{conflict_names}")
            return

        # 保存 items 用于统计
        self._last_items = items

        self.rename_pairs = [(item.source, item.target) for item in items if item.source != item.target]
        target_dir = output_dir or folder.with_name(f"{folder.name}_renamed")
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, "日志：\n")
        self.log_text.insert(tk.END, f"输出目录：{target_dir}\n")
        self.progress_var.set(0.0)
        self.total_files = len(self.rename_pairs)
        self.success_count = 0
        self.error_count = 0
        self.processed_count = 0
        self.is_renaming = True
        self.paused = False
        self.cancel_requested = False
        self.pause_event.set()
        self.last_output_dir = target_dir
        self.log_text.insert(tk.END, f"准备处理 {self.total_files} 个文件。\n")
        self.summary_var.set(f"准备处理：{self.total_files} 个文件")
        self.pause_button.configure(text="暂停", state="normal")
        self.cancel_button.configure(state="normal")
        self.set_busy(True)
        self.rename_thread = threading.Thread(target=self._run_rename_worker, daemon=True)
        self.rename_thread.start()

    # ------------------------------------------------------------------
    # 工作线程
    # ------------------------------------------------------------------

    def _run_rename_worker(self) -> None:
        def on_progress(index: int, source: Path, target: Path, success: bool, error: Exception | None) -> None:
            if success:
                self.success_count += 1
            else:
                self.error_count += 1
            self.root.after(0, self._update_progress, index, source, target, success, error)

        def on_complete(cancelled: bool) -> None:
            self.root.after(0, self._finish_rename, cancelled)

        run_rename_task(
            pairs=self.rename_pairs,
            should_cancel=lambda: self.cancel_requested or not self.is_renaming,
            should_pause=lambda: not self.pause_event.is_set() and not self.cancel_requested and self.is_renaming,
            on_progress=on_progress,
            on_complete=on_complete,
        )

    def _update_progress(self, index: int, source: Path, target: Path, success: bool, error: Exception | None) -> None:
        total = self.total_files
        self.processed_count = index
        version = source.parent.name
        source_display = f"{version}/{source.name}"
        split_tag = " ← 拆集" if "-" in source.stem else ""
        if success:
            self.log_text.insert(tk.END, f"  [{index}/{total}] {source_display} -> {target.name}{split_tag}\n")
        else:
            self.log_text.insert(tk.END, f"  [{index}/{total}] 失败: {source_display} -> {target.name} ({error})\n")
        self.log_text.see(tk.END)
        percent = int(index / total * 100) if total else 100
        self.progress_var.set(percent)
        self.status_var.set(f"正在处理 {index}/{total} 个文件... {build_progress_text(index, total)}")
        self.summary_var.set(f"进度：{build_progress_text(index, total)}")

    def _finish_rename(self, cancelled: bool = False) -> None:
        self.is_renaming = False
        self.paused = False
        self.pause_event.set()
        self.pause_button.configure(text="暂停", state="disabled")
        self.cancel_button.configure(state="disabled")
        self.preview_text.delete("1.0", tk.END)
        if cancelled:
            self.preview_text.insert(tk.END, "任务已取消。")
            self.status_var.set(f"已取消，{build_progress_text(self.processed_count, self.total_files)}")
            self.log_text.insert(tk.END, f"已取消：已处理 {self.processed_count}/{self.total_files} 个文件。\n")
            self.summary_var.set(f"已取消：已处理 {self.processed_count}/{self.total_files} 个文件")
        else:
            self.preview_text.insert(tk.END, "重命名完成。")
            self.progress_var.set(100.0)
            self.status_var.set(f"重命名完成。{build_progress_text(self.processed_count, self.total_files)}")
            self.log_text.insert(tk.END, f"完成：成功 {self.success_count}，失败 {self.error_count}。\n")
            self.summary_var.set(f"完成：成功 {self.success_count}，失败 {self.error_count}")
            self._copy_screenshots_folder()
            self._auto_save_log()
            self._open_output_directory()
            self._show_completion_dialog()
        self.set_busy(False)

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------

    def toggle_pause(self) -> None:
        if not self.is_renaming:
            return
        self.paused, button_text = next_pause_state(self.paused)
        if self.paused:
            self.pause_event.clear()
            self.status_var.set(f"已暂停，{build_progress_text(self.processed_count, self.total_files)}")
            self.summary_var.set(f"暂停中：{build_progress_text(self.processed_count, self.total_files)}")
        else:
            self.pause_event.set()
            self.status_var.set(f"已继续处理，{build_progress_text(self.processed_count, self.total_files)}")
            self.summary_var.set(f"继续处理：{build_progress_text(self.processed_count, self.total_files)}")
        self.pause_button.configure(text=button_text)

    def cancel_rename(self) -> None:
        if not self.is_renaming:
            return
        self.cancel_requested = True
        self.pause_event.set()
        self.status_var.set(f"正在取消当前任务，{build_progress_text(self.processed_count, self.total_files)}")
        self.summary_var.set(f"取消中：{build_progress_text(self.processed_count, self.total_files)}")
        self.cancel_button.configure(state="disabled")

    # ------------------------------------------------------------------
    # 完成处理
    # ------------------------------------------------------------------

    def _open_output_directory(self) -> None:
        if not self.last_output_dir:
            return
        output_dir = self.last_output_dir
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(output_dir))
            return
        try:
            if os.name == "posix":
                subprocess.Popen(["open", str(output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(output_dir)])
        except OSError:
            pass

    def _play_completion_sound(self) -> None:
        if self.error_count > 0:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        else:
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)

    def _copy_screenshots_folder(self) -> None:
        source_dir = Path(self.path_var.get()) / "4.工程截图"
        if not source_dir.is_dir():
            return
        target_dir = self.last_output_dir / "4.工程截图"
        try:
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            self.log_text.insert(tk.END, "已复制「4.工程截图」文件夹。\n")
            self.log_text.see(tk.END)
        except OSError as exc:
            self.log_text.insert(tk.END, f"复制「4.工程截图」失败：{exc}\n")
            self.log_text.see(tk.END)

    def _auto_save_log(self) -> None:
        if not self.last_output_dir or not self.last_output_dir.exists():
            return
        log_path = self.last_output_dir / "重命名日志.txt"
        content = self.log_text.get("1.0", tk.END)
        log_path.write_text(content, encoding="utf-8")
        self.log_text.insert(tk.END, f"日志已保存至：{log_path}\n")
        self.log_text.see(tk.END)

    def _build_statistics(self) -> str:
        """生成版本统计文本。"""
        if not getattr(self, "_last_items", None):
            return ""
        items = self._last_items
        counter: Counter[str] = Counter()
        split_counter: Counter[str] = Counter()
        for item in items:
            version = item.target.parent.name
            counter[version] += 1
            if "-" in item.source.stem:
                split_counter[version] += 1

        lines = ["\n版本统计："]
        for version, count in counter.most_common():
            splits = split_counter.get(version, 0)
            lines.append(f"  {version}: {count} 个文件" + (f"（含 {splits} 个拆集）" if splits else ""))
        return "\n".join(lines)

    def _show_completion_dialog(self) -> None:
        self._play_completion_sound()
        if self.success_count == 0 and self.error_count == 0:
            messagebox.showinfo("处理完成", "处理已完成。")
            return

        stats = self._build_statistics()
        msg = (
            f"处理已完成。\n成功 {self.success_count} 个，失败 {self.error_count} 个。"
            f"{stats}\n\n日志已自动保存至输出目录。"
        )
        messagebox.showinfo("处理完成", msg)

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def save_log(self) -> None:
        log_path = filedialog.asksaveasfilename(
            title="保存日志",
            defaultextension=".log",
            filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not log_path:
            return
        content = self.log_text.get("1.0", tk.END)
        Path(log_path).write_text(content, encoding="utf-8")
        messagebox.showinfo("提示", f"日志已保存到：{log_path}")

    def set_busy(self, busy: bool) -> None:
        for button in self._busy_buttons:
            button.state(["disabled"] if busy else ["!disabled"])
        self.pause_button.state(["!disabled"] if busy else ["disabled"])
        self.cancel_button.state(["!disabled"] if busy else ["disabled"])

    def run(self) -> None:
        self.root.mainloop()
