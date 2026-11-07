"""--random-durations: how long the buffs of consumables and spells last is random.

A grease, a meat, a Baldachin's Blessing or a buff spell applies a SpEffectParam row whose `effectEndurance` is the
duration in seconds (-1 = until removed, 0 = instant).  Consumables: every usable item of the goods pool whose effect is
a SpEffect (EquipParamGoods refCategory 2: refId_default, and refId_1, the second hand's copy of a grease) with a timed
row; both rows of a grease get the same new duration.  Spells: every SpEffect a player spell fires directly (Magic
refCategoryN 2: Scholar's Armament, Flame Grant Me Strength, Golden Vow, the weapon buffs ...); the NPC copies of those
spells share the rows and follow.  Timed rows shorter than MIN_BUFF seconds are mechanics (a parry window, a cast
state), not buffs, and stay.  shuffle: the durations are permuted over the buffs; range: every buff draws a duration
log-uniformly between --duration-min and --duration-max seconds (default: the shortest / longest existing), rounded to 2
significant digits.  Done before the goods / spell effect shuffle, so the report names the item or spell that owns the
effect in vanilla (mapping.txt says which item fires it now).  Vanilla 1.17.1: 94 consumables (11-180 s) + 44 spells.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import erreg

HERE = Path(__file__).resolve().parent
REF_SPEFFECT = 2
MIN_BUFF = 5.0                                     # seconds: shorter timed effects are mechanics, left alone
N_REFS = 10                                        # Magic refCategory1..10 / refId1..10


@dataclass
class Unit:
    kind: str                                      # "goods" | "spell"
    id: int
    name: str
    effects: list[int]                             # SpEffectParam rows that get the new duration
    old: float


class Durations:
    def __init__(self, reg: erreg.Regulation):
        from randomize import build_pool
        self.G = reg.param("EquipParamGoods", erreg.load_paramdef(HERE / "paramdef" / "EquipParamGoods.xml"))
        self.M = reg.param("Magic", erreg.load_paramdef(HERE / "paramdef" / "Magic.xml"))
        self.E = reg.param("SpEffectParam", erreg.load_paramdef(HERE / "paramdef" / "SpEffect.xml"))
        self.goods_names = erreg.load_names(HERE / "names" / "EquipParamGoods.txt")
        self.spell_names = erreg.load_names(HERE / "names" / "Magic.txt")
        self.pool = build_pool(self.G, self.goods_names)
        self.units = self._units()

    def duration(self, eid: int) -> float | None:
        r = self.E.by_id.get(eid)
        return None if r is None else self.E.get(r, "effectEndurance")

    def _units(self) -> list[Unit]:
        units: list[Unit] = []
        claimed: set[int] = set()
        for r in self.pool:
            if self.G.get(r, "refCategory") != REF_SPEFFECT:
                continue
            effects = []
            for f in ("refId_default", "refId_1"):
                eid = self.G.get(r, f)
                d = self.duration(eid) if eid > 0 else None
                if d is not None and d >= MIN_BUFF and eid not in claimed:
                    effects.append(eid)
            if effects:
                claimed.update(effects)
                units.append(Unit("goods", r.id, self.goods_names[r.id], effects, max(self.duration(e) for e in effects)))
        for r in self.M.rows:
            nm = self.spell_names.get(r.id, "")
            if not nm or nm.startswith("[NPC"):
                continue
            for i in range(1, N_REFS + 1):
                eid = self.M.get(r, f"refId{i}")
                if self.M.get(r, f"refCategory{i}") != REF_SPEFFECT or eid <= 0 or eid in claimed:
                    continue
                d = self.duration(eid)
                if d is not None and d >= MIN_BUFF:
                    claimed.add(eid)
                    units.append(Unit("spell", r.id, nm, [eid], d))
        return units

    def randomize(self, rng: random.Random, mode: str, lo: int | None, hi: int | None) -> list[str]:
        from randomize import new_prices
        old = [u.old for u in self.units]
        goods = sum(1 for u in self.units if u.kind == "goods")
        lines = [f"# buff durations: mode={mode} buffs={len(self.units)} ({goods} consumables + {len(self.units) - goods} spell effects; "
                 f"SpEffectParam.effectEndurance, timed effects of {MIN_BUFF:g} s and longer; vanilla {min(old):g}-{max(old):g} s)",
                 "# owner  old -> new (seconds)   [SpEffect rows]"]
        if len(self.units) < 2:
            lines.append("# fewer than two buffs found, nothing changed")
            return lines
        new = new_prices([int(round(o)) for o in old], rng, mode, lo, hi, "duration")
        for u, n in zip(self.units, new):
            for eid in u.effects:
                self.E.set(self.E.by_id[eid], "effectEndurance", float(n))
            lines.append(f"{u.id:>8}  {u.name:<44} {u.old:>5g} -> {n:<4}   [{', '.join(str(e) for e in u.effects)}]")
        return lines
