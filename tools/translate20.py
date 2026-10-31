#!/usr/bin/env python3
"""Put the game's dialogue lines through 20 machine translations and write names/translate20_<language>.txt, the
lines --mixed-pool draws from:

    python tools/translate20.py tools/msg/zhocn/menu_dlc02.msgbnd.dcx --model ~/.cache/er_mod_models/nllb600-ct2-int8
    python tools/translate20.py tools/msg/engus/menu_dlc02.msgbnd.dcx --model ~/.cache/er_mod_models/nllb600-ct2-int8

"谷歌翻译20次" (Bilibili meme, "Google-translated 20 times"): a text is translated into one language after another,
twenty times, the last translation landing back in the original language; every pass loses or bends a little, so
the result is a sentence that still sounds like a sentence and means something else entirely ("被谷歌翻译20次的
《桃花源记》" and the like).  The meme uses the Google Translate web page by hand; Google has no free API and its
web endpoint is not meant for a batch of 300 000 translations, so this script does the same chain offline with
Meta's open NLLB-200 model (the distilled 600M variant converted for CTranslate2, on the GPU when there is one).
The chain is fixed (CHAIN): 19 foreign languages, then back to the source language = 20 translations; the
source language's own entry in the chain is replaced (Chinese for the English archive, English for every other).

Input: the language's msg/<language>/menu_dlc02.msgbnd.dcx (the TalkMsg*.fmg inside; see talkmsg.py), the
language from the folder name (LANG).  Every distinct line is translated once (ids with the same text share the
result); <stage directions> of the English text lose their brackets.  Output: "<text id> <line>" for every text
id that has a line, sorted by id, # header: the file maps id for id, so --translate20 can put every subtitle's
own 20x-translated line in its place.  Nothing is dropped: a result that came back unchanged or equal to another
id's result stays, and no result is empty (a step that answers nothing keeps the previous text).  --trace writes
every intermediate step as TSV (for looking at how a line went astray).

Needs (not part of the randomizer, this is a one-off generator like talkmsg.py):
    pip install ctranslate2 sentencepiece      (+ nvidia-cublas-cu12 nvidia-cudnn-cu12 for the GPU)
    hf download JustFrederik/nllb-200-distilled-600M-ct2-int8 --local-dir ~/.cache/er_mod_models/nllb600-ct2-int8
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import talkmsg  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = Path.home() / ".cache" / "er_mod_models" / "nllb600-ct2-int8"
MODEL_REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
LANG = {                                            # msg folder -> NLLB-200 language code
    "zhocn": "zho_Hans", "zhotw": "zho_Hant", "engus": "eng_Latn", "jpnjp": "jpn_Jpan", "korkr": "kor_Hang",
    "frafr": "fra_Latn", "deude": "deu_Latn", "itait": "ita_Latn", "spaes": "spa_Latn", "spaar": "spa_Latn",
    "porbr": "por_Latn", "rusru": "rus_Cyrl", "polpl": "pol_Latn", "araae": "arb_Arab", "thath": "tha_Thai",
}
# 19 foreign languages, then back home = 20 translations.  Picked the way the meme picks them: some close to
# the source, many far from it and from each other, a few the model is weak in.
CHAIN = ["eng_Latn", "jpn_Jpan", "kor_Hang", "tha_Thai", "vie_Latn", "arb_Arab", "heb_Hebr", "rus_Cyrl",
         "fin_Latn", "hun_Latn", "tur_Latn", "hin_Deva", "swh_Latn", "zul_Latn", "isl_Latn", "deu_Latn",
         "fra_Latn", "spa_Latn", "khk_Cyrl"]
BATCH = 64
CJK = r"㐀-鿿豈-﫿　-〿！-～"
TAG = re.compile(r"<([^<>]*)>")                     # <panting> in the English text


def preload_cuda() -> None:
    """ctranslate2's wheel wants libcublas / libcudnn: the pip packages nvidia-cublas-cu12 / nvidia-cudnn-cu12 carry
       them outside the loader's path, so load them here (harmless when they are absent: the CPU still works)."""
    try:
        import nvidia  # type: ignore
    except ImportError:
        return
    import ctypes
    libs = sorted(p for d in nvidia.__path__ for p in Path(d).glob("*/lib/*.so*"))
    for _ in range(3):                              # dependencies among them resolve on a later round
        for lib in libs:
            try:
                ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def chain_for(source: str) -> list[str]:
    chain = [l for l in CHAIN if l != source]
    if len(chain) < len(CHAIN):                     # the source sat in the chain: another far language instead
        chain.insert(0, "zho_Hans" if source != "zho_Hans" else "eng_Latn")
    return chain + [source]


def clean(text: str) -> str:
    text = text.replace("⁇", " ")                   # an <unk> piece decodes to this
    return " ".join(text.split())


def polish(text: str, lang: str) -> str:
    """A leading dash or comma goes (the model likes to open a line with "- "); Chinese, which the model writes with ASCII
       punctuation, straight quotes and spaces, gets full-width punctuation, curly quotes and no spaces between
       CJK characters (a line without a CJK character is left as it is)."""
    text = re.sub(r"^[-–—,，、\s]+", "", text)
    if not lang.startswith("zho") or not re.search(rf"[{CJK}]", text):
        return text
    text = re.sub(rf"(?<=[{CJK}])\s+(?=[{CJK}])", "", text)
    text = text.replace("...", "……")
    text = re.sub(r"(?<!\d)\.(?!\d)", "。", text)
    for a, b in ((",", "，"), ("?", "？"), ("!", "！"), (":", "："), (";", "；"), ("(", "（"), (")", "）")):
        text = text.replace(a, b)
    parts = text.split('"')
    text = "".join(p + ("“" if i % 2 == 0 else "”") for i, p in enumerate(parts[:-1])) + parts[-1]
    text = re.sub(rf"(?<=[{CJK}])\s+(?=[{CJK}])", "", text)
    return text.strip()


class Engine:
    def __init__(self, model: Path, device: str, beam: int):
        preload_cuda()
        import ctranslate2  # noqa: F401
        import sentencepiece as spm
        if not (model / "model.bin").is_file():
            raise SystemExit(f"--model: {model} has no model.bin; get it with\n"
                             f"    hf download {MODEL_REPO} --local-dir {model}")
        if device == "auto":
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        self.device = device
        self.sp = spm.SentencePieceProcessor(model_file=str(model / "sentencepiece.bpe.model"))
        self.tr = ctranslate2.Translator(str(model), device=device,
                                         compute_type="int8_float16" if device == "cuda" else "int8")
        self.beam = beam

    def hop(self, texts: list[str], src: str, tgt: str) -> list[str]:
        """Every text from src to tgt; an empty answer keeps the text as it was."""
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = list(texts)
        for k in range(0, len(order), BATCH):
            idx = order[k:k + BATCH]
            toks = [[src] + self.sp.encode(texts[i], out_type=str) + ["</s>"] for i in idx]
            longest = max(len(t) for t in toks)
            res = self.tr.translate_batch(toks, target_prefix=[[tgt]] * len(toks), beam_size=self.beam,
                                          max_batch_size=BATCH, max_decoding_length=min(320, 3 * longest + 16),
                                          repetition_penalty=1.2, no_repeat_ngram_size=3)
            for i, r in zip(idx, res):
                pieces = [p for p in r.hypotheses[0] if p not in (tgt, "</s>")]
                got = clean(self.sp.decode(pieces))
                if got:
                    out[i] = got
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive", help="msg/<language>/menu_dlc02.msgbnd.dcx")
    ap.add_argument("--output", default=None, help="default: tools/names/translate20_<language>.txt")
    ap.add_argument("--model", default=str(DEFAULT_MODEL), help=f"CTranslate2 NLLB-200 model folder (default {DEFAULT_MODEL})")
    ap.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    ap.add_argument("--beam", type=int, default=2, help="beam size (2: fast; the meme does not need the best translation)")
    ap.add_argument("--source", default=None, help="NLLB code of the archive's language when the folder name is not in LANG")
    ap.add_argument("--limit", type=int, default=0, help="only the first N distinct lines (a test run)")
    ap.add_argument("--trace", default=None, metavar="TSV", help="write every intermediate step here")
    args = ap.parse_args(argv)

    archive = Path(args.archive)
    folder = archive.parent.name.lower()
    source = args.source or LANG.get(folder)
    if source is None:
        raise SystemExit(f"{archive}: folder '{folder}' is not a language I know ({', '.join(LANG)}); give --source")
    out = Path(args.output) if args.output else HERE / "names" / f"translate20_{folder}.txt"
    chain = chain_for(source)

    given = talkmsg.read_archive(archive)
    texts: dict[int, str] = {}
    for tid, t in sorted(given.items()):
        t = " ".join(t.split())
        if not t or t in talkmsg.PLACEHOLDERS:
            continue
        texts[tid] = " ".join(TAG.sub(r"\1", t).split())
    first_id: dict[str, int] = {}
    for tid, t in texts.items():
        first_id.setdefault(t, tid)
    originals = list(first_id)
    if args.limit:
        originals = originals[:args.limit]
    print(f"# {archive}: {len(given)} entries, {len(texts)} with text, {len(originals)} distinct lines to translate", file=sys.stderr)
    print(f"# chain ({len(chain)} translations): {source} -> " + " -> ".join(chain), file=sys.stderr)

    engine = Engine(Path(args.model), args.device, args.beam)
    print(f"# model {args.model} on {engine.device}, beam {engine.beam}", file=sys.stderr)
    steps = [originals]
    cur, src = originals, source
    t0 = time.time()
    for n, tgt in enumerate(chain, 1):
        t1 = time.time()
        cur = engine.hop(cur, src, tgt)
        steps.append(cur)
        print(f"# {n:>2}/{len(chain)} {src} -> {tgt}: {len(cur)} lines in {time.time() - t1:.0f} s  e.g. {cur[0][:60]!r}", file=sys.stderr)
        src = tgt
    final = [polish(t, source) or t or o for t, o in zip(cur, originals)]   # never empty
    print(f"# done in {time.time() - t0:.0f} s", file=sys.stderr)

    if args.trace:
        with open(args.trace, "w", encoding="utf-8") as f:
            f.write("id\toriginal\t" + "\t".join(chain) + "\tpolished\n")
            for i, o in enumerate(originals):
                f.write(f"{first_id[o]}\t" + "\t".join(s[i] for s in steps) + f"\t{final[i]}\n")
        print(f"# trace: {args.trace}", file=sys.stderr)

    result = dict(zip(originals, final))             # original line -> its result
    lines = {tid: result[t] for tid, t in texts.items() if t in result}
    unchanged = sum(1 for tid, t in texts.items() if lines.get(tid) == t)
    distinct = len(set(lines.values()))
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# {folder}: every dialogue line of {archive.name} ({len(texts)} text ids with a line, {len(originals)} distinct lines) "
                f"after 20 machine translations, {datetime.date.today()}\n")
        f.write(f"# chain: {source} -> " + " -> ".join(chain) + f"  (NLLB-200 distilled 600M via CTranslate2, beam {engine.beam}; tools/translate20.py)\n")
        f.write(f"# \"<text id> <line>\": the id's own line after the chain, one per id (ids with the same original share the result); "
                f"{len(lines)} ids, {distinct} distinct results, {unchanged} ids came back unchanged; nothing dropped, no result is empty\n")
        for tid in sorted(lines):
            f.write(f"{tid} {lines[tid]}\n")
    print(f"# wrote {out}: {len(lines)} ids, {distinct} distinct results, {unchanged} unchanged", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
