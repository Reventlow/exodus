"""World of Darkness 2.0 dice roller for the cyber terminal.

Rules:
- Pool = attribute + skill + modifiers
- Each die is a d10
- Success on 8+ (>= 8)
- 10s explode (roll an additional die)
- Exceptional success: 5+ successes
- Dramatic failure: zero successes when any die shows 1 (only on chance die / 0-pool)
"""

import random
from dataclasses import dataclass, field


@dataclass
class RollResult:
    """Result of a WoD 2.0 dice roll."""

    dice_pool: int
    rolls: list[int] = field(default_factory=list)
    successes: int = 0
    is_exceptional: bool = False
    is_dramatic_failure: bool = False

    def to_dict(self) -> dict:
        return {
            "dicePool": self.dice_pool,
            "rolls": self.rolls,
            "successes": self.successes,
            "isExceptional": self.is_exceptional,
            "isDramaticFailure": self.is_dramatic_failure,
        }


def roll_dice(pool: int) -> RollResult:
    """Roll a WoD 2.0 dice pool.

    Args:
        pool: Number of dice to roll. If <= 0, rolls a single chance die.
    """
    result = RollResult(dice_pool=max(pool, 0))

    if pool <= 0:
        # Chance die: single d10, only 10 succeeds, 1 is dramatic failure
        die = random.randint(1, 10)
        result.rolls = [die]
        if die == 10:
            result.successes = 1
        elif die == 1:
            result.is_dramatic_failure = True
            result.successes = 0
        else:
            result.successes = 0
        return result

    rolls = []
    dice_to_roll = pool
    while dice_to_roll > 0:
        new_rolls = [random.randint(1, 10) for _ in range(dice_to_roll)]
        rolls.extend(new_rolls)
        # 10s explode — count them and roll again
        dice_to_roll = sum(1 for d in new_rolls if d == 10)

    result.rolls = rolls
    result.successes = sum(1 for d in rolls if d >= 8)
    result.is_exceptional = result.successes >= 5

    return result


# Deploy sub-action pool definitions: {action: (attribute_path, skill_category, skill_name)}
DEPLOY_POOLS = {
    "backdoor":       (("finesse", "mental"),    "mental", "Computer"),      # Wits + Computer
    "ransomware":     (("finesse", "mental"),    "mental", "Computer"),      # Wits + Computer
    "bad_deals":      (("finesse", "social"),    "mental", "Computer"),      # Manipulation + Computer
    "steal_intel":    (("power", "mental"),      "mental", "Computer"),      # Intelligence + Computer
    "discover_base":  (("power", "mental"),      "mental", "Investigation"), # Intelligence + Investigation
    "base_access":    (("power", "mental"),      "mental", "Computer"),      # Intelligence + Computer
    "plant_intel":    (("finesse", "social"),    "mental", "Computer"),      # Manipulation + Computer
    "exfil_comms":    (("finesse", "mental"),    "mental", "Computer"),      # Wits + Computer
    "sabotage":       (("finesse", "mental"),    "mental", "Computer"),      # Wits + Computer
    "shutdown_infra":  (("finesse", "mental"),    "mental", "Computer"),      # Wits + Computer
    "close_connection": (("finesse", "mental"),  "mental", "Computer"),      # Wits + Computer
}

ATTR_NAMES = {
    ("power", "mental"): "Intelligence",
    ("power", "physical"): "Strength",
    ("power", "social"): "Presence",
    ("finesse", "mental"): "Wits",
    ("finesse", "physical"): "Dexterity",
    ("finesse", "social"): "Manipulation",
    ("resistance", "mental"): "Resolve",
    ("resistance", "physical"): "Stamina",
    ("resistance", "social"): "Composure",
}


# Merits that affect cyber terminal rolls
# name_lower: (bonus_type, bonus_value_or_"rating", applicable_actions)
# bonus_type: "flat" = fixed bonus, "rating" = bonus equals merit rating
CYBER_MERITS = {
    "computer aptitude":    ("flat", 2, ("gain_access", "deploy", "defend", "detect")),
    "digital infiltration": ("rating", 0, ("gain_access", "deploy")),
    "digital ghost":        ("flat", 2, ("gain_access", "deploy")),
    "firewall":             ("rating", 0, ("defend", "detect")),
    "rapid processing":     ("flat", 2, ("gain_access", "deploy", "defend", "detect")),
    "network puppet":       ("flat", 2, ("deploy",)),  # Bonus on deploy (especially infrastructure)
    "overclock":            ("flat", 3, ("gain_access", "deploy")),  # One-time +3, tracked separately
}


def get_cyber_pool(action_type: str, attributes: dict, skills: dict,
                   specialisations: list[str] | None = None,
                   gm_modifier: int = 0,
                   deploy_action: str = "",
                   merits: list[dict] | None = None,
                   pulling_strings: list[dict] | None = None,
                   use_zero_day: bool = False) -> tuple[int, str, dict]:
    """Calculate the dice pool for a cyber action.

    Args:
        action_type: One of gain_access, deploy, defend, detect.
        attributes: Character attributes dict {power: {mental, physical, social}, ...}
        skills: Character skills dict {mental: {Computer: N, ...}, ...}
        specialisations: List of skill specialisation strings.
        gm_modifier: Bonus/penalty dice from GM.
        deploy_action: Sub-action for deploy (e.g. 'backdoor', 'ransomware').
        merits: List of merit dicts [{name, rating}, ...] from the character/NPC.
        pulling_strings: List of pulling string dicts [{name}, ...].
        use_zero_day: Whether to consume a zero-day from the agency pool.

    Returns:
        Tuple of (pool_size, pool_description, flags_dict).
        flags_dict may contain: free_deploy, defender_bonus, close_penalty, zero_day_used
    """
    # Determine attribute and skill based on action type
    if action_type == "deploy" and deploy_action in DEPLOY_POOLS:
        attr_path, skill_cat, skill_name = DEPLOY_POOLS[deploy_action]
    elif action_type == "gain_access":
        attr_path, skill_cat, skill_name = ("power", "mental"), "mental", "Computer"
    elif action_type == "deploy":
        attr_path, skill_cat, skill_name = ("finesse", "mental"), "mental", "Computer"
    elif action_type in ("defend", "detect"):
        attr_path, skill_cat, skill_name = ("resistance", "mental"), "mental", "Computer"
    else:
        attr_path, skill_cat, skill_name = ("finesse", "mental"), "mental", "Computer"

    attr_name = ATTR_NAMES.get(attr_path, "?")
    attr_value = attributes.get(attr_path[0], {}).get(attr_path[1], 1)
    skill_value = skills.get(skill_cat, {}).get(skill_name, 0)

    pool = attr_value + skill_value + gm_modifier

    # Check for relevant specialisations
    spec_bonus = 0
    if specialisations:
        cyber_specs = ["hacking", "encryption", "network security", "intrusion",
                       "cybersecurity", "cyber warfare", "digital forensics"]
        for spec in specialisations:
            if isinstance(spec, dict):
                spec_name = spec.get("name", "").lower()
            else:
                spec_name = str(spec).lower()
            if spec_name in cyber_specs:
                spec_bonus = 1
                break
    pool += spec_bonus

    # Check for cyber merits
    merit_bonus = 0
    merit_names = []
    if merits:
        for m in merits:
            m_name = (m.get("name") or m.get("merit_name", "")).lower()
            if m_name in CYBER_MERITS:
                bonus_type, bonus_val, applicable = CYBER_MERITS[m_name]
                if action_type in applicable:
                    if bonus_type == "flat":
                        merit_bonus += bonus_val
                        merit_names.append(f"{m.get('name', m_name).title()} +{bonus_val}")
                    elif bonus_type == "rating":
                        rating = m.get("rating", m.get("dots", 1))
                        merit_bonus += rating
                        merit_names.append(f"{m.get('name', m_name).title()} +{rating}")
    pool += merit_bonus

    # Check pulling strings
    ps_bonus = 0
    ps_names = []
    flags = {}
    if pulling_strings:
        ps_lower = {(ps.get("name") or "").lower(): ps for ps in pulling_strings}

        # Bot Farm: +4 gain access, but defender gets +2
        if "bot farm" in ps_lower and action_type == "gain_access":
            ps_bonus += 4
            ps_names.append("Bot Farm +4")
            flags["defender_bonus"] = 2

        # Backdoor Access: free deploy on infrastructure shutdown
        if "backdoor access" in ps_lower and deploy_action == "shutdown_infra":
            flags["free_deploy"] = True
            ps_names.append("Backdoor Access (free action)")

        # Compromise Firmware / Digital Payload: free deploy on sabotage, +4 close penalty
        for name in ("compromise firmware", "digital payload"):
            if name in ps_lower and deploy_action == "sabotage":
                flags["free_deploy"] = True
                flags["close_penalty"] = 4
                ps_names.append(f"{name.title()} (free action, +4 close diff)")
                break
            if name in ps_lower and deploy_action == "close_connection":
                # This would already be handled but flag the penalty
                flags["close_penalty"] = flags.get("close_penalty", 0) + 4

    # Zero-Day Repository: +6 attack roll
    if use_zero_day and action_type in ("gain_access", "deploy"):
        ps_bonus += 6
        ps_names.append("Zero-Day Exploit +6")
        flags["zero_day_used"] = True

    pool += ps_bonus

    parts = [f"{attr_name} {attr_value}", f"{skill_name} {skill_value}"]
    if gm_modifier:
        parts.append(f"GM modifier {gm_modifier:+d}")
    if spec_bonus:
        parts.append("Specialisation +1")
    for mn in merit_names:
        parts.append(mn)
    for pn in ps_names:
        parts.append(pn)
    desc = " + ".join(parts) + f" = {pool} dice"

    return pool, desc, flags


def get_helper_bonus(npc) -> int:
    """Calculate helper dice bonus: (Computer + Wits) // 2."""
    computer = npc.skills.get("mental", {}).get("Computer", 0)
    wits = npc.attributes.get("finesse", {}).get("mental", 1)
    return (computer + wits) // 2


def get_concealment_max(npc) -> int:
    """Calculate digital concealment max: Computer + Resolve + merit bonuses."""
    computer = npc.skills.get("mental", {}).get("Computer", 0)
    resolve = npc.attributes.get("resistance", {}).get("mental", 1)
    bonus = 0
    # Digital Ghost adds +2 concealment levels
    for nm in npc.npc_merits.select_related("merit").all():
        if nm.merit.name.lower() == "digital ghost":
            bonus += 2
            break
    return computer + resolve + bonus


def get_concealment_defender_bonus(damage: int, max_levels: int) -> int:
    """Get defender bonus from helper's concealment damage.

    Last 4 levels give +1, +2, +3, +4 to defender detection.
    """
    if max_levels <= 0:
        return 0
    threshold = max_levels - 4  # First box that gives a bonus
    if damage <= threshold:
        return 0
    return min(damage - threshold, 4)
