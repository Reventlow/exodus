#!/usr/bin/env python3
"""Base building balance tester.

Tests various base configurations against the thrive system to find:
- Elements that never contribute meaningfully
- Combinations that are overpowered or underpowered
- Global penalty thresholds that are too harsh or too lenient
- Optimal builds per base type
"""

# Facility -> department bonuses (mirrors serializers.py)
FACILITY_DEPT = {
    "barracks":      {"military": 2},
    "armory":        {"military": 1, "admin": -1},
    "training":      {"military": 2},
    "shipyard":      {"military": 1, "engineering_ops": 1},
    "motor":         {"military": 1},
    "aviation":      {"military": 1},
    "brig":          {"military": 1, "intelligence": 1, "admin": -1},
    "intel_archive": {"intelligence": 2},
    "comms_centre":  {"intelligence": 1, "engineering_ops": 1},
    "interrogation": {"intelligence": 2, "diplomatic_corps": -1, "admin": -1},
    "computer_core": {"engineering_ops": 2, "intelligence": 1},
    "fabrication":   {"engineering_ops": 2},
    "power_plant":   {"engineering_ops": 1},
    "workspace":     {"engineering_ops": 1},
    "drone_bay":     {"engineering_ops": 1, "military": 1},
    "laboratory":    {"science_ops": 2},
    "medical":       {"science_ops": 1},
    "observatory":   {"science_ops": 2},
    "xenotech_vault": {"science_ops": 2, "military": -1},
    "hydroponics":   {"science_ops": 1},
    "Diplomatic":    {"diplomatic_corps": 2},
    "hr":            {"diplomatic_corps": 1, "admin": 1},
    "safe_room":     {"diplomatic_corps": 1, "intelligence": 1},
    "general":       {"admin": 1},
    "living":        {"admin": 1},
    "recreation":    {"admin": 2},
    "storage":       {"admin": 1},
}

EQUIPMENT_DEPT = {
    "internal_security":   {"admin": 1},
    "segmented_security":  {"intelligence": 1},
    "high_level_monitoring": {"intelligence": 1, "science_ops": -1, "engineering_ops": -1},
}

ALL_DEPTS = ["military", "intelligence", "engineering_ops", "science_ops", "diplomatic_corps", "admin"]

LABELS = {
    1: "Collapsing", 2: "Critical", 3: "Struggling", 4: "Strained",
    5: "Stable", 6: "Functional", 7: "Thriving", 8: "Flourishing",
    9: "Exemplary", 10: "Pinnacle",
}

# Location types with space
LOCATIONS = {
    "safe_house": 4,
    "black_site": 8,
    "estate": 8,
    "official_building": 12,
    "military_base": 30,
    "observitorium": 20,
    "vessel": 12,
}

# Merits that add space
SPACE_MERITS = {
    "extra_large": 10,
    "super_large": 20,
}


def calc_thrive(facilities, workspaces=0, equipment=None, location_space=0,
                merits=None, fringe_count=0, is_isolated=False):
    """Calculate thrive for a base configuration.

    Args:
        facilities: list of (key, level) tuples
        workspaces: number of workspaces
        equipment: list of equipment keys
        location_space: total base space (location + merits)
        merits: set of merit keys
        fringe_count: number of active fringe projects on base
        is_isolated: underwater/mobile/orbital
    """
    equipment = equipment or []
    merits = merits or set()
    total_count = len(facilities) + workspaces

    # Facility bonuses
    raw = {}
    for key, level in facilities:
        mapping = FACILITY_DEPT.get(key, {})
        for dept, bonus in mapping.items():
            raw[dept] = raw.get(dept, 0) + bonus
    raw["engineering_ops"] = raw.get("engineering_ops", 0) + workspaces

    # Equipment bonuses
    for eq_key in equipment:
        mapping = EQUIPMENT_DEPT.get(eq_key, {})
        for dept, bonus in mapping.items():
            raw[dept] = raw.get(dept, 0) + bonus

    # Global modifiers
    global_mod = 0
    reasons = []

    living_max = max((lvl for key, lvl in facilities if key == "living"), default=0)
    general_rec = sum(1 for key, _ in facilities if key in ("general", "recreation"))
    has_medical = any(key == "medical" for key, _ in facilities)
    has_power = any(key == "power_plant" for key, _ in facilities)

    # Housing
    if location_space > 12 and total_count >= 5:
        if living_max == 0:
            mod = -2 if total_count >= 11 else -1
            global_mod += mod
            reasons.append(f"No housing: {mod:+d}")
        elif living_max == 1:
            global_mod -= 1
            reasons.append("Basic housing: -1")
        elif living_max >= 3:
            global_mod += 1
            reasons.append("Luxury housing: +1")

    # Medical
    if total_count >= 8 and not has_medical:
        global_mod -= 1
        reasons.append("No medical: -1")

    # Amenities
    if total_count >= 6:
        ratio = general_rec / total_count if total_count > 0 else 0
        if ratio < 0.10:
            global_mod -= 1
            reasons.append(f"Poor amenities ({ratio:.0%}): -1")
        elif ratio >= 0.20:
            global_mod += 1
            reasons.append(f"Good amenities ({ratio:.0%}): +1")

    # Power (isolated only)
    if is_isolated and not has_power:
        global_mod -= 1
        reasons.append("No power (isolated): -1")

    # Fringe
    if fringe_count > 0:
        global_mod -= fringe_count
        reasons.append(f"Fringe x{fringe_count}: -{fringe_count}")

    # Build results
    result = {}
    for dk in ALL_DEPTS:
        r = raw.get(dk, 0)
        if r != 0 or dk == "admin":
            thrive = max(1, min(10, 1 + int(r + global_mod)))
            dice = (thrive - 5) // 2
            result[dk] = {"raw": r, "thrive": thrive, "dice": dice, "label": LABELS[thrive]}

    return result, global_mod, reasons


def print_base(name, result, global_mod, reasons):
    """Pretty print a base's thrive results."""
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    if reasons:
        print(f"  GLOBAL {global_mod:+d}: {' | '.join(reasons)}")
    else:
        print(f"  GLOBAL: No penalties")
    print()
    for dept in ALL_DEPTS:
        if dept in result:
            r = result[dept]
            bar = "█" * r["thrive"] + "░" * (10 - r["thrive"])
            dice_str = f"{r['dice']:+d} dice" if r["dice"] != 0 else " 0 dice"
            print(f"  {dept:<20s} {bar} {r['thrive']:>2} {r['label']:<12s} {dice_str}  (raw {r['raw']:+.0f})")
    print()


def test_single_facility_impact():
    """Test what each facility contributes when added to a bare base."""
    print("\n" + "=" * 60)
    print("  TEST: Single facility impact on a Military Base")
    print("  (base has living L2 + medical L1 + general L1 + recreation L1 to avoid penalties)")
    print("=" * 60)

    baseline_facilities = [
        ("living", 2), ("medical", 1), ("general", 1), ("recreation", 1),
    ]

    baseline, _, _ = calc_thrive(baseline_facilities, location_space=30)

    all_facilities = set()
    for key in FACILITY_DEPT:
        if key not in ("general", "living", "recreation", "storage", "medical"):
            all_facilities.add(key)

    print(f"\n  {'Facility':<25s} {'Department':<20s} {'Baseline':>3} {'With L1':>4} {'Change':>7}")
    print("  " + "-" * 65)

    never_helps = []
    for fkey in sorted(all_facilities):
        test = baseline_facilities + [(fkey, 1)]
        test_result, _, _ = calc_thrive(test, location_space=30)

        found_change = False
        for dept in ALL_DEPTS:
            base_thrive = baseline.get(dept, {}).get("thrive", 0)
            test_thrive = test_result.get(dept, {}).get("thrive", 0)
            if test_thrive != base_thrive or (dept in test_result and dept not in baseline):
                change = test_thrive - base_thrive if base_thrive > 0 else test_thrive
                print(f"  {fkey:<25s} {dept:<20s} {base_thrive:>3} {test_thrive:>4} {change:>+6d}")
                found_change = True

        if not found_change:
            never_helps.append(fkey)

    if never_helps:
        print(f"\n  ⚠ NO THRIVE IMPACT from single L1: {', '.join(never_helps)}")
        print("    (These only affect thrive at higher levels or through cross-department effects)")


def test_base_archetypes():
    """Test common base archetypes to see if thrive feels right."""

    archetypes = {
        "Safe House (minimal)": {
            "facilities": [("storage", 1), ("comms_centre", 1), ("safe_room", 1)],
            "location_space": 4,
        },
        "Black Site (interrogation focus)": {
            "facilities": [
                ("interrogation", 1), ("interrogation", 2), ("interrogation", 3),
                ("brig", 1), ("brig", 2), ("brig", 3),
                ("intel_archive", 1), ("intel_archive", 2), ("intel_archive", 3),
                ("barracks", 1), ("comms_centre", 1), ("comms_centre", 2),
            ],
            "location_space": 8,
            "is_isolated": False,
        },
        "Military Fortress": {
            "facilities": [
                ("barracks", 1), ("barracks", 2), ("barracks", 3), ("barracks", 4),
                ("armory", 1), ("armory", 2), ("armory", 3),
                ("training", 1), ("training", 2), ("training", 3),
                ("aviation", 1), ("aviation", 2),
                ("motor", 1), ("motor", 2),
                ("brig", 1), ("brig", 2),
                ("living", 2), ("medical", 1),
                ("general", 1), ("general", 2), ("recreation", 1),
                ("power_plant", 1),
            ],
            "equipment": ["internal_security", "segmented_security", "high_level_monitoring"],
            "location_space": 60,
        },
        "Research Campus": {
            "facilities": [
                ("laboratory", 1), ("laboratory", 2), ("laboratory", 3),
                ("medical", 1), ("medical", 2),
                ("observatory", 1), ("observatory", 2),
                ("hydroponics", 1), ("hydroponics", 2),
                ("computer_core", 1), ("computer_core", 2),
                ("xenotech_vault", 1), ("xenotech_vault", 2),
                ("living", 2), ("general", 1), ("general", 2), ("recreation", 1), ("recreation", 2),
                ("power_plant", 2),
            ],
            "workspaces": 3,
            "location_space": 30,
        },
        "Research Campus + 2 Fringe Projects": {
            "facilities": [
                ("laboratory", 1), ("laboratory", 2), ("laboratory", 3),
                ("medical", 1), ("medical", 2),
                ("observatory", 1), ("observatory", 2),
                ("hydroponics", 1), ("hydroponics", 2),
                ("computer_core", 1), ("computer_core", 2),
                ("xenotech_vault", 1), ("xenotech_vault", 2),
                ("living", 2), ("general", 1), ("general", 2), ("recreation", 1), ("recreation", 2),
                ("power_plant", 2),
            ],
            "workspaces": 3,
            "location_space": 30,
            "fringe_count": 2,
        },
        "Diplomatic Hub": {
            "facilities": [
                ("Diplomatic", 1), ("Diplomatic", 2), ("Diplomatic", 3),
                ("hr", 1), ("hr", 2),
                ("safe_room", 1), ("safe_room", 2),
                ("intel_archive", 1), ("intel_archive", 2),
                ("comms_centre", 1),
                ("living", 3), ("general", 1), ("general", 2), ("general", 3),
                ("recreation", 1), ("recreation", 2),
                ("medical", 1),
            ],
            "location_space": 22,
        },
        "Engineering Megabase": {
            "facilities": [
                ("computer_core", 1), ("computer_core", 2), ("computer_core", 3),
                ("fabrication", 1), ("fabrication", 2), ("fabrication", 3),
                ("drone_bay", 1), ("drone_bay", 2), ("drone_bay", 3),
                ("comms_centre", 1), ("comms_centre", 2), ("comms_centre", 3),
                ("shipyard", 1), ("shipyard", 2),
                ("power_plant", 1), ("power_plant", 3),
                ("living", 2), ("medical", 1),
                ("general", 1), ("general", 2), ("recreation", 1),
            ],
            "workspaces": 4,
            "equipment": ["internal_security"],
            "location_space": 60,
        },
        "Submarine Base (isolated)": {
            "facilities": [
                ("computer_core", 1),
                ("laboratory", 1),
                ("medical", 1),
                ("barracks", 1),
                ("comms_centre", 1),
                ("living", 1),
                ("power_plant", 4),  # geothermal
            ],
            "location_space": 12,
            "is_isolated": True,
        },
        "Submarine Base (no power)": {
            "facilities": [
                ("computer_core", 1),
                ("laboratory", 1),
                ("medical", 1),
                ("barracks", 1),
                ("comms_centre", 1),
                ("living", 1),
            ],
            "location_space": 12,
            "is_isolated": True,
        },
        "Bare Military Base (no infrastructure)": {
            "facilities": [
                ("barracks", 1), ("barracks", 2), ("barracks", 3),
                ("armory", 1), ("armory", 2), ("armory", 3),
                ("training", 1), ("training", 2),
                ("aviation", 1), ("aviation", 2),
                ("brig", 1), ("brig", 2),
            ],
            "location_space": 30,
        },
        "Perfectly Balanced Base": {
            "facilities": [
                # Military
                ("barracks", 1), ("barracks", 2), ("training", 1),
                # Intelligence
                ("intel_archive", 1), ("comms_centre", 1),
                # Engineering
                ("computer_core", 1), ("fabrication", 1), ("power_plant", 2),
                # Science
                ("laboratory", 1), ("laboratory", 2), ("medical", 1),
                # Diplomatic
                ("Diplomatic", 1), ("hr", 1), ("safe_room", 1),
                # Infrastructure
                ("living", 2), ("general", 1), ("general", 2), ("recreation", 1),
            ],
            "workspaces": 2,
            "location_space": 50,
        },
    }

    for name, cfg in archetypes.items():
        result, gmod, reasons = calc_thrive(
            cfg["facilities"],
            workspaces=cfg.get("workspaces", 0),
            equipment=cfg.get("equipment"),
            location_space=cfg.get("location_space", 30),
            fringe_count=cfg.get("fringe_count", 0),
            is_isolated=cfg.get("is_isolated", False),
        )
        print_base(name, result, gmod, reasons)


def test_diminishing_returns():
    """Test if stacking one department is too easy."""
    print("\n" + "=" * 60)
    print("  TEST: Stacking — how many levels to reach each thrive tier?")
    print("  (Baseline: living L2 + medical L1 + general L1 + recreation L1)")
    print("=" * 60)

    baseline = [("living", 2), ("medical", 1), ("general", 1), ("recreation", 1)]

    tests = {
        "Military (barracks)": "barracks",
        "Intelligence (intel_archive)": "intel_archive",
        "Engineering (fabrication)": "fabrication",
        "Science (laboratory)": "laboratory",
        "Diplomatic (Diplomatic)": "Diplomatic",
    }

    for label, fkey in tests.items():
        print(f"\n  {label}:")
        dept_key = list(FACILITY_DEPT[fkey].keys())[0]
        for n in range(1, 8):
            facilities = baseline + [(fkey, i) for i in range(1, n + 1)]
            result, _, _ = calc_thrive(facilities, location_space=30)
            if dept_key in result:
                t = result[dept_key]["thrive"]
                d = result[dept_key]["dice"]
                print(f"    {n} levels: thrive {t:>2} {LABELS[t]:<12s} ({d:+d} dice)")
            if dept_key in result and result[dept_key]["thrive"] >= 10:
                break


def test_global_penalty_sensitivity():
    """Test how sensitive bases are to global penalties."""
    print("\n" + "=" * 60)
    print("  TEST: Global penalty sensitivity")
    print("  Same base with/without infrastructure")
    print("=" * 60)

    core = [
        ("barracks", 1), ("barracks", 2),
        ("armory", 1),
        ("computer_core", 1),
        ("laboratory", 1),
        ("Diplomatic", 1),
    ]

    configs = {
        "Core only (no infrastructure)": {
            "f": core, "space": 30,
        },
        "+ Living L1 (basic)": {
            "f": core + [("living", 1)], "space": 30,
        },
        "+ Living L2 (nice)": {
            "f": core + [("living", 2)], "space": 30,
        },
        "+ Living L2 + Medical": {
            "f": core + [("living", 2), ("medical", 1)], "space": 30,
        },
        "+ Living L2 + Medical + General + Rec": {
            "f": core + [("living", 2), ("medical", 1), ("general", 1), ("recreation", 1)], "space": 30,
        },
        "+ Living L3 + Medical + General x2 + Rec (full)": {
            "f": core + [("living", 3), ("medical", 1), ("general", 1), ("general", 2), ("recreation", 1)], "space": 30,
        },
    }

    for name, cfg in configs.items():
        result, gmod, reasons = calc_thrive(cfg["f"], location_space=cfg["space"])
        reason_str = " | ".join(reasons) if reasons else "None"
        mil = result.get("military", {}).get("thrive", 0)
        eng = result.get("engineering_ops", {}).get("thrive", 0)
        sci = result.get("science_ops", {}).get("thrive", 0)
        dip = result.get("diplomatic_corps", {}).get("thrive", 0)
        adm = result.get("admin", {}).get("thrive", 0)
        print(f"\n  {name}")
        print(f"    Global: {gmod:+d} ({reason_str})")
        print(f"    Mil:{mil:>2}  Eng:{eng:>2}  Sci:{sci:>2}  Dip:{dip:>2}  Adm:{adm:>2}")


def test_worthless_facilities():
    """Find facilities that never contribute to thrive."""
    print("\n" + "=" * 60)
    print("  TEST: Facilities with zero thrive impact")
    print("=" * 60)

    worthless = []
    for fkey, mapping in FACILITY_DEPT.items():
        if not mapping:
            worthless.append(fkey)

    if worthless:
        print(f"\n  Zero department bonuses: {', '.join(worthless)}")
        print("  These ONLY matter through global modifiers (housing, amenities, etc.)")
    else:
        print("\n  All facilities contribute to at least one department.")

    # Check equipment
    all_eq = ["internal_security", "segmented_security", "high_level_monitoring",
              "short_med_planes", "helicopters", "long_range_planes", "orbital_vehicles",
              "external_defense", "sam_ssm"]
    eq_no_thrive = [e for e in all_eq if e not in EQUIPMENT_DEPT]
    if eq_no_thrive:
        print(f"\n  Equipment with no thrive impact: {', '.join(eq_no_thrive)}")
        print("  These are purely functional — no department effect.")


if __name__ == "__main__":
    print("=" * 60)
    print("  EXODUS BASE BUILDING BALANCE REPORT")
    print("=" * 60)

    test_worthless_facilities()
    test_single_facility_impact()
    test_diminishing_returns()
    test_global_penalty_sensitivity()
    test_base_archetypes()

    print("\n" + "=" * 60)
    print("  END OF REPORT")
    print("=" * 60)
