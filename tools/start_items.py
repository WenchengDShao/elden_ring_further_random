"""--start-with-bell / --start-with-lantern: the Spirit Calling Bell and / or the Lantern are handed out together
with the two flasks at the start of the game.  Meant for Fog Gate Randomizer runs, where Limgrave (Renna hands
out the bell at the Church of Elleh) or Liurnia (the nomadic merchants sell the lantern) may stay out of reach
for a long time; it works on any regulation.bin all the same.

Why an item lot and not the starting inventory: the game does not look at the inventory to allow spirit
summoning but at event flag 60110, the `getItemFlagId` of Renna's gift (ItemLotParam_map 103900) and the stock
flag of the Twin Maiden Husks' copy (ShopLineupParam 101802).  A bell written into CharaInitParam's item slots
is in the bag but summons nothing (tested in-game 2026-10-31).  The flags of an item lot are set by the game
when it awards the lot, so the bell goes into the flask lot: `AwardItemLot(2000)` (FogMod's start event
755850200 in common.emevd; vanilla: event 18000020 of m18_00_00_00 at the first Site of Grace of the Stranded
Graveyard) awards every row of the group 2000, 2001, ... as long as the ids are consecutive, each with its own
flag (vanilla groups mix flags freely, e.g. 103900 / 103901 = 60110 / 400390).  Rows 2000 / 2001 are the two
flasks (flag 60000, swapped by --random-flask-locations); row 2010 (Roped Fire Pot) starts the next group, so
the bell and the lantern become rows 2002 and 2003 (or the next free ids of the group).  The bell's row gets
flag 60110, the lantern's row no flag (0, like the repeatable drops): the lantern is an ordinary tool.
Nothing else changes: the game then treats the bell as obtained (the Husks' copy shows as sold out, Renna's
lot is skipped if it is ever awarded) exactly as after picking it up in vanilla; the merchants' lanterns stay.
"""
from __future__ import annotations

from pathlib import Path

import erreg

HERE = Path(__file__).resolve().parent
# option -> EquipParamGoods id, name, getItemFlagId of the new lot row
ITEMS = {"bell": (8158, "Spirit Calling Bell", 60110), "lantern": (2070, "Lantern", 0)}
GROUP = 2000                  # the flask lot: AwardItemLot(2000) awards rows 2000, 2001, ... while the ids run on
GROUP_MAX = 2009              # row 2010 (Roped Fire Pot) belongs to the next lot
GOODS = 1                     # lotItemCategory of goods
SLOTS = 8                     # lotItemId01 .. lotItemId08


def give(reg: erreg.Regulation, keys: list[str]) -> list[str]:
    """Append the goods of `keys` (ITEMS) to the flask lot group of ItemLotParam_map; report lines."""
    L = reg.param("ItemLotParam_map", erreg.load_paramdef(HERE / "paramdef" / "ItemLotParam.xml"))
    group = []
    rid = GROUP
    while rid in L.by_id and rid <= GROUP_MAX:
        group.append(rid)
        rid += 1
    if not group:
        raise ValueError(f"ItemLotParam_map row {GROUP} (the flask lot) is missing, cannot add starting items")
    goods = [ITEMS[k] for k in keys]
    lines = ["# starting items: " + ", ".join(f"{n} ({g})" for g, n, _ in goods) + " x1 appended to the flask lot "
             f"(ItemLotParam_map rows {GROUP}+, awarded together with the flasks at the start: FogMod's start "
             "event / the first Site of Grace); the bell's row sets flag 60110, which enables spirit summoning"]
    for gid, name, flag in goods:
        held = [r for r in group if any(L.get(L.by_id[r], f"lotItemCategory0{i}") == GOODS
                                        and L.get(L.by_id[r], f"lotItemId0{i}") == gid for i in range(1, SLOTS + 1))]
        if held:
            lines.append(f"ItemLotParam_map {held[0]} already gives {name} ({gid}), left alone")
            continue
        new_id = group[-1] + 1
        if new_id > GROUP_MAX:
            lines.append(f"ItemLotParam_map: no free row left in the group {GROUP}-{GROUP_MAX}, {name} ({gid}) not added")
            continue
        row = L.add_row(new_id, L.by_id[group[-1]])
        for i in range(1, SLOTS + 1):
            for f, v in (("lotItemId", 0), ("lotItemCategory", 0), ("lotItemNum", 0), ("lotItemBasePoint", 0),
                         ("cumulateLotPoint", 0), ("getItemFlagId", 0), ("enableLuck", 0), ("cumulateReset", 0)):
                if f"{f}{i:02d}" in L.pd:
                    L.set(row, f"{f}{i:02d}", v)
        L.set(row, "lotItemId01", gid)
        L.set(row, "lotItemCategory01", GOODS)
        L.set(row, "lotItemNum01", 1)
        L.set(row, "lotItemBasePoint01", 1000)
        L.set(row, "getItemFlagId", flag)
        L.set(row, "cumulateNumFlagId", 0)
        L.set(row, "cumulateNumMax", 0)
        group.append(new_id)
        lines.append(f"ItemLotParam_map {new_id} = {name} ({gid}) x1, getItemFlagId {flag}")
    return lines
