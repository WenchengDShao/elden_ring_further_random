#!/usr/bin/env python3
"""Elden Ring regulation.bin randomizer.

Goods:
  (always)              each consumable item gets the use-effect of another consumable
  --random-prices       rune prices of goods in shops (ShopLineupParam.value)
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


def randomize_prices(reg: erreg.Regulation, rng: random.Random, mode: str,
                     pmin: int | None, pmax: int | None) -> list[str]:
    pd = erreg.load_paramdef(HERE / "paramdef" / "ShopLineupParam.xml")
    names = erreg.load_names(HERE / "names" / "ShopLineupParam.txt")
    Sh = reg.param("ShopLineupParam", pd)
    rows = [r for r in Sh.rows
            if Sh.get(r, "equipType") == SHOP_EQUIP_TYPE_GOODS
            and Sh.get(r, "costType") == SHOP_COST_RUNES
            and Sh.get(r, "value") > 0]            # free (0) and non-rune entries are left alone
    old = [Sh.get(r, "value") for r in rows]
    if mode == "shuffle":
        new = old[:]
        rng.shuffle(new)
    else:
        lo = pmin if pmin is not None else min(old)
        hi = pmax if pmax is not None else max(old)
        if lo < 1 or hi < lo:
            raise SystemExit(f"bad price range {lo}..{hi}")
        new = [round_price(math.exp(rng.uniform(math.log(lo), math.log(hi)))) for _ in old]
    lines = [f"# prices: mode={mode} entries={len(rows)}", "# shop entry : old -> new (runes)"]
    for r, o, n in zip(rows, old, new):
        Sh.set(r, "value", n)
        lines.append(f"{r.id:>8}  {names.get(r.id, '?'):<60} {o:>7} -> {n}")
    return lines


DLL_HELP = f"""
# 没有找到 {oodle.DLL_NAME}，无法用游戏自带的 Oodle 压成原版 KRAK 格式。
# 默认只在当前目录找（./randomize.sh 会先切到项目目录，所以就是 er_mod/{oodle.DLL_NAME}）。
# 这个文件在游戏目录（Steam\\steamapps\\common\\ELDEN RING\\Game\\）里，
# 雾门/道具随机器的 mod 文件夹（如 mod/fog/、mod/randomizer/）里也各有一份，复制一份到当前目录即可；
# 或者在下面输入它的完整路径，也可以用 --oodle-dll PATH 或环境变量 OODLE_DLL 指定。
# 直接回车表示提供不了：那样会回退到 zstd 格式（64 KB 窗口），文件大约大 35%，可能超出大小限制。"""


def choose_codec(wanted: str) -> str:
    """Resolve --compression: kraken needs the game's Oodle DLL.  When it is missing, ask the user
    for it before falling back to zstd (and never fall back silently)."""
    if wanted == erreg.CODEC_ZSTD:
        return wanted
    why = oodle.available()
    while why and oodle.missing_dll():
        print(DLL_HELP)
        if not sys.stdin.isatty():
            raise SystemExit(f"# {oodle.DLL_NAME} 找不到，且无法交互询问。请用 --oodle-dll PATH 或 OODLE_DLL 指定，"
                             "或明确加 --compression zstd 回退到 zstd 格式。")
        try:
            answer = input(f"{oodle.DLL_NAME} 的路径（回车 = 提供不了）: ").strip().strip('"').strip("'")
        except EOFError:
            answer = ""
        if not answer:
            if wanted != "auto":
                raise SystemExit(f"--compression {wanted} 需要 {oodle.DLL_NAME}，已取消。")
            print("# 没有提供 DLL，回退到 zstd 格式（64 KB 窗口，文件更大）。")
            return erreg.CODEC_ZSTD
        if not oodle.use_dll(answer):
            print(f"# 文件不存在: {answer}")
        why = oodle.available()
    if why:                                   # liblinoodle.so missing or the DLL unusable
        if wanted != "auto":
            raise SystemExit(f"--compression {wanted} unavailable: {why}")
        print(f"# note: {why}; 回退到 zstd 格式（64 KB 窗口，文件更大）。")
        return erreg.CODEC_ZSTD
    return erreg.CODEC_KRAKEN if wanted == "auto" else wanted


def main() -> int:
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
                    help="also randomize rune prices of goods in all shops (ShopLineupParam.value)")
    ap.add_argument("--price-mode", choices=["shuffle", "range"], default="shuffle",
                    help="shuffle: permute the existing prices (default); range: draw a new price between --price-min/--price-max")
    ap.add_argument("--price-min", type=int, default=None, help="range mode: lowest price (default: lowest existing)")
    ap.add_argument("--price-max", type=int, default=None, help="range mode: highest price (default: highest existing)")
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
    args = ap.parse_args()
    if args.weapons:
        args.somber_infusable = args.random_movesets = args.random_default_ash = args.random_stats = True
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
        lines += [""] + randomize_prices(reg, rng, args.price_mode, args.price_min, args.price_max)
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
