"""--random-flask-locations: the Flask of Crimson Tears and the Flask of Cerulean Tears are found
somewhere else in the world.

Vanilla hands out both flasks at the first Site of Grace the player rests at, through the item lots
2000 (Crimson Tears x3) and 2001 (Cerulean Tears x1) of ItemLotParam_map: one lot group (shared
flag 60000) that the event script awards; the quantity is the number of charges.  The item randomizer
leaves those two rows alone.  Here each flask swaps places with the content of a random other item
location: a lot row (the flask is then picked up, dropped by a boss or handed over by an NPC where
that row's item was) or a shop slot (a merchant then sells the flask, as many as it has charges, at
the slot's price), and the first grace hands out that item instead.  Everything else about both sides
(flags, weights, lot groups, prices) stays, so the location stays one-time and the event still fires.

Candidates come from names/item_locations.txt (rows the item randomizer treats as real item
locations, see locations.py) and must be present in the input.  A lot row must award exactly one item
for certain (a single weighted slot with item id > 0 and quantity > 0, nothing left to chance, a
getItemFlagId), be the first row of its lot group (the row a map or event references; set pieces and
great runes that follow it stay) and have a vanilla content Paramdex names uniquely, so the report can
say "where the Dragonscale Blade is in vanilla".  Rows of the group that are not adjacent to it but hold
the same item (the same gift by another route, e.g. the NPC's corpse) get the flask too; a group with
a different item on another route is skipped as ambiguous (the other route would set the flag first).  A shop slot must have a limited stock (sellQuantity >= 1 with
a stock flag) and cost runes or dragon hearts.  Map fragments are never touched, on either side.
Enemy drop tables (ItemLotParam_enemy) are never used.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import erreg

HERE = Path(__file__).resolve().parent
LOCATIONS_FILE = HERE / "names" / "item_locations.txt"

FLASK_LOTS = {2000: (1000, 1025), 2001: (1050, 1075)}   # lot -> goods id range: Crimson / Cerulean Tears +0..+12
LOT_SLOT = ("lotItemId01", "lotItemCategory01", "lotItemNum01")
CATEGORY_GOODS = 1
CATEGORY_OF_SHOP_TYPE = {0: 2, 1: 3, 2: 4, 3: 1, 4: 5, 5: 6}      # ShopLineupParam.equipType -> lotItemCategory
SHOP_TYPE_OF_CATEGORY = {c: t for t, c in CATEGORY_OF_SHOP_TYPE.items()}
SHOP_COST = {0: "runes", 1: "dragon hearts"}                     # other costTypes (puppets, Bayle) are skipped
CATEGORY_NAMES = {1: "EquipParamGoods", 2: "EquipParamWeapon", 3: "EquipParamProtector",
                  4: "EquipParamAccessory", 5: "EquipParamGem"}
CATEGORY_WORD = {1: "goods", 2: "weapon", 3: "armor", 4: "talisman", 5: "ash of war", 6: "custom weapon"}
MAP_WORD = re.compile(r"\bMap\b")                                 # "Map: Limgrave, West", "Cross Map", "Ruins Map (2nd)"


def load_locations(path: Path = LOCATIONS_FILE) -> dict[str, dict[int, str]]:
    """table -> {row id: 'base' | 'dlc'}."""
    locs: dict[str, dict[int, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        table, rid, tag, *_ = line.split("\t")
        locs.setdefault(table, {})[int(rid)] = tag
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


@dataclass
class Spot:
    kind: str                       # "lot" | "shop"
    row: object
    name: str                       # vanilla content / "[merchant] item" of the slot
    alternatives: list = field(default_factory=list)   # lot rows giving the same item by another route


class Flasks:
    def __init__(self, reg: erreg.Regulation):
        self.reg = reg
        self.L = reg.param("ItemLotParam_map", erreg.load_paramdef(HERE / "paramdef" / "ItemLotParam.xml"))
        self.S = reg.param("ShopLineupParam", erreg.load_paramdef(HERE / "paramdef" / "ShopLineupParam.xml"))
        self.lot_names = erreg.load_names(HERE / "names" / "ItemLotParam_map.txt")
        self.shop_names = erreg.load_names(HERE / "names" / "ShopLineupParam.txt")
        self.locations = load_locations()
        self._names: dict[int, dict[int, str]] = {}
        self.map_goods = {i for i, n in self.names(CATEGORY_GOODS).items() if MAP_WORD.search(n)}

    def names(self, cat: int) -> dict[int, str]:
        if cat not in self._names:
            p = HERE / "names" / f"{CATEGORY_NAMES.get(cat, '')}.txt"
            self._names[cat] = erreg.load_names(p) if cat in CATEGORY_NAMES and p.is_file() else {}
        return self._names[cat]

    def item_name(self, iid: int, cat: int, num: int) -> str:
        names = self.names(cat)
        if cat == 2:                                   # weapon id = base + affinity * 100 + upgrade level
            base, level = iid - iid % 10000, iid % 100
            nm = names.get(base, f"weapon {base}") + (f" +{level}" if level else "")
        else:
            nm = names.get(iid, f"{CATEGORY_WORD.get(cat, f'category {cat}')} {iid}")
        return f"{nm} x{num}"

    # ------------------------------------------------------------ candidates
    def lot_content(self, r) -> tuple:
        return tuple(self.L.get(r, f) for f in LOT_SLOT)

    def is_map(self, iid: int, cat: int) -> bool:
        return cat == CATEGORY_GOODS and iid in self.map_goods

    def certain(self, r) -> bool:
        """The row gives exactly one item, for sure: one slot with a weight, item id > 0, quantity > 0,
           a flag (one-time); no other weighted slot (an id-0 slot with a weight is a chance of nothing)."""
        L = self.L
        if [i for i in range(1, 9) if L.get(r, f"lotItemBasePoint0{i}") > 0] != [1]:
            return False
        return L.get(r, "lotItemId01") > 0 and L.get(r, "lotItemNum01") > 0 and L.get(r, "getItemFlagId") != 0

    def lot_spots(self) -> list[Spot]:
        L = self.L
        known = self.locations.get("ItemLotParam_map", {})
        count: dict[str, int] = {}
        for nm in self.lot_names.values():
            count[nm] = count.get(nm, 0) + 1
        groups: dict[int, list] = {}
        for r in L.rows:
            groups.setdefault(L.get(r, "getItemFlagId"), []).append(r)      # rows come sorted by id
        spots = []
        for r in L.rows:
            if r.id not in known or r.id in FLASK_LOTS:
                continue
            nm = self.lot_names.get(r.id, "")
            if not nm or nm == "?" or count[nm] != 1 or MAP_WORD.search(nm) or not self.certain(r):
                continue
            content = self.lot_content(r)
            if self.is_map(content[0], content[1]):
                continue
            group = groups[L.get(r, "getItemFlagId")]
            if group[0].id != r.id:
                continue                               # a later row of a group: set piece, great rune, corpse copy
            ids = {x.id for x in group}
            alternatives, ok = [], True
            for x in group[1:]:
                if x.id - 1 in ids:
                    continue                           # given together with the row before it (set piece, great rune)
                if self.lot_content(x) == content:
                    alternatives.append(x)             # the same item by another route (NPC gift / NPC corpse)
                else:
                    ok = False                         # a different item by another route under the same flag
                    break
            if ok:
                spots.append(Spot("lot", r, nm, alternatives))
        return spots

    def shop_spots(self) -> list[Spot]:
        S = self.S
        known = self.locations.get("ShopLineupParam", {})
        spots = []
        for r in S.rows:
            nm = self.shop_names.get(r.id, "")
            if r.id not in known or not nm or MAP_WORD.search(nm):
                continue
            t, iid = S.get(r, "equipType"), S.get(r, "equipId")
            if t not in CATEGORY_OF_SHOP_TYPE or S.get(r, "costType") not in SHOP_COST or iid <= 0:
                continue
            if S.get(r, "sellQuantity") < 1 or S.get(r, "eventFlag_forStock") == 0:
                continue                               # unlimited stock, or no flag to remember the sale
            if self.is_map(iid, CATEGORY_OF_SHOP_TYPE[t]):
                continue
            spots.append(Spot("shop", r, nm))
        return spots

    # ------------------------------------------------------------ the swap
    def randomize(self, rng: random.Random) -> list[str]:
        L, S = self.L, self.S
        lots, shops = self.lot_spots(), self.shop_spots()
        pool = lots + shops
        lines = [f"# flask locations: candidates={len(pool)} ({len(lots)} pickups / rewards / NPC gifts that give one item "
                 f"for certain, {len(shops)} shop slots with a limited stock; see names/item_locations.txt)",
                 "# flask  ->  where it is now (vanilla content of that spot)  |  the first Site of Grace gives instead"]
        if len(pool) < len(FLASK_LOTS):
            lines.append("# not enough candidate rows, flasks left where they are")
            return lines
        picked: set[tuple[str, int]] = set()
        for lot, (lo, hi) in FLASK_LOTS.items():
            row = L.by_id.get(lot)
            if row is None or L.get(row, "lotItemCategory01") != CATEGORY_GOODS or not lo <= L.get(row, "lotItemId01") <= hi:
                lines.append(f"# lot {lot} does not hold the flask any more (already moved?), left alone")
                continue
            dest = rng.choice([s for s in pool if (s.kind, s.row.id) not in picked])
            picked.add((dest.kind, dest.row.id))
            flask = self.lot_content(row)
            if dest.kind == "lot":
                item = self.lot_content(dest.row)
                for x in [dest.row] + dest.alternatives:
                    for f, v in zip(LOT_SLOT, flask):
                        L.set(x, f, v)
                where = place(dest.row.id, dest.name)
                spot = (f"lot {dest.row.id}: {dest.name}" + (f" ({where})" if where else "")
                        + (f" [also rows {', '.join(str(x.id) for x in dest.alternatives)}: the same spot by another route]"
                           if dest.alternatives else ""))
            else:
                sr = dest.row
                item = (S.get(sr, "equipId"), CATEGORY_OF_SHOP_TYPE[S.get(sr, "equipType")], min(S.get(sr, "sellQuantity"), 255))
                S.set(sr, "equipId", flask[0])
                S.set(sr, "equipType", SHOP_TYPE_OF_CATEGORY[CATEGORY_GOODS])
                S.set(sr, "sellQuantity", flask[2])
                spot = (f"shop {sr.id}: {dest.name} ({S.get(sr, 'value')} {SHOP_COST[S.get(sr, 'costType')]} each, "
                        f"stock {flask[2]})")
            for f, v in zip(LOT_SLOT, item):
                L.set(row, f, v)
            lines.append(f"{self.item_name(*flask):<28} ->  {spot}  |  {self.item_name(*item)}")
        return lines
