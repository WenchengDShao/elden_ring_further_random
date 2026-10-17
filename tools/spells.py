"""Spell randomization (Magic.param): sorceries and incantations share ONE effect pool.

Every player spell keeps its identity row (id, icon, sort order, sorcery / incantation category =
ezStateBehaviorType, which is what gates staffs vs seals and picks the menu tab) and receives the
*effect* of another spell: the ten ref slots the cast animation fires (bullets / attacks / SpEffects),
their FP consumption types, costs, requirements, memory slots and the effect-side flags.  By default the
cast animation (refType = MAGIC_MOTION_TYPE, SFX, dexterity cast-speed window, horseback flag) travels
with the effect, so the receiver plays the donor's motion; --split-anim takes the animation from a
second donor ("same": one whose vanilla ref-slot signature equals the effect donor's, so the motion's
TAE events find a ref in every slot they fire; "any": any spell).

Staffs and seals share animation bank 41 (wepmotionCategory), so sorcery motions on incantation rows
and vice versa resolve to existing animations; whether every cross-category pairing also deals damage
the way the catalyst expects is untested in-game.

--random-stats (stat group "spells"): FP cost drawn from weighted tiers (0-10: 50 %, 11-20: 30 %,
21-40: 20 %), stamina cost likewise (0-20 / 21-40 / 41-60), the charged costs keep the row's ratio,
1-3 required attributes among INT / FAI / ARC drawn from the weapon requirement tiers (sum <= 60,
scaled down proportionally otherwise), and every spell takes exactly one memory slot.
"""
from __future__ import annotations

import random
from pathlib import Path

import erreg
from weapons import REQ_MAX, REQ_TIERS, REQ_TOTAL_MAX, cap_total, tiered

HERE = Path(__file__).resolve().parent

SORCERY, INCANTATION = 0, 1            # ezStateBehaviorType (MAGIC_CATEGORY)
N_REFS = 10

# What the spell does: ref slots fired by the cast animation, costs, requirements, slots, effect flags.
EFFECT_FIELDS = [
    *[f"refCategory{i}" for i in range(1, N_REFS + 1)],
    *[f"refId{i}" for i in range(1, N_REFS + 1)],
    *[f"consumeType{i}" for i in range(1, N_REFS + 1)],
    "mp", "mp_charge", "stamina", "stamina_charge", "consumeLoopMP_forMenu", "consumeSA",
    "requirementIntellect", "requirementFaith", "requirementLuck", "slotLength",
    "isEnchant", "isShieldEnchant", "createLimitGroupId", "limitCancelSpEffectId",
    "hasSpEffectType", "replaceCategory", "ReplacementStatusType",
    *[f"ReplacementStatus{i}" for i in range(1, 5)], *[f"ReplacementMagic{i}" for i in range(1, 5)],
    "subCategory1", "subCategory2", "castResonanceMagic", "isValidTough_ProtSADmg", "toughnessCorrectRate",
    "isWarpMagic", "isUseNoAttackRegion", "useLimitCategory", "yesNoDialogMessageId", "aiUseJudgeId",
    "aiNotifyType", "behaviorId",
]
# The cast animation: motion type (picks the EzState animation), its SFX, cast-speed window, horseback.
ANIM_FIELDS = ["refType", "castSfxId", "fireSfxId", "effectSfxId", "analogDexterityMin", "analogDexterityMax",
               "overDexterity", "enableRiding", "disableRiding"]
# Kept by the receiver: ezStateBehaviorType / spEffectCategory (sorcery vs incantation), sortId, iconId,
# opmeMenuType, disableOffline, enable_* / vowType* online flags, replaceMagicId, mtrlItemId, maxQuantity.

REQ_STATS = ["requirementIntellect", "requirementFaith", "requirementLuck"]   # INT / FAI / ARC
REQ_COUNT_WEIGHTS = [70, 25, 5]        # one / two / three required attributes
FP_TIERS = [((0, 10), 50), ((11, 20), 30), ((21, 40), 20)]        # (inclusive range, weight %) of the FP cost
STAMINA_TIERS = [((0, 20), 50), ((21, 40), 30), ((41, 60), 20)]   # same for the stamina cost


def scaled_charge(old: int, old_charge: int, new: int) -> int:
    """Charged-cast cost after the normal cost changed: 0 stays 0, otherwise the row's ratio is kept."""
    if old_charge == 0:
        return 0
    return round(new * old_charge / old) if old else new


def derangement(n: int, rng: random.Random) -> list[int]:
    """Permutation with no fixed point (every spell gets a *different* spell's effect)."""
    while True:
        perm = list(range(n))
        rng.shuffle(perm)
        if all(i != p for i, p in enumerate(perm)):
            return perm


class Spells:
    def __init__(self, reg: erreg.Regulation):
        self.reg = reg
        self.P = reg.param("Magic", erreg.load_paramdef(HERE / "paramdef" / "Magic.xml"))
        self.names = erreg.load_names(HERE / "names" / "Magic.txt")
        self.pool = self.build_pool()

    def build_pool(self) -> list[erreg.ParamRow]:
        """Every spell the player can learn: Paramdex names it [Sorcery] / [Incantation] (NPC rows are
           [NPC: ...]), it takes memory slots (NPC rows have slotLength 0) and it is not a cut row."""
        g = self.P.get
        return [r for r in self.P.rows
                if self.names.get(r.id, "").startswith(("[Sorcery]", "[Incantation]"))
                and g(r, "slotLength") > 0 and "(Unused" not in self.names[r.id]]

    def slot_signature(self, row: erreg.ParamRow) -> tuple[int, ...]:
        return tuple(i for i in range(1, N_REFS + 1) if self.P.get(row, f"refId{i}") != -1)

    def anim_sources(self, src: list[int], mode: str, rng: random.Random, any_sig: bool) -> list[int]:
        """Per spell, the pool index whose cast animation it gets: among spells whose vanilla ref-slot
           signature equals that of the effect donor src[i] (any_sig: the whole pool).  shuffle: every
           animation of a group is used once; random: free draw."""
        pool = self.pool
        key = [() if any_sig else self.slot_signature(r) for r in pool]
        by_key: dict[tuple, list[int]] = {}
        for j, k in enumerate(key):
            by_key.setdefault(k, []).append(j)
        anim = [0] * len(pool)
        if mode == "shuffle":
            receivers: dict[tuple, list[int]] = {}
            for i in range(len(pool)):
                receivers.setdefault(key[src[i]], []).append(i)
            for k, idx in receivers.items():
                donors = by_key[k][:]
                rng.shuffle(donors)
                for i, j in zip(idx, donors):
                    anim[i] = j
        else:
            for i in range(len(pool)):
                anim[i] = rng.choice(by_key[key[src[i]]])
        return anim

    def randomize_effects(self, rng: random.Random, mode: str, split: str | None) -> list[str]:
        """Move EFFECT_FIELDS (and, unless split, ANIM_FIELDS) between the pool spells.  Returns the
           report lines: `id name <- effect donor (id) [| animation donor (id)]`."""
        P, pool, names = self.P, self.pool, self.names
        bundles = [{f: P.get(r, f) for f in EFFECT_FIELDS + ANIM_FIELDS} for r in pool]
        if mode == "shuffle":
            src = derangement(len(pool), rng)
        else:
            src = [rng.randrange(len(pool)) for _ in pool]
        anim = self.anim_sources(src, mode, rng, split == "any") if split else src
        lines = ["# spell  <-  effect taken from" + ("  |  cast animation taken from" if split else "")]
        for i, r in enumerate(pool):
            s, a = pool[src[i]], pool[anim[i]]
            lines.append(f"{r.id:>8}  {names[r.id]:<44} <-  {names[s.id]} ({s.id})"
                         + (f"  |  {names[a.id]} ({a.id})" if split else ""))
            for f in EFFECT_FIELDS:
                P.set(r, f, bundles[src[i]][f])
            for f in ANIM_FIELDS:
                P.set(r, f, bundles[anim[i]][f])
        return lines

    def random_stats(self, rng: random.Random) -> list[str]:
        """FP and stamina costs from the weighted tiers (charged costs keep the row's charge / normal
           ratio), 1-3 required attributes like weapon requirements, slotLength 1.  Run after
           randomize_effects so the ratios and the report's "before" values are those of the effect now
           on the row."""
        P, names = self.P, self.names
        tiers = lambda ts: ", ".join(f"{lo}-{hi}: {w}%" for (lo, hi), w in ts)
        lines = [f"# random spell stats: FP {tiers(FP_TIERS)}; stamina {tiers(STAMINA_TIERS)}; "
                 f"requirements {tiers(REQ_TIERS)} per attribute, sum <= {REQ_TOTAL_MAX}; memory slots 1",
                 "# spell                                                FP                   stamina              INT/FAI/ARC         slots"]
        for r in self.pool:
            old_mp, old_charge, old_slots = P.get(r, "mp"), P.get(r, "mp_charge"), P.get(r, "slotLength")
            old_st, old_st_charge = P.get(r, "stamina"), P.get(r, "stamina_charge")
            old_req = [P.get(r, f) for f in REQ_STATS]
            mp = tiered(rng, FP_TIERS)
            charge = scaled_charge(old_mp, old_charge, mp)
            st = tiered(rng, STAMINA_TIERS)
            st_charge = scaled_charge(old_st, old_st_charge, st)
            k = rng.choices([1, 2, 3], REQ_COUNT_WEIGHTS)[0]
            stats = rng.sample(REQ_STATS, k)
            req = {f: 0 for f in REQ_STATS}
            for f in stats:
                req[f] = tiered(rng, REQ_TIERS)
            req = cap_total(req, REQ_TOTAL_MAX)
            P.set(r, "mp", mp)
            P.set(r, "mp_charge", charge)
            P.set(r, "stamina", st)
            P.set(r, "stamina_charge", st_charge)
            for f in REQ_STATS:
                P.set(r, f, req[f])
            P.set(r, "slotLength", 1)
            new_req = "/".join(str(req[f]) for f in REQ_STATS)
            cost = lambda o, n, c: f"{o:>3} -> {n:<3}" + (f" (charge {c:>2})" if c else "            ")
            lines.append(f"{r.id:>8}  {names[r.id]:<44} {cost(old_mp, mp, charge)}  {cost(old_st, st, st_charge)}"
                         f"  {'/'.join(map(str, old_req)):>9} -> {new_req:<9} {old_slots} -> 1")
        return lines
