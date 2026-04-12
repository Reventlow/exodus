#!/usr/bin/env python3
"""
Balance test for the Cyber Terminal system.

Runs 100 simulated encounters per configuration with varying
attacker/defender stat levels to check:
- Gain Access success rate
- Passive detection rate
- Average deploy actions available
- Exceptional success rate
- Chance die scenarios
"""

import sys
import os

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "exodus.settings")
sys.path.insert(0, os.path.dirname(__file__))

import django
django.setup()

from comms.dice import roll_dice

RUNS = 100


def simulate_gain_access(attacker_int, attacker_comp, defender_res, defender_comp,
                         attacker_merits=0, defense_bonus=0, difficulty_penalty=0,
                         mental_load=0):
    """Simulate a Gain Access attempt and passive detection."""
    pool = attacker_int + attacker_comp + attacker_merits - mental_load - difficulty_penalty
    result = roll_dice(pool)

    if result.successes == 0:
        return {
            "access": False, "exceptional": False, "detected": False,
            "successes": 0, "deploys": 0, "chance_die": pool <= 0,
        }

    s = result.successes
    exceptional = s >= 5
    deploys = s // 2

    # Passive detection (skip if exceptional)
    detected = False
    if not exceptional and defender_comp >= 1:
        detect_pool = defender_res + defender_comp + defense_bonus
        detect_result = roll_dice(detect_pool)
        detected = detect_result.successes >= s

    return {
        "access": True, "exceptional": exceptional, "detected": detected,
        "successes": s, "deploys": deploys, "chance_die": pool <= 0,
    }


def simulate_deploy_with_detection(attacker_successes, defender_res, defender_comp,
                                   defense_bonus=0):
    """Simulate passive detection on a deploy action."""
    if defender_comp < 1:
        return False
    detect_pool = defender_res + defender_comp + defense_bonus
    detect_result = roll_dice(detect_pool)
    return detect_result.successes >= attacker_successes


def simulate_defend(defender_res, defender_comp, merits=0, mental_load=0):
    """Simulate a Defend action."""
    pool = defender_res + defender_comp + merits - mental_load
    result = roll_dice(pool)
    return result.successes


def simulate_sweep(intelligence, computer, merits=0, mental_load=0, difficulty=3):
    """Simulate a Sweep & Clear roll against a condition."""
    pool = intelligence + computer + merits - mental_load
    result = roll_dice(pool)
    return result.successes >= difficulty, result.successes


def run_scenario(name, attacker_int, attacker_comp, defender_res, defender_comp,
                 attacker_merits=0, defense_bonus=0, difficulty_penalty=0,
                 mental_load=0):
    """Run RUNS simulations and report stats."""
    access_count = 0
    exceptional_count = 0
    detected_on_access = 0
    total_successes = 0
    total_deploys = 0
    chance_die_count = 0
    deploy_detected = 0
    deploy_total = 0

    for _ in range(RUNS):
        r = simulate_gain_access(
            attacker_int, attacker_comp, defender_res, defender_comp,
            attacker_merits, defense_bonus, difficulty_penalty, mental_load,
        )
        if r["chance_die"]:
            chance_die_count += 1
        if r["access"]:
            access_count += 1
            total_successes += r["successes"]
            total_deploys += r["deploys"]
            if r["exceptional"]:
                exceptional_count += 1
            if r["detected"]:
                detected_on_access += 1

            # Simulate deploy actions with detection
            for _ in range(r["deploys"]):
                deploy_total += 1
                if simulate_deploy_with_detection(
                    r["successes"], defender_res, defender_comp, defense_bonus
                ):
                    deploy_detected += 1

    avg_succ = total_successes / access_count if access_count else 0
    avg_deploys = total_deploys / access_count if access_count else 0

    print(f"\n{'='*70}")
    print(f"SCENARIO: {name}")
    print(f"  Attacker: Int {attacker_int} + Comp {attacker_comp} + merits {attacker_merits} - ML {mental_load} - penalty {difficulty_penalty}")
    print(f"  Defender: Res {defender_res} + Comp {defender_comp} + defense {defense_bonus}")
    print(f"  Pool: {attacker_int + attacker_comp + attacker_merits - mental_load - difficulty_penalty}")
    print(f"{'='*70}")
    print(f"  Access rate:      {access_count}/{RUNS} ({access_count*100//RUNS}%)")
    print(f"  Exceptional:      {exceptional_count}/{RUNS} ({exceptional_count*100//RUNS}%)")
    print(f"  Detected on GA:   {detected_on_access}/{access_count if access_count else 1} ({detected_on_access*100//(access_count or 1)}%)")
    print(f"  Avg successes:    {avg_succ:.1f}")
    print(f"  Avg deploys:      {avg_deploys:.1f}")
    print(f"  Chance die:       {chance_die_count}/{RUNS}")
    if deploy_total:
        print(f"  Deploy detections:{deploy_detected}/{deploy_total} ({deploy_detected*100//deploy_total}%)")
    print()


def run_defend_scenarios():
    """Test defend action outcomes."""
    print(f"\n{'='*70}")
    print("DEFEND ACTION OUTCOMES (100 rolls each)")
    print(f"{'='*70}")

    for res, comp, merits, label in [
        (2, 2, 0, "Low defender (Res 2, Comp 2)"),
        (3, 4, 0, "Mid defender (Res 3, Comp 4)"),
        (3, 4, 2, "Mid defender + Computer Aptitude"),
        (4, 5, 4, "High defender (Res 4, Comp 5, +4 merits)"),
        (2, 4, 0, "Defender with mental load 2"),
    ]:
        ml = 2 if "mental load" in label else 0
        results = [simulate_defend(res, comp, merits, ml) for _ in range(RUNS)]
        avg = sum(results) / len(results)
        dist = {}
        for r in results:
            dist[r] = dist.get(r, 0) + 1
        print(f"  {label}: avg {avg:.1f} successes | pool {res+comp+merits-ml}")
        print(f"    Distribution: {dict(sorted(dist.items()))}")


def run_sweep_scenarios():
    """Test sweep & clear outcomes."""
    print(f"\n{'='*70}")
    print("SWEEP & CLEAR OUTCOMES (100 rolls each, difficulty 3)")
    print(f"{'='*70}")

    for intel, comp, merits, ml, label in [
        (2, 2, 0, 0, "Low (Int 2, Comp 2)"),
        (3, 4, 0, 0, "Mid (Int 3, Comp 4)"),
        (4, 4, 2, 0, "High (Int 4, Comp 4, Aptitude +2)"),
        (3, 4, 0, 2, "Mid with mental load 2"),
        (4, 5, 4, 0, "Max (Int 4, Comp 5, +4 merits)"),
    ]:
        cleared = 0
        total_succ = 0
        for _ in range(RUNS):
            c, s = simulate_sweep(intel, comp, merits, ml, difficulty=3)
            if c:
                cleared += 1
            total_succ += s
        print(f"  {label}: clear rate {cleared}% | avg {total_succ/RUNS:.1f} succ | pool {intel+comp+merits-ml}")


# ===== RUN ALL SCENARIOS =====

print("CYBER TERMINAL BALANCE TEST")
print(f"Running {RUNS} simulations per scenario\n")

# === GAIN ACCESS SCENARIOS ===
print("\n" + "="*70)
print("GAIN ACCESS SCENARIOS")
print("="*70)

# Novice attacker vs unskilled defender
run_scenario("Novice vs Unskilled",
    attacker_int=2, attacker_comp=4,
    defender_res=2, defender_comp=0)

# Novice attacker vs skilled defender
run_scenario("Novice vs Skilled Defender",
    attacker_int=2, attacker_comp=4,
    defender_res=3, defender_comp=3)

# Mid attacker vs mid defender
run_scenario("Mid vs Mid",
    attacker_int=3, attacker_comp=4,
    defender_res=3, defender_comp=4)

# High attacker vs mid defender
run_scenario("High vs Mid",
    attacker_int=4, attacker_comp=5,
    defender_res=3, defender_comp=4)

# High attacker with merits vs high defender with defense
run_scenario("High+Merits vs High+Defense",
    attacker_int=4, attacker_comp=5, attacker_merits=4,
    defender_res=4, defender_comp=5, defense_bonus=3)

# Mid attacker with mental load
run_scenario("Mid with Mental Load 3",
    attacker_int=3, attacker_comp=4,
    defender_res=3, defender_comp=4,
    mental_load=3)

# Re-entry with difficulty penalty
run_scenario("Mid attacker, 2nd attempt (+1 penalty)",
    attacker_int=3, attacker_comp=4,
    defender_res=3, defender_comp=4,
    difficulty_penalty=1)

run_scenario("Mid attacker, 3rd attempt (+2 penalty)",
    attacker_int=3, attacker_comp=4,
    defender_res=3, defender_comp=4,
    difficulty_penalty=2)

# Bot Farm scenario
run_scenario("Mid + Bot Farm (+4) vs Mid (defender +2)",
    attacker_int=3, attacker_comp=4, attacker_merits=4,
    defender_res=3, defender_comp=4, defense_bonus=2)

# Valentina Ruiz (Int 4, Comp 4, Computer Aptitude +2) vs Wei (Int 3, Comp 3)
run_scenario("Valentina vs Zhang Wei",
    attacker_int=4, attacker_comp=4, attacker_merits=2,
    defender_res=2, defender_comp=3)

# === DEFEND & SWEEP ===
run_defend_scenarios()
run_sweep_scenarios()

print("\n" + "="*70)
print("BALANCE ANALYSIS")
print("="*70)
print("""
Key observations to check:
- Novice vs Unskilled: Should almost always gain access (no detection possible)
- Mid vs Mid: ~70-80% access, ~30-50% detection — tension sweet spot
- High vs High+Defense: Should still be viable but risky
- Mental load: Should noticeably reduce effectiveness
- Re-entry penalties: Each attempt should be harder
- Bot Farm: Big boost but defender also gets help
- Defend: 1-3 successes typical, occasionally 4-5
- Sweep: Should take multiple rolls to clear difficulty 3
""")
