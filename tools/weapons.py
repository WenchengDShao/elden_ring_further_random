"""Weapon-side randomization for Elden Ring regulation.bin.

Weapon ids are  base(…0000) + affinity*100 + upgrade level.  EquipParamWeapon holds one
row per (weapon, affinity); upgrade levels are applied at runtime through
ReinforceParamWeapon, so only affinity rows exist.

1. somber_infusable():  every single-affinity (somber / unique) weapon gets the 12 missing
   affinity rows (Heavy .. Occult) synthesized from a reference weapon of the same type,
   and gemMountType=2 so Ashes of War can be mounted.
2. random_movesets():   every (weapon, affinity) row receives the moveset bundle of a random
   other melee weapon or shield (animation set, attack behaviour block).
3. random_default_ash(): every (weapon, affinity) row gets a random default skill that is
   mountable on its weapon type, and every weapon handed out by item lots, shops and the
   starting classes gets a random affinity.
4. random_stats():      every (weapon, affinity) row (melee, shields, bows, crossbows, staves,
   seals) gets random attack power per element, critical, poise and stamina damage, guard
   negation, attribute requirements, scaling and status build-ups.
"""
from __future__ import annotations

import random
from pathlib import Path

import erreg

HERE = Path(__file__).resolve().parent
D, N = HERE / "paramdef", HERE / "names"

AFFINITY_NAMES = {0: "Standard", 1: "Heavy", 2: "Keen", 3: "Quality", 4: "Fire", 5: "Flame Art",
                  6: "Lightning", 7: "Sacred", 8: "Magic", 9: "Cold", 10: "Poison", 11: "Blood", 12: "Occult"}
# sortId offset of each affinity row relative to the Standard row (vanilla pattern)
SORT_DELTA = {0: 0, 1: 1, 2: 2, 3: 3, 4: 5, 5: 6, 6: 7, 7: 8, 8: 4, 9: 11, 10: 9, 11: 10, 12: 12}

MELEE_TYPES = {1, 3, 5, 7, 9, 11, 13, 14, 15, 16, 17, 19, 21, 23, 24, 25, 28, 29, 31, 35, 37, 39, 41,
               88, 89, 91, 92, 93, 94, 95}
MIN_ASHES_PER_CATEGORY = 30     # bound mode: an affinity never maps to a category with fewer animating ashes
SHIELD_TYPES = {65, 67, 69, 90}
# weapons that take part in affinity / moveset / default-ash randomization (staves, seals, torches do not)
INFUSABLE_TYPES = MELEE_TYPES | SHIELD_TYPES
# bows and crossbows: no affinities, movesets swapped only among themselves (never with the melee pool),
# wepType never changes so arrows stay arrows and bolts stay bolts
BOW_TYPES = {50, 51, 53, 55, 56}
BOW_ASH_TYPES = {50, 51, 53}        # crossbows / ballistas have no Ashes of War in vanilla
# wepType -> similar wepType, used to find a reference weapon when the type has no infusable weapon
REFERENCE_FALLBACK = {28: 25, 16: 15, 11: 9, 94: 13, 93: 5, 95: 37, 92: 9, 91: 1, 89: 35, 88: 35,
                      90: 67, 24: 21, 31: 29, 39: 9, 14: 3, 37: 35, 41: 23, 7: 5, 19: 17, 23: 21,
                      65: 67, 69: 67}
# wepType -> bit index inside EquipParamGem's 64-bit canMountWep block (bits 36+ are the DLC types)
WEPTYPE_BIT = {1: 0, 3: 1, 5: 2, 7: 3, 9: 4, 11: 5, 13: 6, 14: 7, 15: 8, 16: 9, 17: 10, 19: 11, 21: 12,
               23: 13, 24: 14, 25: 15, 28: 17, 29: 18, 31: 19, 35: 20, 37: 21, 39: 22, 41: 23,
               50: 24, 51: 25, 53: 26, 55: 27, 56: 28, 57: 29, 61: 31, 65: 32, 67: 33, 69: 34, 87: 35,
               88: 36, 89: 37, 90: 38, 91: 39, 92: 40, 93: 41, 94: 42, 95: 43}

# the "moveset": animation set + attack behaviour block.  wepType is handled separately: the
# game validates mounted Ashes of War against wepType when loading a save, so it may only
# change when every affinity row of a weapon gets the same type (mode "weapon").
MOVESET_FIELDS = ("weaponCategory", "wepmotionCategory", "guardmotionCategory",
                  "wepmotionOneHandId", "wepmotionBothHandId", "spAtkcategory",
                  "behaviorVariationId", "isDualBlade", "isThrustAttackType")
# Fields that belong to the item rather than to the attack moveset, so every row keeps its own:
# guardmotionCategory selects the guard (block) animation set, and weaponCategory is the item class
# the game maps inputs with (12 = shield: a left-hand shield guards on L1 instead of attacking).
# Found in-game 2026-10-17: with the donor's weaponCategory a left-hand shield attacked on L1.
# They stay in MOVESET_FIELDS so pool keys and weapons.txt donor names are unchanged.
KEEP_OWN_FIELDS = ("guardmotionCategory", "weaponCategory")

TYPE_NAMES = {1: "Dagger", 3: "Straight Sword", 5: "Greatsword", 7: "Colossal Sword", 9: "Curved Sword",
              11: "Curved Greatsword", 13: "Katana", 14: "Twinblade", 15: "Thrusting Sword",
              16: "Heavy Thrusting Sword", 17: "Axe", 19: "Greataxe", 21: "Hammer", 23: "Great Hammer",
              24: "Flail", 25: "Spear", 28: "Great Spear", 29: "Halberd", 31: "Reaper", 35: "Fist",
              37: "Claw", 39: "Whip", 41: "Colossal Weapon", 50: "Light Bow", 51: "Bow", 53: "Greatbow",
              55: "Crossbow", 56: "Ballista", 57: "Glintstone Staff", 61: "Sacred Seal", 65: "Small Shield",
              67: "Medium Shield", 69: "Greatshield", 87: "Torch", 88: "Hand-to-Hand", 89: "Perfume Bottle",
              90: "Thrusting Shield", 91: "Throwing Blade", 92: "Backhand Blade", 93: "Light Greatsword",
              94: "Great Katana", 95: "Beast Claw"}

ATTACK_FIELDS = ("attackBasePhysics", "attackBaseMagic", "attackBaseFire", "attackBaseThunder", "attackBaseDark")
SCALING_FIELDS = ("correctStrength", "correctAgility", "correctMagic", "correctFaith", "correctLuck")
COPY_IF_CHANGED = ("attackElementCorrectId", "correctType_Physics", "correctType_Magic", "correctType_Fire",
                   "correctType_Thunder", "correctType_Dark", "correctType_Poison", "correctType_Blood",
                   "correctType_Sleep", "correctType_Madness", "spAttribute", "isEnhance")
EFFECT_SLOTS = ("spEffectBehaviorId0", "spEffectBehaviorId1", "spEffectBehaviorId2")
MSG_SLOTS = ("spEffectMsgId0", "spEffectMsgId1", "spEffectMsgId2")

# --- 4. per-row stats (random_stats) -----------------------------------------------------
STAT_GROUPS = ("attack", "guard", "requirements", "scaling", "effects", "stamina", "spells")   # spells: see spells.py
STAMINA_RATE_RANGE = (0.3, 1.7)      # staminaConsumptionRate of every row, uniform in this range (group "stamina")
STAT_TYPES = INFUSABLE_TYPES | BOW_TYPES | {57, 61}       # + staves and seals (torches untouched)
ELEMENTS = ("Physics", "Magic", "Fire", "Thunder", "Dark")      # attackBase* / correctType_* suffixes
STATS = ("Strength", "Agility", "Magic", "Faith", "Luck")        # correct* / proper* suffixes
AEC_STAT = {"Strength": "Strength", "Agility": "Dexterity", "Magic": "Magic", "Faith": "Faith", "Luck": "Luck"}
AEC_BASE = 10000                     # vanilla default AttackElementCorrectParam row, template for new rows
AEC_NEW = 90000000                   # new rows: AEC_NEW + stat_mask (every scaling attribute raises every damage type)
GUARD_CUT = ("physGuardCutRate", "magGuardCutRate", "fireGuardCutRate", "thunGuardCutRate", "darkGuardCutRate")
GUARD_RESIST = ("poisonGuardResist", "diseaseGuardResist", "bloodGuardResist", "curseGuardResist",
                "freezeGuardResist", "sleepGuardResist", "madnessGuardResist")
SP_ATTRIBUTE = {"Magic": 10, "Fire": 11, "Thunder": 12, "Dark": 13}
CRIT_VALUES = (0, 10, 20, 30, 40, 50, 60)                   # throwAtkRate: critical = 100 + value
REQ_MAX = 60                         # attribute requirements never exceed this, singly or summed
# Each drawn requirement: (inclusive range, weight %).  Shared with spells (spells.py).
REQ_TIERS = [((0, 10), 40), ((11, 20), 30), ((21, 30), 20), ((31, 40), 9), ((41, REQ_MAX), 1)]
REQ_TOTAL_MAX = REQ_MAX              # sum over all attributes; scaled down proportionally when above
REQ_EXTRA_CHANCE = 0.15              # chance that an attribute the weapon does not scale with still needs points


def tiered(rng: random.Random, tiers) -> int:
    """Pick a tier by weight, then a uniform integer inside it."""
    (lo, hi), = rng.choices([t[0] for t in tiers], [t[1] for t in tiers])
    return rng.randint(lo, hi)


def cap_total(req: dict, cap: int) -> dict:
    """Scale every value down proportionally (rounded down) when their sum exceeds cap."""
    tot = sum(req.values())
    if tot <= cap:
        return req
    return {k: int(v * cap / tot) for k, v in req.items()}
CRIT_WEIGHTS = (35, 25, 15, 10, 8, 5, 2)
PHYS_CURVES = (0, 1, 2, 7, 8)        # CalcCorrectGraph ids vanilla weapons use for physical scaling
ELEM_CURVES = (0, 4)                 # ... for elemental scaling
CATALYST_CURVES = (12, 14, 15, 16)   # ... staves / seals (spell scaling)
# status build-ups: SpEffect ids used by vanilla weapons.  "flat" ids keep their strength at every
# upgrade level; "series" ids are the affinity ones that grow with the level (id + level) and may only
# sit in the slot that the row's ReinforceParamWeapon type offsets (Blood: slot 0, Poison/Cold: slot 1).
STATUS_FLAT = {"blood": (6400, 6401, 6402, 6403, 6404, 6405, 6406),
               "poizon": (6500, 6501, 6502, 6503, 6505),
               "disease": (6600, 6601, 6602, 6603, 6605),
               "freeze": (6700, 6701, 6702),
               "sleep": (6451, 6452, 6454, 6455, 6456),
               "madness": (6750, 6751, 6752, 6753)}
STATUS_SERIES = {"blood": (105000, 105100, 105200), "poizon": (106000, 106100, 106200),
                 "freeze": (107500, 107600, 107700)}
STATUS_MSG = {"blood": 6501, "poizon": 6401, "disease": 6451, "freeze": 6601, "sleep": 6651, "madness": 6701}
STATUS_MSG_IDS = frozenset(range(6400, 6900))       # effect-text ids of status build-ups (6401, 6500, 6501, ...)
STATUS_LABEL = {"blood": "bleed", "poizon": "poison", "disease": "rot", "freeze": "frost",
                "sleep": "sleep", "madness": "madness"}
# crossbows / ballistas use reinforce types whose scaling rates are 0; to give them scaling they take
# the regular (25 levels) or somber (10 levels) type with the same materials and level count
CROSSBOW_REINFORCE = {3100: 0, 3500: 0, 3200: 2200, 3300: 2200, 3400: 2200}


def base_id(i: int) -> int:
    return i - i % 10000


def affinity(i: int) -> int:
    return i % 10000 // 100


def level(i: int) -> int:
    return i % 100


class Weapons:
    def __init__(self, reg: erreg.Regulation):
        self.reg = reg
        self.W = reg.param("EquipParamWeapon", erreg.load_paramdef(D / "EquipParamWeapon.xml"))
        self.names = erreg.load_names(N / "EquipParamWeapon.txt")
        self.orig_type = {}      # base id -> wepType
        for r in self.W.rows:
            if r.id >= 1000000 and r.id % 10000 == 0:
                self.orig_type[r.id] = self.W.get(r, "wepType")
        self.moveset_type: dict[int, int] = {}   # row id -> wepType of the weapon whose moveset it got
        self.row_cat: dict[int, int] = {}        # row id -> wepmotionCategory after randomization
        self.G = reg.param("EquipParamGem", erreg.load_paramdef(D / "EquipParamGem.xml"))
        self.gem_names = erreg.load_names(N / "EquipParamGem.txt")
        self.ashes = self._ashes()               # vanilla mount bits, read before any gem edit
        # weapon type -> animation category (wepmotionCategory) used by its weapons (majority vote)
        votes: dict[int, dict[int, int]] = {}
        for b in self.bases():
            if self.named(b):
                c = self.W.get(self.W.by_id[b], "wepmotionCategory")
                votes.setdefault(self.orig_type[b], {})[c] = votes.get(self.orig_type[b], {}).get(c, 0) + 1
        self.cat_of_type = {t: max(v, key=v.get) for t, v in votes.items()}
        self._animated_cache: dict[int, set[int]] = {}

    def animated(self, cat: int) -> set[int]:
        """swordArts ids of ashes whose animations exist in animation category `cat`
        (= ashes mountable on some weapon type that uses that category)."""
        if cat not in self._animated_cache:
            types = [t for t, c in self.cat_of_type.items() if c == cat and t in WEPTYPE_BIT]
            self._animated_cache[cat] = {sa for sa, (_, bits) in self.ashes.items()
                                         if any(bits >> WEPTYPE_BIT[t] & 1 for t in types)}
        return self._animated_cache[cat]

    # --- helpers --------------------------------------------------------------
    def variants(self, b: int) -> list[int]:
        return [a for a in range(13) if b + a * 100 in self.W.by_id]

    def bases(self) -> list[int]:
        return sorted(self.orig_type)

    def named(self, b: int) -> bool:
        n = self.names.get(b, "?")
        return n != "?" and not n.startswith("[NPC]")

    def name(self, rid: int) -> str:
        b, a = base_id(rid), affinity(rid)
        n = self.names.get(b, f"#{b}")
        return n if a == 0 else f"{AFFINITY_NAMES[a]} {n}"

    # --- 1. somber weapons: add affinity rows ------------------------------------------
    def somber_infusable(self) -> list[str]:
        W, g, s = self.W, self.W.get, self.W.set
        refs: dict[int, int] = {}
        for b in self.bases():
            if len(self.variants(b)) == 13 and self.named(b):
                wt = self.orig_type[b]
                innate = sum(1 for f in EFFECT_SLOTS if g(W.by_id[b], f) != -1)
                if wt not in refs or innate < refs[wt][0]:
                    refs[wt] = (innate, b)
        refs = {wt: v[1] for wt, v in refs.items()}
        clean_ref = next(b for b in self.bases() if self.names.get(b) == "Longsword")
        lines = ["# somber/unique weapons made infusable (12 affinity rows added, gemMountType=2)",
                 "# weapon  <-  stats derived from reference weapon"]
        for b in self.bases():
            wt = self.orig_type[b]
            if wt not in INFUSABLE_TYPES or len(self.variants(b)) != 1 or not self.named(b):
                continue
            base = W.by_id[b]
            if g(base, "materialSetId") == -1:
                continue                                   # cannot be reinforced at all
            ref = refs.get(wt) or refs.get(REFERENCE_FALLBACK.get(wt, -1)) or clean_ref
            eff_ref = ref if all(g(W.by_id[ref], f) == -1 for f in EFFECT_SLOTS) else clean_ref
            s(base, "gemMountType", 2)
            for a in range(1, 13):
                new = W.add_row(b + a * 100, base)
                self._synthesize(new, base, W.by_id[ref], W.by_id[ref + a * 100],
                                 W.by_id[eff_ref], W.by_id[eff_ref + a * 100])
                if g(base, "sortId") != -1:
                    s(new, "sortId", g(base, "sortId") + SORT_DELTA[a])
            lines.append(f"{b:>9}  {self.names[b]:<40} <-  {self.names.get(ref, ref)}")
        lines.insert(0, f"# {len(lines) - 2} weapons")
        return lines

    def _synthesize(self, new, base, ref0, refa, eref0, erefa) -> None:
        g, s = self.W.get, self.W.set
        scale = g(base, "attackBasePhysics") / g(ref0, "attackBasePhysics") if g(ref0, "attackBasePhysics") else 1.0
        for f in ATTACK_FIELDS:
            r0, ra, bv = g(ref0, f), g(refa, f), g(base, f)
            nv = bv * ra / r0 if r0 else (bv + ra * scale if ra else bv)
            s(new, f, max(0, min(65535, int(round(nv)))))
        for f in SCALING_FIELDS:
            r0, ra, bv = g(ref0, f), g(refa, f), g(base, f)
            nv = bv * ra / r0 if r0 else (bv + ra if ra else bv)
            s(new, f, float(round(nv, 1)))
        for f in COPY_IF_CHANGED:
            if g(ref0, f) != g(refa, f):
                s(new, f, g(refa, f))
        # status effects: the affinity's bleed/poison/frost replaces an innate effect of the
        # same kind (vanilla: Blood Uchigatana swaps its innate bleed for the stronger one).
        # Effect-text ids (spEffectMsgId*) are an unordered list, handled separately.
        eff = [g(base, f) for f in EFFECT_SLOTS]
        msg = [g(base, f) for f in MSG_SLOTS]
        ref_msgs0 = {g(eref0, f) for f in MSG_SLOTS} - {-1}
        added_msgs = [m for f in MSG_SLOTS if (m := g(erefa, f)) != -1 and m not in ref_msgs0]
        removed_msgs = [m for m in ref_msgs0 if m not in {g(erefa, f) for f in MSG_SLOTS}]
        added = replaced = removed = False
        for i, fe in enumerate(EFFECT_SLOTS):
            r0, ra = g(eref0, fe), g(erefa, fe)
            if r0 == ra:
                continue
            if ra == -1:                           # affinity removes the reference's innate effect
                if eff[i] == r0:
                    eff[i], removed = -1, True
                continue
            fam = self.status_family(ra)
            same = [j for j, e in enumerate(eff) if e != -1 and (e == r0 or (fam and self.status_family(e) == fam))]
            if same:
                eff[same[0]], replaced = ra, True
            else:
                empty = [j for j in ([i] + list(range(3))) if eff[j] == -1]
                eff[empty[0] if empty else i], added = ra, True
        if removed:
            msg = [-1 if m in removed_msgs else m for m in msg]
        if added:
            for m in added_msgs:
                if m not in msg and -1 in msg:
                    msg[msg.index(-1)] = m
        for f, v in zip(EFFECT_SLOTS, eff):
            s(new, f, v)
        for f, v in zip(MSG_SLOTS, msg):
            s(new, f, v)

    def status_family(self, sp_id: int) -> str | None:
        """'blood', 'poizon', 'freeze', ... for a status build-up SpEffect, else None."""
        if not hasattr(self, "_sp"):
            self._sp = self.reg.param("SpEffectParam", erreg.load_paramdef(D / "SpEffect.xml"))
            self._sp_fields = [f.name for f in self._sp.pd.fields if f.name.endswith("AttackPower")]
            self._fam_cache = {}
        if sp_id not in self._fam_cache:
            r = self._sp.by_id.get(sp_id)
            fam = None
            if r is not None:
                for f in self._sp_fields:
                    if self._sp.get(r, f) > 0:
                        fam = f[: -len("AttackPower")]
                        break
            self._fam_cache[sp_id] = fam
        return self._fam_cache[sp_id]

    # --- 2. movesets ------------------------------------------------------------------
    def random_movesets(self, rng: random.Random, mode: str = "affinity", variety: int = 3,
                        keep_standard: bool = False, weptype_follows: bool = False,
                        shield_movesets: str = "shields", bow_movesets: str = "bows") -> list[str]:
        """mode="affinity": (default) a different moveset per affinity row (Standard included),
                          wepType untouched, every melee/shield ash unlocked on every melee weapon
                          and shield (the player must pick fitting ones from weapons.txt).
           mode="bound":    per weapon per affinity movesets from per-affinity clusters, ashes keep
                          only the affinities that animate them (see _movesets_bound).
           mode="weapon":   one random moveset per weapon, shared by all its affinity rows, and
                          wepType follows the moveset -> the smithing table only offers Ashes of
                          War whose animations exist for that moveset.  Shields do not take part
                          (their wepType must stay a shield type).
           The pool holds the movesets of all named melee weapons and shields; in modes affinity
           and bound shields receive movesets too.  Every row gets the donor's complete bundle;
           the only hard limit found so far is the regulation.bin size (erreg.REGULATION_MAX_SIZE).
           keep_standard: in mode affinity leave the Standard row of every weapon untouched (bound
           already does; weapon cannot).  weptype_follows (affinity / bound): every randomized row
           also takes the donor's wepType, so the smithing table lists exactly the ashes that
           animate with that row's moveset and the ash unlock is skipped.  Untested against the
           game's save validation: a mounted ash may become invalid after an affinity change.
           shield_movesets: "shields" (default) = shields only swap among the four shield animation
           sets and weapons never get a shield set (a left-hand shield still guards on L1: the
           guard/attack choice for L1 lives in the animation set itself, found in-game 2026-10-17);
           "none" = shields keep their own moveset; "all" = everything swaps with everything.
           bow_movesets: "bows" (default) = every bow / crossbow / ballista takes the moveset of a
           random other bow-class weapon (all modes, wepType and ammo unchanged); "none" = untouched."""
        W, g, s = self.W, self.W.get, self.W.set
        lines_bows = self._bow_movesets(rng) if bow_movesets == "bows" else []
        recipients = MELEE_TYPES if mode == "weapon" else INFUSABLE_TYPES
        pool: dict[tuple, tuple[str, int]] = {}
        for b in self.bases():
            if self.named(b) and self.orig_type[b] in recipients:
                key = (self.orig_type[b],) + tuple(g(W.by_id[b], f) for f in MOVESET_FIELDS)
                pool.setdefault(key, (self.names[b], self.orig_type[b]))
        pool_items = sorted(pool.items())
        n_shield = sum(1 for _, (_, t) in pool_items if t in SHIELD_TYPES)
        lines = [f"# movesets: mode={mode}, {len(pool_items)} distinct movesets in the pool ({n_shield} from shields); "
                 f"shields: {dict(shields='swap only among shield movesets', none='keep their own moveset', all='swap with everything')[shield_movesets]}"]
        if mode == "bound":
            return lines + self._movesets_bound(rng, pool_items, variety, weptype_follows, shield_movesets) + lines_bows
        if mode == "weapon":
            lines += ["# weapon  <-  moveset of (new weapon type; ashes of war offered at the smithing table follow it)",
                      "#           safe = ashes mountable on both the old and the new type (mount one of these on",
                      "#           weapons you already own BEFORE switching regulation.bin, or the save will not load)",
                      "# shields are left alone in this mode"]
        else:
            lines += ["# every affinity row of every melee weapon and shield gets its own moveset"
                      + (" (Standard rows keep their own)" if keep_standard else " (Standard included)")
                      + ("; wepType follows the moveset" if weptype_follows else ""),
                      "# weapon row  <-  moveset of (weapon type whose ashes of war animate with it)"]
        shield_items = [p for p in pool_items if p[1][1] in SHIELD_TYPES]
        weapon_items = [p for p in pool_items if p[1][1] not in SHIELD_TYPES]
        for b in self.bases():
            if not self.named(b) or self.orig_type[b] not in recipients:
                continue
            is_shield = self.orig_type[b] in SHIELD_TYPES
            if is_shield and shield_movesets == "none":
                continue
            own = (self.orig_type[b],) + tuple(g(W.by_id[b], f) for f in MOVESET_FIELDS)
            vs = self.variants(b)
            cand = pool_items if shield_movesets == "all" else (shield_items if is_shield else weapon_items)
            others = [p for p in cand if p[0] != own]
            if mode == "weapon":
                key, (donor, dtype) = rng.choice(others)
                for a in vs:
                    row = W.by_id[b + a * 100]
                    for f, v in zip(MOVESET_FIELDS, key[1:]):
                        if f not in KEEP_OWN_FIELDS:
                            s(row, f, v)
                    s(row, "wepType", dtype)
                    self.moveset_type[row.id] = dtype
                    self.row_cat[row.id] = key[2]
                old_t, new_t = self.orig_type[b], dtype
                safe = sorted(nm for nm, bits in self.ashes.values()
                              if bits >> WEPTYPE_BIT[old_t] & 1 and bits >> WEPTYPE_BIT[new_t] & 1)
                lines.append(f"{b:>9}  {self.names[b]:<36} <-  {donor} ({TYPE_NAMES.get(dtype, dtype)})"
                             f"   safe[{len(safe)}]: {', '.join(safe[:6])}{', ...' if len(safe) > 6 else ''}")
            else:
                if keep_standard:
                    vs = [a for a in vs if a]
                    self.row_cat[b] = own[2]
                picks = rng.sample(others, len(vs)) if len(others) >= len(vs) else [rng.choice(others) for _ in vs]
                for a, (key, (donor, dtype)) in zip(vs, picks):
                    row = W.by_id[b + a * 100]
                    for f, v in zip(MOVESET_FIELDS, key[1:]):
                        if f not in KEEP_OWN_FIELDS:
                            s(row, f, v)
                    if weptype_follows:
                        s(row, "wepType", dtype)
                    self.moveset_type[row.id] = dtype
                    self.row_cat[row.id] = key[2]
                    lines.append(f"{row.id:>9}  {self.name(row.id):<48} <-  {donor} ({TYPE_NAMES.get(dtype, dtype)})")
        if mode == "affinity" and weptype_follows:
            lines += ["", "# wepType follows each row's moveset: the smithing table lists exactly the ashes that",
                      "# animate with the current affinity's moveset (EquipParamGem mount lists untouched)"]
        elif mode == "affinity":
            lines += [""] + self._unlock_ashes(cross_shields=(shield_movesets == "all"))
        lines += lines_bows
        lines += [""] + self._ash_lists()
        return lines

    def _bow_movesets(self, rng: random.Random) -> list[str]:
        """Every named bow / crossbow / ballista takes the complete moveset bundle of a random other
        bow-class weapon (light bow, bow, greatbow, crossbow, ballista animation sets).  wepType is
        never touched, so the ammunition type stays the weapon's own."""
        W, g, s = self.W, self.W.get, self.W.set
        pool: dict[tuple, tuple[str, int]] = {}
        for b in self.bases():
            if self.named(b) and self.orig_type[b] in BOW_TYPES:
                key = (self.orig_type[b],) + tuple(g(W.by_id[b], f) for f in MOVESET_FIELDS)
                pool.setdefault(key, (self.names[b], self.orig_type[b]))
        items = sorted(pool.items())
        lines = ["", f"# bows / crossbows / ballistas: {len(items)} distinct movesets swapped only among themselves "
                     "(wepType and ammunition unchanged)",
                 "# weapon  <-  moveset of"]
        for b in self.bases():
            if not self.named(b) or self.orig_type[b] not in BOW_TYPES:
                continue
            row = W.by_id[b]
            own = (self.orig_type[b],) + tuple(g(row, f) for f in MOVESET_FIELDS)
            others = [p for p in items if p[0] != own]
            if not others:
                continue
            key, (donor, dtype) = rng.choice(others)
            for f, v in zip(MOVESET_FIELDS, key[1:]):
                if f not in KEEP_OWN_FIELDS:
                    s(row, f, v)
            self.moveset_type[row.id] = dtype
            self.row_cat[row.id] = key[2]
            lines.append(f"{b:>9}  {self.names[b]:<36} <-  {donor} ({TYPE_NAMES.get(dtype, dtype)})")
        return lines

    def _movesets_bound(self, rng: random.Random, pool_items, variety: int = 3,
                        weptype_follows: bool = False, shield_movesets: str = "shields") -> list[str]:
        """Every (weapon, affinity>0) row gets its own random moveset:
           * each affinity owns a cluster of `variety` animation categories chosen so that as many
             ashes as possible animate in all of them (e.g. straight sword / katana / light greatsword);
           * every weapon draws, per affinity, one category of that affinity's cluster (all 12
             affinities of a weapon get different categories where possible, never its own) and a
             random concrete moveset of that category;
           * afterwards each Ash of War keeps only the affinities for which *every* weapon it can be
             mounted on uses a category that animates it (EquipParamGem.configurableWepAttr), so the
             smithing table never offers an ash/affinity pair without an animation.
           Standard keeps each weapon's own moveset; wepType stays vanilla.  Shields take part
           like weapons; weapon ashes that keep at least one affinity on the shield rows become
           mountable on shields (bits only added, never removed)."""
        W, g, s = self.W, self.W.get, self.W.set
        by_cat: dict[int, list] = {}
        for key, (donor, dtype) in pool_items:
            by_cat.setdefault(key[2], []).append((key, donor, dtype))   # key[2] = wepmotionCategory
        shield_items = [(key, donor, dtype) for key, (donor, dtype) in pool_items if dtype in SHIELD_TYPES]
        if shield_movesets != "all":      # weapons never take a shield animation set
            by_cat = {c: [d for d in ds if d[2] not in SHIELD_TYPES] for c, ds in by_cat.items()}
            by_cat = {c: ds for c, ds in by_cat.items() if ds}
        # skip perfume / hand-to-hand / plain shield style sets with few skill animations
        elig = sorted(c for c in by_cat if len(self.animated(c)) >= MIN_ASHES_PER_CATEGORY)
        variety = max(1, min(variety, len(elig)))
        anim = {c: self.animated(c) for c in elig}
        # clusters: first category = least used so far, then greedily the ones sharing most ashes
        clusters: dict[int, list[int]] = {}
        used: dict[int, int] = {c: 0 for c in elig}
        for a in range(1, 13):
            least = min(used.values())
            first = rng.choice([c for c in elig if used[c] == least])
            pool, common = [first], set(anim[first])
            while len(pool) < variety:
                rest = [c for c in elig if c not in pool]
                score = {c: (len(common & anim[c]), -used[c]) for c in rest}
                top = max(score.values())
                best = rng.choice([c for c in rest if score[c] == top])
                pool.append(best)
                common &= anim[best]
            for c in pool:
                used[c] += 1
            clusters[a] = pool
        lines = [f"# bound mode (variety={variety}): each affinity owns a cluster of animation categories; every",
                 "# weapon draws its own category per affinity from that cluster. Ashes of war then keep only the",
                 "# affinities whose categories (on every weapon they can be mounted on) animate them.",
                 "# Standard keeps each weapon's own moveset. Shields take part; weapon ashes that still animate",
                 "# on the shield rows at some affinity become mountable on shields (Standard shields keep the",
                 "# shield moveset, so a weapon ash on a Standard shield has no animation)."]
        for a in range(1, 13):
            desc = ", ".join(f"{c} ({'/'.join(sorted({TYPE_NAMES.get(d[2], str(d[2])) for d in by_cat[c]}))})" for c in clusters[a])
            lines.append(f"#   {AFFINITY_NAMES[a]:<9} -> {desc}")
        lines.append("# weapon row  <-  moveset of")
        for b in self.bases():
            if not self.named(b) or self.orig_type[b] not in INFUSABLE_TYPES:
                continue
            own = g(W.by_id[b], "wepmotionCategory")
            is_shield = self.orig_type[b] in SHIELD_TYPES
            if is_shield and shield_movesets != "all":
                for a in self.variants(b):
                    row = W.by_id[b + a * 100]
                    self.row_cat[row.id] = own
                    if a == 0 or shield_movesets == "none":
                        continue
                    key, donor, dtype = rng.choice([d for d in shield_items if d[0][2] != own] or shield_items)
                    for f, v in zip(MOVESET_FIELDS, key[1:]):
                        if f not in KEEP_OWN_FIELDS:
                            s(row, f, v)
                    if weptype_follows:
                        s(row, "wepType", dtype)
                    self.row_cat[row.id] = key[2]
                    self.moveset_type[row.id] = dtype
                    lines.append(f"{row.id:>9}  {self.name(row.id):<48} <-  {donor} ({TYPE_NAMES.get(dtype, dtype)})")
                continue
            taken = {own}
            for a in rng.sample(self.variants(b), len(self.variants(b))):
                row = W.by_id[b + a * 100]
                if a == 0:
                    self.row_cat[row.id] = own
                    continue
                opts = ([c for c in clusters[a] if c not in taken]
                        or [c for c in clusters[a] if c != own] or clusters[a])
                c = rng.choice(opts)
                taken.add(c)
                key, donor, dtype = rng.choice([d for d in by_cat[c] if d[1] != self.names[b]] or by_cat[c])
                for f, v in zip(MOVESET_FIELDS, key[1:]):
                    if f not in KEEP_OWN_FIELDS:
                        s(row, f, v)
                if weptype_follows:
                    s(row, "wepType", dtype)
                self.row_cat[row.id] = c
                self.moveset_type[row.id] = dtype
            for a in self.variants(b):
                if a:
                    row = W.by_id[b + a * 100]
                    lines.append(f"{row.id:>9}  {self.name(row.id):<48} <-  "
                                 f"{TYPE_NAMES.get(self.moveset_type[row.id], '?')} moveset (category {self.row_cat[row.id]})")
        lines += [""] + self._restrict_ash_affinities(weptype_follows)
        return lines

    def _restrict_ash_affinities(self, weptype_follows: bool = False) -> list[str]:
        """Clear configurableWepAttr bits of every real Ash of War for the affinities where some
        weapon it can be mounted on uses an animation category without that ash's animation.
        An ash not yet mountable on every shield type is opened to all shield types when at least
        one affinity animates on every shield row (shields got weapon movesets)."""
        G, W = self.G, self.W
        attr = [f"configurableWepAttr{a:02d}" for a in range(13)]
        off = G.pd["canMountWep_Dagger"].offset
        shield_mask = 0
        for t in SHIELD_TYPES:
            shield_mask |= 1 << WEPTYPE_BIT[t]
        # (wepType, affinity) -> categories actually used by weapons of that type at that affinity
        cats_used: dict[tuple[int, int], set[int]] = {}
        for b in self.bases():
            if not self.named(b) or self.orig_type[b] not in INFUSABLE_TYPES:
                continue
            for a in self.variants(b):
                if a:
                    cats_used.setdefault((self.orig_type[b], a), set()).add(self.row_cat[b + a * 100])

        # weptype_follows: every row's smithing list follows its own moveset, so an ash can be
        # reached on nearly every weapon -> an affinity survives only if every weapon's row at that
        # affinity animates the ash (the cluster rule), whatever the weapon's original type.
        cats_all: dict[int, set[int]] = {}
        for (t, a), cs in cats_used.items():
            cats_all.setdefault(a, set()).update(cs)

        def kept_for(r, sa, types):
            if weptype_follows:
                return [a for a in range(1, 13) if G.get(r, attr[a])
                        and all(sa in self.animated(c) for c in cats_all.get(a, ()))]
            return [a for a in range(1, 13) if G.get(r, attr[a])
                    and all(sa in self.animated(c) for t in types for c in cats_used.get((t, a), ()))]

        removed = standard_only = opened = 0
        lines = ["# ash of war -> affinities still offered (others removed because some weapon that can mount",
                 "# the ash uses an animation category without the ash's animation at that affinity)",
                 "# [+shields] = now mountable on every shield type; its default affinity is the first one listed"]
        for r in G.rows:
            nm = self.gem_names.get(r.id, "")
            sa = G.get(r, "swordArtsParamId")
            if not nm.startswith("Ash of War:") or sa not in self.ashes or G.get(r, "sortId") == 999999:
                continue
            bits = self.ashes[sa][1]
            types = sorted(t for t in INFUSABLE_TYPES if bits >> WEPTYPE_BIT[t] & 1)
            kept = kept_for(r, sa, types)
            tag = ""
            if weptype_follows:
                tag = "  [row types]" if kept else ""
            elif bits & shield_mask != shield_mask:
                with_shields = kept_for(r, sa, sorted(set(types) | SHIELD_TYPES))
                if with_shields:
                    kept = with_shields
                    rb = int.from_bytes(bytes(r.data[off:off + 8]), "little")
                    r.data[off:off + 8] = (rb | shield_mask).to_bytes(8, "little")
                    G.dirty = True
                    opened += 1
                    tag = "  [+shields]"
            for a in range(1, 13):
                if G.get(r, attr[a]) and a not in kept:
                    G.set(r, attr[a], 0)
                    removed += 1
            if G.get(r, "defaultWepAttr") not in (0, *kept):
                G.set(r, "defaultWepAttr", 0)
            if tag and G.get(r, "defaultWepAttr") == 0:
                G.set(r, "defaultWepAttr", kept[0])   # Standard rows keep their own moveset: no animation there
            standard_only += not kept
            lines.append(f"{r.id:>7}  {nm.split(':', 1)[1].strip():<34} "
                         f"{', '.join(AFFINITY_NAMES[a] for a in [0] + kept)}{tag}")
        lines.insert(3, f"# {removed} (ash, affinity) combinations removed; {standard_only} ashes are Standard-only; "
                        f"{opened} ashes opened to shields")
        return lines

    def _unlock_ashes(self, cross_shields: bool = False) -> list[str]:
        """Every Ash of War mountable on some melee type becomes mountable on all melee types, and
        every ash mountable on some shield type on all shield types (one shared group when
        cross_shields), so a weapon can take the ashes that animate with its new moveset and save
        validation never fails because of a moveset change (bits are only ever added)."""
        G = self.G
        off = G.pd["canMountWep_Dagger"].offset
        groups = ([INFUSABLE_TYPES] if cross_shields else [MELEE_TYPES, SHIELD_TYPES]) + [BOW_ASH_TYPES]
        masks = []
        for ts in groups:
            m = 0
            for wt in ts:
                m |= 1 << WEPTYPE_BIT[wt]
            masks.append(m)
        n = 0
        for r in G.rows:
            bits = int.from_bytes(bytes(r.data[off:off + 8]), "little")
            new = bits
            for m in masks:
                if new & m:
                    new |= m
            if new != bits:
                r.data[off:off + 8] = new.to_bytes(8, "little")
                G.dirty = True
                n += 1
        what = ("every melee weapon and shield type, bow ashes on every bow type" if cross_shields
                else "every type of their own group (melee weapons / shields / bows)")
        return [f"# {n} ash of war rows made mountable on {what} (EquipParamGem canMountWep_*)"]

    def _ash_lists(self) -> list[str]:
        lines = ["# ashes of war that have animations for each weapon type (pick from the list of the",
                 "# type named after '<-' above; other ashes can be mounted but may not animate)"]
        for wt in sorted(INFUSABLE_TYPES | BOW_ASH_TYPES):
            names = sorted(nm for nm, bits in self.ashes.values() if bits >> WEPTYPE_BIT[wt] & 1)
            lines.append(f"{TYPE_NAMES.get(wt, wt)}: " + ", ".join(names))
        return lines

    # --- 3. default ash + affinity -----------------------------------------------------
    def _ashes(self) -> dict[int, tuple[str, int]]:
        G, gn = self.G, self.gem_names
        off = G.pd["canMountWep_Dagger"].offset
        ashes: dict[int, tuple[str, int]] = {}
        for r in G.rows:
            nm = gn.get(r.id, "")
            sa = G.get(r, "swordArtsParamId")
            if not nm.startswith("Ash of War:") or sa == -1 or G.get(r, "sortId") == 999999:
                continue                               # sortId 999999 = NPC/test rows mountable on everything
            nm = nm.split(":", 1)[1].strip()
            if nm in ("", "No Skill"):             # unnamed rows are unused test gems
                continue
            bits = int.from_bytes(bytes(r.data[off:off + 8]), "little")
            prev = ashes.get(sa, ("", 0))
            ashes[sa] = (prev[0] or nm, prev[1] | bits)
        return ashes

    def random_default_ash(self, rng: random.Random) -> list[str]:
        W, g, s = self.W, self.W.get, self.W.set
        ashes = self.ashes
        lines = [f"# default skills: {len(ashes)} ashes of war in the pool (chosen to match the row's moveset)",
                 "# weapon row  <-  default skill"]
        for b in self.bases():
            if not self.named(b) or self.orig_type[b] not in INFUSABLE_TYPES | BOW_ASH_TYPES:
                continue
            for a in self.variants(b):
                row = W.by_id[b + a * 100]
                if row.id in self.moveset_type:          # moveset came from another weapon type
                    bit = WEPTYPE_BIT[self.moveset_type[row.id]]
                    cands = [sa for sa, (_, bits) in ashes.items() if bits >> bit & 1]
                    if self.orig_type[b] in BOW_ASH_TYPES:   # bows: must also be mountable on the bow's own type
                        own_bit = WEPTYPE_BIT[self.orig_type[b]]
                        cands = [sa for sa in cands if ashes[sa][1] >> own_bit & 1]
                else:                                   # own moveset: anything that animates in its category
                    cands = sorted(self.animated(self.row_cat.get(row.id, g(row, "wepmotionCategory"))))
                if not cands:
                    continue
                sa = rng.choice(sorted(cands))
                s(row, "swordArtsParamId", sa)
                lines.append(f"{row.id:>9}  {self.name(row.id):<48} <-  {ashes[sa][0]}")
        lines += [""] + self._random_affinity_sources(rng)
        return lines

    def _random_affinity_sources(self, rng: random.Random) -> list[str]:
        lines = ["# affinity of weapons given by item lots / shops / starting classes",
                 "# source  :  old weapon id -> new weapon id"]
        var_cache = {b: self.variants(b) for b in self.bases()}

        def reroll(wid: int):
            b = base_id(wid)
            vs = var_cache.get(b)
            if wid <= 0 or not vs or len(vs) < 2:
                return None
            return b + rng.choice(vs) * 100 + level(wid)

        pdl = erreg.load_paramdef(D / "ItemLotParam.xml")
        for pn in ("ItemLotParam_map", "ItemLotParam_enemy"):
            L = self.reg.param(pn, pdl)
            ln = erreg.load_names(N / f"{pn}.txt")
            for r in L.rows:
                for i in range(1, 9):
                    if L.get(r, f"lotItemCategory0{i}") != 2:
                        continue
                    old = L.get(r, f"lotItemId0{i}")
                    new = reroll(old)
                    if new is not None and new != old:
                        L.set(r, f"lotItemId0{i}", new)
                        lines.append(f"{pn} {r.id} [{ln.get(r.id, '?')}] : {old} -> {new}  ({self.name(new - level(new))})")
        Sh = self.reg.param("ShopLineupParam", erreg.load_paramdef(D / "ShopLineupParam.xml"))
        sn = erreg.load_names(N / "ShopLineupParam.txt")
        for r in Sh.rows:
            if Sh.get(r, "equipType") != 0:
                continue
            old = Sh.get(r, "equipId")
            new = reroll(old)
            if new is not None and new != old:
                Sh.set(r, "equipId", new)
                lines.append(f"ShopLineupParam {r.id} [{sn.get(r.id, '?')}] : {old} -> {new}  ({self.name(new - level(new))})")
        C = self.reg.param("CharaInitParam", erreg.load_paramdef(D / "CharaInitParam.xml"))
        cn = erreg.load_names(N / "CharaInitParam.txt")
        for rid in range(3000, 3010):
            r = C.by_id.get(rid)
            if r is None:
                continue
            for f in ("equip_Wep_Right", "equip_Subwep_Right", "equip_Subwep_Right3",
                      "equip_Wep_Left", "equip_Subwep_Left", "equip_Subwep_Left3"):
                if f not in C.pd:
                    continue
                old = C.get(r, f)
                new = reroll(old)
                if new is not None and new != old:
                    C.set(r, f, new)
                    lines.append(f"CharaInitParam {rid} [{cn.get(rid, '?')}] {f} : {old} -> {new}  ({self.name(new - level(new))})")
        return lines

    # --- 4. per-row stats ---------------------------------------------------------------
    @staticmethod
    def stat_group(wt: int) -> str:
        if wt in INFUSABLE_TYPES:
            return "hand"
        if wt in (55, 56):
            return "xbow"
        if wt in BOW_TYPES:
            return "bow"
        return "catalyst"

    def random_stats(self, rng: random.Random, groups=STAT_GROUPS,
                     stamina_rate: tuple[float, float] = STAMINA_RATE_RANGE) -> list[str]:
        """Random stats for every (weapon, affinity) row of melee weapons, shields, bows, crossbows,
           ballistas, staves and seals (torches untouched):
           attack:       the five attackBase* values of a random donor row of the same class (hand
                         weapons / bows / crossbows / catalysts), elements shuffled (50%: the biggest
                         value stays physical), each +-15%; critical (throwAtkRate), poise damage
                         (saWeaponDamage) and stamina damage (attackBaseStamina) drawn separately;
                         spAttribute follows the main element.
           guard:        physical / elemental guard negation, guard boost (staminaGuardDef) and the
                         seven status resists, shields in the shield range, everything else in the
                         weapon range (bows and crossbows cannot guard and are skipped).
           scaling:      1-4 random attributes share a budget taken from a donor row (+-15%), random
                         CalcCorrectGraph curves, and an AttackElementCorrectParam row (one per attribute
                         set, 31 at most) in which every scaling attribute raises every damage type, so
                         the displayed letters always matter and spell scaling of catalysts follows.
                         Heavy rows never get Dexterity (the Heavy
                         reinforce table multiplies it by 0); crossbows switch to the regular / somber
                         reinforce type so their scaling rates are not 0.
           requirements: every scaling attribute (and 15% of the others) draws from REQ_TIERS
                         (0-10: 40%, 11-20: 30%, 21-30: 20%, 31-40: 9%, 41-60: 1%); when the sum
                         exceeds 60 all values are scaled down proportionally.
           effects:      0-2 status build-ups (bleed, poison, scarlet rot, frost, sleep, madness) from
                         the SpEffect ids vanilla weapons use; rows whose reinforce type raises an effect
                         with the upgrade level (vanilla Blood / Poison / Cold) always carry a growing
                         bleed / poison / frost series in that slot.  Unique non-status on-hit effects
                         are kept.
           stamina:      staminaConsumptionRate uniform in stamina_rate (default 0.3-1.7, 2 decimals);
                         it multiplies the BehaviorParam_PC stamina cost of every attack of the row's
                         moveset (the cost itself comes from the moveset donor after --random-movesets).
           greases:      isEnhance is 1 on every row, so greases / weapon buffs can be applied whatever
                         the element or status build-up (vanilla sets 0 on elemental and status rows and
                         on most unique weapons; bows and shields use their own greases, gated elsewhere)."""
        W, g, s = self.W, self.W.get, self.W.set
        groups = set(groups)
        R = self.reg.param("ReinforceParamWeapon", erreg.load_paramdef(D / "ReinforceParamWeapon.xml"))
        offset_slot: dict[int, int] = {}            # reinforce type -> effect slot that grows with the level
        for r in R.rows:
            for i, f in enumerate(("spEffectId1", "spEffectId2", "spEffectId3")):
                if R.get(r, f):
                    offset_slot[r.id - r.id % 100] = i
        A = self.reg.param("AttackElementCorrectParam", erreg.load_paramdef(D / "AttackElementCorrectParam.xml"))
        targets = [(b, W.by_id[b + a * 100]) for b in self.bases()
                   if self.named(b) and self.orig_type[b] in STAT_TYPES for a in self.variants(b)]
        donors: dict[str, list[dict]] = {}
        for b, row in targets:                      # vanilla values, read before anything is changed
            donors.setdefault(self.stat_group(self.orig_type[b]), []).append({
                "atk": [g(row, f"attackBase{e}") for e in ELEMENTS],
                "stamina": g(row, "attackBaseStamina"), "poise": g(row, "saWeaponDamage"),
                "corr": sum(g(row, f"correct{st}") for st in STATS)})
        lines = [f"# stats: {len(targets)} weapon rows, groups: {', '.join(x for x in STAT_GROUPS if x in groups)}"
                 + (f", stamina rate {stamina_rate[0]:g}-{stamina_rate[1]:g}" if "stamina" in groups else ""),
                 "# row  name  |  atk phys/mag/fire/ltng/holy  crit  poise  stam  |  guard phys/mag/fire/ltng/holy"
                 "  boost  |  req str/dex/int/fai/arc  |  scaling str/dex/int/fai/arc  |  status build-ups"
                 "  |  stamina rate"]
        n_aec = 0
        for b, row in targets:
            wt = self.orig_type[b]
            grp = self.stat_group(wt)
            pool = donors[grp]
            rt = g(row, "reinforceTypeId")
            if "scaling" in groups and rt in CROSSBOW_REINFORCE:
                rt = CROSSBOW_REINFORCE[rt]
                s(row, "reinforceTypeId", rt)
            # attack ---------------------------------------------------------------
            if "attack" in groups:
                vals = list(rng.choice(pool)["atk"])
                if rng.random() < 0.5:                      # biggest value stays physical
                    i = max(range(5), key=lambda k: vals[k])
                    vals[0], vals[i] = vals[i], vals[0]
                    rest = vals[1:]
                    rng.shuffle(rest)
                    vals = [vals[0]] + rest
                else:
                    rng.shuffle(vals)
                vals = [max(0, min(65535, int(round(v * rng.uniform(0.85, 1.15))))) for v in vals]
                if not any(vals):
                    vals[0] = 1
                for e, v in zip(ELEMENTS, vals):
                    s(row, f"attackBase{e}", v)
                s(row, "attackBaseStamina", max(5, min(65535, 5 * int(round(rng.choice(pool)["stamina"] * rng.uniform(0.85, 1.15) / 5)))))
                s(row, "saWeaponDamage", rng.choice(pool)["poise"])
                s(row, "throwAtkRate", rng.choices(CRIT_VALUES, CRIT_WEIGHTS)[0])
                main = max(ELEMENTS[1:], key=lambda e: g(row, f"attackBase{e}"))
                s(row, "spAttribute", SP_ATTRIBUTE[main] if g(row, f"attackBase{main}") else 0)
            atk = [g(row, f"attackBase{e}") for e in ELEMENTS]
            # guard ----------------------------------------------------------------
            if "guard" in groups and grp in ("hand", "catalyst"):
                r5 = lambda lo, hi: 5 * rng.randint(lo // 5, hi // 5)      # multiples of 5 compress better
                if wt in SHIELD_TYPES:
                    phys = 100 if rng.random() < 0.35 else r5(60, 95)
                    elem, boost, resist = (15, 90), (35, 85), (15, 50)
                else:
                    phys, elem, boost, resist = r5(10, 90), (10, 70), (15, 60), (9, 29)
                s(row, GUARD_CUT[0], float(phys))
                for f in GUARD_CUT[1:]:
                    s(row, f, float(r5(*elem)))
                s(row, "staminaGuardDef", r5(*boost))
                resist = rng.randint(*resist)              # one value for all seven, as in vanilla
                for f in GUARD_RESIST:
                    s(row, f, resist)
            # scaling --------------------------------------------------------------
            if "scaling" in groups:
                avail = [st for st in STATS if not (rt == 100 and st == "Agility")]
                chosen = rng.sample(avail, min(rng.choices((1, 2, 3, 4), (30, 45, 20, 5))[0], len(avail)))
                cpool = donors["bow"] if grp == "xbow" else pool
                total = 0.0
                for _ in range(8):
                    total = rng.choice(cpool)["corr"] * rng.uniform(0.85, 1.15)
                    if total >= 15:
                        break
                if total < 15:
                    total = rng.uniform(40, 90)
                w = [rng.uniform(0.15, 1.0) for _ in chosen]
                for st in STATS:
                    v = round(total * w[chosen.index(st)] / sum(w)) if st in chosen else 0
                    s(row, f"correct{st}", float(v))
                if grp == "catalyst":
                    c = rng.choice(CATALYST_CURVES)
                    for e in ELEMENTS:
                        s(row, f"correctType_{e}", c)
                else:
                    s(row, "correctType_Physics", rng.choice(PHYS_CURVES))
                    for e in ELEMENTS[1:]:
                        s(row, f"correctType_{e}", rng.choice(ELEM_CURVES))
                smask = sum(1 << i for i, st in enumerate(STATS) if st in chosen)
                aid = AEC_NEW + smask       # bits for damage types the row lacks are harmless (0 attack)
                if aid not in A.by_id:
                    ar = A.add_row(aid, A.by_id[AEC_BASE])
                    for i, st in enumerate(STATS):
                        for e in ELEMENTS:
                            A.set(ar, f"is{AEC_STAT[st]}Correct_by{e}", smask >> i & 1)
                    n_aec += 1
                s(row, "attackElementCorrectId", aid)
            scaling_stats = [st for st in STATS if g(row, f"correct{st}") > 0]
            # requirements ---------------------------------------------------------
            if "requirements" in groups:
                req = {st: 0 for st in STATS}
                for st in STATS:
                    if st in scaling_stats or rng.random() < REQ_EXTRA_CHANCE:
                        req[st] = tiered(rng, REQ_TIERS)
                req = cap_total(req, REQ_TOTAL_MAX)
                for st in STATS:
                    s(row, f"proper{st}", req[st])
            # status build-ups -----------------------------------------------------
            if "effects" in groups:
                slot = offset_slot.get(rt)
                eff = [g(row, f) for f in EFFECT_SLOTS]
                msg = [g(row, f) for f in MSG_SLOTS]
                eff = [-1 if (e != -1 and self.status_family(e)) else e for e in eff]
                msg = [-1 if m in STATUS_MSG_IDS else m for m in msg]
                fams = rng.sample(sorted(STATUS_FLAT), rng.choices((0, 1, 2), (45, 40, 15))[0])
                if slot is not None and eff[slot] == -1:
                    if not any(f in STATUS_SERIES for f in fams):
                        fams = [rng.choice(sorted(STATUS_SERIES))] + fams[:1]
                    fams.sort(key=lambda f: f not in STATUS_SERIES)     # series family first
                for fam in fams:
                    if slot is not None and eff[slot] == -1 and fam in STATUS_SERIES:
                        eff[slot] = rng.choice(STATUS_SERIES[fam])
                    else:
                        free = [i for i in range(3) if eff[i] == -1 and i != slot]
                        if not free:
                            continue
                        eff[free[0]] = rng.choice(STATUS_FLAT[fam])
                    if -1 in msg:
                        msg[msg.index(-1)] = STATUS_MSG[fam]
                for f, v in zip(EFFECT_SLOTS, eff):
                    s(row, f, v)
                for f, v in zip(MSG_SLOTS, msg):
                    s(row, f, v)
            s(row, "isEnhance", 1)                  # greases / buffs on every row, whatever it rolled
            # stamina consumption ----------------------------------------------------
            if "stamina" in groups:
                s(row, "staminaConsumptionRate", round(rng.uniform(*stamina_rate), 2))
            # report ---------------------------------------------------------------
            effs = [self.status_family(e) for e in (g(row, f) for f in EFFECT_SLOTS) if e != -1]
            effs = [STATUS_LABEL.get(x, "unique") for x in effs]
            guard = "-" if grp in ("bow", "xbow") else ("/".join(str(int(g(row, f))) for f in GUARD_CUT)
                                                           + f" boost {g(row, 'staminaGuardDef')}")
            lines.append(f"{row.id:>9}  {self.name(row.id):<44} | atk {'/'.join(map(str, atk))} "
                         f"crit {100 + g(row, 'throwAtkRate')} poise {g(row, 'saWeaponDamage'):g} "
                         f"stam {g(row, 'attackBaseStamina')} | guard {guard} | req "
                         + "/".join(str(g(row, f"proper{st}")) for st in STATS) + " | scl "
                         + "/".join(f"{g(row, f'correct{st}'):g}" for st in STATS)
                         + " | " + (", ".join(effs) if effs else "-")
                         + f" | rate {g(row, 'staminaConsumptionRate'):.2f}")
        lines.insert(1, f"# {n_aec} AttackElementCorrectParam rows added (ids {AEC_NEW}+)")
        return lines
