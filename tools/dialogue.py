"""--random-dialogue: the subtitles of NPC dialogue are shuffled.

Every line an NPC says through its talk script is a TalkParam row: msgId is the subtitle (a TalkMsg text id),
voiceId the voice line, with msgId_female / voiceId_female for a female player character (67 rows differ,
"my lord" / "my lady").  The talk scripts (ESD) reference rows, never texts, and the TalkMsg FMGs are loaded
as a whole, so any row may show any line: msgId / msgId_female are permuted (as a pair) over the lines of
every NPC while the voices stay where they are.  The NPC speaks its own line and the box shows another one,
for as long as the voice lasts.  talkAnimationId (a gesture) and isForceDisp stay with the row too.

Voices are deliberately left alone: a 9-digit voice id xxxoooooo lives in sd/enus/vcxxx.bnk and the game
loads a voice bank only around the NPCs that use it, so a voice handed to another NPC would stay silent (and
a line whose voice never ends waits for GameSystemCommonParam.npcTalkTimeOutThreshold, 30 s).

Rows that are not dialogue (dummy rows 100 / 200, test and system rows 99xxxxxxx) and rows whose text id has
no known text (names/TalkMsg.txt: cut content, or text newer than the table) neither move nor receive
anything, so no line ends up with an empty subtitle.  Unless jokes fill the gap: with --dialogue-jokes every
text id of a dialogue row that has no text in a given language archive (msg/<language>/menu_dlc02.msgbnd.dcx)
gets a joke in that language (names/jokes_<language>.txt, cycled; which ids are empty differs a little per
language, e.g. a laugh that is "……哈哈。" in Chinese and blank in English), the archive is rewritten (see
talkmsg.py), and all dialogue rows join the shuffle, so jokes turn up in real conversations and some real
lines vanish into rows nobody ever plays.

--zhocn-pool (Chinese subtitles only): the Chinese text archive is rewritten so that the subtitles are drawn
first from a pool of lines, names/sanguo_zhocn.txt (lines from the 2010 TV series "Three Kingdoms") plus
names/jokes_zhocn.txt, every pool line shown exactly once (the "speaker：" prefix of the Three Kingdoms file is
dropped, the subtitle shows the line alone), and only when the pool is used up do the remaining rows keep the
game's own Chinese lines.  The permutation of the text ids is the same as without the option
(the pool draws its random numbers afterwards); what changes is the text behind the ids that the Chinese
archive carries: the text ids in play are put in a random order, the cut ids first (with --dialogue-jokes
they are in play and would otherwise be blank), and the first len(pool) of them get a pool line each, a
female-variant id getting the same line as its male partner.  Other languages are untouched.
"""
from __future__ import annotations

import random
import re
import sys
from collections import Counter
from pathlib import Path

import erreg
import talkmsg

HERE = Path(__file__).resolve().parent
TEXT_FILE = HERE / "names" / "TalkMsg.txt"        # text id -> English line (tools/talkmsg.py builds it)

ARCHIVE = "menu_dlc02.msgbnd.dcx"                 # the text archive that holds TalkMsg*.fmg (msg/<language>/)
# The archives shipped with the tool (game 1.17.1 text, base + DLC, DCX DFLT): tools/msg/<language>/ when run from
# the source, the msg/ folder next to the executable when packed (build_exe copies it there, the Release zip has it).
MSG_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent) / "msg"
TEXT_FIELDS = ("msgId", "msgId_female")
DUMMY_ROWS = {100, 200}
SYSTEM_ROWS = 990_000_000                          # 99xxxxxxx: test / debug / system rows
JOKE_LANG_REPORT = "engus"                         # the report quotes this list when it exists
POOL_LANG = "zhocn"                                # --zhocn-pool rewrites this language's archive only
POOL_FILES = ("sanguo_zhocn.txt", "jokes_zhocn.txt")  # names/: the Three Kingdoms lines, then the cold jokes
SPEAKER = re.compile(r"^[^，。！？：；…“”（）\s]{1,4}：")   # "曹操：台词" in sanguo_zhocn.txt: the speaker is dropped in game


def strip_speaker(line: str) -> str:
    """The Three Kingdoms file keeps the speaker for reference ("司马懿：我都病危十几年了！"); the subtitle shows the
       line alone.  A speaker is 1-4 characters before the first full-width colon; a line without one is kept."""
    return SPEAKER.sub("", line, count=1).strip()


def load_jokes(path: Path) -> list[str]:
    """One joke per line; blank lines and # comments skipped; line breaks are not possible in a subtitle."""
    jokes = [" ".join(l.split()) for l in path.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    if not jokes:
        raise SystemExit(f"{path}: no jokes in it")
    return jokes


def joke_languages() -> list[str]:
    """Languages a joke list exists for: names/jokes_<language>.txt."""
    return sorted(p.stem[len("jokes_"):] for p in (HERE / "names").glob("jokes_*.txt"))


def default_archives() -> list[Path]:
    """--dialogue-jokes without paths: the shipped archives MSG_DIR/<language>/menu_dlc02.msgbnd.dcx, one per
       language that has a joke list (whichever of them exist)."""
    return [MSG_DIR / lang / ARCHIVE for lang in joke_languages() if (MSG_DIR / lang / ARCHIVE).is_file()]


def has_text(t: str | None) -> bool:
    return bool(t) and bool(t.strip()) and t not in talkmsg.PLACEHOLDERS


class Jokes:
    """--dialogue-jokes: one text archive per game language (msg/<language>/menu_dlc02.msgbnd.dcx).  Every
       dialogue text id that has no text in an archive gets a joke from names/jokes_<language>.txt in that
       archive; one joke index per id is shared by all languages, so parallel lists show the same joke
       everywhere.  Give the game's own language first: the report describes that archive."""

    def __init__(self, archives: list[str]):
        self.archives = [Path(a) for a in archives]
        self.langs = [p.parent.name.lower() for p in self.archives]
        if len(set(self.langs)) != len(self.langs):
            raise SystemExit("--dialogue-jokes: one archive per language folder, please")
        self.lists: dict[str, list[str]] = {}
        self.given: dict[str, dict[int, str]] = {}
        for p, lang in zip(self.archives, self.langs):
            if not p.is_file():
                raise SystemExit(f"--dialogue-jokes: {p} does not exist")
            jokes = HERE / "names" / f"jokes_{lang}.txt"
            if not jokes.is_file():
                raise SystemExit(f"--dialogue-jokes: {p} is in folder '{p.parent.name}', but there is no "
                                 f"{jokes.name} in tools/names/ (write one, a joke per line)")
            self.lists[lang] = load_jokes(jokes)
            self.given[lang] = talkmsg.read_archive(p)
        self.missing: dict[str, set[int]] = {}
        self.index: dict[int, int] = {}

    def plan(self, ids: list[int], rng: random.Random) -> None:
        """ids: every text id of the dialogue rows.  Per language the ids without a text; one joke index per
           id (a random permutation spreads the lists evenly)."""
        for lang, texts in self.given.items():
            self.missing[lang] = {tid for tid in ids if not has_text(texts.get(tid))}
        union = sorted(set().union(*self.missing.values()))
        order = list(range(len(union)))
        rng.shuffle(order)
        self.index = dict(zip(union, order))

    def joke(self, lang: str, tid: int) -> str:
        jokes = self.lists[lang]
        return jokes[self.index[tid] % len(jokes)]

    def texts(self, lang: str) -> dict[int, str]:
        """What to write into that language's archive."""
        return {tid: self.joke(lang, tid) for tid in sorted(self.missing[lang])}

    def label(self, tid: int) -> str:
        """Report text for an id names/TalkMsg.txt has no English line for: the joke it shows in the first
           archive's language (quoted from the English list when there is one), else that archive's own text."""
        first = self.langs[0]
        if tid in self.missing[first]:
            lang = JOKE_LANG_REPORT if JOKE_LANG_REPORT in self.lists else first
            return f"[joke] {self.joke(lang, tid)}"
        return f"[{first}] {self.given[first].get(tid, '')}"


class ZhPool:
    """--zhocn-pool: the Chinese archive (msg/zhocn/menu_dlc02.msgbnd.dcx) gets the pool lines, names/sanguo_zhocn.txt
       + names/jokes_zhocn.txt, written over the text ids the dialogue rows show: every pool line once, cut ids
       first, then random ids; the ids left over keep the game's Chinese text.  The "说话人：" prefix of the
       Three Kingdoms lines is dropped, the subtitle shows the line alone."""

    def __init__(self, archive: Path):
        self.archive = Path(archive)
        if self.archive.parent.name.lower() != POOL_LANG:
            raise SystemExit(f"--zhocn-pool: {self.archive} is not in a folder named {POOL_LANG}; the option rewrites "
                             f"the Chinese archive only (msg/{POOL_LANG}/{ARCHIVE})")
        if not self.archive.is_file():
            raise SystemExit(f"--zhocn-pool: {self.archive} does not exist")
        self.lists: dict[str, list[str]] = {}
        for name in POOL_FILES:
            path = HERE / "names" / name
            if not path.is_file():
                raise SystemExit(f"--zhocn-pool: {path} is missing (a line per row, # comments allowed)")
            lines = load_jokes(path)
            if name == POOL_FILES[0]:
                lines = [strip_speaker(l) for l in lines]      # the speaker names stay in the file only
            self.lists[name] = lines
        self.lines: list[str] = [l for name in POOL_FILES for l in self.lists[name]]
        self.given = talkmsg.read_archive(self.archive)
        self.texts: dict[int, str] = {}                # id -> pool line to write (female partners included)
        self.shown: dict[int, str] = {}                # primary id -> pool line, for the report
        self.cut = 0                                   # how many of the ids given a line had no Chinese text
        self.unused = 0                                # pool lines left over (more lines than ids)

    def plan(self, ids: list[int], pairs: dict[int, int], rng: random.Random) -> None:
        """ids: the text ids the dialogue rows show (msgId, distinct); pairs: msgId -> msgId_female where they
           differ.  The cut ids (no text in the Chinese archive) come first so none stays blank, the rest in
           random order; each gets the next pool line (the pool in random order).  Should the cut ids outnumber
           the pool, the lines cycle over the remaining cut ids."""
        cut = [t for t in ids if not has_text(self.given.get(t))]
        rest = [t for t in ids if has_text(self.given.get(t))]
        rng.shuffle(cut)
        rng.shuffle(rest)
        order = cut + rest
        lines = list(self.lines)
        rng.shuffle(lines)
        self.cut = len(cut)
        self.shown = {}
        for i, tid in enumerate(order):
            if i >= len(lines) and i >= len(cut):
                break
            self.shown[tid] = lines[i % len(lines)]
        self.unused = max(0, len(lines) - len(order))
        self.texts = {}
        for tid, line in self.shown.items():
            self.texts[tid] = line
            if tid in pairs:
                self.texts[pairs[tid]] = line

    def summary(self) -> str:
        parts = " + ".join(f"names/{n} {len(self.lists[n])}" for n in POOL_FILES)
        return (f"# zhocn pool: {len(self.lines)} lines ({parts}) given to {len(self.shown)} text ids "
                f"({self.cut} of them cut ids, {len(self.texts) - len(self.shown)} female-variant ids get their "
                f"partner's line), the other ids keep the game's Chinese text"
                + (f"; {self.unused} lines unused" if self.unused else "")
                + f"; archive {self.archive}")


class Dialogue:
    def __init__(self, reg: erreg.Regulation):
        self.P = reg.param("TalkParam", erreg.load_paramdef(HERE / "paramdef" / "TalkParam.xml"))
        self.text = erreg.load_names(TEXT_FILE) if TEXT_FILE.is_file() else {}

    def line(self, msg: int) -> str:
        return self.text.get(msg) or f"text {msg}"

    def dialogue_ids(self) -> list[int]:
        """Every text id the dialogue rows use: msgId and msgId_female."""
        ids = set()
        for r in self.P.rows:
            if r.id in DUMMY_ROWS or r.id >= SYSTEM_ROWS:
                continue
            for f in TEXT_FIELDS:
                tid = self.P.get(r, f)
                if tid > 0:
                    ids.add(tid)
        return sorted(ids)

    def pool(self) -> tuple[list, Counter]:
        rows, skipped = [], Counter()
        for r in self.P.rows:
            if r.id in DUMMY_ROWS or r.id >= SYSTEM_ROWS:
                skipped["not dialogue"] += 1
            elif not self.text.get(self.P.get(r, "msgId")):
                skipped["no text known"] += 1
            else:
                rows.append(r)
        return rows, skipped

    def randomize(self, rng: random.Random, draw: str = "shuffle", jokes: Jokes | None = None,
                  pool: ZhPool | None = None) -> list[str]:
        """draw: shuffle = a permutation (every line shown once), random = free draws (a line may show up
           several times).  jokes: the cut rows' text ids get a joke each and the rows join the pool.
           pool: the Chinese archive shows the pool lines first (planned after the permutation, so the
           permutation does not depend on it)."""
        filled = ""
        if jokes is not None:
            ids = self.dialogue_ids()
            jokes.plan(ids, rng)
            for tid in ids:
                if not self.text.get(tid):
                    self.text[tid] = jokes.label(tid)
            filled = "; jokes fill " + ", ".join(f"{len(m)} text ids in {lang}" for lang, m in jokes.missing.items())
        rows, skipped = self.pool()
        bundle = {r.id: {f: self.P.get(r, f) for f in TEXT_FIELDS} for r in rows}
        idx = list(range(len(rows)))
        if draw == "shuffle":
            rng.shuffle(idx)
        else:
            idx = [rng.randrange(len(rows)) for _ in rows]
        lines = [f"# dialogue: draw={draw} lines={len(rows)} of {len(self.P.rows)} TalkParam rows  "
                 "(subtitles permuted over every NPC's lines; voices unchanged)"
                 + filled,
                 "# skipped: " + ", ".join(f"{n} {k}" for k, n in skipped.items()),
                 "# row  <-  row the subtitle came from  subtitle shown (English, names/TalkMsg.txt)"]
        if pool is not None:
            shown = sorted({bundle[rows[j].id]["msgId"] for j in idx})
            pairs = {b["msgId"]: b["msgId_female"] for b in bundle.values()
                     if b["msgId_female"] > 0 and b["msgId_female"] != b["msgId"]}
            pool.plan(shown, pairs, rng)
            lines.insert(1, pool.summary())
            lines[-1] += "  || zhocn: the pool line the Chinese archive shows for that id, when it got one"
        for r, j in zip(rows, idx):
            s = rows[j]
            for f in TEXT_FIELDS:
                self.P.set(r, f, bundle[s.id][f])
            shown_id = bundle[s.id]["msgId"]
            extra = f"  || zhocn: {pool.shown[shown_id]}" if pool is not None and shown_id in pool.shown else ""
            lines.append(f"{r.id:>9}  <- {s.id:>9}  {self.line(shown_id)}{extra}")
        return lines
