"""--random-flask-locations: the Flask of Crimson Tears and the Flask of Cerulean Tears are found
somewhere else in the world.

Vanilla hands out both flasks at the first Site of Grace the player rests at, through the item lots
2000 (Crimson Tears x3) and 2001 (Cerulean Tears x1) of ItemLotParam_map: one lot group (shared
flag 60000) that the event script awards.  The item randomizer leaves those two rows alone.  Here
each flask swaps places with the content of a random other lot row: the flask is then found where
that row's item was, and the first grace hands out that item instead.  Everything else about both
rows (flags, weights, group structure) stays, so the pickup stays one-time and the event still fires.

Candidate rows (names/ItemLotParam_map.locations.txt, see lotdiff.py): rows the item randomizer
treats as real item locations, that are present in the input, award exactly one item for certain
(a single weighted slot with item id > 0 and quantity > 0, nothing left to chance, a getItemFlagId),
start their lot group (the row a map or event references) and whose vanilla content Paramdex names
uniquely, so the report can say "where the Dragonscale Blade is in vanilla".  Enemy drop tables
(ItemLotParam_enemy) are never used.  Scope base leaves the Land of Shadow out; all takes it in.
"""
from __future__ import annotations

import random
from pathlib import Path

import erreg

HERE = Path(__file__).resolve().parent
LOCATIONS_FILE = HERE / "names" / "ItemLotParam_map.locations.txt"
SCOPES = ("base", "all")

# lot id -> (goods id range of the flask that vanilla puts there)
FLASK_LOTS = {2000: (1000, 1025), 2001: (1050, 1075)}       # Crimson Tears +0..+12, Cerulean Tears +0..+12
CATEGORY_NAMES = {1: "EquipParamGoods", 2: "EquipParamWeapon", 3: "EquipParamProtector",
                  4: "EquipParamAccessory", 5: "EquipParamGem"}
CATEGORY_WORD = {1: "goods", 2: "weapon", 3: "armor", 4: "talisman", 5: "ash of war"}


def load_locations(path: Path = LOCATIONS_FILE) -> dict[int, str]:
    """lot id -> 'base' | 'dlc'."""
    locs: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        rid, tag, *_ = line.split("\t")
        locs[int(rid)] = tag
    return locs


def place(rid: int, name: str) -> str:
    """Where a lot row is, as far as the id says: map tile of the overworld, map area of a dungeon."""
    if rid >= 1_000_000_000:
        m = rid // 1_000_000_000                       # 1 = m60 (Lands Between), 2 = m61 (Land of Shadow)
        return f"m6{m - 1}_{rid // 1_000_000 % 100:02d}_{rid // 10_000 % 100:02d}"
    if rid >= 100_000_000:                             # troll carriage chests: 9 + overworld id
        return f"m60_{rid // 1_000_000 % 100:02d}_{rid // 10_000 % 100:02d}"
    if rid >= 10_000_000:
        return "" if name.startswith("[") else f"m{rid // 1_000_000}_{rid // 10_000 % 100:02d}"
    return "" if name.startswith("[") else "event reward"


class Flasks:
    def __init__(self, reg: erreg.Regulation):
        self.reg = reg
        self.L = reg.param("ItemLotParam_map", erreg.load_paramdef(HERE / "paramdef" / "ItemLotParam.xml"))
        self.lot_names = erreg.load_names(HERE / "names" / "ItemLotParam_map.txt")
        self.locations = load_locations()
        self._names: dict[int, dict[int, str]] = {}

    def item_name(self, cat: int, iid: int, num: int) -> str:
        if cat not in CATEGORY_NAMES:
            return f"category {cat} item {iid} x{num}"
        if cat not in self._names:
            p = HERE / "names" / f"{CATEGORY_NAMES[cat]}.txt"
            self._names[cat] = erreg.load_names(p) if p.is_file() else {}
        names = self._names[cat]
        if cat == 2:                                   # weapon id = base + affinity * 100 + upgrade level
            base, level = iid - iid % 10000, iid % 100
            nm = names.get(base, f"weapon {base}") + (f" +{level}" if level else "")
        else:
            nm = names.get(iid, f"{CATEGORY_WORD[cat]} {iid}")
        return f"{nm} x{num}"

    def certain(self, r) -> bool:
        """The row gives exactly one item, for sure: one slot with a weight, item id > 0, quantity > 0,
           no other weighted slot (an id-0 slot with a weight is a chance of getting nothing)."""
        L = self.L
        weighted = [i for i in range(1, 9) if L.get(r, f"lotItemBasePoint0{i}") > 0]
        if weighted != [1]:
            return False
        return L.get(r, "lotItemId01") > 0 and L.get(r, "lotItemNum01") > 0 and L.get(r, "getItemFlagId") != 0

    def candidates(self, scope: str) -> list:
        L = self.L
        count: dict[str, int] = {}
        for nm in self.lot_names.values():
            count[nm] = count.get(nm, 0) + 1
        out = []
        for r in L.rows:
            tag = self.locations.get(r.id)
            if tag is None or (scope == "base" and tag == "dlc") or r.id in FLASK_LOTS:
                continue
            nm = self.lot_names.get(r.id, "")
            if not nm or nm == "?" or count[nm] != 1 or not self.certain(r):
                continue
            prev = L.by_id.get(r.id - 1)               # second row of a group (armor set, boss drop + great rune)
            if prev is not None and L.get(prev, "getItemFlagId") == L.get(r, "getItemFlagId"):
                continue
            out.append(r)
        return out

    def randomize(self, rng: random.Random, scope: str) -> list[str]:
        L, g, s = self.L, self.L.get, self.L.set
        pool = self.candidates(scope)
        lines = [f"# flask locations: scope={scope} candidates={len(pool)} (ItemLotParam_map rows that are real item "
                 "locations, give one item for certain and whose vanilla content has a unique name)",
                 "# flask  ->  where it is now (lot id: vanilla content of that spot)  |  the first Site of Grace gives instead"]
        if len(pool) < len(FLASK_LOTS):
            lines.append("# not enough candidate rows, flasks left where they are")
            return lines
        picked: set[int] = set()
        for lot, (lo, hi) in FLASK_LOTS.items():
            row = L.by_id.get(lot)
            if row is None or g(row, "lotItemCategory01") != 1 or not lo <= g(row, "lotItemId01") <= hi:
                lines.append(f"# lot {lot} does not hold the flask any more (already moved?), left alone")
                continue
            dest = rng.choice([r for r in pool if r.id not in picked])
            picked.add(dest.id)
            flask = tuple(g(row, f) for f in ("lotItemId01", "lotItemCategory01", "lotItemNum01"))
            item = tuple(g(dest, f) for f in ("lotItemId01", "lotItemCategory01", "lotItemNum01"))
            for f, v in zip(("lotItemId01", "lotItemCategory01", "lotItemNum01"), item):
                s(row, f, v)
            for f, v in zip(("lotItemId01", "lotItemCategory01", "lotItemNum01"), flask):
                s(dest, f, v)
            nm = self.lot_names[dest.id]
            where = place(dest.id, nm)
            lines.append(f"{self.item_name(flask[1], flask[0], flask[2]):<28} ->  lot {dest.id}: {nm}"
                         + (f" ({where})" if where else "") + f"  |  {self.item_name(item[1], item[0], item[2])}")
        return lines
