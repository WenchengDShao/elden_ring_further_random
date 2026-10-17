"""Night-sky look of the window: the palette, dark ttk styles and the Melina sidebar (assets/melina.jpg).

Pillow scales, crops and fades the image and hands it to Tk as a PPM byte string (no ImageTk needed).
Without Pillow or without the image the window keeps the colours and the title only.
"""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

try:
    from PIL import Image, ImageChops
except ImportError:                       # Pillow not installed: plain dark window
    Image = None

HERE = Path(__file__).resolve().parent
IMAGE = HERE / "assets" / "melina.jpg"

# 星夜·紫：偏紫的夜空底色，淡紫强调
PALETTE = dict(bg="#0d0b1c", panel="#181536", raised="#221e48", field="#100e24", border="#352f63",
               fg="#e6e2f5", muted="#9a93bd", accent="#c3a6ff", accent_hi="#dcc9ff", accent_fg="#140c2a",
               select="#3a3270", log_bg="#09071a", log_fg="#cfc8e6")
SIDE = 270                                # sidebar width at 96 dpi
MINSIZE = (1110, 720)
TITLE_LINES = ("ELDEN RING", "F U R T H E R   R A N D O M", "regulation.bin 随机器 · 道具 / 法术 / 武器")
TITLE_FAMILIES = ("Cinzel", "Trajan Pro", "Georgia", "Palatino Linotype", "Book Antiqua", "Times New Roman",
                  "DejaVu Serif", "Liberation Serif")
_FONTS: list = []          # tkinter deletes a Font's Tk font when the object is garbage-collected: keep ours alive


def _font(root: tk.Tk, families, size: int, weight: str = "normal") -> tkfont.Font:
    have = set(tkfont.families(root))
    fam = next((f for f in families if f in have), "Times")
    f = tkfont.Font(root=root, family=fam, size=size, weight=weight)
    _FONTS.append(f)
    return f


def dpi_scale(root: tk.Tk) -> float:
    try:
        return max(1.0, root.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        return 1.0


# ---------------------------------------------------------------- ttk styles
def apply(root: tk.Tk, pal: dict = PALETTE) -> ttk.Style:
    """Dark ttk styles on top of the 'clam' theme (the only built-in theme whose colours are all adjustable)."""
    st = ttk.Style(root)
    st.theme_use("clam")
    root.configure(bg=pal["bg"])
    base = tkfont.nametofont("TkDefaultFont")
    size = base.cget("size")                   # cget, not actual(): actual() is off on some X displays
    bold = tkfont.Font(root=root, family=base.cget("family"), size=size, weight="bold")
    head = tkfont.Font(root=root, family=base.cget("family"), size=size + (1 if size > 0 else -1), weight="bold")
    _FONTS.extend((bold, head))
    st.configure(".", background=pal["panel"], foreground=pal["fg"], fieldbackground=pal["field"],
                 bordercolor=pal["border"], lightcolor=pal["panel"], darkcolor=pal["panel"],
                 troughcolor=pal["bg"], selectbackground=pal["select"], selectforeground=pal["fg"],
                 insertcolor=pal["fg"], focuscolor=pal["accent"])
    # clam maps a disabled / active background to its own light grey for every widget: override at the root
    st.map(".", foreground=[("disabled", pal["muted"])],
           background=[("disabled", pal["panel"]), ("active", pal["panel"])])
    st.configure("Bg.TFrame", background=pal["bg"])
    st.configure("Bg.TLabel", background=pal["bg"])
    st.configure("Hint.TLabel", foreground=pal["muted"])
    st.configure("Status.TLabel", background=pal["bg"], foreground=pal["muted"], padding=(4, 2))
    st.configure("TLabelframe", bordercolor=pal["border"], relief="solid", borderwidth=1, padding=(4, 2, 4, 6))
    st.configure("TLabelframe.Label", foreground=pal["accent"], font=head)
    for kind in ("TCheckbutton", "TRadiobutton"):
        st.configure(kind, indicatorbackground=pal["field"], indicatorforeground=pal["accent_fg"],
                     upperbordercolor=pal["border"], lowerbordercolor=pal["border"], padding=2)
        st.map(kind, background=[("disabled", pal["panel"]), ("active", pal["panel"])],
               indicatorbackground=[("disabled", pal["panel"]), ("selected", pal["accent"]), ("active", pal["raised"])],
               indicatorforeground=[("disabled", pal["muted"]), ("selected", pal["accent_fg"])])
    st.configure("TButton", background=pal["raised"], bordercolor=pal["border"], lightcolor=pal["raised"],
                 darkcolor=pal["raised"], padding=(10, 4))
    st.map("TButton", background=[("disabled", pal["panel"]), ("pressed", pal["select"]), ("active", pal["select"])],
           bordercolor=[("disabled", pal["border"]), ("active", pal["accent"])])
    st.configure("Accent.TButton", background=pal["accent"], foreground=pal["accent_fg"], bordercolor=pal["accent"],
                 lightcolor=pal["accent"], darkcolor=pal["accent"], font=bold)
    st.map("Accent.TButton", background=[("disabled", pal["raised"]), ("pressed", pal["accent_hi"]), ("active", pal["accent_hi"])],
           foreground=[("disabled", pal["muted"])], bordercolor=[("disabled", pal["border"])])
    st.configure("TEntry", fieldbackground=pal["field"], lightcolor=pal["field"], darkcolor=pal["field"], padding=3)
    st.map("TEntry", fieldbackground=[("disabled", pal["panel"]), ("readonly", pal["field"])],
           bordercolor=[("focus", pal["accent"])])
    st.configure("TCombobox", fieldbackground=pal["field"], background=pal["raised"], arrowcolor=pal["accent"],
                 lightcolor=pal["field"], darkcolor=pal["field"], padding=2)
    st.map("TCombobox", fieldbackground=[("disabled", pal["panel"]), ("readonly", pal["field"])],
           selectbackground=[("readonly", pal["field"])], selectforeground=[("readonly", pal["fg"])],
           arrowcolor=[("disabled", pal["muted"])], background=[("disabled", pal["panel"]), ("active", pal["select"])],
           bordercolor=[("focus", pal["accent"])])
    for opt, val in (("background", pal["field"]), ("foreground", pal["fg"]),
                     ("selectBackground", pal["select"]), ("selectForeground", pal["fg"])):
        root.option_add(f"*TCombobox*Listbox.{opt}", val)
    st.configure("TSpinbox", fieldbackground=pal["field"], background=pal["raised"], arrowcolor=pal["accent"],
                 lightcolor=pal["field"], darkcolor=pal["field"], padding=2)
    st.map("TSpinbox", fieldbackground=[("disabled", pal["panel"])], arrowcolor=[("disabled", pal["muted"])],
           background=[("disabled", pal["panel"])],
           bordercolor=[("focus", pal["accent"])])
    st.configure("TScrollbar", background=pal["raised"], troughcolor=pal["bg"], bordercolor=pal["bg"],
                 arrowcolor=pal["muted"], lightcolor=pal["raised"], darkcolor=pal["raised"])
    st.map("TScrollbar", background=[("active", pal["select"])], arrowcolor=[("active", pal["accent"])])
    return st


def style_text(widget: tk.Text, pal: dict = PALETTE) -> None:
    widget.configure(bg=pal["log_bg"], fg=pal["log_fg"], insertbackground=pal["fg"], selectbackground=pal["select"],
                     selectforeground=pal["fg"], relief="flat", bd=0, padx=6, pady=4, highlightthickness=1,
                     highlightbackground=pal["border"], highlightcolor=pal["accent"])


# ---------------------------------------------------------------- backdrop image
def _mask(size: tuple[int, int], side: str, start: float, strength: float) -> "Image.Image":
    """Alpha mask that is 0 up to `start` (fraction of the axis) and rises to `strength` at the `side` edge."""
    w, h = size
    m = Image.new("L", size, 0)
    up, down = bytes(range(256)), bytes(range(255, -1, -1))
    if side in ("bottom", "top"):
        n = max(1, round(h * (1 - start)))
        g = Image.frombytes("L", (1, 256), up if side == "bottom" else down).resize((w, n))
        m.paste(g, (0, h - n) if side == "bottom" else (0, 0))
    else:
        n = max(1, round(w * (1 - start)))
        g = Image.frombytes("L", (256, 1), up if side == "right" else down).resize((n, h))
        m.paste(g, (w - n, 0) if side == "right" else (0, 0))
    return m.point(lambda v: int(v * strength)) if strength < 1 else m


def render(src: "Image.Image", w: int, h: int, pal: dict, focus=(0.5, 0.5), fades=()) -> bytes:
    """Cover-crop `src` to w x h around `focus` (fractions of the image), fade the given sides into
       pal['bg'] ((side, start, strength) each) and return the result as PPM bytes."""
    sw, sh = src.size
    scale = max(w / sw, h / sh)
    cw, ch = w / scale, h / scale                              # crop box in source pixels
    x0 = min(max(focus[0] * sw - cw / 2, 0), sw - cw)
    y0 = min(max(focus[1] * sh - ch / 2, 0), sh - ch)
    img = src.resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
    if fades:
        mask = None
        for side, start, strength in fades:
            m = _mask((w, h), side, start, strength)
            mask = m if mask is None else ImageChops.lighter(mask, m)
        img = Image.composite(Image.new("RGB", (w, h), pal["bg"]), img, mask)
    return b"P6 %d %d 255\n" % (w, h) + img.tobytes()


class Backdrop:
    """A Canvas showing the image, re-rendered (debounced) whenever the canvas is resized."""

    def __init__(self, parent, pal: dict, *, focus=(0.5, 0.5), fades=(), **kw):
        self.canvas = tk.Canvas(parent, highlightthickness=0, bd=0, bg=pal["bg"], **kw)
        self.pal, self.focus, self.fades = pal, focus, tuple(fades)
        self.src = None
        if Image is not None and IMAGE.is_file():
            try:
                self.src = Image.open(IMAGE).convert("RGB")
            except Exception:
                self.src = None
        self.photo = None
        self.item = None
        self.size = (0, 0)
        self.job = None
        self.on_resize: list = []                               # callbacks (w, h) after a re-render
        self.canvas.bind("<Configure>", self._configure, add="+")

    def _configure(self, e) -> None:
        if (e.width, e.height) == self.size:
            return
        self.size = (e.width, e.height)
        if self.job:
            self.canvas.after_cancel(self.job)
        self.job = self.canvas.after(30, self._render)

    def _render(self) -> None:
        self.job = None
        w, h = self.size
        if w < 2 or h < 2:
            return
        if self.src is not None:
            self.photo = tk.PhotoImage(data=render(self.src, w, h, self.pal, self.focus, self.fades))
            if self.item is None:
                self.item = self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
                self.canvas.tag_lower(self.item)
            else:
                self.canvas.itemconfigure(self.item, image=self.photo)
        for cb in self.on_resize:
            cb(w, h)

    def title(self, root: tk.Tk, lines: tuple[str, str, str], place) -> None:
        """Three text lines (big serif, small serif, hint); `place(w, h)` -> (x, y, anchor, justify)."""
        pal, c = self.pal, self.canvas
        f1 = _font(root, TITLE_FAMILIES, 24, "bold")
        f2 = _font(root, TITLE_FAMILIES, 11)
        ids = (c.create_text(0, 0, text=lines[0], font=f1, fill=pal["accent"]),
               c.create_text(0, 0, text=lines[1], font=f2, fill=pal["fg"]),
               c.create_text(0, 0, text=lines[2], fill=pal["muted"]))
        gaps = (0, f1.metrics("linespace") + 2, f1.metrics("linespace") + f2.metrics("linespace") + 6)

        def move(w, h):
            x, y, anchor, justify = place(w, h)
            for i, g in zip(ids, gaps):
                c.coords(i, x, y + g)
                c.itemconfigure(i, anchor=anchor, justify=justify)
        self.on_resize.append(move)


# ---------------------------------------------------------------- layout
def layout(root: tk.Tk, pal: dict = PALETTE) -> ttk.Frame:
    """Melina sidebar on the left (title at its foot), returns the frame the sections go into."""
    s = dpi_scale(root)
    root.minsize(round(MINSIZE[0] * s), round(MINSIZE[1] * s))
    root.columnconfigure(1, weight=1)
    root.rowconfigure(0, weight=1)
    bd = Backdrop(root, pal, width=round(SIDE * s), focus=(0.5, 0.45),
                  fades=[("right", 0.78, 1.0), ("bottom", 0.6, 0.97)])
    bd.canvas.grid(row=0, column=0, sticky="ns")
    bd.title(root, TITLE_LINES, lambda w, h: (w // 2, h - round(96 * s), "n", "center"))
    body = ttk.Frame(root, style="Bg.TFrame")
    body.grid(row=0, column=1, sticky="nsew")
    return body


def arrange(body: ttk.Frame, sections) -> None:
    """sections: (widget, sticky, grows, pady), stacked top to bottom."""
    body.columnconfigure(0, weight=1)
    for i, (w, sticky, grow, pady) in enumerate(sections):
        w.grid(row=i, column=0, sticky=sticky, padx=8, pady=pady)
        if grow:
            body.rowconfigure(i, weight=1)
