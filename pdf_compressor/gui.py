"""tkinter 图形界面。"""
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

from .compressor import compress_pdf

LEVEL_MAP = {"轻度": "low", "中度": "medium", "强度": "high"}


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%d B" % n if unit == "B" else "%.2f %s" % (n, unit)
        n /= 1024


def output_path(src, out_dir=None):
    base, ext = os.path.splitext(os.path.basename(src))
    folder = out_dir or os.path.dirname(os.path.abspath(src))
    return os.path.join(folder, base + "_compressed" + (ext or ".pdf"))


def pick_font(root):
    avail = set(tkfont.families(root))
    for f in ("Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "SimHei"):
        if f in avail:
            return f
    return None


class App:
    def __init__(self, root):
        self.root = root
        root.title("PDF 压缩工具")
        root.geometry("760x460")
        font = pick_font(root)
        if font:
            style = ttk.Style(root)
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
                tkfont.nametofont(name).configure(family=font)
            style.configure("Treeview", font=(font, 10))
        self.q = queue.Queue()
        self.files = []
        self.out_dir = tk.StringVar(value="")
        self.level = tk.StringVar(value="中度")
        self.running = False

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="添加文件", command=self.add_files).pack(side="left")
        ttk.Button(top, text="移除选中", command=self.remove_sel).pack(side="left", padx=4)
        ttk.Button(top, text="清空", command=self.clear).pack(side="left")
        ttk.Label(top, text="压缩级别:").pack(side="left", padx=(16, 4))
        ttk.Combobox(top, textvariable=self.level, values=list(LEVEL_MAP),
                     state="readonly", width=6).pack(side="left")

        outf = ttk.Frame(root, padding=(8, 0))
        outf.pack(fill="x")
        ttk.Label(outf, text="输出目录:").pack(side="left")
        ttk.Entry(outf, textvariable=self.out_dir, state="readonly").pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(outf, text="选择", command=self.choose_dir).pack(side="left")
        ttk.Button(outf, text="默认(源文件旁)", command=lambda: self.out_dir.set("")).pack(side="left", padx=4)

        cols = ("file", "orig", "new", "ratio", "status")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", height=10)
        for c, t, w in zip(cols, ("文件", "原大小", "压缩后", "节省比例", "状态"), (300, 90, 90, 80, 160)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c == "file" else "center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        bottom = ttk.Frame(root, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        self.start_btn = ttk.Button(bottom, text="开始压缩", command=self.start)
        self.start_btn.pack(side="left")
        self.bar = ttk.Progressbar(bottom, maximum=100)
        self.bar.pack(side="left", fill="x", expand=True, padx=8)
        self.status = ttk.Label(bottom, text="就绪", width=24)
        self.status.pack(side="left")

    def add_files(self):
        for p in filedialog.askopenfilenames(title="选择 PDF 文件", filetypes=[("PDF 文件", "*.pdf")]):
            if p not in self.files:
                self.files.append(p)
                self.tree.insert("", "end", iid=p, values=(os.path.basename(p), fmt_size(os.path.getsize(p)), "-", "-", "等待"))

    def remove_sel(self):
        if self.running:
            return
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.files.remove(iid)

    def clear(self):
        if self.running:
            return
        self.tree.delete(*self.tree.get_children())
        self.files.clear()

    def choose_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.out_dir.set(d)

    def start(self):
        if self.running:
            return
        if not self.files:
            messagebox.showinfo("提示", "请先添加 PDF 文件")
            return
        self.running = True
        self.start_btn.state(["disabled"])
        self.bar["value"] = 0
        level = LEVEL_MAP[self.level.get()]
        out_dir = self.out_dir.get() or None
        threading.Thread(target=self.worker, args=(list(self.files), level, out_dir), daemon=True).start()
        self.root.after(100, self.poll)

    def worker(self, files, level, out_dir):
        n = len(files)
        for idx, src in enumerate(files):
            self.q.put(("status", src, "压缩中...", idx, n))
            try:
                dst = output_path(src, out_dir)
                o, nw = compress_pdf(src, dst, level,
                                     lambda f, idx=idx: self.q.put(("prog", (idx + f) / n * 100)))
                self.q.put(("done", src, o, nw, idx, n))
            except Exception as e:
                self.q.put(("error", src, str(e), idx, n))
        self.q.put(("finish",))

    def poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                k = m[0]
                if k == "prog":
                    self.bar["value"] = m[1]
                elif k == "status":
                    self.tree.set(m[1], "status", m[2])
                    self.status.config(text="处理中 %d/%d" % (m[3] + 1, m[4]))
                elif k == "done":
                    _, src, o, nw, idx, n = m
                    ratio = (1 - nw / o) * 100 if o else 0
                    self.tree.item(src, values=(os.path.basename(src), fmt_size(o), fmt_size(nw),
                                                "%.1f%%" % ratio, "完成" if nw < o else "无法进一步压缩"))
                    self.bar["value"] = (idx + 1) / n * 100
                elif k == "error":
                    self.tree.set(m[1], "status", "失败: " + m[2][:30])
                    self.bar["value"] = (m[3] + 1) / m[4] * 100
                elif k == "finish":
                    self.running = False
                    self.start_btn.state(["!disabled"])
                    self.status.config(text="全部完成")
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def run():
    root = tk.Tk()
    App(root)
    root.mainloop()
