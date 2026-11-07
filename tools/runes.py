"""--random-runes: the runes an enemy gives when it dies are random.

Every enemy is an NpcParam row and its runes are `getSoul` (vanilla 1.17.1: 2739 of the 7045 rows give runes, 4 to
50000; the Item and Enemy Randomizer adds scaled copies of enemies it moves, up to 138353, and leaves the vanilla rows
alone).  Rows without runes (NPCs, summons, dummies) stay without.  shuffle: the existing amounts are permuted over the
enemies, so a rat may be worth a dragon and a dragon a rat, the sum over the world unchanged; range: every enemy draws
an amount log-uniformly between --rune-min and --rune-max (default: the lowest / highest existing amount), rounded to
2 significant digits.  Report in runes.txt, enemies named after the drop table they point at (names/ItemLotParam_*.txt).
"""
from __future__ import annotations

import random
import re
from pathlib import Path

import erreg

HERE = Path(__file__).resolve().parent
BRACKET = re.compile(r"^\[(.+?)\]")


def randomize(reg: erreg.Regulation, rng: random.Random, mode: str, lo: int | None, hi: int | None) -> list[str]:
    from randomize import new_prices                   # the shuffle / log-uniform range draw of --random-prices
    N = reg.param("NpcParam", erreg.load_paramdef(HERE / "paramdef" / "NpcParam.xml"))
    enemy = erreg.load_names(HERE / "names" / "ItemLotParam_enemy.txt")
    boss = erreg.load_names(HERE / "names" / "ItemLotParam_map.txt")
    rows = [r for r in N.rows if N.get(r, "getSoul") > 0]
    old = [N.get(r, "getSoul") for r in rows]
    new = new_prices(old, rng, mode, lo, hi, "runes")
    lines = [f"# runes: mode={mode} enemies={len(rows)} (NpcParam rows with getSoul > 0; vanilla {min(old)}-{max(old)})",
             "# npc row  [enemy of its drop table]  old -> new (runes)"]
    for r, o, n in zip(rows, old, new):
        N.set(r, "getSoul", n)
        nm = enemy.get(N.get(r, "itemLotId_enemy")) or boss.get(N.get(r, "itemLotId_map")) or ""
        m = BRACKET.match(nm)
        lines.append(f"{r.id:>9}  {(m.group(0) if m else nm):<44} {o:>7} -> {n}")
    return lines
