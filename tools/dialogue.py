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

--pool-first (both archives; --zhocn-pool is the old name): per language the text archive is rewritten so that
the subtitles are drawn first from a pool, every pool line shown exactly once, and only when the pool is used
up do the remaining rows keep the game's own lines.  Chinese: names/sanguo_zhocn.txt (lines from the 2010 TV
series "Three Kingdoms", the "speaker：" prefix dropped, the subtitle shows the line alone) + names/jokes_zhocn.txt;
English: names/jokes_engus.txt.  The permutation of the text ids is the same as without the option (the pool
draws its random numbers afterwards); what changes is the text behind the ids that an archive carries: the text
ids in play are put in a random order, the cut ids first (with --dialogue-jokes they are in play and would
otherwise be blank), and the first len(pool) of them get a pool line each, a female-variant id getting the same
line as its male partner (unless it is shown itself).

--mixed-pool (both archives): every subtitle the dialogue rows show comes from one heap per language, in no
order: Chinese = names/sanguo_zhocn.txt + jokes_zhocn.txt + translate20_zhocn.txt, English = jokes_engus.txt +
translate20_engus.txt, where translate20_<language>.txt holds the game's own lines after 20 machine translations
(the "谷歌翻译20次" meme; tools/translate20.py makes the file).  The game's own lines are not in the heap: every
shown text id gets a heap line (the heap reshuffled and gone through again when the ids outnumber it), a
female-variant id its partner's line.  Planned after the permutation like --pool-first, which it excludes.

--translate20 (both archives, with or without --random-dialogue): every text id that has a line in
names/translate20_<language>.txt shows that line, its own line after the 20 translations, id for id; the other
ids are left alone (--dialogue-jokes may fill the cut ones).  Not together with the pools, which rewrite the same
ids.  Without --random-dialogue nothing moves: every NPC speaks its own line under its garbled subtitle.
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
TRANSLATED = "translate20_{}.txt"                  # names/: the game's lines after 20 machine translations (translate20.py)
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


def load_translated_map(path: Path) -> dict[int, str]:
    """names/translate20_<language>.txt: "<text id> <line>" per text id (tools/translate20.py), # comments and blank
       lines skipped; text id -> line (an entry without a line is left out)."""
    lines: dict[int, str] = {}
    for l in path.read_text(encoding="utf-8").splitlines():
        if not l.strip() or l.startswith("#"):
            continue
        head, _, rest = l.partition(" ")
        if head.isdigit() and rest.strip():
            lines[int(head)] = " ".join(rest.split())
    if not lines:
        raise SystemExit(f"{path}: no \"<text id> <line>\" lines in it")
    return lines


def load_translated(path: Path) -> list[str]:
    """The distinct lines of names/translate20_<language>.txt in file order, for a heap (the file has one line per
       text id, so many lines repeat: 20 translations make different lines end up the same)."""
    return list(dict.fromkeys(load_translated_map(path).values()))


def first_pool_files(lang: str) -> list[str]:
    """--pool-first, per language (names/): the Three Kingdoms lines when that language has them, then the jokes."""
    files = [f"jokes_{lang}.txt"]
    if (HERE / "names" / f"sanguo_{lang}.txt").is_file():
        files.insert(0, f"sanguo_{lang}.txt")
    return files


def mixed_files(lang: str) -> list[str]:
    """--mixed-pool, per language (names/): the Three Kingdoms lines when that language has them, the jokes and
       the 20x-translated game lines."""
    files = [f"jokes_{lang}.txt", TRANSLATED.format(lang)]
    if (HERE / "names" / f"sanguo_{lang}.txt").is_file():
        files.insert(0, f"sanguo_{lang}.txt")
    return files


def translated_languages() -> list[str]:
    """Languages a names/translate20_<language>.txt exists for (--translate20)."""
    return sorted(p.stem[len("translate20_"):] for p in (HERE / "names").glob("translate20_*.txt"))


def mixed_languages() -> list[str]:
    """Languages --mixed-pool has lines for: names/translate20_<language>.txt plus a joke list."""
    return [lang for lang in translated_languages() if (HERE / "names" / f"jokes_{lang}.txt").is_file()]


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


class FirstPool:
    """--pool-first: per language archive (msg/<language>/menu_dlc02.msgbnd.dcx) a pool, names/sanguo_<language>.txt
       when there is one (the Three Kingdoms lines, speaker dropped) + jokes_<language>.txt, is written over the
       text ids the dialogue rows show: every pool line once, cut ids first, then random ids; the ids left over
       keep the game's own lines.  Chinese: Three Kingdoms + jokes; English: the jokes."""
    what = "pool first"

    def __init__(self, archives: list[str]):
        self.archives = [Path(a) for a in archives]
        self.langs = [p.parent.name.lower() for p in self.archives]
        if len(set(self.langs)) != len(self.langs):
            raise SystemExit("--pool-first: one archive per language folder, please")
        self.lists: dict[str, dict[str, list[str]]] = {}      # language -> names/ file -> its lines
        self.lines: dict[str, list[str]] = {}                 # language -> the pool
        self.given: dict[str, dict[int, str]] = {}
        for p, lang in zip(self.archives, self.langs):
            if not p.is_file():
                raise SystemExit(f"--pool-first: {p} does not exist")
            files = first_pool_files(lang)
            missing = [n for n in files if not (HERE / "names" / n).is_file()]
            if missing:
                raise SystemExit(f"--pool-first: {p} is in folder '{p.parent.name}', but tools/names/ has no "
                                 f"{', '.join(missing)} (a line per row, # comments allowed)")
            self.lists[lang] = {}
            for n in files:
                lines = load_jokes(HERE / "names" / n)
                if n.startswith("sanguo_"):
                    lines = [strip_speaker(l) for l in lines]      # the speaker names stay in the file only
                self.lists[lang][n] = lines
            self.lines[lang] = [l for n in files for l in self.lists[lang][n]]
            self.given[lang] = talkmsg.read_archive(p)
        self.texts: dict[str, dict[int, str]] = {lang: {} for lang in self.langs}   # id -> pool line to write
        self.shown: dict[str, dict[int, str]] = {lang: {} for lang in self.langs}   # primary id -> line (report)
        self.cut: dict[str, int] = {lang: 0 for lang in self.langs}      # ids given a line that had no text
        self.unused: dict[str, int] = {lang: 0 for lang in self.langs}   # pool lines left over

    def plan(self, ids: list[int], pairs: dict[int, set[int]], rng: random.Random) -> None:
        """ids: the text ids the dialogue rows show (msgId, distinct); pairs: msgId -> the msgId_female ids that
           differ from it.  Per language (in the order the archives were given): the cut ids (no text in that
           archive) come first so none stays blank, the rest in random order; each gets the next pool line (the
           pool in random order).  Should the cut ids outnumber the pool, the lines cycle over the remaining cut
           ids.  A female-variant id gets its partner's line unless it is a shown id with a line of its own."""
        for lang in self.langs:
            given = self.given[lang]
            cut = [t for t in ids if not has_text(given.get(t))]
            rest = [t for t in ids if has_text(given.get(t))]
            rng.shuffle(cut)
            rng.shuffle(rest)
            order = cut + rest
            lines = list(self.lines[lang])
            rng.shuffle(lines)
            shown: dict[int, str] = {}
            for i, tid in enumerate(order):
                if i >= len(lines) and i >= len(cut):
                    break
                shown[tid] = lines[i % len(lines)]
            self.shown[lang] = shown
            self.cut[lang] = len(cut)
            self.unused[lang] = max(0, len(lines) - len(order))
            texts = {}
            for tid, line in shown.items():
                texts[tid] = line
                for f in pairs.get(tid, ()):
                    if f not in shown:
                        texts[f] = line
            self.texts[lang] = texts

    def summary(self) -> str:
        out = []
        for lang, archive in zip(self.langs, self.archives):
            parts = " + ".join(f"names/{n} {len(l)}" for n, l in self.lists[lang].items())
            out.append(f"# pool first {lang}: {len(self.lines[lang])} lines ({parts}) given to {len(self.shown[lang])} text ids "
                       f"({self.cut[lang]} of them cut ids, {len(self.texts[lang]) - len(self.shown[lang])} female-variant ids "
                       f"get their partner's line), the other ids keep the game's {lang} text"
                       + (f"; {self.unused[lang]} lines unused" if self.unused[lang] else "")
                       + f"; archive {archive}")
        return "\n".join(out)

    def archive_of(self, lang: str) -> Path:
        return self.archives[self.langs.index(lang)]

    def texts_for(self, lang: str) -> dict[int, str]:
        return self.texts[lang]

    def detail(self, lang: str) -> str:
        return f"{len(self.lines[lang])} pool lines over {len(self.shown[lang])} text ids, the rest unchanged"

    def report_header(self) -> str:
        return "".join(f"  || {lang}: the pool line the {lang} archive shows for that id, when it got one" for lang in self.langs)

    def report(self, tid: int) -> str:
        return "".join(f"  || {lang}: {self.shown[lang][tid]}" for lang in self.langs if tid in self.shown[lang])


class MixedPool:
    """--mixed-pool: every subtitle the dialogue rows show comes from a heap, one per language archive
       (msg/<language>/menu_dlc02.msgbnd.dcx): names/sanguo_<language>.txt when there is one (the Three Kingdoms
       lines, speaker dropped), jokes_<language>.txt and translate20_<language>.txt (the game's own lines after 20
       machine translations, tools/translate20.py), all in one heap and in no order.  The game's own lines are
       not in it: every shown id gets a heap line (the heap reshuffled and gone through again when the ids
       outnumber it), a female-variant id its partner's line unless it is shown itself.  Same interface as
       FirstPool."""
    what = "mixed pool"

    def __init__(self, archives: list[str]):
        self.archives = [Path(a) for a in archives]
        self.langs = [p.parent.name.lower() for p in self.archives]
        if len(set(self.langs)) != len(self.langs):
            raise SystemExit("--mixed-pool: one archive per language folder, please")
        self.lists: dict[str, dict[str, list[str]]] = {}      # language -> names/ file -> its lines
        self.lines: dict[str, list[str]] = {}                 # language -> the heap
        self.given: dict[str, dict[int, str]] = {}
        for p, lang in zip(self.archives, self.langs):
            if not p.is_file():
                raise SystemExit(f"--mixed-pool: {p} does not exist")
            files = mixed_files(lang)
            missing = [n for n in files if not (HERE / "names" / n).is_file()]
            if missing:
                raise SystemExit(f"--mixed-pool: {p} is in folder '{p.parent.name}', but tools/names/ has no "
                                 f"{', '.join(missing)} (jokes_<language>.txt: a joke per line; translate20_<language>.txt: "
                                 "tools/translate20.py writes it)")
            self.lists[lang] = {}
            for n in files:
                path = HERE / "names" / n
                if n.startswith("translate20_"):
                    lines = load_translated(path)
                else:
                    lines = load_jokes(path)
                    if n.startswith("sanguo_"):
                        lines = [strip_speaker(l) for l in lines]
                self.lists[lang][n] = lines
            self.lines[lang] = [l for n in files for l in self.lists[lang][n]]
            self.given[lang] = talkmsg.read_archive(p)
        self.texts: dict[str, dict[int, str]] = {lang: {} for lang in self.langs}   # id -> line to write
        self.shown: dict[str, dict[int, str]] = {lang: {} for lang in self.langs}   # primary id -> line (report)
        self.cut: dict[str, int] = {lang: 0 for lang in self.langs}

    def plan(self, ids: list[int], pairs: dict[int, set[int]], rng: random.Random) -> None:
        """ids: the text ids the dialogue rows show (msgId, distinct); pairs: msgId -> the msgId_female ids that
           differ from it.  Per language (in the order the archives were given): the ids in random order, the
           heap in random order, one line per id; more ids than lines, and the heap is shuffled again and
           continued.  A female-variant id that is not shown itself gets its partner's line."""
        for lang in self.langs:
            order = list(ids)
            rng.shuffle(order)
            heap: list[str] = []
            while len(heap) < len(order):
                more = list(self.lines[lang])
                rng.shuffle(more)
                heap += more
            self.shown[lang] = dict(zip(order, heap))
            self.cut[lang] = sum(1 for t in ids if not has_text(self.given[lang].get(t)))
            texts = {}
            for tid, line in self.shown[lang].items():
                texts[tid] = line
                for f in pairs.get(tid, ()):
                    if f not in self.shown[lang]:
                        texts[f] = line
            self.texts[lang] = texts

    def summary(self) -> str:
        out = []
        for lang, archive in zip(self.langs, self.archives):
            parts = " + ".join(f"names/{n} {len(l)}" for n, l in self.lists[lang].items())
            n_ids, n_lines = len(self.shown[lang]), len(self.lines[lang])
            out.append(f"# mixed pool {lang}: {n_lines} lines ({parts}) in no order over all {n_ids} shown text ids "
                       f"({self.cut[lang]} of them cut ids, {len(self.texts[lang]) - n_ids} female-variant ids get their "
                       f"partner's line); "
                       + (f"{n_ids - n_lines} lines show twice" if n_ids > n_lines else f"{n_lines - n_ids} lines unused")
                       + f"; none of the game's own lines is shown; archive {archive}")
        return "\n".join(out)

    def archive_of(self, lang: str) -> Path:
        return self.archives[self.langs.index(lang)]

    def texts_for(self, lang: str) -> dict[int, str]:
        return self.texts[lang]

    def detail(self, lang: str) -> str:
        return f"{len(self.lines[lang])} heap lines over all {len(self.shown[lang])} shown text ids"

    def report_header(self) -> str:
        return "".join(f"  || {lang}: the heap line the {lang} archive shows for that id" for lang in self.langs)

    def report(self, tid: int) -> str:
        return "".join(f"  || {lang}: {self.shown[lang][tid]}" for lang in self.langs if tid in self.shown[lang])


class Translated:
    """--translate20: every text id of an archive (msg/<language>/menu_dlc02.msgbnd.dcx) that has a line in
       names/translate20_<language>.txt (its own line after 20 machine translations, tools/translate20.py) shows
       that line, id for id; the other ids are left alone (--dialogue-jokes may fill the cut ones).  With
       --random-dialogue the rows are shuffled as usual and the texts behind the ids are the translated ones;
       without it nothing moves.  Same interface as the pools, but nothing is random (plan does nothing)."""
    what = "translate20"

    def __init__(self, archives: list[str]):
        self.archives = [Path(a) for a in archives]
        self.langs = [p.parent.name.lower() for p in self.archives]
        if len(set(self.langs)) != len(self.langs):
            raise SystemExit("--translate20: one archive per language folder, please")
        self.texts: dict[str, dict[int, str]] = {}            # language -> id -> its translated line
        self.skipped: dict[str, int] = {}                     # file entries whose id has no line in the archive
        for p, lang in zip(self.archives, self.langs):
            if not p.is_file():
                raise SystemExit(f"--translate20: {p} does not exist")
            path = HERE / "names" / TRANSLATED.format(lang)
            if not path.is_file():
                raise SystemExit(f"--translate20: {p} is in folder '{p.parent.name}', but there is no {path.name} in "
                                 "tools/names/ (tools/translate20.py writes it)")
            given = talkmsg.read_archive(p)
            lines = load_translated_map(path)
            self.texts[lang] = {tid: line for tid, line in lines.items() if has_text(given.get(tid))}
            self.skipped[lang] = len(lines) - len(self.texts[lang])

    def plan(self, ids: list[int], pairs: dict[int, set[int]], rng: random.Random) -> None:
        pass                                                   # id for id, nothing to draw

    def summary(self) -> str:
        return "\n".join(f"# translate20 {lang}: {len(self.texts[lang])} text ids show their own line after 20 machine "
                         f"translations (names/{TRANSLATED.format(lang)}"
                         + (f"; {self.skipped[lang]} entries have no line in this archive and are skipped" if self.skipped[lang] else "")
                         + f"); the other ids are unchanged; archive {archive}"
                         for lang, archive in zip(self.langs, self.archives))

    def archive_of(self, lang: str) -> Path:
        return self.archives[self.langs.index(lang)]

    def texts_for(self, lang: str) -> dict[int, str]:
        return self.texts[lang]

    def detail(self, lang: str) -> str:
        return f"{len(self.texts[lang])} text ids replaced id for id by names/{TRANSLATED.format(lang)}"

    def report_header(self) -> str:
        return "".join(f"  || {lang}: that id's own line after 20 translations" for lang in self.langs)

    def report(self, tid: int) -> str:
        return "".join(f"  || {lang}: {self.texts[lang][tid]}" for lang in self.langs if tid in self.texts[lang])


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
                  pool: FirstPool | MixedPool | Translated | None = None) -> list[str]:
        """draw: shuffle = a permutation (every line shown once), random = free draws (a line may show up
           several times).  jokes: the cut rows' text ids get a joke each and the rows join the pool.
           pool: --pool-first / --mixed-pool / --translate20, the texts behind the ids the rows show in the
           rewritten archives (planned after the permutation, so the permutation does not depend on it)."""
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
            pairs: dict[int, set[int]] = {}                 # msgId -> its female-variant ids (a few rows differ)
            for b in bundle.values():
                if b["msgId_female"] > 0 and b["msgId_female"] != b["msgId"]:
                    pairs.setdefault(b["msgId"], set()).add(b["msgId_female"])
            pool.plan(shown, pairs, rng)
            lines[1:1] = pool.summary().split("\n")
            lines[-1] += pool.report_header()
        for r, j in zip(rows, idx):
            s = rows[j]
            for f in TEXT_FIELDS:
                self.P.set(r, f, bundle[s.id][f])
            shown_id = bundle[s.id]["msgId"]
            extra = pool.report(shown_id) if pool is not None else ""
            lines.append(f"{r.id:>9}  <- {s.id:>9}  {self.line(shown_id)}{extra}")
        return lines
