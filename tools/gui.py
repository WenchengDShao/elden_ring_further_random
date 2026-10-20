#!/usr/bin/env python3
"""Graphical front end of the Elden Ring regulation.bin randomizer (tkinter; Pillow for the backdrop image).

    python tools/gui.py                open the window
    python tools/gui.py FILE.bin       open the window with FILE.bin as the input
    python tools/gui.py --opt ...      no window: exactly the command line of randomize.py, so the
                                       packaged executable doubles as the command-line tool

build_exe.bat / build_exe.sh pack this file into one executable with PyInstaller.  paramdef/, names/,
assets/ (and liblinoodle.so on Linux) travel inside it; the game's oo2core_6_win64.dll never does, it is
expected next to the executable (or wherever the "Oodle DLL" field points).

The texts are English; lang.py holds the Chinese translations and the language setting (gui.ini next to the
program).  The language box in the window's top-right corner rebuilds the widgets in the chosen language.
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
import lang       # noqa: E402
import oodle      # noqa: E402
import randomize  # noqa: E402
import theme      # noqa: E402
import weapons    # noqa: E402
from lang import tr as _  # noqa: E402

TITLE = "Elden Ring Further Random"
WINDOWS = sys.platform == "win32"
FROZEN = bool(getattr(sys, "frozen", False))
# Like randomize.sh / randomize.bat the window works from the project folder (the executable's folder
# when packaged): relative paths and the default ./oo2core_6_win64.dll resolve there.
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]
INI = APP_DIR / lang.INI                       # [gui] language = en | zh


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
        text += "\n\n" + _("(this message was also written to {})").format(log)
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
NO_TK_HINT = ("Windows: install Python from python.org (tick \"tcl/tk and IDLE\" in the installer), delete "
              "%USERPROFILE%\\.venvs\\er_mod and run randomize_gui.bat / build_exe.bat again."
              if WINDOWS else "Ubuntu / WSL: sudo apt install python3-tk")


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
        self.repack = False
        self.out = Path("randomized/regulation.bin")
        self.vars: list[tk.Variable] = []
        self.cmd = tk.StringVar()                      # command preview, not traced
        self.lang_name = tk.StringVar(value=lang.name(lang.current))   # the language box, not in self.vars
        self._status: tuple = ("Ready",)               # (English template, *format args) of the status line
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
        self.flask_locations = B(False)
        self.dialogue = B(False)
        self.jokes = B(False)                        # "joke shifu", --dialogue-jokes
        self.joke_archives = S("")                   # its optional paths, ';' separated (empty = found next to the input)
        self.spells = B(True)
        self.random_prices, self.price_mode = B(False), S("shuffle")
        self.price_min, self.price_max = S(""), S("")
        self.sell_prices, self.sell_min, self.sell_max = B(True), S(""), S("")
        self.sell_equipment = B(False)
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
        self.dep_dialogue: list = []
        self.dep_jokes: list = []
        self._build()
        for v in self.vars:
            v.trace_add("write", lambda *a: self._refresh())
        self.lang_name.trace_add("write", lambda *a: self._language_changed())
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
        lines = theme.TITLE_LINES[:2] + (_(theme.TITLE_LINES[2]),)
        parent = theme.layout(self.root, self.pal, lines)
        sections = []                                   # (widget, sticky, grows, pady)

        top = ttk.Frame(parent, style="Bg.TFrame")
        ttk.Combobox(top, textvariable=self.lang_name, values=[n for c, n in lang.LANGUAGES], width=8,
                     state="readonly").pack(side="right", padx=(0, 6))
        ttk.Label(top, text=_("Language"), style="Bg.TLabel").pack(side="right", padx=6)
        self.btn_repack = ttk.Button(top, text=_("Repack only (no randomization)"),
                                     command=lambda: self._start(False, repack=True))
        self.btn_repack.pack(side="right", padx=(0, 12))      # left of the language selector
        sections.append((top, "ew", False, (6, 0)))

        f = ttk.LabelFrame(parent, text=_("Files"))
        f.columnconfigure(1, weight=1)
        self._file_row(f, 0, _("Input regulation.bin"), self.input, self._pick_input)
        self._file_row(f, 1, _("Output file"), self.output, self._pick_output)
        ttk.Button(f, text=_("Open output folder"), command=self._open_out_dir).grid(row=1, column=3, **PAD)
        self._file_row(f, 2, "Oodle DLL", self.dll, self._pick_dll)
        ttk.Label(f, text=_("{}: in the game's Game\\ folder or ModEngine2's mod folder; without it the output is zstd "
                            "and larger").format(oodle.DLL_NAME),
                  style="Hint.TLabel").grid(row=3, column=1, columnspan=3, sticky="w", **PAD)
        r = ttk.Frame(f)
        r.grid(row=4, column=0, columnspan=4, sticky="w")
        ttk.Label(r, text=_("Seed")).pack(side="left", **PAD)
        ttk.Entry(r, textvariable=self.seed, width=12).pack(side="left")
        ttk.Label(r, text=_("(blank = random; the log shows it, enter it here to reproduce a run)"),
                  style="Hint.TLabel").pack(side="left", **PAD)
        ttk.Label(r, text=_("Compression")).pack(side="left", padx=(18, 6))
        ttk.Combobox(r, textvariable=self.compression, values=("auto",) + tuple(erreg.CODECS), width=10,
                     state="readonly").pack(side="left")
        sections.append((f, "ew", False, 2))

        g = ttk.LabelFrame(parent, text=_("Goods and spells (effects are always randomized)"))
        r = ttk.Frame(g)
        r.grid(row=0, column=0, sticky="w")
        ttk.Label(r, text=_("Effect assignment")).pack(side="left", **PAD)
        ttk.Radiobutton(r, text=_("shuffle: each effect is used exactly once"), variable=self.mode,
                        value="shuffle").pack(side="left", **PAD)
        ttk.Radiobutton(r, text=_("random: effects may repeat"), variable=self.mode, value="random").pack(side="left", **PAD)
        r = ttk.Frame(g)
        r.grid(row=1, column=0, sticky="w")
        ttk.Label(r, text=_("Use animation")).pack(side="left", **PAD)
        ttk.Radiobutton(r, text=_("follows the effect"), variable=self.split_anim, value="none").pack(side="left", **PAD)
        ttk.Radiobutton(r, text=_("from another item of the same kind (--split-anim same)"), variable=self.split_anim,
                        value="same").pack(side="left", **PAD)
        ttk.Radiobutton(r, text=_("from any item (--split-anim any)"), variable=self.split_anim,
                        value="any").pack(side="left", **PAD)
        r = ttk.Frame(g)
        r.grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(r, text=_("Flask effects too (--include-flasks)"), variable=self.include_flasks).pack(side="left", **PAD)
        ttk.Checkbutton(r, text=_("Remembrances too (--include-remembrances)"),
                        variable=self.include_remembrances).pack(side="left", **PAD)
        ttk.Checkbutton(r, text=_("Sorcery / incantation effects (off = --no-spells)"),
                        variable=self.spells).pack(side="left", **PAD)
        r = ttk.Frame(g)
        r.grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(r, text=_("Shop prices (--random-prices)"), variable=self.random_prices).pack(side="left", **PAD)
        w = ttk.Radiobutton(r, text=_("shuffle: permute the existing prices"), variable=self.price_mode, value="shuffle")
        w.pack(side="left", **PAD)
        self.dep_prices.append(w)
        w = ttk.Radiobutton(r, text=_("range: redraw within a range"), variable=self.price_mode, value="range")
        w.pack(side="left", **PAD)
        self.dep_prices.append(w)
        for label, var in ((_("min"), self.price_min), (_("max"), self.price_max)):
            w = ttk.Label(r, text=label)
            w.pack(side="left", padx=(10, 2))
            self.dep_prices.append(w)
            w = ttk.Entry(r, textvariable=var, width=8)
            w.pack(side="left")
            self.dep_prices.append(w)
        r = ttk.Frame(g)
        r.grid(row=4, column=0, sticky="w")
        w = ttk.Checkbutton(r, text=_("Sell prices of goods too (off = --no-sell-prices)"), variable=self.sell_prices)
        w.pack(side="left", **PAD)
        self.dep_prices.append(w)
        for label, var in ((_("sell min"), self.sell_min), (_("sell max"), self.sell_max)):
            w = ttk.Label(r, text=label)
            w.pack(side="left", padx=(10, 2))
            self.dep_sell.append(w)
            w = ttk.Entry(r, textvariable=var, width=8)
            w.pack(side="left")
            self.dep_sell.append(w)
        r = ttk.Frame(g)
        r.grid(row=5, column=0, sticky="w")
        w = ttk.Checkbutton(r, text=_("Sell prices of weapons / armor / Ashes of War too (--sell-equipment)"),
                            variable=self.sell_equipment)
        w.pack(side="left", **PAD)
        self.dep_prices.append(w)
        sections.append((g, "ew", False, 2))

        wf = ttk.LabelFrame(parent, text=_("Weapons (all four = --weapons)"))
        r = ttk.Frame(wf)
        r.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(r, text=_("Somber weapons: affinities + Ashes of War (--somber-infusable)"),
                        variable=self.somber).pack(side="left", **PAD)
        ttk.Checkbutton(r, text=_("Random default skill and affinity on new weapons (--random-default-ash)"), variable=self.default_ash).pack(side="left", **PAD)
        r = ttk.Frame(wf)
        r.grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(r, text=_("Random movesets (--random-movesets)"), variable=self.movesets).pack(side="left", **PAD)
        for label, var, values, width in ((_("Mode"), self.moveset_mode, ("affinity", "bound", "weapon"), 8),
                                          (_("Shields"), self.shield, ("shields", "none", "all"), 7),
                                          (_("Bows"), self.bow, ("bows", "none"), 6)):
            w = ttk.Label(r, text=label)
            w.pack(side="left", padx=(10, 2))
            self.dep_movesets.append(w)
            w = ttk.Combobox(r, textvariable=var, values=values, width=width, state="readonly")
            w.pack(side="left")
            self.dep_movesets.append(w)
        w = ttk.Label(r, text=_("bound variety"))
        w.pack(side="left", padx=(10, 2))
        self.dep_movesets.append(w)
        w = ttk.Spinbox(r, textvariable=self.variety, from_=1, to=12, width=4)
        w.pack(side="left")
        self.dep_movesets.append(w)
        r = ttk.Frame(wf)
        r.grid(row=2, column=0, sticky="w", padx=(24, 0))
        w = ttk.Checkbutton(r, text=_("Standard rows keep their moveset (--keep-standard-moveset)"),
                            variable=self.keep_standard)
        w.pack(side="left", **PAD)
        self.dep_movesets.append(w)
        w = ttk.Checkbutton(r, text=_("wepType follows (--weptype-follows, save validation untested)"),
                            variable=self.weptype)
        w.pack(side="left", **PAD)
        self.dep_movesets.append(w)
        r = ttk.Frame(wf)
        r.grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(r, text=_("Random stats (--random-stats)"), variable=self.stats).pack(side="left", **PAD)
        w = ttk.Label(r, text=_("Groups"))
        w.pack(side="left", padx=(10, 2))
        self.dep_stats.append(w)
        for gname in weapons.STAT_GROUPS:
            w = ttk.Checkbutton(r, text=gname, variable=self.groups[gname])
            w.pack(side="left", padx=2)
            self.dep_stats.append(w)
        r = ttk.Frame(wf)
        r.grid(row=4, column=0, sticky="w", padx=(24, 0))
        w = ttk.Label(r, text=_("Stamina cost multiplier range (--stamina-rate)"))
        w.pack(side="left", **PAD)
        self.dep_stats.append(w)
        w = ttk.Entry(r, textvariable=self.stamina_lo, width=6)
        w.pack(side="left")
        self.dep_stats.append(w)
        w = ttk.Label(r, text=_("to"))
        w.pack(side="left", padx=4)
        self.dep_stats.append(w)
        w = ttk.Entry(r, textvariable=self.stamina_hi, width=6)
        w.pack(side="left")
        self.dep_stats.append(w)
        sections.append((wf, "ew", False, 2))

        il = ttk.LabelFrame(parent, text=_("Item locations"))
        r = ttk.Frame(il)
        r.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(r, text=_("Random flask locations (--random-flask-locations)"),
                        variable=self.flask_locations).pack(side="left", **PAD)
        ttk.Label(r, text=_("(both flasks are found elsewhere: a pickup, boss, NPC or shop; the first grace gives "
                            "what was there)"), style="Hint.TLabel").pack(side="left", **PAD)
        sections.append((il, "ew", False, 2))

        dg = ttk.LabelFrame(parent, text=_("Fun"))
        r = ttk.Frame(dg)
        r.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(r, text=_("Random dialogue subtitles (--random-dialogue)"), variable=self.dialogue).pack(side="left", **PAD)
        ttk.Label(r, text=_("(every NPC line shows the subtitle of another line; the voices stay, so the NPC still speaks "
                            "its own line)"), style="Hint.TLabel").pack(side="left", **PAD)
        r = ttk.Frame(dg)
        r.grid(row=1, column=0, sticky="ew")
        r.columnconfigure(1, weight=1)
        w = ttk.Checkbutton(r, text=_("Joke shifu (--dialogue-jokes)"), variable=self.jokes)
        w.grid(row=0, column=0, sticky="w", **PAD)
        self.dep_dialogue.append(w)
        w = ttk.Entry(r, textvariable=self.joke_archives)
        w.grid(row=0, column=1, sticky="ew", **PAD)
        self.dep_jokes.append(w)
        w = ttk.Button(r, text=_("Browse…"), command=self._pick_jokes)
        w.grid(row=0, column=2, **PAD)
        self.dep_jokes.append(w)
        w = ttk.Label(r, text=_("(the cut lines show a joke and join the shuffle; text archives: empty = the English and "
                                "Chinese msg\\<language>\\menu_dlc02.msgbnd.dcx shipped with the program; or pick the game's "
                                "own, one per language)"), style="Hint.TLabel")
        w.grid(row=1, column=0, columnspan=3, sticky="w", **PAD)
        self.dep_jokes.append(w)
        dg.columnconfigure(0, weight=1)
        sections.append((dg, "ew", False, 2))

        b = ttk.Frame(parent, style="Bg.TFrame")
        ttk.Button(b, text=_("Preset"), command=self._preset).pack(side="left", **PAD)
        ttk.Label(b, text="= --split-anim any --random-prices --weapons --random-flask-locations --random-dialogue --dialogue-jokes",
                  style="Bg.TLabel").pack(side="left")
        ttk.Button(b, text=_("Reset options"), command=self._reset).pack(side="left", padx=(16, 6))
        self.btn_run = ttk.Button(b, text=_("Randomize"), style="Accent.TButton", command=lambda: self._start(False))
        self.btn_run.pack(side="right", **PAD)
        self.btn_dry = ttk.Button(b, text=_("Preview (no file written)"), command=lambda: self._start(True))
        self.btn_dry.pack(side="right", **PAD)
        sections.append((b, "ew", False, 4))

        c = ttk.Frame(parent, style="Bg.TFrame")
        c.columnconfigure(1, weight=1)
        ttk.Label(c, text=_("Command line"), style="Bg.TLabel").grid(row=0, column=0, sticky="w", **PAD)
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

        self.status = ttk.Label(parent, anchor="w", style="Status.TLabel")
        self._set_status(*self._status)
        sections.append((self.status, "ew", False, (2, 8)))
        theme.arrange(parent, sections)

    def _file_row(self, parent, row: int, label: str, var: tk.StringVar, pick) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", **PAD)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", **PAD)
        ttk.Button(parent, text=_("Browse…"), command=pick).grid(row=row, column=2, **PAD)

    def _set_status(self, template: str, *args) -> None:
        """The status line keeps its English template so a language change can re-render it."""
        self._status = (template, *args)
        self.status.configure(text=_(template).format(*args))

    # ---------------------------------------------------------------- language
    def _language_changed(self) -> None:
        code = lang.code(self.lang_name.get())
        if code is None or code == lang.current:
            return
        lang.current = code
        try:
            lang.save(INI, code)
        except OSError as e:
            self._status = ("Language not saved ({}): {}", INI.name, e)
        self.root.after_idle(self._rebuild)        # not inside the combobox's own event handling

    def _rebuild(self) -> None:
        """Throw the widgets away and build them again in the current language.  The variables (so every
           option), the log and the status line survive; a running job keeps going."""
        text = self.log.get("1.0", "end-1c")
        for w in self.root.winfo_children():
            w.destroy()
        for dep in (self.dep_prices, self.dep_sell, self.dep_movesets, self.dep_stats, self.dep_dialogue, self.dep_jokes):
            dep.clear()
        self._build()
        if text:
            self._append(text)
        if self.running:
            for b in (self.btn_dry, self.btn_repack, self.btn_run):
                b.state(["disabled"])
        self._refresh()

    # ---------------------------------------------------------------- pickers
    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(title=_("Input regulation.bin"),
                                       filetypes=[("regulation.bin", "*.bin"), (_("All files"), "*.*")])
        if p:
            self.input.set(p)

    def _pick_output(self) -> None:
        cur = Path(self.output.get() or "randomized/regulation.bin")
        p = filedialog.asksaveasfilename(title=_("Output file"), initialdir=str(cur.parent), initialfile=cur.name,
                                         defaultextension=".bin", filetypes=[("regulation.bin", "*.bin")])
        if p:
            self.output.set(p)

    def _pick_jokes(self) -> None:
        ps = filedialog.askopenfilenames(title=_("Joke shifu (--dialogue-jokes)"),
                                         filetypes=[("menu_dlc02.msgbnd.dcx", "*.msgbnd.dcx"), (_("All files"), "*.*")])
        if ps:
            have = [x for x in self.joke_archives.get().split(";") if x.strip()]
            self.joke_archives.set(";".join(have + [p for p in ps if p not in have]))

    def _pick_dll(self) -> None:
        p = filedialog.askopenfilename(title=oodle.DLL_NAME,
                                       filetypes=[(oodle.DLL_NAME, oodle.DLL_NAME), ("DLL", "*.dll")])
        if p:
            self.dll.set(p)

    def _open_out_dir(self) -> None:
        d = Path(self.output.get().strip() or "randomized/regulation.bin").resolve().parent
        if not d.is_dir():
            messagebox.showinfo(TITLE, _("The folder does not exist yet: {}").format(d))
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
            raise ValueError(_("{} must be an integer: {}").format(_(what), s)) from None

    def argv(self, dry_run: bool, repack: bool = False) -> list[str]:
        a = ["--input", self.input.get().strip() or "regulation.bin",
             "--output", self.output.get().strip() or "randomized/regulation.bin"]
        if repack:                                    # re-compress only: no randomization options at all
            a.append("--repack")
            if self.compression.get() != "auto":
                a += ["--compression", self.compression.get()]
            if self.dll.get().strip():
                a += ["--oodle-dll", self.dll.get().strip()]
            return a
        if self.seed.get().strip():
            a += ["--seed", str(self._int(self.seed.get(), "Seed"))]
        if self.mode.get() != "shuffle":
            a += ["--mode", self.mode.get()]
        if self.include_flasks.get():
            a.append("--include-flasks")
        if self.include_remembrances.get():
            a.append("--include-remembrances")
        if self.split_anim.get() != "none":
            a += ["--split-anim", self.split_anim.get()]
        if self.flask_locations.get():
            a.append("--random-flask-locations")
        if self.dialogue.get():
            a.append("--random-dialogue")
            if self.jokes.get():
                a.append("--dialogue-jokes")
                a += [x.strip() for x in self.joke_archives.get().split(";") if x.strip()]
        if not self.spells.get():
            a.append("--no-spells")
        if self.random_prices.get():
            a.append("--random-prices")
            if self.price_mode.get() == "range":
                a += ["--price-mode", "range"]
                for var, flag, what in ((self.price_min, "--price-min", "min price"),
                                        (self.price_max, "--price-max", "max price")):
                    if var.get().strip():
                        a += [flag, str(self._int(var.get(), what))]
            if not self.sell_prices.get():
                a.append("--no-sell-prices")
            if self.sell_equipment.get():
                a.append("--sell-equipment")
            if self.price_mode.get() == "range" and (self.sell_prices.get() or self.sell_equipment.get()):
                for var, flag, what in ((self.sell_min, "--sell-min", "min sell price"),
                                        (self.sell_max, "--sell-max", "max sell price")):
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
                raise ValueError(_("Random stats needs at least one group"))
            if len(groups) != len(weapons.STAT_GROUPS):
                a += ["--stat-groups", ",".join(groups)]
            lo, hi = self.stamina_lo.get().strip(), self.stamina_hi.get().strip()
            if (lo, hi) != STAMINA_DEFAULT:
                try:
                    flo, fhi = float(lo), float(hi)
                except ValueError:
                    flo, fhi = 0.0, 0.0
                if not 0 < flo <= fhi:
                    raise ValueError(_("The stamina multiplier range must satisfy 0 < min <= max, e.g. 0.3 to 1.7"))
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
                            (self.dep_sell, self.random_prices.get()
                             and (self.sell_prices.get() or self.sell_equipment.get())),
                            (self.dep_movesets, self.movesets.get()),
                            (self.dep_stats, self.stats.get()),
                            (self.dep_dialogue, self.dialogue.get()),
                            (self.dep_jokes, self.dialogue.get() and self.jokes.get())):
            for w in widgets:
                w.state(["!disabled"] if on else ["disabled"])
        try:
            self.cmd.set(f"{LAUNCHER} {join_argv(self.argv(False))}")
        except ValueError as e:
            self.cmd.set(_("Bad option: {}").format(e))

    def _preset(self) -> None:
        self.split_anim.set("any")
        self.random_prices.set(True)
        self.flask_locations.set(True)
        self.dialogue.set(True)
        self.jokes.set(True)
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
        self.sell_equipment.set(False)
        self.sell_min.set("")
        self.sell_max.set("")
        for v in (self.include_flasks, self.include_remembrances, self.flask_locations, self.dialogue, self.jokes,
                  self.random_prices, self.somber, self.movesets, self.default_ash, self.stats, self.keep_standard,
                  self.weptype):
            v.set(False)
        self.joke_archives.set("")
        self.moveset_mode.set("affinity")
        self.shield.set("shields")
        self.bow.set("bows")
        self.variety.set("3")
        for v in self.groups.values():
            v.set(True)
        self.stamina_lo.set(STAMINA_DEFAULT[0])
        self.stamina_hi.set(STAMINA_DEFAULT[1])

    # ---------------------------------------------------------------- running
    def _start(self, dry_run: bool, repack: bool = False) -> None:
        if self.running:
            return
        try:
            argv = self.argv(dry_run, repack)
        except ValueError as e:
            messagebox.showerror(TITLE, str(e))
            return
        inp = Path(self.input.get().strip() or "regulation.bin")
        if not inp.is_file():
            messagebox.showerror(TITLE, _("Input file not found: {}").format(inp))
            return
        outp = Path(self.output.get().strip() or "randomized/regulation.bin")
        if not dry_run and inp.resolve().parent == outp.resolve().parent:
            messagebox.showerror(TITLE, _("The output file must not be in the same folder as the input ({}): the reports "
                                          "and the joke shifu's msg folder are written next to the output and would end up "
                                          "in that folder, and an output named regulation.bin would replace the input. "
                                          "Create a new folder for the output; that also keeps the mods easy to "
                                          "manage.").format(inp.resolve().parent))
            return
        dll = self.dll.get().strip()
        if dll and not Path(dll).is_file():
            messagebox.showerror(TITLE, _("DLL not found: {}").format(dll))
            return
        if not dll:
            os.environ.pop("OODLE_DLL", None)      # the field is the only source, not the DLL of an earlier run
        if not dry_run and not dll and self.compression.get() != erreg.CODEC_ZSTD:
            if oodle.find_dll() is None:
                if not messagebox.askyesno(TITLE, _(
                        "No {} given and there is none in the current folder ({}).\n\n"
                        "It is in the game's Game\\ folder; pick it with Browse… to write the game's own KRAK format.\n\n"
                        "Continue with the zstd format instead? The file will be about 35% larger and may exceed "
                        "the game's size limit.").format(oodle.DLL_NAME, Path.cwd())):
                    return
                if "--compression" in argv:
                    argv[argv.index("--compression") + 1] = erreg.CODEC_ZSTD
                else:
                    argv += ["--compression", erreg.CODEC_ZSTD]
        self.running, self.dry_run, self.repack = True, dry_run, repack
        self.out = Path(self.output.get().strip() or "randomized/regulation.bin")
        for b in (self.btn_dry, self.btn_repack, self.btn_run):
            b.state(["disabled"])
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._set_status("Running…")
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
        for b in (self.btn_dry, self.btn_repack, self.btn_run):
            b.state(["!disabled"])
        if rc == 0 and self.dry_run:
            self._set_status("Preview finished, no file written")
        elif rc == 0 and self.repack:
            self._set_status("Done: {}", self.out)
            messagebox.showinfo(TITLE, _("Written: {}\n\nContent unchanged, only re-compressed. Replace the regulation.bin "
                                         "in the mod folder with it to use it.").format(self.out))
        elif rc == 0:
            self._set_status("Done: {}", self.out)
            messagebox.showinfo(TITLE, _("Written: {}\n\nReplace the regulation.bin in the mod folder with it to use it.\n"
                                         "mapping.txt / weapons.txt / spells.txt / dialogue.txt (what was randomized) "
                                         "are in the same folder; with jokes, copy its msg folder into the mod folder "
                                         "too.").format(self.out))
        else:
            if msg:
                self._append("\n" + msg.rstrip() + "\n")
            self._set_status("Failed, see the log")
            messagebox.showerror(TITLE, (msg or _("The run failed, see the log")).strip()[-2000:])

    def _close(self) -> None:
        if self.running and not messagebox.askyesno(TITLE, _("Still running. Quit anyway? The output file may be "
                                                             "incomplete.")):
            return
        self.root.destroy()


def run_gui(args: list[str]) -> int:
    if tk is None:
        fatal(_("This Python has no usable tkinter, the window cannot be shown.") + "\n\n" + (TK_ERROR or "").rstrip()
              + "\n\n" + _(NO_TK_HINT))
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
    lang.load(INI)
    try:
        return run_gui(args)
    except Exception:
        fatal(_("The window failed to start:") + "\n\n" + traceback.format_exc().rstrip())
        return 1


if __name__ == "__main__":
    sys.exit(main())
