#!/usr/bin/env python3
"""Graphical front end of the Elden Ring regulation.bin randomizer (tkinter; Pillow for the backdrop image).

    python tools/gui.py                open the window
    python tools/gui.py FILE.bin       open the window with FILE.bin as the input
    python tools/gui.py --opt ...      no window: exactly the command line of randomize.py, so the
                                       packaged executable doubles as the command-line tool

build_exe.bat / build_exe.sh pack this file into one executable with PyInstaller.  paramdef/, names/,
assets/ (and liblinoodle.so on Linux) travel inside it; the game's oo2core_6_win64.dll never does, it is
expected next to the executable (or wherever the "Oodle DLL" field points).
"""
from __future__ import annotations

import os
import queue
import shlex
import subprocess
import sys
import threading
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import erreg      # noqa: E402
import oodle      # noqa: E402
import randomize  # noqa: E402
import theme      # noqa: E402
import weapons    # noqa: E402

TITLE = "Elden Ring Further Random"
WINDOWS = sys.platform == "win32"
FROZEN = bool(getattr(sys, "frozen", False))
# Like randomize.sh / randomize.bat the window works from the project folder (the executable's folder
# when packaged): relative paths and the default ./oo2core_6_win64.dll resolve there.
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]


def _tcl_env() -> None:
    """Point Tcl / Tk at the base installation's script libraries when the environment does not: in a
       venv of a relocated (uv-managed) Windows Python, Tk may otherwise fail with 'Can't find a usable
       init.tcl'.  PyInstaller sets these itself in the packaged program."""
    if FROZEN or not WINDOWS:
        return
    base = Path(sys.base_prefix)
    for var, name, probe in (("TCL_LIBRARY", "tcl", "init.tcl"), ("TK_LIBRARY", "tk", "tk.tcl")):
        if os.environ.get(var):
            continue
        for d in (base / "tcl", base / "lib", base / "Lib"):
            hits = sorted(d.glob(f"{name}[89].*")) if d.is_dir() else []   # tcl8.6 / tcl9.0
            if hits and (hits[-1] / probe).is_file():
                os.environ[var] = str(hits[-1])
                break


_tcl_env()
TK_ERROR: str | None = None
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:                         # Linux without python3-tk, Windows Python without tcl/tk
    tk = None
    TK_ERROR = traceback.format_exc()


def fatal(text: str) -> None:
    """Report a start-up failure in a way that survives having no console (pythonw, windowed exe):
       gui_error.log next to the program, a Windows message box, and stderr when there is one."""
    log = APP_DIR / "gui_error.log"
    try:
        log.write_text(text + "\n", encoding="utf-8")
        text += f"\n\n（以上内容已写入 {log}）"
    except OSError:
        pass
    if sys.stderr is not None:
        print(text, file=sys.stderr)
    if WINDOWS:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10)
        except Exception:
            pass
LAUNCHER = "randomize.bat" if WINDOWS else "./randomize.sh"
WEAPON_FLAGS = ("--somber-infusable", "--random-movesets", "--random-default-ash", "--random-stats")
STAMINA_DEFAULT = ("0.3", "1.7")
PAD = dict(padx=6, pady=2)


def join_argv(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv) if WINDOWS else shlex.join(argv)


class QueueWriter:
    """sys.stdout / sys.stderr while the randomizer runs in the worker thread."""

    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s: str) -> int:
        if s:
            self.q.put(s)
        return len(s)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


class Gui:
    def __init__(self, root: tk.Tk, input_file: str | None, pal: dict = theme.PALETTE):
        self.root = root
        self.pal = pal
        root.title(TITLE)
        root.protocol("WM_DELETE_WINDOW", self._close)
        self.q: queue.Queue = queue.Queue()
        self.running = False
        self.dry_run = False
        self.out = Path("randomized/regulation.bin")
        self.vars: list[tk.Variable] = []
        self.cmd = tk.StringVar()                      # command preview, not traced
        S, B = self._str, self._bool
        # files
        self.input = S(input_file or "")
        self.output = S(str(APP_DIR / "randomized" / "regulation.bin"))
        env = os.environ.get("OODLE_DLL", "")                 # $OODLE_DLL, else ./oo2core_6_win64.dll
        dll = Path(env) if env and Path(env).is_file() else APP_DIR / oodle.DLL_NAME
        self.dll = S(str(dll) if dll.is_file() else "")
        self.seed = S("")
        self.compression = S("auto")
        # goods / spells
        self.mode = S("shuffle")
        self.include_flasks, self.include_remembrances = B(False), B(False)
        self.split_anim = S("none")
        self.spells = B(True)
        self.random_prices, self.price_mode = B(False), S("shuffle")
        self.price_min, self.price_max = S(""), S("")
        self.sell_prices, self.sell_min, self.sell_max = B(True), S(""), S("")
        # weapons
        self.somber, self.movesets, self.default_ash, self.stats = B(False), B(False), B(False), B(False)
        self.moveset_mode, self.shield, self.bow, self.variety = S("affinity"), S("shields"), S("bows"), S("3")
        self.keep_standard, self.weptype = B(False), B(False)
        self.groups = {g: B(True) for g in weapons.STAT_GROUPS}
        self.stamina_lo, self.stamina_hi = S(STAMINA_DEFAULT[0]), S(STAMINA_DEFAULT[1])
        self.dep_prices: list = []
        self.dep_sell: list = []
        self.dep_movesets: list = []
        self.dep_stats: list = []
        self._build()
        for v in self.vars:
            v.trace_add("write", lambda *_: self._refresh())
        self._refresh()
        root.after(100, self._poll)

    def _str(self, v: str) -> tk.StringVar:
        var = tk.StringVar(value=v)
        self.vars.append(var)
        return var

    def _bool(self, v: bool) -> tk.BooleanVar:
        var = tk.BooleanVar(value=v)
        self.vars.append(var)
        return var

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        parent = theme.layout(self.root, self.pal)
        sections = []                                   # (widget, sticky, grows, pady)

        f = ttk.LabelFrame(parent, text="文件")
        f.columnconfigure(1, weight=1)
        self._file_row(f, 0, "输入 regulation.bin", self.input, self._pick_input)
        self._file_row(f, 1, "输出文件", self.output, self._pick_output)
        ttk.Button(f, text="打开输出目录", command=self._open_out_dir).grid(row=1, column=3, **PAD)
        self._file_row(f, 2, "Oodle DLL", self.dll, self._pick_dll)
        ttk.Label(f, text=f"{oodle.DLL_NAME} 在游戏目录 Game\\ 里（ModEngine2 的 mod 文件夹里也有）；"
                          "没有它只能输出 zstd 格式，文件更大", style="Hint.TLabel").grid(row=3, column=1, columnspan=3,
                                                                                    sticky="w", **PAD)
        r = ttk.Frame(f)
        r.grid(row=4, column=0, columnspan=4, sticky="w")
        ttk.Label(r, text="随机种子").pack(side="left", **PAD)
        ttk.Entry(r, textvariable=self.seed, width=12).pack(side="left")
        ttk.Label(r, text="（留空 = 随机抽一个，运行后显示在日志里，填回去可复现）", style="Hint.TLabel").pack(side="left", **PAD)
        ttk.Label(r, text="压缩格式").pack(side="left", padx=(18, 6))
        ttk.Combobox(r, textvariable=self.compression, values=("auto",) + tuple(erreg.CODECS), width=10,
                     state="readonly").pack(side="left")
        sections.append((f, "ew", False, (8, 2)))

        g = ttk.LabelFrame(parent, text="道具与法术（效果总是随机）")
        r = ttk.Frame(g)
        r.grid(row=0, column=0, sticky="w")
        ttk.Label(r, text="效果分配").pack(side="left", **PAD)
        ttk.Radiobutton(r, text="shuffle：每个效果恰好用一次", variable=self.mode, value="shuffle").pack(side="left", **PAD)
        ttk.Radiobutton(r, text="random：效果可重复", variable=self.mode, value="random").pack(side="left", **PAD)
        r = ttk.Frame(g)
        r.grid(row=1, column=0, sticky="w")
        ttk.Label(r, text="使用动作").pack(side="left", **PAD)
        ttk.Radiobutton(r, text="跟着效果走", variable=self.split_anim, value="none").pack(side="left", **PAD)
        ttk.Radiobutton(r, text="同类道具里另选 (--split-anim same)", variable=self.split_anim,
                        value="same").pack(side="left", **PAD)
        ttk.Radiobutton(r, text="任意道具 (--split-anim any)", variable=self.split_anim, value="any").pack(side="left", **PAD)
        r = ttk.Frame(g)
        r.grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(r, text="圣杯瓶也随机 (--include-flasks)", variable=self.include_flasks).pack(side="left", **PAD)
        ttk.Checkbutton(r, text="追忆也随机 (--include-remembrances)", variable=self.include_remembrances).pack(side="left", **PAD)
        ttk.Checkbutton(r, text="魔法 / 祷告效果随机（取消 = --no-spells）", variable=self.spells).pack(side="left", **PAD)
        r = ttk.Frame(g)
        r.grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(r, text="商店价格随机 (--random-prices)", variable=self.random_prices).pack(side="left", **PAD)
        w = ttk.Radiobutton(r, text="shuffle：打乱现有价格", variable=self.price_mode, value="shuffle")
        w.pack(side="left", **PAD)
        self.dep_prices.append(w)
        w = ttk.Radiobutton(r, text="range：区间内重抽", variable=self.price_mode, value="range")
        w.pack(side="left", **PAD)
        self.dep_prices.append(w)
        for label, var in (("最低", self.price_min), ("最高", self.price_max)):
            w = ttk.Label(r, text=label)
            w.pack(side="left", padx=(10, 2))
            self.dep_prices.append(w)
            w = ttk.Entry(r, textvariable=var, width=8)
            w.pack(side="left")
            self.dep_prices.append(w)
        r = ttk.Frame(g)
        r.grid(row=4, column=0, sticky="w")
        w = ttk.Checkbutton(r, text="道具售价也随机（取消 = --no-sell-prices）", variable=self.sell_prices)
        w.pack(side="left", **PAD)
        self.dep_prices.append(w)
        for label, var in (("售价最低", self.sell_min), ("售价最高", self.sell_max)):
            w = ttk.Label(r, text=label)
            w.pack(side="left", padx=(10, 2))
            self.dep_sell.append(w)
            w = ttk.Entry(r, textvariable=var, width=8)
            w.pack(side="left")
            self.dep_sell.append(w)
        sections.append((g, "ew", False, 2))

        wf = ttk.LabelFrame(parent, text="武器（四项全选 = --weapons）")
        r = ttk.Frame(wf)
        r.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(r, text="失色 / 独特武器可质变、可装战灰 (--somber-infusable)",
                        variable=self.somber).pack(side="left", **PAD)
        ttk.Checkbutton(r, text="默认战技随机，掉落 / 商店 / 初始武器的质变随机 (--random-default-ash)",
                        variable=self.default_ash).pack(side="left", **PAD)
        r = ttk.Frame(wf)
        r.grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(r, text="动作模组随机 (--random-movesets)", variable=self.movesets).pack(side="left", **PAD)
        for label, var, values, width in (("模式", self.moveset_mode, ("affinity", "bound", "weapon"), 8),
                                          ("盾", self.shield, ("shields", "none", "all"), 7),
                                          ("弓", self.bow, ("bows", "none"), 6)):
            w = ttk.Label(r, text=label)
            w.pack(side="left", padx=(10, 2))
            self.dep_movesets.append(w)
            w = ttk.Combobox(r, textvariable=var, values=values, width=width, state="readonly")
            w.pack(side="left")
            self.dep_movesets.append(w)
        w = ttk.Label(r, text="bound 模式的 variety")
        w.pack(side="left", padx=(10, 2))
        self.dep_movesets.append(w)
        w = ttk.Spinbox(r, textvariable=self.variety, from_=1, to=12, width=4)
        w.pack(side="left")
        self.dep_movesets.append(w)
        r = ttk.Frame(wf)
        r.grid(row=2, column=0, sticky="w", padx=(24, 0))
        w = ttk.Checkbutton(r, text="Standard 行保留原动作 (--keep-standard-moveset)", variable=self.keep_standard)
        w.pack(side="left", **PAD)
        self.dep_movesets.append(w)
        w = ttk.Checkbutton(r, text="wepType 跟随动作 (--weptype-follows，未测试存档校验)", variable=self.weptype)
        w.pack(side="left", **PAD)
        self.dep_movesets.append(w)
        r = ttk.Frame(wf)
        r.grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(r, text="数值随机 (--random-stats)", variable=self.stats).pack(side="left", **PAD)
        w = ttk.Label(r, text="分组")
        w.pack(side="left", padx=(10, 2))
        self.dep_stats.append(w)
        for gname in weapons.STAT_GROUPS:
            w = ttk.Checkbutton(r, text=gname, variable=self.groups[gname])
            w.pack(side="left", padx=2)
            self.dep_stats.append(w)
        r = ttk.Frame(wf)
        r.grid(row=4, column=0, sticky="w", padx=(24, 0))
        w = ttk.Label(r, text="出招耐力倍率范围 (--stamina-rate)")
        w.pack(side="left", **PAD)
        self.dep_stats.append(w)
        w = ttk.Entry(r, textvariable=self.stamina_lo, width=6)
        w.pack(side="left")
        self.dep_stats.append(w)
        w = ttk.Label(r, text="到")
        w.pack(side="left", padx=4)
        self.dep_stats.append(w)
        w = ttk.Entry(r, textvariable=self.stamina_hi, width=6)
        w.pack(side="left")
        self.dep_stats.append(w)
        sections.append((wf, "ew", False, 2))

        b = ttk.Frame(parent, style="Bg.TFrame")
        ttk.Button(b, text="常用设定", command=self._preset).pack(side="left", **PAD)
        ttk.Label(b, text="= --split-anim any --random-prices --weapons", style="Bg.TLabel").pack(side="left")
        ttk.Button(b, text="恢复默认选项", command=self._reset).pack(side="left", padx=(16, 6))
        self.btn_run = ttk.Button(b, text="开始随机", style="Accent.TButton", command=lambda: self._start(False))
        self.btn_run.pack(side="right", **PAD)
        self.btn_dry = ttk.Button(b, text="预览（不写文件）", command=lambda: self._start(True))
        self.btn_dry.pack(side="right", **PAD)
        sections.append((b, "ew", False, 4))

        c = ttk.Frame(parent, style="Bg.TFrame")
        c.columnconfigure(1, weight=1)
        ttk.Label(c, text="等价命令", style="Bg.TLabel").grid(row=0, column=0, sticky="w", **PAD)
        ttk.Entry(c, textvariable=self.cmd, state="readonly").grid(row=0, column=1, sticky="ew", **PAD)
        sections.append((c, "ew", False, 0))

        lf = ttk.Frame(parent, style="Bg.TFrame")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.log = tk.Text(lf, height=8, wrap="none", state="disabled", font="TkFixedFont")
        theme.style_text(self.log, self.pal)
        self.log.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(lf, orient="vertical", command=self.log.yview)
        ys.grid(row=0, column=1, sticky="ns")
        xs = ttk.Scrollbar(lf, orient="horizontal", command=self.log.xview)
        xs.grid(row=1, column=0, sticky="ew")
        self.log.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        sections.append((lf, "nsew", True, 2))

        self.status = ttk.Label(parent, text="就绪", anchor="w", style="Status.TLabel")
        sections.append((self.status, "ew", False, (2, 8)))
        theme.arrange(parent, sections)

    def _file_row(self, parent, row: int, label: str, var: tk.StringVar, pick) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", **PAD)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", **PAD)
        ttk.Button(parent, text="浏览…", command=pick).grid(row=row, column=2, **PAD)

    # ---------------------------------------------------------------- pickers
    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(title="输入 regulation.bin",
                                       filetypes=[("regulation.bin", "*.bin"), ("所有文件", "*.*")])
        if p:
            self.input.set(p)

    def _pick_output(self) -> None:
        cur = Path(self.output.get() or "randomized/regulation.bin")
        p = filedialog.asksaveasfilename(title="输出文件", initialdir=str(cur.parent), initialfile=cur.name,
                                         defaultextension=".bin", filetypes=[("regulation.bin", "*.bin")])
        if p:
            self.output.set(p)

    def _pick_dll(self) -> None:
        p = filedialog.askopenfilename(title=oodle.DLL_NAME,
                                       filetypes=[(oodle.DLL_NAME, oodle.DLL_NAME), ("DLL", "*.dll")])
        if p:
            self.dll.set(p)

    def _open_out_dir(self) -> None:
        d = Path(self.output.get().strip() or "randomized/regulation.bin").resolve().parent
        if not d.is_dir():
            messagebox.showinfo(TITLE, f"目录还不存在：{d}")
            return
        if WINDOWS:
            os.startfile(d)                                  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(d)])

    # ---------------------------------------------------------------- options -> argv
    @staticmethod
    def _int(s: str, what: str) -> int:
        try:
            return int(s.strip())
        except ValueError:
            raise ValueError(f"{what} 应为整数：{s}") from None

    def argv(self, dry_run: bool) -> list[str]:
        a = ["--input", self.input.get().strip() or "regulation.bin",
             "--output", self.output.get().strip() or "randomized/regulation.bin"]
        if self.seed.get().strip():
            a += ["--seed", str(self._int(self.seed.get(), "随机种子"))]
        if self.mode.get() != "shuffle":
            a += ["--mode", self.mode.get()]
        if self.include_flasks.get():
            a.append("--include-flasks")
        if self.include_remembrances.get():
            a.append("--include-remembrances")
        if self.split_anim.get() != "none":
            a += ["--split-anim", self.split_anim.get()]
        if not self.spells.get():
            a.append("--no-spells")
        if self.random_prices.get():
            a.append("--random-prices")
            if self.price_mode.get() == "range":
                a += ["--price-mode", "range"]
                for var, flag, what in ((self.price_min, "--price-min", "最低价格"),
                                        (self.price_max, "--price-max", "最高价格")):
                    if var.get().strip():
                        a += [flag, str(self._int(var.get(), what))]
            if not self.sell_prices.get():
                a.append("--no-sell-prices")
            elif self.price_mode.get() == "range":
                for var, flag, what in ((self.sell_min, "--sell-min", "最低售价"),
                                        (self.sell_max, "--sell-max", "最高售价")):
                    if var.get().strip():
                        a += [flag, str(self._int(var.get(), what))]
        four = (self.somber.get(), self.movesets.get(), self.default_ash.get(), self.stats.get())
        if all(four):
            a.append("--weapons")
        else:
            a += [flag for on, flag in zip(four, WEAPON_FLAGS) if on]
        if self.movesets.get():
            if self.moveset_mode.get() != "affinity":
                a += ["--moveset-mode", self.moveset_mode.get()]
            if self.moveset_mode.get() == "bound" and self.variety.get().strip() != "3":
                a += ["--moveset-variety", str(self._int(self.variety.get(), "variety"))]
            if self.keep_standard.get():
                a.append("--keep-standard-moveset")
            if self.shield.get() != "shields":
                a += ["--shield-movesets", self.shield.get()]
            if self.bow.get() != "bows":
                a += ["--bow-movesets", self.bow.get()]
            if self.weptype.get():
                a.append("--weptype-follows")
        if self.stats.get():
            groups = [g for g in weapons.STAT_GROUPS if self.groups[g].get()]
            if not groups:
                raise ValueError("数值随机至少要选一个分组")
            if len(groups) != len(weapons.STAT_GROUPS):
                a += ["--stat-groups", ",".join(groups)]
            lo, hi = self.stamina_lo.get().strip(), self.stamina_hi.get().strip()
            if (lo, hi) != STAMINA_DEFAULT:
                try:
                    flo, fhi = float(lo), float(hi)
                except ValueError:
                    flo, fhi = 0.0, 0.0
                if not 0 < flo <= fhi:
                    raise ValueError("出招耐力倍率范围应满足 0 < 最低 <= 最高，例如 0.3 到 1.7")
                a += ["--stamina-rate", f"{lo},{hi}"]
        if self.compression.get() != "auto":
            a += ["--compression", self.compression.get()]
        if self.dll.get().strip():
            a += ["--oodle-dll", self.dll.get().strip()]
        if dry_run:
            a.append("--dry-run")
        return a

    def _refresh(self) -> None:
        for widgets, on in ((self.dep_prices, self.random_prices.get()),
                            (self.dep_sell, self.random_prices.get() and self.sell_prices.get()),
                            (self.dep_movesets, self.movesets.get()),
                            (self.dep_stats, self.stats.get())):
            for w in widgets:
                w.state(["!disabled"] if on else ["disabled"])
        try:
            self.cmd.set(f"{LAUNCHER} {join_argv(self.argv(False))}")
        except ValueError as e:
            self.cmd.set(f"参数有误：{e}")

    def _preset(self) -> None:
        self.split_anim.set("any")
        self.random_prices.set(True)
        for v in (self.somber, self.movesets, self.default_ash, self.stats):
            v.set(True)

    def _reset(self) -> None:
        self.seed.set("")
        self.compression.set("auto")
        self.mode.set("shuffle")
        self.split_anim.set("none")
        self.spells.set(True)
        self.price_mode.set("shuffle")
        self.price_min.set("")
        self.price_max.set("")
        self.sell_prices.set(True)
        self.sell_min.set("")
        self.sell_max.set("")
        for v in (self.include_flasks, self.include_remembrances, self.random_prices, self.somber, self.movesets,
                  self.default_ash, self.stats, self.keep_standard, self.weptype):
            v.set(False)
        self.moveset_mode.set("affinity")
        self.shield.set("shields")
        self.bow.set("bows")
        self.variety.set("3")
        for v in self.groups.values():
            v.set(True)
        self.stamina_lo.set(STAMINA_DEFAULT[0])
        self.stamina_hi.set(STAMINA_DEFAULT[1])

    # ---------------------------------------------------------------- running
    def _start(self, dry_run: bool) -> None:
        if self.running:
            return
        try:
            argv = self.argv(dry_run)
        except ValueError as e:
            messagebox.showerror(TITLE, str(e))
            return
        inp = Path(self.input.get().strip() or "regulation.bin")
        if not inp.is_file():
            messagebox.showerror(TITLE, f"找不到输入文件：{inp}")
            return
        dll = self.dll.get().strip()
        if dll and not Path(dll).is_file():
            messagebox.showerror(TITLE, f"找不到 DLL：{dll}")
            return
        if not dll:
            os.environ.pop("OODLE_DLL", None)      # the field is the only source, not the DLL of an earlier run
        if not dry_run and not dll and self.compression.get() != erreg.CODEC_ZSTD:
            if oodle.find_dll() is None:
                if not messagebox.askyesno(
                        TITLE, f"没有指定 {oodle.DLL_NAME}，当前目录（{Path.cwd()}）里也没有。\n\n"
                               f"它在游戏目录 Game\\ 里，用“浏览…”选中它就能输出原版的 KRAK 格式。\n\n"
                               "改用 zstd 格式继续吗？文件会大约 35%，可能超过游戏的大小上限。"):
                    return
                if "--compression" in argv:
                    argv[argv.index("--compression") + 1] = erreg.CODEC_ZSTD
                else:
                    argv += ["--compression", erreg.CODEC_ZSTD]
        self.running, self.dry_run = True, dry_run
        self.out = Path(self.output.get().strip() or "randomized/regulation.bin")
        for b in (self.btn_dry, self.btn_run):
            b.state(["disabled"])
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.status.configure(text="运行中…")
        self._append(f"$ {LAUNCHER} {join_argv(argv)}\n\n")
        threading.Thread(target=self._work, args=(argv,), daemon=True).start()

    def _work(self, argv: list[str]) -> None:
        saved = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = QueueWriter(self.q)          # type: ignore[assignment]
        try:
            rc = randomize.main(argv)
            self.q.put(("done", rc or 0, None))
        except SystemExit as e:                                 # argparse errors, missing DLL...
            code = e.code
            if code in (None, 0):
                self.q.put(("done", 0, None))
            elif isinstance(code, int):
                self.q.put(("done", code, None))
            else:
                self.q.put(("done", 1, str(code)))
        except Exception:
            self.q.put(("done", 1, traceback.format_exc()))
        finally:
            sys.stdout, sys.stderr = saved

    def _poll(self) -> None:
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple):
                    self._finished(item[1], item[2])
                else:
                    self._append(item)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _append(self, s: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _finished(self, rc: int, msg: str | None) -> None:
        self.running = False
        for b in (self.btn_dry, self.btn_run):
            b.state(["!disabled"])
        if rc == 0 and self.dry_run:
            self.status.configure(text="预览完成，没有写文件")
        elif rc == 0:
            self.status.configure(text=f"完成：{self.out}")
            messagebox.showinfo(TITLE, f"已写入 {self.out}\n\n要覆盖 mod 目录里的 regulation.bin 才会生效。\n"
                                       f"mapping.txt / weapons.txt / spells.txt（随机结果清单）在同一目录。")
        else:
            if msg:
                self._append("\n" + msg.rstrip() + "\n")
            self.status.configure(text="失败，见日志")
            messagebox.showerror(TITLE, (msg or "运行失败，详见日志").strip()[-2000:])

    def _close(self) -> None:
        if self.running and not messagebox.askyesno(TITLE, "还在运行中，确定退出？输出文件可能不完整。"):
            return
        self.root.destroy()


NO_TK_HINT = (
    "Windows：安装 python.org 的 Python（安装时勾选 “tcl/tk and IDLE”），删除 %USERPROFILE%\\.venvs\\er_mod 后"
    "重新运行 randomize_gui.bat / build_exe.bat。" if WINDOWS else "Ubuntu / WSL: sudo apt install python3-tk")


def run_gui(args: list[str]) -> int:
    if tk is None:
        fatal("这个 Python 没有可用的 tkinter，无法显示窗口。\n\n" + (TK_ERROR or "").rstrip() + "\n\n" + NO_TK_HINT)
        return 1
    input_file = str(Path(args[0]).resolve()) if args and Path(args[0]).is_file() else None
    os.chdir(APP_DIR)
    if WINDOWS:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)      # crisp text on high-DPI screens
        except Exception:
            pass
    root = tk.Tk()
    theme.apply(root)
    Gui(root, input_file)
    root.mainloop()
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0].startswith("-"):                 # command-line mode, same options as randomize.py
        return randomize.main(args)
    try:
        return run_gui(args)
    except Exception:
        fatal("图形界面启动失败：\n\n" + traceback.format_exc().rstrip())
        return 1


if __name__ == "__main__":
    sys.exit(main())
