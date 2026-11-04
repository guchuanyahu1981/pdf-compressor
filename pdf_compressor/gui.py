"""图形界面(CustomTkinter)。"""
import os
import queue
import subprocess
import sys
import threading
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .compressor import compress_pdf

LEVELS = [
    ("轻度", "low", "画质几乎无损,体积小幅减少"),
    ("中度", "medium", "画质与体积均衡,推荐日常使用"),
    ("强度", "high", "体积最小,图片会明显变模糊"),
]
LEVEL_KEY = {name: key for name, key, _ in LEVELS}
LEVEL_DESC = {name: desc for name, _, desc in LEVELS}

ACCENT = ("#2563EB", "#3B82F6")
ACCENT_HOVER = ("#1D4ED8", "#2563EB")
BG = ("#F3F4F6", "#111827")
CARD = ("#FFFFFF", "#1F2937")
ROW = ("#F9FAFB", "#273244")
BORDER = ("#E5E7EB", "#374151")
TEXT = ("#111827", "#F9FAFB")
MUTED = ("#6B7280", "#9CA3AF")
GREEN = ("#16A34A", "#22C55E")
RED = ("#DC2626", "#F87171")
ORANGE = ("#D97706", "#FBBF24")


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%d B" % n if unit == "B" else "%.2f %s" % (n, unit)
        n /= 1024


def output_path(src, out_dir=None):
    base, ext = os.path.splitext(os.path.basename(src))
    folder = out_dir or os.path.dirname(os.path.abspath(src))
    return os.path.join(folder, base + "_compressed" + (ext or ".pdf"))


def open_folder(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def pick_font(root):
    avail = set(tkfont.families(root))
    for f in ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB",
              "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "SimHei"):
        if f in avail:
            return f
    return None


class FileRow(ctk.CTkFrame):
    """文件列表中的一行。"""

    def __init__(self, master, app, path):
        super().__init__(master, fg_color=ROW, corner_radius=10, border_width=1, border_color=BORDER)
        self.path = path
        self.app = app
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="PDF", width=44, height=44, corner_radius=8,
                     fg_color=("#FEE2E2", "#7F1D1D"), text_color=RED,
                     font=app.font(12, "bold")).grid(row=0, column=0, rowspan=2, padx=12, pady=10)

        ctk.CTkLabel(self, text=os.path.basename(path), anchor="w", text_color=TEXT,
                     font=app.font(14, "bold")).grid(row=0, column=1, sticky="ew", pady=(10, 0))
        self.size_lbl = ctk.CTkLabel(self, text=fmt_size(os.path.getsize(path)), anchor="w",
                                     text_color=MUTED, font=app.font(12))
        self.size_lbl.grid(row=1, column=1, sticky="ew", pady=(0, 10))

        self.status_lbl = ctk.CTkLabel(self, text="等待压缩", text_color=MUTED, font=app.font(12),
                                       width=120, anchor="e")
        self.status_lbl.grid(row=0, column=2, rowspan=2, padx=8)

        self.remove_btn = ctk.CTkButton(self, text="✕", width=30, height=30, corner_radius=15,
                                        fg_color="transparent", hover_color=BORDER, text_color=MUTED,
                                        font=app.font(14), command=lambda: app.remove_file(path))
        self.remove_btn.grid(row=0, column=3, rowspan=2, padx=(0, 12))

    def set_status(self, text, color=MUTED):
        self.status_lbl.configure(text=text, text_color=color)

    def set_result(self, orig, new):
        ratio = (1 - new / orig) * 100 if orig else 0
        self.size_lbl.configure(text="%s  →  %s" % (fmt_size(orig), fmt_size(new)))
        if new < orig:
            self.set_status("已节省 %.1f%%" % ratio, GREEN)
        else:
            self.set_status("无法再压缩", ORANGE)

    def reset(self):
        self.size_lbl.configure(text=fmt_size(os.path.getsize(self.path)))
        self.set_status("等待压缩")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF 压缩工具")
        self.geometry("880x640")
        self.minsize(720, 520)
        self.configure(fg_color=BG)

        self._family = pick_font(self)
        self.q = queue.Queue()
        self.rows = {}  # path -> FileRow
        self.out_dir = None
        self.running = False
        self.saved = 0
        self.ok = self.fail = 0
        self.last_out_dirs = set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_settings()
        self._build_list()
        self._build_footer()
        self._refresh_empty()

    # ---------- 工具 ----------
    def font(self, size, weight="normal"):
        if self._family:
            return ctk.CTkFont(family=self._family, size=size, weight=weight)
        return ctk.CTkFont(size=size, weight=weight)

    def card(self, row, **grid):
        f = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        f.grid(row=row, column=0, sticky="nsew", padx=20, **grid)
        return f

    # ---------- 布局 ----------
    def _build_header(self):
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 12))
        h.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(h, text="PDF 压缩工具", text_color=TEXT, font=self.font(24, "bold"),
                     anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(h, text="批量减小 PDF 体积,原文件不会被修改", text_color=MUTED,
                     font=self.font(13), anchor="w").grid(row=1, column=0, sticky="w")
        self.theme_switch = ctk.CTkSwitch(h, text="深色模式", font=self.font(13), text_color=MUTED,
                                          progress_color=ACCENT, command=self._toggle_theme)
        self.theme_switch.grid(row=0, column=1, rowspan=2, sticky="e")
        if ctk.get_appearance_mode() == "Dark":
            self.theme_switch.select()

    def _build_settings(self):
        c = self.card(1, pady=(0, 12))
        c.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(c, text="压缩级别", text_color=TEXT, font=self.font(14, "bold")).grid(
            row=0, column=0, sticky="w", padx=(18, 12), pady=(16, 4))
        self.level = ctk.CTkSegmentedButton(
            c, values=[n for n, _, _ in LEVELS], command=self._on_level, font=self.font(13),
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER, height=32)
        self.level.set("中度")
        self.level.grid(row=0, column=1, sticky="w", pady=(16, 4))
        self.level_desc = ctk.CTkLabel(c, text=LEVEL_DESC["中度"], text_color=MUTED, font=self.font(12))
        self.level_desc.grid(row=1, column=1, sticky="w")

        ctk.CTkLabel(c, text="保存位置", text_color=TEXT, font=self.font(14, "bold")).grid(
            row=2, column=0, sticky="w", padx=(18, 12), pady=(12, 16))
        self.out_lbl = ctk.CTkLabel(c, text="", text_color=MUTED, font=self.font(12), anchor="w")
        self.out_lbl.grid(row=2, column=1, sticky="ew", pady=(12, 16))
        btns = ctk.CTkFrame(c, fg_color="transparent")
        btns.grid(row=2, column=2, padx=18, pady=(12, 16))
        self.out_btn = ctk.CTkButton(btns, text="更改…", width=70, height=30, font=self.font(13),
                                     fg_color="transparent", border_width=1, border_color=BORDER,
                                     text_color=TEXT, hover_color=ROW, command=self.choose_dir)
        self.out_btn.pack(side="left")
        self.reset_out_btn = ctk.CTkButton(btns, text="恢复默认", width=70, height=30, font=self.font(13),
                                           fg_color="transparent", text_color=ACCENT, hover_color=ROW,
                                           command=lambda: self._set_out_dir(None))
        self.reset_out_btn.pack(side="left", padx=(6, 0))
        self._set_out_dir(None)

    def _build_list(self):
        c = self.card(2, pady=(0, 12))
        c.grid_columnconfigure(0, weight=1)
        c.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(c, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        top.grid_columnconfigure(0, weight=1)
        self.count_lbl = ctk.CTkLabel(top, text="", text_color=TEXT, font=self.font(14, "bold"))
        self.count_lbl.grid(row=0, column=0, sticky="w")
        self.clear_btn = ctk.CTkButton(top, text="清空", width=60, height=30, font=self.font(13),
                                       fg_color="transparent", text_color=MUTED, hover_color=ROW,
                                       command=self.clear)
        self.clear_btn.grid(row=0, column=1, padx=(0, 6))
        self.add_btn = ctk.CTkButton(top, text="+  添加文件", width=110, height=30, font=self.font(13),
                                     fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.add_files)
        self.add_btn.grid(row=0, column=2)

        self.list = ctk.CTkScrollableFrame(c, fg_color="transparent")
        self.list.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))
        self.list.grid_columnconfigure(0, weight=1)

        # 空列表时显示的占位区域,点击即可添加文件
        self.empty = ctk.CTkFrame(self.list, fg_color=ROW, corner_radius=12, border_width=2,
                                  border_color=BORDER, height=220, cursor="hand2")
        self.empty.grid_propagate(False)
        self.empty.grid_columnconfigure(0, weight=1)
        self.empty.grid_rowconfigure((0, 3), weight=1)
        for i, (txt, f, col) in enumerate([
            ("📄", self.font(40), MUTED),
            ("点击此处添加 PDF 文件", self.font(16, "bold"), TEXT),
            ("支持一次选择多个文件", self.font(12), MUTED),
        ]):
            lbl = ctk.CTkLabel(self.empty, text=txt, font=f, text_color=col, cursor="hand2")
            lbl.grid(row=i, column=0, sticky="s" if i == 0 else "")
            lbl.bind("<Button-1>", lambda e: self.add_files())
        self.empty.bind("<Button-1>", lambda e: self.add_files())

    def _build_footer(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 20))
        f.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(f, text="就绪", text_color=MUTED, font=self.font(13), anchor="w")
        self.status.grid(row=0, column=0, sticky="ew")
        self.bar = ctk.CTkProgressBar(f, height=8, corner_radius=4, progress_color=ACCENT)
        self.bar.set(0)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self.open_btn = ctk.CTkButton(f, text="打开输出目录", width=120, height=40, font=self.font(14),
                                      fg_color="transparent", border_width=1, border_color=BORDER,
                                      text_color=TEXT, hover_color=CARD, command=self.open_output,
                                      state="disabled")
        self.open_btn.grid(row=0, column=1, rowspan=2, padx=(16, 8))
        self.start_btn = ctk.CTkButton(f, text="开始压缩", width=140, height=40,
                                       font=self.font(15, "bold"), fg_color=ACCENT,
                                       hover_color=ACCENT_HOVER, command=self.start)
        self.start_btn.grid(row=0, column=2, rowspan=2)

    # ---------- 交互 ----------
    def _toggle_theme(self):
        ctk.set_appearance_mode("dark" if self.theme_switch.get() else "light")

    def _on_level(self, name):
        self.level_desc.configure(text=LEVEL_DESC[name])

    def _set_out_dir(self, d):
        self.out_dir = d
        self.out_lbl.configure(text=d if d else "与源文件相同的文件夹(文件名后加 _compressed)")

    def _refresh_empty(self):
        n = len(self.rows)
        self.count_lbl.configure(text="文件列表" + ("  ·  %d 个" % n if n else ""))
        if n:
            self.empty.grid_forget()
        else:
            self.empty.grid(row=0, column=0, sticky="ew", padx=8, pady=8)

    def _relayout(self):
        for i, row in enumerate(self.rows.values()):
            row.grid(row=i, column=0, sticky="ew", padx=8, pady=4)
        self._refresh_empty()

    def _set_busy(self, busy):
        self.running = busy
        state = "disabled" if busy else "normal"
        for w in (self.start_btn, self.add_btn, self.clear_btn, self.out_btn, self.reset_out_btn):
            w.configure(state=state)
        self.level.configure(state=state)
        for row in self.rows.values():
            row.remove_btn.configure(state=state)
        self.start_btn.configure(text="压缩中…" if busy else "开始压缩")

    def add_files(self):
        if self.running:
            return
        paths = filedialog.askopenfilenames(title="选择 PDF 文件", filetypes=[("PDF 文件", "*.pdf")])
        for p in paths:
            p = os.path.abspath(p)
            if p not in self.rows and os.path.isfile(p):
                self.rows[p] = FileRow(self.list, self, p)
        self._relayout()

    def remove_file(self, path):
        if self.running:
            return
        row = self.rows.pop(path, None)
        if row:
            row.destroy()
        self._relayout()

    def clear(self):
        if self.running:
            return
        for row in self.rows.values():
            row.destroy()
        self.rows.clear()
        self.bar.set(0)
        self.status.configure(text="就绪", text_color=MUTED)
        self._relayout()

    def choose_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self._set_out_dir(d)

    def open_output(self):
        dirs = [d for d in self.last_out_dirs if os.path.isdir(d)]
        if dirs:
            try:
                open_folder(sorted(dirs)[0])
            except Exception as e:
                messagebox.showerror("错误", "无法打开目录: %s" % e)

    def start(self):
        if self.running:
            return
        if not self.rows:
            messagebox.showinfo("提示", "请先添加 PDF 文件")
            return
        files = list(self.rows)
        for row in self.rows.values():
            row.reset()
        self.saved = 0
        self.ok = self.fail = 0
        self.last_out_dirs = set()
        self.bar.set(0)
        self._set_busy(True)
        level = LEVEL_KEY[self.level.get()]
        threading.Thread(target=self._worker, args=(files, level, self.out_dir), daemon=True).start()
        self.after(100, self._poll)

    def _worker(self, files, level, out_dir):
        n = len(files)
        for idx, src in enumerate(files):
            self.q.put(("status", src, idx, n))
            dst = output_path(src, out_dir)
            try:
                o, nw = compress_pdf(src, dst, level,
                                     lambda f, idx=idx: self.q.put(("prog", (idx + f) / n)))
                self.q.put(("done", src, dst, o, nw, idx, n))
            except Exception as e:
                self.q.put(("error", src, str(e), idx, n))
        self.q.put(("finish", n))

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                kind = m[0]
                if kind == "prog":
                    self.bar.set(m[1])
                elif kind == "status":
                    _, src, idx, n = m
                    self.rows[src].set_status("压缩中…", ACCENT)
                    self.status.configure(text="正在处理第 %d / %d 个文件" % (idx + 1, n), text_color=MUTED)
                elif kind == "done":
                    _, src, dst, o, nw, idx, n = m
                    self.rows[src].set_result(o, nw)
                    self.saved += o - nw
                    self.ok += 1
                    self.last_out_dirs.add(os.path.dirname(dst))
                    self.bar.set((idx + 1) / n)
                elif kind == "error":
                    _, src, err, idx, n = m
                    self.rows[src].set_status("失败", RED)
                    self.fail += 1
                    self.bar.set((idx + 1) / n)
                    print("压缩失败 %s: %s" % (src, err), file=sys.stderr)
                    self.rows[src].size_lbl.configure(text=err[:60])
                elif kind == "finish":
                    self._set_busy(False)
                    msg = "完成 %d 个,共节省 %s" % (self.ok, fmt_size(self.saved))
                    if self.fail:
                        msg += ",失败 %d 个" % self.fail
                    self.status.configure(text=msg, text_color=RED if self.fail else GREEN)
                    self.open_btn.configure(state="normal" if self.last_out_dirs else "disabled")
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll)


def run():
    ctk.set_appearance_mode("system")
    App().mainloop()
