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


def get_cyber_pool(action_type: str, attributes: dict, skills: dict,
                   specialisations: list[str] | None = None,
                   gm_modifier: int = 0) -> tuple[int, str]:
    """Calculate the dice pool for a cyber action.

    Args:
        action_type: One of gain_access, deploy, defend, detect.
        attributes: Character attributes dict {power: {mental, physical, social}, ...}
        skills: Character skills dict {mental: {Computer: N, ...}, ...}
        specialisations: List of skill specialisation strings.
        gm_modifier: Bonus/penalty dice from GM.

    Returns:
        Tuple of (pool_size, pool_description).
    """
    computers = skills.get("mental", {}).get("Computer", 0)

    # Determine which attribute to use
    attr_name = ""
    attr_value = 0
    if action_type == "gain_access":
        attr_name = "Intelligence"
        attr_value = attributes.get("power", {}).get("mental", 1)
    elif action_type == "deploy":
        attr_name = "Wits"
        attr_value = attributes.get("finesse", {}).get("mental", 1)
    elif action_type in ("defend", "detect"):
        attr_name = "Resolve"
        attr_value = attributes.get("resistance", {}).get("mental", 1)

    pool = attr_value + computers + gm_modifier

    # Check for relevant specialisations
    spec_bonus = 0
    if specialisations:
        cyber_specs = ["hacking", "encryption", "network security", "intrusion",
                       "cybersecurity", "cyber warfare", "digital forensics"]
        for spec in specialisations:
            if spec.lower() in cyber_specs:
                spec_bonus = 1
                break
    pool += spec_bonus

    parts = [f"{attr_name} {attr_value}", f"Computer {computers}"]
    if gm_modifier:
        parts.append(f"GM modifier {gm_modifier:+d}")
    if spec_bonus:
        parts.append(f"Specialisation +1")
    desc = " + ".join(parts) + f" = {pool} dice"

    return pool, desc
