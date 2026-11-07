"""--random-enemy-drops: every enemy drops something, and what it drops is random.

ItemLotParam_enemy holds the enemy drop tables.  An enemy (NpcParam.itemLotId_enemy) points at one row and the
game rolls that row and every row after it with a consecutive id (300000000-300000005: the Castle Exile's
crossbow, hood, armor, gauntlets, greaves and feather are six independent rolls).  A row is up to eight weighted
slots; in vanilla nearly every row is "nothing" (lotItemId 0, weight 950-990) against one item (weight 10-50).
The Item and Enemy Randomizer swaps the two slots around and clears most one-time flags, but keeps the shape.

For every lot an NpcParam row points at (1361 in vanilla 1.17.1; rows nothing points at are cut content and
stay as they are):
  - its first row drops for certain: the "nothing" slots lose their weight, and a row without an item slot
    (the 0 % rows of the Crucible Knights and others) gets one;
  - every item slot of every row of the lot gets a random item; the rows after the first keep their chance,
    so an enemy with several rolls still has its rare extra drops, only random ones;
  - a row with a getItemFlagId is a one-time drop (the Alabaster Lord's sword, the Banished Knight's Dragon
    Communion Seal, the Silver Tear Orbs' Larval Tears; the item randomizer's own placements) and is left
    alone, item and chance, as is a row holding a key item (belt and braces: the item randomizer may put a key
    item into an enemy drop).  When such a row is the lot's first, a row with a guaranteed random item is
    appended to the lot (next id), so the enemy still drops something once its one-time drop is gone.

The pool is every item the input hands out somewhere: the pickups, rewards and gifts of names/item_locations.txt,
the shops listed there and the enemy drops themselves -- weapons (upgrade level dropped), armor, talismans, Ashes
of War and goods, except key items, Great Runes, info items (letters), the Flask of Wondrous Physick and the
Flasks of Crimson / Cerulean Tears.  Each distinct item is in the pool once, so a weapon is as likely as a Rowa
Fruit; the quantity is one the game gives that item somewhere (a stack of 5 arrows, 1 sword).  --mode has no
effect here.  Items of the Land of Shadow are in the pool whenever the input hands them out.
"""
from __future__ import annotations

import random
from pathlib import Path

import erreg
from flasks import CATEGORY_NAMES, CATEGORY_OF_SHOP_TYPE, CATEGORY_WORD, load_locations

HERE = Path(__file__).resolve().parent
SLOTS = 8
CATEGORY_GOODS, CATEGORY_WEAPON = 1, 2
POOL_CATEGORIES = (1, 2, 3, 4, 5)                     # goods, weapon, armor, talisman, ash of war
# EquipParamGoods.goodsType values that never drop: 1 key item, 9 Flask of Wondrous Physick, 12 info item
# (letters, notes), 13 (unused), 15 Great Rune.  Flasks of Crimson / Cerulean Tears are goodsType 0 with a suppleType.
KEEP_GOODS_TYPES = {1, 9, 12, 13, 15}
CERTAIN = 1000                                        # weight of the only slot of a guaranteed drop
SLOT_FIELDS = ("lotItemId", "lotItemCategory", "lotItemBasePoint", "lotItemNum", "enableLuck",
               "cumulateLotPoint", "getItemFlagId", "cumulateReset")


class EnemyDrops:
    def __init__(self, reg: erreg.Regulation):
        self.reg = reg
        pd = erreg.load_paramdef(HERE / "paramdef" / "ItemLotParam.xml")
        self.L = reg.param("ItemLotParam_enemy", pd)
        self.M = reg.param("ItemLotParam_map", pd)
        self.S = reg.param("ShopLineupParam", erreg.load_paramdef(HERE / "paramdef" / "ShopLineupParam.xml"))
        self.N = reg.param("NpcParam", erreg.load_paramdef(HERE / "paramdef" / "NpcParam.xml"))
        self.G = reg.param("EquipParamGoods", erreg.load_paramdef(HERE / "paramdef" / "EquipParamGoods.xml"))
        self.lot_names = erreg.load_names(HERE / "names" / "ItemLotParam_enemy.txt")
        self._names: dict[int, dict[int, str]] = {}

    # ------------------------------------------------------------ names
    def names(self, cat: int) -> dict[int, str]:
        if cat not in self._names:
            p = HERE / "names" / f"{CATEGORY_NAMES.get(cat, '')}.txt"
            self._names[cat] = erreg.load_names(p) if cat in CATEGORY_NAMES and p.is_file() else {}
        return self._names[cat]

    def item_name(self, iid: int, cat: int, num: int = 1) -> str:
        names = self.names(cat)
        if cat == CATEGORY_WEAPON:                     # weapon id = base + affinity * 100 + upgrade level
            base, level = iid - iid % 10000, iid % 100
            nm = names.get(base, f"weapon {base}") + (f" +{level}" if level else "")
        else:
            nm = names.get(iid, f"{CATEGORY_WORD.get(cat, f'category {cat}')} {iid}")
        return f"{nm} x{num}"

    # ------------------------------------------------------------ the lots
    def lots(self) -> list[int]:
        """The first rows of the enemy drop lots: every ItemLotParam_enemy row an NpcParam row points at."""
        L = self.L
        refs = {self.N.get(r, "itemLotId_enemy") for r in self.N.rows}
        return sorted(k for k in refs if k > 0 and k in L.by_id)

    def run(self, first: int) -> list:
        """The rows the game rolls for a lot: the first row and every row after it with a consecutive id."""
        rows, rid = [], first
        while rid in self.L.by_id:
            rows.append(self.L.by_id[rid])
            rid += 1
        return rows

    def slots(self, r) -> list[tuple[int, int, int, int]]:
        """(item id, category, weight, quantity) of every slot of a row."""
        L = self.L
        return [(L.get(r, f"lotItemId0{i}"), L.get(r, f"lotItemCategory0{i}"), L.get(r, f"lotItemBasePoint0{i}"),
                 L.get(r, f"lotItemNum0{i}")) for i in range(1, SLOTS + 1)]

    def is_key(self, iid: int, cat: int) -> bool:
        if cat != CATEGORY_GOODS:
            return False
        g = self.G.by_id.get(iid)
        return g is None or self.G.get(g, "goodsType") in KEEP_GOODS_TYPES or self.G.get(g, "suppleType") != 0

    def protected(self, r) -> str:
        """Why a row is left alone: a one-time drop (flag) or a key item in a weighted slot; '' otherwise."""
        if self.L.get(r, "getItemFlagId"):
            return "one-time drop"
        if any(w > 0 and iid > 0 and self.is_key(iid, cat) for iid, cat, w, _ in self.slots(r)):
            return "key item"
        return ""

    def describe(self, r) -> str:
        """'Crab Eggs x1 3% / Strip of White Flesh x1 3%', 'nothing' for an empty row."""
        slots = self.slots(r)
        total = sum(w for _, _, w, _ in slots)
        parts = [f"{self.item_name(iid, cat, num)} {100 * w / total:g}%" for iid, cat, w, num in slots if w > 0 and iid > 0]
        return " / ".join(parts) if parts else "nothing"

    # ------------------------------------------------------------ the pool
    def build_pool(self, lot_rows: list) -> list[tuple[int, int, tuple[int, ...]]]:
        """(category, item id, quantities seen) of every item handed out by the real pickups / rewards / gifts and
           shops of names/item_locations.txt and by the enemy drop rows given; one entry per item, in table order."""
        seen: dict[tuple[int, int], set[int]] = {}

        def add(cat: int, iid: int, num: int) -> None:
            if iid <= 0 or cat not in POOL_CATEGORIES or self.is_key(iid, cat):
                return
            if cat == CATEGORY_WEAPON:
                iid -= iid % 100                       # the drop is +0; the affinity (if any) stays
            seen.setdefault((cat, iid), set()).add(max(1, min(num, 255)))

        locations = load_locations()
        for P, rows in ((self.M, [self.M.by_id[k] for k in locations.get("ItemLotParam_map", {}) if k in self.M.by_id]),
                        (self.L, lot_rows)):
            for r in rows:
                for i in range(1, SLOTS + 1):
                    if P.get(r, f"lotItemBasePoint0{i}") > 0:
                        add(P.get(r, f"lotItemCategory0{i}"), P.get(r, f"lotItemId0{i}"), P.get(r, f"lotItemNum0{i}"))
        for k in locations.get("ShopLineupParam", {}):
            r = self.S.by_id.get(k)
            if r is not None and self.S.get(r, "equipType") in CATEGORY_OF_SHOP_TYPE:
                add(CATEGORY_OF_SHOP_TYPE[self.S.get(r, "equipType")], self.S.get(r, "equipId"), 1)
        return [(cat, iid, tuple(sorted(nums))) for (cat, iid), nums in seen.items()]

    # ------------------------------------------------------------ the change
    def room_after(self, run: list) -> int:
        """How many rows can be appended to a lot: the free ids after its last row, less one that must stay free so
           the lot does not run on into the next one (the game rolls every row with a consecutive id)."""
        n, rid = 0, run[-1].id + 1
        while rid not in self.L.by_id and n < 64:
            n, rid = n + 1, rid + 1
        return max(0, n - 1)

    def randomize(self, rng: random.Random, rolls: int | None = None, chance: int = 50) -> list[str]:
        """rolls=None: the first row of every lot drops for certain, the rows after it keep their chance, every row's
           items are random.  rolls=N: every lot gets exactly N rows, each one random item at `chance` percent (rows
           appended or emptied as needed), so a kill drops 0 to N items."""
        L = self.L
        lots = self.lots()
        rows: dict[int, object] = {}
        for k in lots:
            for r in self.run(k):
                rows.setdefault(r.id, r)
        pool = self.build_pool(list(rows.values()))
        by_cat = {c: sum(1 for cat, _, _ in pool if cat == c) for c in POOL_CATEGORIES}
        mode = (f"every lot gets {rolls} rolls at {chance}% each: 0 to {rolls} items per kill, {rolls * chance / 100:g} on average "
                "(one-time drops and rows with a key item stay and do not count)" if rolls else
                "the first row of every lot always drops, the rows after it keep their chance, one-time drops (rows with a "
                "flag) and rows with a key item stay")
        lines = [f"# enemy drops: lots={len(lots)} (ItemLotParam_enemy rows NpcParam.itemLotId_enemy points at, with the "
                 f"consecutive rows after them: {len(rows)} rows), pool={len(pool)} items ({by_cat[1]} goods, {by_cat[2]} weapons, "
                 f"{by_cat[3]} armor pieces, {by_cat[4]} talismans, {by_cat[5]} ashes of war: every item the input hands out "
                 f"somewhere, each once); {mode}",
                 "# lot row  [enemy] vanilla content (Paramdex name)  :  before  ->  after   (chance per item; 'kept' = left alone, "
                 "'+ row' = row appended to the lot)"]
        if len(pool) < 2:
            lines.append("# pool too small, nothing changed")
            return lines
        done: set[int] = set()
        n_empty: set[int] = set()        # rows that are no roll of their lot: emptied or left alone
        n = {"rows": 0, "certain": 0, "kept": 0, "added": 0, "emptied": 0, "short": 0}
        old: dict[int, str] = {}

        def draw() -> tuple[int, int, int]:
            cat, iid, nums = rng.choice(pool)
            return iid, cat, rng.choice(nums)

        def set_slot(r, i: int, iid: int, cat: int, weight: int, num: int) -> None:
            for f, v in (("lotItemId", iid), ("lotItemCategory", cat), ("lotItemBasePoint", weight), ("lotItemNum", num),
                         ("enableLuck", 0), ("cumulateLotPoint", 0), ("getItemFlagId", 0), ("cumulateReset", 0)):
                L.set(r, f"{f}{i:02d}", v)

        def clear(r) -> None:
            for i in range(1, SLOTS + 1):
                set_slot(r, i, 0, 0, 0, 0)

        def randomize_items(r) -> None:
            for i, (iid, cat, w, _) in enumerate(self.slots(r), 1):
                if w > 0 and iid > 0:
                    iid, cat, num = draw()
                    L.set(r, f"lotItemId{i:02d}", iid)
                    L.set(r, f"lotItemCategory{i:02d}", cat)
                    L.set(r, f"lotItemNum{i:02d}", num)

        def make_certain(r) -> None:
            slots = self.slots(r)
            for i, (iid, _, w, _) in enumerate(slots, 1):
                if w > 0 and iid <= 0:
                    L.set(r, f"lotItemBasePoint{i:02d}", 0)
            if not any(w > 0 and iid > 0 for iid, _, w, _ in slots):
                clear(r)
                iid, cat, num = draw()
                set_slot(r, 1, iid, cat, CERTAIN, num)

        def set_roll(r) -> None:
            """One random item at `chance` percent, nothing otherwise."""
            clear(r)
            iid, cat, num = draw()
            set_slot(r, 1, iid, cat, chance * 10, num)
            if chance < 100:
                set_slot(r, 2, 0, 0, CERTAIN - chance * 10, 0)

        def empty(r) -> None:
            clear(r)
            set_slot(r, 1, 0, 0, CERTAIN, 0)

        def append_row(run: list):
            """A new row after the lot's last one (None when the next id is taken or the lot would run on into the
               next lot), copied from the last row and emptied."""
            if self.room_after(run) < 1:
                return None
            row = L.add_row(run[-1].id + 1, run[-1])
            clear(row)
            L.set(row, "getItemFlagId", 0)
            L.set(row, "cumulateNumFlagId", 0)
            L.set(row, "cumulateNumMax", 0)
            run.append(row)
            return row

        def name(r) -> str:
            return self.lot_names.get(r.id) or "?"

        for k in lots:
            run = self.run(k)
            for r in run:
                if r.id not in old:
                    old[r.id] = self.describe(r)
            if rolls:
                active = [r for r in run if r.id in done and r.id not in n_empty]
                need = rolls - len(active)
                for r in run:
                    if r.id in done:
                        continue
                    why = self.protected(r)
                    if why:
                        done.add(r.id)
                        n_empty.add(r.id)              # not a roll of this lot either
                        n["kept"] += 1
                        lines.append(f"{r.id:>10}  {name(r)}  :  {old[r.id]}  kept ({why})")
                        continue
                    done.add(r.id)
                    if need > 0:
                        set_roll(r)
                        n["rows"] += 1
                        need -= 1
                        lines.append(f"{r.id:>10}  {name(r)}  :  {old[r.id]}  ->  {self.describe(r)}")
                    else:
                        empty(r)
                        n_empty.add(r.id)
                        n["emptied"] += 1
                        lines.append(f"{r.id:>10}  {name(r)}  :  {old[r.id]}  ->  nothing (beyond the {rolls} rolls)")
                while need > 0:
                    row = append_row(run)
                    if row is None:
                        n["short"] += 1
                        lines.append(f"{'':>10}  lot {k}: only {rolls - need} of {rolls} rolls, no free id before the next lot")
                        break
                    set_roll(row)
                    done.add(row.id)
                    n["added"] += 1
                    need -= 1
                    lines.append(f"{row.id:>10}  + row for lot {k}  :  nothing  ->  {self.describe(row)}")
                continue
            for j, r in enumerate(list(run)):          # append_row extends run; the new row needs no pass of its own
                why = self.protected(r)
                if why:
                    if r.id not in done:
                        done.add(r.id)
                        n["kept"] += 1
                        lines.append(f"{r.id:>10}  {name(r)}  :  {old[r.id]}  kept ({why})")
                    if j == 0:
                        row = append_row(run)
                        if row is None:
                            n["short"] += 1
                            lines.append(f"{'':>10}  lot {k}: no free id before the next lot, no guaranteed row added")
                        else:
                            iid, cat, num = draw()
                            set_slot(row, 1, iid, cat, CERTAIN, num)
                            done.add(row.id)
                            n["added"] += 1
                            lines.append(f"{row.id:>10}  + row for lot {k}  :  nothing  ->  {self.describe(row)}")
                    continue
                if r.id not in done:
                    done.add(r.id)
                    n["rows"] += 1
                    randomize_items(r)
                if j == 0:
                    make_certain(r)
                    n["certain"] += 1
                lines.append(f"{r.id:>10}  {name(r)}  :  {old[r.id]}  ->  {self.describe(r)}")
        summary = (f"# rows set to a roll={n['rows']}, rows emptied={n['emptied']}, rows appended={n['added']}, rows left alone={n['kept']}"
                   + (f", lots short of rolls (no free id)={n['short']}" if n["short"] else "") if rolls else
                   f"# rows randomized={n['rows']} (guaranteed first rows={n['certain']}), rows left alone={n['kept']}, "
                   f"guaranteed rows appended={n['added']}" + (f", lots without one (no free id)={n['short']}" if n["short"] else ""))
        lines.insert(2, summary)
        return lines
