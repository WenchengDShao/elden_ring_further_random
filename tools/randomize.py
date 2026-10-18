#!/usr/bin/env python3
"""Elden Ring regulation.bin randomizer.

Goods:
  (always)              each consumable item gets the use-effect of another consumable
  --random-prices       rune prices of goods in shops (ShopLineupParam.value) and the sell prices of goods
                        (EquipParamGoods.sellValue); --no-sell-prices keeps the sell prices
  --sell-equipment      with --random-prices: sell prices of weapons, armor and Ashes of War too
  --random-flask-locations
                        the Flask of Crimson Tears and the Flask of Cerulean Tears are found somewhere
                        else: a random one-time pickup, boss reward, NPC gift or shop slot (never a
                        chance drop, never a map fragment, no Land of Shadow NPC); the first Site of
                        Grace gives what was there.  Needs names/item_locations.txt (tools/locations.py)
  --flask-at lot:ID[,lot:ID|shop:ID]
                        choose the spots yourself (Crimson first, Cerulean second), e.g.
                        --flask-at shop:100510,lot:1042360050; implies --random-flask-locations
Weapons:
  --somber-infusable    somber / unique weapons get all 12 affinities and can mount Ashes of War
  --random-movesets     every melee weapon and shield gets the moveset of a random other weapon/shield
  --moveset-mode        affinity (default: a moveset per affinity row, all ashes unlocked) | bound | weapon
  --moveset-variety N   bound mode: categories per affinity cluster (default 3)
  --keep-standard-moveset
                        affinity mode: leave every weapon's Standard row as it is
  --shield-movesets     shields (default: shields swap only among shield movesets) | none | all
  --bow-movesets        bows (default: bows/crossbows/ballistas swap only among themselves) | none
  --weptype-follows     affinity/bound: each randomized row also takes the donor's wepType, so the
                        smithing table lists exactly the ashes animated for it (no ash unlock);
                        untested against save validation, see README
  --random-default-ash  random default skill per (weapon, affinity) + random affinity for
                        weapons given by item lots, shops and starting classes
  --random-stats        random attack / critical / poise & stamina damage / guard / requirements /
                        scaling / status build-ups per (weapon, affinity) row, incl. bows,
                        crossbows, staves and seals
  --stat-groups LIST    restrict --random-stats to some of attack,guard,requirements,scaling,effects,
                        stamina,spells
  --stamina-rate LO,HI  range of the random staminaConsumptionRate (attack stamina cost multiplier)
                        per row, group "stamina" (default 0.3,1.7)
  --weapons             shortcut for the four weapon options
Spells (Magic.param):
  (always)              each sorcery / incantation gets the effect of another spell (one pool for both);
                        --split-anim also splits cast animation and effect; --random-stats (group
                        "spells") rerolls FP cost (tiers 0-10 / 11-20 / 21-40 at 50 / 30 / 20 %),
                        stamina cost (0-20 / 21-40 / 41-60), requirements (<= 60) and sets the memory
                        slots of every spell to 1
  --no-spells           leave Magic.param alone

Usage:
    python randomize.py [--input regulation.bin] [--output randomized/regulation.bin] [--seed N]
                        [--mode shuffle|random] [--include-flasks] [--include-remembrances] [--split-anim [same|any]]
                        [--no-spells] [--dry-run]
                        [--random-prices] [--price-mode shuffle|range] [--price-min N] [--price-max N]
                        [--no-sell-prices] [--sell-min N] [--sell-max N] [--sell-equipment]
                        [--random-flask-locations] [--flask-at lot:ID,shop:ID]
                        [--somber-infusable] [--random-movesets] [--random-default-ash]
                        [--random-stats] [--stat-groups attack,guard,...] [--stamina-rate 0.3,1.7] [--weapons]
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import erreg  # noqa: E402
import flasks  # noqa: E402
import oodle  # noqa: E402
import spells  # noqa: E402
import weapons  # noqa: E402

HERE = Path(__file__).resolve().parent

# Fields that travel together as "the effect" of a consumable item.
EFFECT_FIELDS = [
    "refCategory", "refId_default", "refId_1", "spEffectCategory", "refVirtualWepId",
    "behaviorId", "sfxVariationId",
    "goodsUseAnim", "castSfxId", "fireSfxId", "effectSfxId", "isDisableHand", "opmeMenuType",
    "isEnableFastUseItem", "canMultiUse", "isApplySpecialEffect", "isShieldEnchant",
    "consumeMP", "consumeHP", "consumeHeroPoint", "overDexterity",
    "useLimitCategory", "useLimitSpEffectType", "useEnableSpEffectType", "useLimitSummonBuddy",
    "enable_live", "enable_gray", "enable_white", "enable_black", "enable_multi",
    "disable_offline", "disableUseAtColiseum", "disableUseAtOutOfColiseum",
    "isUseMultiPlayPreparation", "isUseMultiPenaltyOnly", "isWarpProhibited",
    "enableRiding", "disableRiding", "isSummonHorse", "isUseNoAttackRegion",
    "isBonfireWarpItem", "enable_Ladder", "enable_ActiveBigRune",
    "useLevel", *[f"useLevel_vowType{i}" for i in range(16)],
    "aiUseJudgeId", "yesNoDialogMessageId", "replaceItemId", "replaceCategory",
    "appearanceReplaceItemId",
]

# Subset of EFFECT_FIELDS that is the use *animation* (motion, hand-held / release SFX, fast cancel).
# --split-anim takes these from a second donor: `same` = one whose vanilla refCategory equals the
# effect donor's (thrown items release a bullet, applied / eaten items apply a SpEffect; the TAE events
# differ), `any` = any pool item (cross-category triggering untested in-game).
ANIM_FIELDS = ["goodsUseAnim", "castSfxId", "fireSfxId", "sfxVariationId", "isEnableFastUseItem"]

GOODS_TYPE_NORMAL, GOODS_TYPE_KEY, GOODS_TYPE_REMEMBRANCE = 0, 1, 3
MENU_NONE, MENU_YES_NO = 0, 1          # opmeMenuType: 1 is only a yes/no confirmation, the rest open real menus
REF_BULLET, REF_SPEFFECT = 1, 2
SHOP_EQUIP_TYPE_GOODS = 3
SHOP_COST_RUNES = 0


def build_pool(P: erreg.Param, names: dict[int, str], include_flasks: bool = False,
               include_remembrances: bool = False):
    """Every item the player can use from the inventory: consumables (Golden / Shadow Realm Runes
       included), reusable tools (shackles, bairns, Miquella's Great Rune...), usable key items;
       flasks and remembrances only on request."""
    types = {GOODS_TYPE_NORMAL, GOODS_TYPE_KEY} | ({GOODS_TYPE_REMEMBRANCE} if include_remembrances else set())
    pool = []
    for r in P.rows:
        name = names.get(r.id)
        if not name or name == "?":
            continue                                   # unnamed / cut rows
        if P.get(r, "goodsType") not in types:
            continue                                   # materials, spells, spirit ashes, crystal tears...
        if P.get(r, "refCategory") not in (REF_BULLET, REF_SPEFFECT) or P.get(r, "refId_default") == -1:
            continue                                   # no usable effect
        if P.get(r, "opmeMenuType") not in (MENU_NONE, MENU_YES_NO):
            continue                                   # opens a real menu (fingers, effigies, whistle)
        if P.get(r, "disable_offline"):
            continue                                   # multiplayer-only (fingers, phantom items)
        if P.get(r, "isSummonHorse"):
            continue                                   # Spectral Steed Whistle (both states): Torrent stays as is
        if P.get(r, "iconId") == 0 or P.get(r, "sortId") in (0, 999999):
            continue                                   # unused / placeholder rows
        if not include_flasks and P.get(r, "suppleType") != 0:
            continue                                   # Flask of Crimson/Cerulean Tears
        pool.append(r)
    return pool


def anim_sources(P: erreg.Param, pool: list, src: list[int], mode: str, rng: random.Random,
                 any_category: bool = False) -> list[int]:
    """Per item, the index of the pool item whose use animation it gets: drawn among the items whose
       vanilla refCategory equals that of the item's effect donor src[i], or among the whole pool with
       any_category.  shuffle: every animation of a category is used once (a permutation of that
       category's items); random: free draw."""
    cat = [0 if any_category else P.get(r, "refCategory") for r in pool]
    by_cat: dict[int, list[int]] = {}
    for j, c in enumerate(cat):
        by_cat.setdefault(c, []).append(j)
    anim = [0] * len(pool)
    if mode == "shuffle":
        receivers: dict[int, list[int]] = {}
        for i in range(len(pool)):
            receivers.setdefault(cat[src[i]], []).append(i)
        for c, idx in receivers.items():
            donors = by_cat[c][:]
            while len(donors) < len(idx):            # only in random mode; shuffle keeps the multiset
                donors += by_cat[c]
            rng.shuffle(donors)
            for i, j in zip(idx, donors):
                anim[i] = j
    else:
        for i in range(len(pool)):
            anim[i] = rng.choice(by_cat[cat[src[i]]])
    return anim


def derangement(n: int, rng: random.Random) -> list[int]:
    """Permutation with no fixed point (every item gets a *different* item's effect)."""
    while True:
        perm = list(range(n))
        rng.shuffle(perm)
        if all(i != p for i, p in enumerate(perm)):
            return perm


def round_price(v: float) -> int:
    """Round to 2 significant digits so prices look like shop prices (1234 -> 1200)."""
    v = max(1, int(round(v)))
    digits = int(math.log10(v))
    step = 10 ** max(0, digits - 1)
    return max(1, int(round(v / step)) * step)


def new_prices(old: list[int], rng: random.Random, mode: str, lo: int | None, hi: int | None,
               what: str) -> list[int]:
    """shuffle: a permutation of the existing prices (an entry may land on its own price again);
    range: log-uniform draws between lo and hi (default: the lowest / highest existing price),
    rounded to 2 significant digits."""
    if mode == "shuffle":
        new = old[:]
        rng.shuffle(new)
        return new
    lo = lo if lo is not None else min(old)
    hi = hi if hi is not None else max(old)
    if lo < 1 or hi < lo:
        raise SystemExit(f"bad {what} range {lo}..{hi}")
    return [round_price(math.exp(rng.uniform(math.log(lo), math.log(hi)))) for _ in old]


EQUIPMENT_SELL = (("EquipParamWeapon", "weapon"), ("EquipParamProtector", "armor"), ("EquipParamGem", "ash of war"))


def randomize_equipment_sell(reg: erreg.Regulation, rng: random.Random, mode: str,
                             smin: int | None, smax: int | None) -> list[str]:
    """--sell-equipment: sellValue of weapons, armor pieces and Ashes of War, one pool per table.
    A weapon is one entry (its base row, id % 10000 == 0) and every affinity row of it gets the same
    new price.  Rows with sellValue <= 0 (unsellable, dummies) stay as they are; unnamed rows (cut
    content, DLC pieces Paramdex has no name for) take part and are listed by id."""
    lines: list[str] = []
    for param, what in EQUIPMENT_SELL:
        P = reg.param(param, erreg.load_paramdef(HERE / "paramdef" / f"{param}.xml"))
        names = erreg.load_names(HERE / "names" / f"{param}.txt")
        weapon = param == "EquipParamWeapon"
        heads = [r for r in P.rows if P.get(r, "sellValue") > 0 and (not weapon or r.id % 10000 == 0)]
        members: dict[int, list] = {}
        for r in P.rows:
            members.setdefault(r.id - r.id % 10000 if weapon else r.id, []).append(r)
        old = [P.get(r, "sellValue") for r in heads]
        new = new_prices(old, rng, mode, smin, smax, f"{what} sell price")
        lines += ["", f"# {what} sell prices: mode={mode} entries={len(heads)}  ({param}.sellValue"
                  + ("; every affinity row of a weapon gets its price)" if weapon else ")"),
                  "# item  old -> new (runes)"]
        for r, o, n in zip(heads, old, new):
            for m in members[r.id]:
                P.set(m, "sellValue", n)
            lines.append(f"{r.id:>8}  {names.get(r.id, f'{what} {r.id}'):<40} {o:>7} -> {n}")
    return lines


def randomize_prices(reg: erreg.Regulation, rng: random.Random, mode: str,
                     pmin: int | None, pmax: int | None,
                     sell: bool = True, smin: int | None = None, smax: int | None = None) -> list[str]:
    """Shop prices: ShopLineupParam.value of every goods entry priced in runes (whatever the slot sells,
    so items an item randomizer put into shops are included).  Sell prices (unless sell is False):
    EquipParamGoods.sellValue of every named goods row that can be sold (sellValue > 0; -1 = unsellable).
    Shop prices and sell prices are drawn independently, so an item may well sell back for more
    than a merchant asks for it; the user prefers that to a cap."""
    pd = erreg.load_paramdef(HERE / "paramdef" / "ShopLineupParam.xml")
    slots = erreg.load_names(HERE / "names" / "ShopLineupParam.txt")     # vanilla "[merchant] item" per slot
    goods = erreg.load_names(HERE / "names" / "EquipParamGoods.txt")
    Sh = reg.param("ShopLineupParam", pd)
    rows = [r for r in Sh.rows
            if Sh.get(r, "equipType") == SHOP_EQUIP_TYPE_GOODS
            and Sh.get(r, "costType") == SHOP_COST_RUNES
            and Sh.get(r, "value") > 0]            # free (0) and non-rune entries are left alone
    old = [Sh.get(r, "value") for r in rows]
    new = new_prices(old, rng, mode, pmin, pmax, "price")
    lines = [f"# prices: mode={mode} entries={len(rows)}",
             "# shop entry  [merchant] item sold  old -> new (runes)   (slot: what the slot sells in vanilla,"
             " shown when an item randomizer put something else there)"]
    for r, o, n in zip(rows, old, new):
        Sh.set(r, "value", n)
        eid = Sh.get(r, "equipId")
        slot = slots.get(r.id, "")
        merchant, _, slot_item = slot.rpartition("] ") if slot.startswith("[") else ("", "", slot)
        merchant = merchant + "]" if merchant else ""
        item = goods.get(eid, f"goods {eid}")
        note = f"   (slot: {slot_item})" if slot_item and slot_item != item else ""
        lines.append(f"{r.id:>8}  {merchant:<44} {item:<40} {o:>7} -> {n:<6}{note}".rstrip())
    if not sell:
        return lines
    G = reg.param("EquipParamGoods", erreg.load_paramdef(HERE / "paramdef" / "EquipParamGoods.xml"))
    srows = [r for r in G.rows if G.get(r, "sellValue") > 0 and r.id in goods]   # named rows only: ids 23-99 are debug items
    sold = [G.get(r, "sellValue") for r in srows]
    snew = new_prices(sold, rng, mode, smin, smax, "sell price")
    lines += ["", f"# sell prices: mode={mode} entries={len(srows)}  (EquipParamGoods.sellValue)",
              "# item  old -> new (runes)"]
    for r, o, n in zip(srows, sold, snew):
        G.set(r, "sellValue", n)
        lines.append(f"{r.id:>8}  {goods.get(r.id, '?'):<40} {o:>7} -> {n}")
    return lines


DLL_HELP = f"""
# {oodle.DLL_NAME} not found, so the output cannot be compressed with the game's own Oodle (KRAK format).
# It is only looked for in the current directory (randomize.sh / .bat switch to the project directory first,
# so that is er_mod/{oodle.DLL_NAME}).  The file is in the game folder (Steam\\steamapps\\common\\ELDEN RING\\Game\\)
# and in the mod folders of the fog gate / item randomizer (mod/fog/, mod/randomizer/); copy it next to the tool,
# enter its full path below, or pass --oodle-dll PATH / set the OODLE_DLL environment variable.
# Press Enter without a path to go without it: the output is then zstd (64 KB window), about 35% larger,
# and may exceed the game's size limit."""


def choose_codec(wanted: str) -> str:
    """Resolve --compression: kraken needs the game's Oodle DLL.  When it is missing, ask the user
    for it before falling back to zstd (and never fall back silently)."""
    if wanted == erreg.CODEC_ZSTD:
        return wanted
    why = oodle.available()
    while why and oodle.missing_dll():
        print(DLL_HELP)
        if sys.stdin is None or not sys.stdin.isatty():
            raise SystemExit(f"# {oodle.DLL_NAME} not found and no terminal to ask for it. Pass --oodle-dll PATH or "
                             "set OODLE_DLL, or add --compression zstd explicitly to use zstd instead.")
        try:
            answer = input(f"Path to {oodle.DLL_NAME} (Enter = I do not have it): ").strip().strip('"').strip("'")
        except EOFError:
            answer = ""
        if not answer:
            if wanted != "auto":
                raise SystemExit(f"--compression {wanted} needs {oodle.DLL_NAME}; cancelled.")
            print("# no DLL given, falling back to zstd (64 KB window, larger file).")
            return erreg.CODEC_ZSTD
        if not oodle.use_dll(answer):
            print(f"# file not found: {answer}")
        why = oodle.available()
    if why:                                   # liblinoodle.so missing or the DLL unusable
        if wanted != "auto":
            raise SystemExit(f"--compression {wanted} unavailable: {why}")
        print(f"# note: {why}; falling back to zstd (64 KB window, larger file).")
        return erreg.CODEC_ZSTD
    return erreg.CODEC_KRAKEN if wanted == "auto" else wanted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="regulation.bin")
    ap.add_argument("--output", default="randomized/regulation.bin")
    ap.add_argument("--seed", type=int, default=None, help="random seed (printed; reuse to reproduce)")
    ap.add_argument("--mode", choices=["shuffle", "random"], default="shuffle",
                    help="shuffle: every effect used exactly once (default); random: effects may repeat")
    ap.add_argument("--include-flasks", action="store_true", help="also randomize Flask of Crimson/Cerulean Tears")
    ap.add_argument("--include-remembrances", action="store_true",
                    help="also randomize remembrances (using one for runes becomes a random effect and vice versa)")
    ap.add_argument("--split-anim", nargs="?", const="same", default=None, choices=["same", "any"],
                    metavar="same|any",
                    help="use animation and effect randomized separately; same (default when given): the "
                         "animation comes from an item of the same effect category (thrown / applied); any: "
                         "from any item, so a pot may get an eating animation (untested in-game); omitted: "
                         "animation and effect come from the same item. Also splits spell cast animations "
                         "(same: donor with the same ref-slot signature)")
    ap.add_argument("--no-spells", action="store_true", help="do not randomize sorceries / incantations (Magic.param)")
    ap.add_argument("--dry-run", action="store_true", help="only print the mapping, write nothing")
    ap.add_argument("--random-prices", action="store_true",
                    help="also randomize rune prices of goods in all shops (ShopLineupParam.value) and the sell "
                         "prices of goods (EquipParamGoods.sellValue)")
    ap.add_argument("--price-mode", choices=["shuffle", "range"], default="shuffle",
                    help="shuffle: permute the existing prices (default); range: draw a new price between --price-min/--price-max")
    ap.add_argument("--price-min", type=int, default=None, help="range mode: lowest price (default: lowest existing)")
    ap.add_argument("--price-max", type=int, default=None, help="range mode: highest price (default: highest existing)")
    ap.add_argument("--no-sell-prices", action="store_true", help="--random-prices: leave the sell prices of goods alone")
    ap.add_argument("--sell-min", type=int, default=None, help="range mode: lowest sell price (default: lowest existing)")
    ap.add_argument("--sell-max", type=int, default=None, help="range mode: highest sell price (default: highest existing)")
    ap.add_argument("--sell-equipment", action="store_true",
                    help="--random-prices: also randomize the sell prices of weapons, armor and Ashes of War")
    ap.add_argument("--random-flask-locations", action="store_true",
                    help="the Flask of Crimson Tears and the Flask of Cerulean Tears are found somewhere else: each "
                         "swaps places with a random one-time pickup, boss reward, NPC gift or shop slot (never a "
                         "chance drop or a map fragment; Land of Shadow NPCs and shops excluded), and the first "
                         "Site of Grace gives that item instead")
    ap.add_argument("--flask-at", default=None, metavar="SPOT[,SPOT]",
                    help="--random-flask-locations with the spots chosen by hand: lot:ID (ItemLotParam_map row) or "
                         "shop:ID (ShopLineupParam row), the Crimson flask's spot first, the Cerulean flask's second "
                         "(one given: the other is drawn at random); the ids are in names/item_locations.txt")
    ap.add_argument("--somber-infusable", action="store_true", help="somber/unique weapons get all affinities and Ashes of War")
    ap.add_argument("--random-movesets", action="store_true",
                    help="random light/heavy attack moveset on every melee weapon and shield")
    ap.add_argument("--moveset-mode", choices=["affinity", "bound", "weapon"], default="affinity",
                    help="affinity (default): free moveset per affinity row (shields included), every melee/shield "
                         "ash unlocked on every melee weapon and shield; "
                         "bound: every (weapon, affinity) gets its own moveset drawn from the affinity's cluster of "
                         "animation categories, ashes only offer affinities that animate them; "
                         "weapon: one moveset per weapon, wepType follows it (shields left alone)")
    ap.add_argument("--moveset-variety", type=int, default=3,
                    help="bound mode: animation categories per affinity cluster (1 = same category on every "
                         "weapon, more = more variety but fewer affinities left per ash of war; default 3)")
    ap.add_argument("--keep-standard-moveset", action="store_true",
                    help="affinity mode: keep each weapon's own moveset on its Standard row (only the other 12 "
                         "affinities change; bound mode always does this)")
    ap.add_argument("--shield-movesets", choices=["shields", "none", "all"], default="shields",
                    help="shields (default): shields swap movesets only among the four shield animation sets and "
                         "weapons never get one, so a left-hand shield still guards on L1; none: shields keep their "
                         "moveset; all: shields and weapons swap freely (left-hand shields then attack on L1)")
    ap.add_argument("--bow-movesets", choices=["bows", "none"], default="bows",
                    help="bows (default): every bow, crossbow and ballista takes the moveset of a random other "
                         "bow-class weapon (never from the melee pool; wepType and ammo unchanged); none: untouched")
    ap.add_argument("--weptype-follows", action="store_true",
                    help="affinity/bound modes: every randomized row also takes the donor's wepType (smithing "
                         "table follows the moveset, ashes not unlocked); untested against the game's save checks")
    ap.add_argument("--random-default-ash", action="store_true",
                    help="random default skill per (weapon, affinity); random affinity for weapons from lots/shops/classes")
    ap.add_argument("--random-stats", action="store_true",
                    help="random attack power per element, critical, poise/stamina damage, guard negation, "
                         "requirements, scaling and status build-ups on every (weapon, affinity) row; bows, "
                         "crossbows, ballistas, staves and seals included")
    ap.add_argument("--stat-groups", default=",".join(weapons.STAT_GROUPS),
                    help="comma list of stat groups for --random-stats: attack, guard, requirements, scaling, "
                         "effects, stamina, spells (default: all)")
    ap.add_argument("--stamina-rate", default="0.3,1.7", metavar="LO,HI",
                    help="--random-stats group stamina: every weapon row's staminaConsumptionRate (multiplier of "
                         "the attack stamina cost) is drawn uniformly from this range (default 0.3,1.7)")
    ap.add_argument("--weapons", action="store_true",
                    help="= --somber-infusable --random-movesets --random-default-ash --random-stats")
    ap.add_argument("--compression", choices=("auto",) + erreg.CODECS, default="auto",
                    help="kraken (default when oo2core_6_win64.dll is found): the game's own Oodle Kraken format, "
                         "file ~25%% smaller than zstd; zstd: 64 KB-window zstd like the fog gate / item randomizers "
                         "(the fallback when the DLL is missing); leviathan: Oodle Leviathan under the same KRAK "
                         "header (smaller still, untested in-game)")
    ap.add_argument("--oodle-dll", default=None, metavar="PATH",
                    help="path to oo2core_6_win64.dll (default: ./oo2core_6_win64.dll in the current directory, "
                         "or $OODLE_DLL; asked for interactively when not found)")
    ap.add_argument("--zstd-window", type=int, default=16, choices=range(16, 23), metavar="16..22",
                    help="zstd window log of the output; 16 (64 KB) is the only value the game accepts "
                         "(22 crashed it), kept for experiments only")
    args = ap.parse_args(argv)
    if args.weapons:
        args.somber_infusable = args.random_movesets = args.random_default_ash = args.random_stats = True
    flask_at: list[tuple[str, int]] = []
    if args.flask_at:
        for spot in args.flask_at.split(","):
            kind, _, num = spot.strip().partition(":")
            if kind not in ("lot", "shop") or not num.isdigit():
                raise SystemExit(f"--flask-at: expected lot:ID or shop:ID, got {spot!r}")
            flask_at.append((kind, int(num)))
        if len(flask_at) > 2:
            raise SystemExit("--flask-at: at most two spots (Crimson, Cerulean)")
        args.random_flask_locations = True
    if args.oodle_dll is not None and not oodle.use_dll(args.oodle_dll):
        raise SystemExit(f"--oodle-dll: {args.oodle_dll} does not exist")
    codec = erreg.CODEC_ZSTD if args.dry_run else choose_codec(args.compression)
    stat_groups = [x.strip() for x in args.stat_groups.split(",") if x.strip()]
    bad = [x for x in stat_groups if x not in weapons.STAT_GROUPS]
    if bad:
        raise SystemExit(f"unknown --stat-groups entries: {', '.join(bad)} (choose from {', '.join(weapons.STAT_GROUPS)})")
    spell_stats = not args.no_spells and args.random_stats and "spells" in stat_groups
    try:
        stamina_rate = tuple(float(x) for x in args.stamina_rate.split(","))
        if len(stamina_rate) != 2 or not 0 < stamina_rate[0] <= stamina_rate[1]:
            raise ValueError
    except ValueError:
        raise SystemExit(f"--stamina-rate {args.stamina_rate}: expected LO,HI with 0 < LO <= HI, e.g. 0.3,1.7")

    seed = args.seed if args.seed is not None else random.randrange(1, 2**31)
    rng = random.Random(seed)

    pd = erreg.load_paramdef(HERE / "paramdef" / "EquipParamGoods.xml")
    names = erreg.load_names(HERE / "names" / "EquipParamGoods.txt")
    reg = erreg.Regulation(args.input)
    P = reg.param("EquipParamGoods", pd)

    pool = build_pool(P, names, args.include_flasks, args.include_remembrances)
    if len(pool) < 2:
        print("pool too small", file=sys.stderr)
        return 1

    bundles = [{f: P.get(r, f) for f in EFFECT_FIELDS} for r in pool]
    if args.mode == "shuffle":
        src = derangement(len(pool), rng)
    else:
        src = [rng.randrange(len(pool)) for _ in pool]
    anim = anim_sources(P, pool, src, args.mode, rng, args.split_anim == "any") if args.split_anim else src
    reusable = sum(1 for r in pool if not P.get(r, "isConsume"))

    lines = [f"# seed={seed} mode={args.mode} pool={len(pool)} items ({reusable} reusable tools)"
             + (f" anim split ({args.split_anim} category)" if args.split_anim else ""),
             "# item  <-  effect taken from" + ("  |  animation taken from" if args.split_anim else "")]
    for i, r in enumerate(pool):
        s, a = pool[src[i]], pool[anim[i]]
        lines.append(f"{r.id:>8}  {names[r.id]:<40} <-  {names[s.id]} ({s.id})"
                     + (f"  |  {names[a.id]} ({a.id})" if args.split_anim else ""))
        for f in EFFECT_FIELDS:
            P.set(r, f, bundles[src[i]][f])
        for f in ANIM_FIELDS:
            P.set(r, f, bundles[anim[i]][f])
    if args.random_prices:
        lines += [""] + randomize_prices(reg, rng, args.price_mode, args.price_min, args.price_max,
                                         not args.no_sell_prices, args.sell_min, args.sell_max)
        if args.sell_equipment:
            lines += randomize_equipment_sell(reg, rng, args.price_mode, args.sell_min, args.sell_max)
    report = "\n".join(lines)
    print(report)

    wlines: list[str] = []
    if args.somber_infusable or args.random_movesets or args.random_default_ash or args.random_stats:
        wp = weapons.Weapons(reg)
        wlines.append(f"# seed={seed}")
        if args.somber_infusable:
            wlines += [""] + wp.somber_infusable()
        if args.random_movesets:
            wlines += [""] + wp.random_movesets(rng, args.moveset_mode, args.moveset_variety,
                                                 args.keep_standard_moveset, args.weptype_follows,
                                                 args.shield_movesets, args.bow_movesets)
        if args.random_default_ash:
            wlines += [""] + wp.random_default_ash(rng)
        if args.random_stats:
            wlines += [""] + wp.random_stats(rng, stat_groups, stamina_rate)
        print("\n".join(l for l in wlines if l.startswith("#")))

    slines: list[str] = []
    if not args.no_spells:
        sp = spells.Spells(reg)
        slines.append(f"# seed={seed} mode={args.mode} spells={len(sp.pool)} (sorceries + incantations in one pool)"
                      + (f" anim split ({args.split_anim} signature)" if args.split_anim else ""))
        slines += sp.randomize_effects(rng, args.mode, args.split_anim)
        if spell_stats:
            slines += [""] + sp.random_stats(rng)
        print("\n".join(l for l in slines if l.startswith("#")))

    if args.random_flask_locations:
        flines = flasks.Flasks(reg).randomize(rng, flask_at)
        print("\n".join(flines))
        report += "\n\n" + "\n".join(flines)

    if args.dry_run:
        return 0
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    size = reg.save(out, window_log=args.zstd_window, codec=codec)
    print(f"# wrote {out} ({codec}, {size} bytes, limit {erreg.REGULATION_MAX_SIZE}; {erreg.REGULATION_MAX_SIZE - size} bytes to spare)")
    out.with_name("mapping.txt").write_text(report + "\n", encoding="utf-8")
    if wlines:
        out.with_name("weapons.txt").write_text("\n".join(wlines) + "\n", encoding="utf-8")
    if slines:
        out.with_name("spells.txt").write_text("\n".join(slines) + "\n", encoding="utf-8")
    print(f"\nwritten: {out}  (mapping: {out.with_name('mapping.txt')}"
          + (f", weapons: {out.with_name('weapons.txt')}" if wlines else "")
          + (f", spells: {out.with_name('spells.txt')}" if slines else "") + f")  seed={seed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
