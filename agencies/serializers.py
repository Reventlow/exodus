"""Manual JSON serialization for Agency models. No DRF dependency."""

from characters.models import Character
from npcs.models import NPC
from .models import GlobalFlaw, FTLProject, AgencyFTLProject, CouncilItem, CouncilVote, BaseConfig, Base, BASE_DEPARTMENTS, THRIVE_LABELS

CLASSIFIED = "CLASSIFIED"

# --- Auto-calculated thrive system ---
# Facility -> department bonuses (per facility level present on base)
FACILITY_DEPT_BONUSES = {
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

# Equipment -> department bonuses (checked separately from facilities)
EQUIPMENT_DEPT_BONUSES = {
    "internal_security":   {"admin": 1},
    "segmented_security":  {"intelligence": 1},
    "high_level_monitoring": {"intelligence": 1, "science_ops": -1, "engineering_ops": -1},
}

# Location type -> thrive modifiers
# These apply per facility of the penalised type (not flat)
LOCATION_THRIVE_PENALTIES = {
    "military_base": {
        "penalty_per_facility": {"science_ops": -1, "diplomatic_corps": -1, "engineering_ops": -1},
        "bonus": {},
    },
    "black_site": {
        "penalty_per_facility": {"science_ops": -1, "diplomatic_corps": -1, "engineering_ops": -1},
        "bonus": {},
    },
    "rd_installation": {
        "penalty_per_facility": {"military": -1},
        "bonus": {"science_ops": 1, "engineering_ops": 1},
    },
    "new_location_1774111686349": {  # Observitorium
        "penalty_per_facility": {"military": -1},
        "bonus": {"science_ops": 1, "engineering_ops": 1},
    },
}

# Which facility keys count as "military" for R&D penalty
MILITARY_FACILITY_KEYS = {"barracks", "armory", "training", "shipyard", "motor", "aviation", "brig"}
# Which facility keys count as "science" for military base penalty
SCIENCE_FACILITY_KEYS = {"laboratory", "medical", "observatory", "xenotech_vault", "hydroponics"}
# Which facility keys count as "diplomatic" for military base penalty
DIPLOMATIC_FACILITY_KEYS = {"Diplomatic", "hr", "safe_room"}
# Which facility keys count as "engineering" for military base penalty
ENGINEERING_FACILITY_KEYS = {"computer_core", "fabrication", "power_plant", "workspace", "drone_bay", "comms_centre"}

MOBILE_MERIT_KEYS = {"new_merit_1774341649496", "new_merit_1774341869469", "new_merit_1774341977938", "mobile_platform"}
ISOLATED_MERIT_KEYS = {"underwater", "orbital"}


def compute_base_thrive(base, agency=None):
    """Auto-calculate department thrive scores from facilities on a base.

    Returns list of {key, name, thrive, label, linked_class} dicts.
    """
    facilities = base.facilities or []
    workspaces = base.workspaces or []
    merits = set(base.merits or [])

    total_count = len(facilities) + len(workspaces)
    living_max = max((f.get("level", 0) for f in facilities if f.get("key") == "living"), default=0)
    general_rec = sum(1 for f in facilities if f.get("key") in ("general", "recreation"))
    has_medical = any(f.get("key") == "medical" for f in facilities)
    has_power = any(f.get("key") == "power_plant" for f in facilities)
    is_isolated = bool(merits & ISOLATED_MERIT_KEYS) or bool(merits & MOBILE_MERIT_KEYS)

    # Facility bonuses
    raw = {}
    for f in facilities:
        mapping = FACILITY_DEPT_BONUSES.get(f.get("key"), {})
        for dept, bonus in mapping.items():
            raw[dept] = raw.get(dept, 0) + bonus
    for _w in workspaces:
        raw["engineering_ops"] = raw.get("engineering_ops", 0) + 1

    # Equipment bonuses (security levels, etc.)
    for eq_key in (base.equipment or []):
        mapping = EQUIPMENT_DEPT_BONUSES.get(eq_key, {})
        for dept, bonus in mapping.items():
            raw[dept] = raw.get(dept, 0) + bonus

    # Location type penalties/bonuses (per facility of penalised type)
    loc_config = LOCATION_THRIVE_PENALTIES.get(base.location_type, {})
    penalty_map = loc_config.get("penalty_per_facility", {})
    loc_bonus = loc_config.get("bonus", {})
    if penalty_map:
        for f in facilities:
            fkey = f.get("key")
            # Count how many science/diplomatic/military facilities trigger penalties
            for dept, penalty in penalty_map.items():
                if dept == "science_ops" and fkey in SCIENCE_FACILITY_KEYS:
                    raw[dept] = raw.get(dept, 0) + penalty
                elif dept == "diplomatic_corps" and fkey in DIPLOMATIC_FACILITY_KEYS:
                    raw[dept] = raw.get(dept, 0) + penalty
                elif dept == "engineering_ops" and fkey in ENGINEERING_FACILITY_KEYS:
                    raw[dept] = raw.get(dept, 0) + penalty
                elif dept == "military" and fkey in MILITARY_FACILITY_KEYS:
                    raw[dept] = raw.get(dept, 0) + penalty
    for dept, bonus in loc_bonus.items():
        raw[dept] = raw.get(dept, 0) + bonus

    # Global modifiers
    global_mod = 0
    global_reasons = []

    # Location type label for global reasons
    if penalty_map or loc_bonus:
        loc_name = base.location_type.replace("_", " ").title()
        penalties_desc = []
        for dept, p in penalty_map.items():
            dept_name = dept.replace("_", " ").title()
            penalties_desc.append(f"{p:+d}/facility to {dept_name}")
        bonuses_desc = []
        for dept, b in loc_bonus.items():
            dept_name = dept.replace("_", " ").title()
            bonuses_desc.append(f"{b:+d} {dept_name}")
        parts = penalties_desc + bonuses_desc
        if parts:
            global_reasons.append(f"{loc_name}: {', '.join(parts)}")

    # Calculate total base space for housing threshold
    from .models import BaseConfig as _BC
    _cfg = _BC.load()
    _lt_map = {lt["key"]: lt for lt in (_cfg.location_types or [])}
    _merit_map = {m["key"]: m for m in (_cfg.location_merits or [])}
    _loc = _lt_map.get(base.location_type)
    _total_space = (_loc.get("space", 0) if _loc else 0)
    for mk in merits:
        _m = _merit_map.get(mk)
        if _m:
            _total_space += _m.get("extraSpace", 0)

    # Living — based on highest quality level built
    # Small bases (≤12 space) assume staff rotation, no housing needed
    if _total_space > 12 and total_count >= 5:
        if living_max == 0:
            mod = -2 if total_count >= 11 else -1
            global_mod += mod
            global_reasons.append(f"No housing: {mod:+d}")
        elif living_max == 1:
            global_mod -= 1
            global_reasons.append("Basic housing (Normal): -1")
        elif living_max == 2:
            pass  # Nice housing = neutral, no modifier
        elif living_max >= 3:
            global_mod += 1
            global_reasons.append("Luxury housing (Luxus): +1")

    # Medical
    if total_count >= 8 and not has_medical:
        global_mod -= 1
        global_reasons.append("No medical: -1")

    # Amenities ratio
    if total_count >= 6:
        ratio = general_rec / total_count if total_count > 0 else 0
        if ratio < 0.10:
            global_mod -= 1
            global_reasons.append(f"Poor amenities ({ratio:.0%}): -1")
        elif ratio >= 0.20:
            global_mod += 1
            global_reasons.append(f"Good amenities ({ratio:.0%}): +1")

    # Power (isolated only)
    if is_isolated and not has_power:
        global_mod -= 1
        global_reasons.append("No power (isolated): -1")

    # Fringe projects on this base: -1 per active fringe project
    # Child prodigy assigned to a project on this base: additional -1 per prodigy
    if agency:
        base_id = base.id
        fringe_count = 0
        prodigy_count = 0
        for proj in (agency.projects or []):
            if not isinstance(proj, dict):
                continue
            if proj.get("discarded"):
                continue
            if str(proj.get("baseId", "")) == str(base_id) and proj.get("fringe"):
                fringe_count += 1
                if proj.get("assignedProdigyId"):
                    prodigy_count += 1
        # Also check FTL projects
        for afp in agency.ftl_assignments.all():
            if afp.base_id == base_id:
                meta = afp.metadata or {}
                if meta.get("fringe") or any(meta.get(k) for k in ["darkGrantsLevel", "liveTestingDice"]):
                    fringe_count += 1
                    if meta.get("assignedProdigyId"):
                        prodigy_count += 1
        if fringe_count > 0:
            global_mod -= fringe_count
            global_reasons.append(f"Fringe projects x{fringe_count}: -{fringe_count}")

    # Build department list
    dept_lookup = {d["key"]: d for d in BASE_DEPARTMENTS}
    all_dept_keys = ["military", "intelligence", "engineering_ops", "science_ops", "diplomatic_corps", "admin"]
    result = []
    for dk in all_dept_keys:
        r = raw.get(dk, 0)
        if r == 0 and dk != "admin" and dk not in raw:
            continue  # department doesn't exist on this base
        thrive = max(1, min(10, 1 + int(r + global_mod)))
        dept_def = dept_lookup.get(dk, {})
        # Build breakdown of what contributes to this department
        sources = []
        for f in facilities:
            mapping = FACILITY_DEPT_BONUSES.get(f.get("key"), {})
            bonus = mapping.get(dk)
            if bonus:
                # Look up facility name from config
                from .models import BaseConfig
                config = BaseConfig.load()
                ft = next((ft for ft in (config.facility_types or []) if ft["key"] == f.get("key")), None)
                fname = ft["name"] if ft else f.get("key", "")
                lvl_def = next((l for l in ft.get("levels", []) if l["level"] == f.get("level")), None) if ft else None
                lname = lvl_def["name"] if lvl_def else f"L{f.get('level')}"
                sources.append(f"{fname} ({lname}): {bonus:+g}")
        if dk == "engineering_ops" and workspaces:
            sources.append(f"Workspaces x{len(workspaces)}: +{len(workspaces)}")
        for eq_key in (base.equipment or []):
            eq_mapping = EQUIPMENT_DEPT_BONUSES.get(eq_key, {})
            eq_bonus = eq_mapping.get(dk)
            if eq_bonus:
                eq_name = eq_key.replace("_", " ").title()
                sources.append(f"{eq_name}: {eq_bonus:+g}")
        if global_mod != 0:
            for reason in global_reasons:
                sources.append(f"[Global] {reason}")
        tooltip = f"Base: 1\n" + "\n".join(sources) + f"\n= {thrive}"

        result.append({
            "key": dk,
            "name": dept_def.get("name", dk),
            "thrive": thrive,
            "label": THRIVE_LABELS.get(thrive, ""),
            "linked_class": dept_def.get("linked_class", "general"),
            "raw": round(r, 1),
            "tooltip": tooltip,
        })

    return result, global_mod, global_reasons

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

FRINGE_DICE_FIELDS = [
    ("darkGrantsLevel", "Dark Grants", False),
    ("liveTestingDice", "Live Testing", False),
    ("stimulantDice", "Stimulants (next roll)", True),
    ("blackMarketTechDice", "Black Market Tech", False),
    ("geneManipulationDice", "Gene Manipulation", False),
    ("neuralInterfaceDice", "Neural Interface (next roll)", True),
    ("sleepDeprivationDice", "Sleep Deprivation (next roll)", True),
    ("overclockedEquipmentDice", "Overclocked Equipment", False),
    ("childProdigyDice", "Child Prodigy", False),
    ("assignedProdigyDice", "Assigned Prodigy", False),
]

WORKSPACE_BONUS = {1: 0, 2: 1, 3: 3, 4: 5}


def _compute_project_dice_pool(project, agency, characters_by_name, bases_list):
    """Compute the dice pool for a project based on its dicePoolConfig."""
    config = project.get("dicePoolConfig")
    if not config:
        return None

    pool = 0
    parts = []

    # Resolve assigned character
    player_name = project.get("player", "")
    char = characters_by_name.get(player_name)

    # 1. Character attributes (0-2)
    for attr_path in (config.get("charAttributes") or []):
        if char and isinstance(attr_path, list) and len(attr_path) == 2:
            val = (char.attributes or {}).get(attr_path[0], {}).get(attr_path[1], 0)
            label = ATTR_NAMES.get(tuple(attr_path), attr_path[1])
            pool += val
            parts.append({"label": label, "value": val, "type": "charAttr"})

    # 2. Character skill (1)
    skill_cfg = config.get("charSkill")
    if char and skill_cfg:
        cat = skill_cfg.get("category", "")
        name = skill_cfg.get("name", "")
        val = (char.skills or {}).get(cat, {}).get(name, 0)
        pool += val
        parts.append({"label": name, "value": val, "type": "charSkill"})

    # 3. Agency attributes (0-2)
    for attr_path in (config.get("agencyAttributes") or []):
        if isinstance(attr_path, list) and len(attr_path) == 2:
            val = (agency.attributes or {}).get(attr_path[0], {}).get(attr_path[1], 0)
            pool += val
            parts.append({"label": attr_path[1], "value": val, "type": "agencyAttr"})

    # 4. Matching pulling strings (+1 base, linked NPCs get +1 per 15 XP)
    # Values may be composite "name|npcName" for linkable PS like Personal NPC
    matching_ps = config.get("matchingPullingStrings") or []
    if char and matching_ps:
        char_ps_names = set()
        for cps in char.character_pulling_strings.all():
            char_ps_names.add(cps.pulling_string.name)
        for ps_entry in matching_ps:
            ps_name = ps_entry.split("|")[0] if "|" in ps_entry else ps_entry
            if ps_name in char_ps_names:
                bonus = 1
                label = ps_name
                # Linked NPC: look up XP for bonus calculation
                if "|" in ps_entry:
                    npc_name = ps_entry.split("|", 1)[1]
                    label = ps_name + " — " + npc_name
                    linked_npc = NPC.objects.filter(name=npc_name).only("experience").first()
                    if linked_npc:
                        bonus = 1 + (linked_npc.experience or 0) // 15
                pool += bonus
                parts.append({"label": label, "value": bonus, "type": "pullingString"})

    # 5. Matching merits (+rating each)
    matching_merits = config.get("matchingMerits") or []
    if char and matching_merits:
        matching_lower = {m.lower() for m in matching_merits}
        for cm in char.character_merits.all():
            if cm.merit.name.lower() in matching_lower:
                pool += cm.rating
                parts.append({"label": cm.merit.name, "value": cm.rating, "type": "merit"})

    # 6. Workspace quality bonus
    base_id = project.get("baseId")
    if char and base_id:
        for b in bases_list:
            if b.id == int(base_id):
                for ws in (b.workspaces or []):
                    if ws.get("assignedType") == "character" and ws.get("assignedTo") == char.id:
                        bonus = WORKSPACE_BONUS.get(ws.get("level", 1), 0)
                        if bonus > 0:
                            pool += bonus
                            parts.append({"label": "Workspace", "value": bonus, "type": "workspace"})
                        break
                break

    # 7. Department thrive modifier (auto-calculated from facilities)
    if char and base_id:
        char_class = char.character_class or ""
        for b in bases_list:
            if b.id == int(base_id):
                computed_depts, _, _ = compute_base_thrive(b, agency=agency)
                best_thrive = None
                best_dept = None
                for dept in computed_depts:
                    linked = dept.get("linked_class", "")
                    if linked == char_class or linked == "general":
                        t = dept.get("thrive", 1)
                        if best_thrive is None or t > best_thrive:
                            best_thrive = t
                            best_dept = dept
                if best_thrive is not None:
                    modifier = (best_thrive - 5) // 2
                    if modifier != 0:
                        label = f"{best_dept['name']} ({best_dept.get('label', '')})"
                        pool += modifier
                        parts.append({"label": label, "value": modifier, "type": "thrive"})
                break

    # 8. Assigned NPCs (+1 base + 1 per 15 XP each)
    assigned_npc_ids = project.get("assignedNpcs") or []
    if assigned_npc_ids:
        npcs = NPC.objects.filter(id__in=assigned_npc_ids).only("id", "name", "experience")
        for npc in npcs:
            bonus = 1 + (npc.experience or 0) // 15
            pool += bonus
            parts.append({"label": npc.name, "value": bonus, "type": "npc"})

    # 9. Fringe dice
    for field_key, label, is_per_roll in FRINGE_DICE_FIELDS:
        val = project.get(field_key, 0) or 0
        if val > 0:
            pool += val
            parts.append({"label": label, "value": val, "type": "fringePerRoll" if is_per_roll else "fringe"})

    # 10. Mental load (only the last 4 boxes give penalties)
    # Total boxes = 4 + floor((Composure + Resolve) / 2)
    # Penalty zone starts at (total - 3). The 4 penalty boxes give:
    #   Box 1: -2 social
    #   Box 2: -2 cognitive
    #   Box 3: -1 social, -1 cognitive
    #   Box 4: -2 social, -2 cognitive
    # Projects use cognitive penalty for the dice pool.
    if char and (char.mental_load or 0) > 0:
        attrs = char.attributes or {}
        composure = (attrs.get("resistance", {}).get("social", 1))
        resolve = (attrs.get("resistance", {}).get("mental", 1))
        ml_max = 4 + (composure + resolve) // 2
        penalty_start = ml_max - 3  # first penalty box level
        ml = char.mental_load or 0
        cognitive = 0
        if ml >= penalty_start:
            pass  # box 1: social only, no cognitive
        if ml >= penalty_start + 1:
            cognitive -= 2  # box 2: -2 cognitive
        if ml >= penalty_start + 2:
            cognitive -= 1  # box 3: -1 cognitive
        if ml >= penalty_start + 3:
            cognitive -= 2  # box 4: -2 cognitive
        if cognitive < 0:
            pool += cognitive  # cognitive is negative
            parts.append({"label": "Mental Load", "value": cognitive, "type": "mentalLoad"})

    return {"pool": max(pool, 0), "parts": parts, "raw": pool}


def _serialize_projects(agency, show_all, user, is_field_visible_fn):
    """Serialize projects with fringe visibility control."""
    if not is_field_visible_fn(agency, "projects") and not show_all:
        return CLASSIFIED

    projects = agency.projects or []
    if not show_all:
        # Non-admin: filter out classified and discarded projects
        projects = [p for p in projects if isinstance(p, dict) and not p.get("classified", False) and not p.get("discarded", False)]

    # Check if user is science class
    char = Character.objects.filter(owner=user).first()
    is_science = user.is_superuser or (char and char.character_class == "science")

    if not is_science:
        # Strip fringe field from projects
        projects = [{k: v for k, v in p.items() if k != "fringe"} if isinstance(p, dict) else p for p in projects]

    # Compute dice pools for projects with config
    has_config = any(isinstance(p, dict) and p.get("dicePoolConfig") for p in projects)
    if has_config:
        characters_by_name = {
            c.name: c for c in Character.objects.prefetch_related(
                "character_merits__merit", "character_pulling_strings__pulling_string"
            ).all()
        }
        bases_list = list(agency.bases.all())
        for p in projects:
            if isinstance(p, dict) and p.get("dicePoolConfig"):
                p["computedPool"] = _compute_project_dice_pool(p, agency, characters_by_name, bases_list)

    return projects


def _get_player_rolls(agency, user):
    """Get roll allocation for the current player, plus personal NPCs for downtime."""
    rolls = agency.project_rolls or {}
    char = Character.objects.filter(owner=user).first()
    char_name = char.name if char else ""
    personal = rolls.get(char_name, {})
    # Personal NPCs assigned to this player
    personal_npcs = [
        {"id": n.id, "name": n.name}
        for n in NPC.objects.filter(assigned_to=user).order_by("name").only("id", "name")
    ] if not user.is_superuser else []
    return {
        "free": personal.get("free", 0) or 0,
        "spare": personal.get("spare", 0) or 0,
        "charName": char_name,
        "personalNpcs": personal_npcs,
    }


def _get_fringe_info(agency, user):
    """Get fringe project slot info for the current user."""
    char = Character.objects.filter(owner=user).first()
    is_science = user.is_superuser or (char and char.character_class == "science")
    if not is_science:
        return None

    science_score = 99 if user.is_superuser else char.skills.get("mental", {}).get("Science", 0)
    active_fringe = sum(
        1 for p in (agency.projects or [])
        if isinstance(p, dict) and p.get("fringe") and not p.get("discarded")
    )
    return {
        "maxSlots": science_score,
        "usedSlots": active_fringe,
        "availableSlots": max(0, science_score - active_fringe),
    }


def _get_sweep_info(agency, user):
    """Calculate sweep roll info for the current user or best NPC dossier."""
    info = {"pool": 0, "parts": ["Intelligence + Computer + merit modifiers"], "merits": []}

    if agency.is_player_agency and not user.is_superuser:
        # Player agency — use the requesting user's character
        char = Character.objects.filter(owner=user).first()
        if not char:
            return info
        intelligence = char.attributes.get("power", {}).get("mental", 1)
        computer = char.skills.get("mental", {}).get("Computer", 0)
        pool = intelligence + computer
        parts = [f"Intelligence {intelligence}", f"Computer {computer}"]
        merits = []
        for cm in char.character_merits.select_related("merit").all():
            if cm.merit.name.lower() == "computer aptitude":
                pool += 2
                parts.append("Computer Aptitude +2")
                merits.append(cm.merit.name)
            elif cm.merit.name.lower() == "rapid processing":
                pool += 2
                parts.append("Rapid Processing +2")
                merits.append(cm.merit.name)
        if char.mental_load > 0:
            pool -= char.mental_load
            parts.append(f"Mental Load -{char.mental_load}")
        info = {"pool": pool, "parts": parts, "merits": merits}
        return info

    if agency.is_player_agency and user.is_superuser:
        # GM viewing player agency — show all player characters' sweep pools
        best_pool = 0
        best_info = info
        for char in Character.objects.all():
            intelligence = char.attributes.get("power", {}).get("mental", 1)
            computer = char.skills.get("mental", {}).get("Computer", 0)
            if computer <= 0:
                continue
            pool = intelligence + computer
            parts = [f"{char.name}: Intelligence {intelligence}", f"Computer {computer}"]
            merits = []
            for cm in char.character_merits.select_related("merit").all():
                if cm.merit.name.lower() in ("computer aptitude", "rapid processing"):
                    pool += 2
                    parts.append(f"{cm.merit.name} +2")
                    merits.append(cm.merit.name)
            if pool > best_pool:
                best_pool = pool
                best_info = {"pool": pool, "parts": parts, "merits": merits, "characterName": char.name}
        return best_info

    # NPC agency — find dossier with highest Intelligence + Computer + merits
    best_pool = 0
    best_info = info
    for npc in NPC.objects.filter(agency=agency, is_npc_dossier=True):
        intelligence = npc.attributes.get("power", {}).get("mental", 1)
        computer = npc.skills.get("mental", {}).get("Computer", 0)
        if computer <= 0:
            continue
        pool = intelligence + computer
        parts = [f"{npc.name}: Intelligence {intelligence}", f"Computer {computer}"]
        merits = []
        for nm in npc.npc_merits.select_related("merit").all():
            if nm.merit.name.lower() == "computer aptitude":
                pool += 2
                parts.append("Computer Aptitude +2")
                merits.append(nm.merit.name)
            elif nm.merit.name.lower() == "rapid processing":
                pool += 2
                parts.append("Rapid Processing +2")
                merits.append(nm.merit.name)
        if pool > best_pool:
            best_pool = pool
            best_info = {"pool": pool, "parts": parts, "merits": merits, "npcName": npc.name}
    info = best_info

    return info


def is_field_visible(agency, field_path):
    """Check if a field is visible on an NPC agency.

    Returns True if the agency is the player agency (always visible),
    or if the field_visibility dict marks it as visible (default: True).
    """
    if agency.is_player_agency:
        return True
    return agency.field_visibility.get(field_path, True)


def redact_value(value):
    """Return CLASSIFIED placeholder matching the value type."""
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return CLASSIFIED
    if isinstance(value, int):
        return CLASSIFIED
    return CLASSIFIED


def serialize_agency(agency, user):
    """Full agency data for API responses.

    For NPC agencies, hidden fields are replaced with CLASSIFIED unless
    the user is an admin.
    """
    is_admin = user.is_superuser
    show_all = agency.is_player_agency or is_admin

    def vis(field_path, value):
        """Return value or CLASSIFIED based on visibility."""
        if show_all:
            return value
        if is_field_visible(agency, field_path):
            return value
        return redact_value(value)

    # For NPC attributes, filter visibility per-skill
    def vis_attributes(attrs):
        if show_all:
            return attrs
        result = {}
        for category, skills in attrs.items():
            result[category] = {}
            for skill, val in skills.items():
                path = f"attributes.{category}.{skill}"
                result[category][skill] = vis(path, val)
        return result

    data = {
        "id": agency.id,
        "name": agency.name,
        "alliance": vis("alliance", agency.alliance),
        "motto": vis("motto", agency.motto),
        "headquarters": vis("headquarters", agency.headquarters),
        "notes": vis("notes", agency.notes),
        "integrity": vis("integrity", agency.integrity),
        "experience": vis("experience", agency.experience),
        "isPlayerAgency": agency.is_player_agency,
        "isCouncilMember": agency.is_council_member,
        "isCouncilChairman": agency.is_council_chairman,
        "isHidden": agency.is_hidden,
        "mapColor": agency.map_color,
        "zeroDayPool": agency.zero_day_pool if is_admin else None,
        "isNuclearPower": agency.is_nuclear_power,
        "sweepPool": agency.sweep_pool,
        "sweepInfo": _get_sweep_info(agency, user),
        "fringeInfo": _get_fringe_info(agency, user),
        "projectRolls": agency.project_rolls if is_admin else _get_player_rolls(agency, user),
        "conditions_cyber": [
            {
                "id": c.id,
                "type": c.condition_type,
                "typeDisplay": c.get_condition_type_display(),
                "description": c.description,
                "difficulty": c.difficulty,
                "sweepPool": c.sweep_pool,
                "sweepProgress": c.sweep_progress,
                "targetBaseId": c.target_base_id,
                "infraType": c.infra_type,
                "isActive": c.is_active,
                "createdAt": c.created_at.isoformat(),
            }
            for c in agency.agency_conditions.filter(is_active=True)
        ],
        "attributes": vis_attributes(agency.attributes),
        "specializations": vis("specializations", agency.specializations),
        "merits": vis("merits", agency.merits),
        "flaws": vis("flaws", agency.flaws),
        "assets": vis("assets", agency.assets),
        "fleet": vis("fleet", agency.fleet),
        "conditions": vis("conditions", agency.conditions),
        "projects": _serialize_projects(agency, show_all, user, is_field_visible),
        "history": vis("history", agency.history),
        # Optimistic concurrency: per-section version map. Frontend echoes
        # the value via If-Match on subsequent PATCH calls.
        "sectionVersions": agency.section_versions or {},
    }

    # Global flaws — visible to everyone, not editable per-agency
    data["globalFlaws"] = [serialize_global_flaw(gf) for gf in GlobalFlaw.objects.all()]

    # Council items — visible to everyone, not editable per-agency
    data["councilItems"] = [serialize_council_item(ci) for ci in CouncilItem.objects.all()]

    # Determine character class for base building visibility filtering
    # Admins see all options; players see only their class + general
    if is_admin:
        char_class = None  # No filtering
    else:
        char = Character.objects.filter(owner=user).first()
        char_class = char.character_class if char else ""

    # Bases + config for cost lookups (with per-base visibility for NPC agencies)
    # Hidden bases are only visible to superusers
    config = BaseConfig.load()
    bases_qs = agency.bases.all() if is_admin else agency.bases.filter(is_hidden=False)
    if show_all:
        data["bases"] = [serialize_base(b, is_admin=is_admin, character_class=char_class, base_config=config, agency=agency) for b in bases_qs]
    elif is_field_visible(agency, "bases"):
        serialized_bases = []
        for b in bases_qs:
            base_path = f"bases.{b.id}"
            if not is_field_visible(agency, base_path):
                serialized_bases.append({"id": b.id, "name": b.name, "classified": True})
            else:
                sb = serialize_base(b, is_admin=is_admin, character_class=char_class, base_config=config, agency=agency)
                if not is_field_visible(agency, f"{base_path}.facilities"):
                    sb["facilities"] = []
                    sb["classifiedFacilities"] = True
                if not is_field_visible(agency, f"{base_path}.workspaces"):
                    sb["workspaces"] = []
                    sb["classifiedWorkspaces"] = True
                if not is_field_visible(agency, f"{base_path}.equipment"):
                    sb["equipment"] = []
                    sb["classifiedEquipment"] = True
                serialized_bases.append(sb)
        data["bases"] = serialized_bases
    else:
        data["bases"] = []
        data["classifiedBases"] = True
    data["baseConfig"] = serialize_base_config(config, character_class=char_class)
    # Full definitions for display lookups (names/costs of built items from other classes)
    if char_class is not None:
        data["baseConfigLookup"] = {
            "facilityTypes": config.facility_types,
            "locationTypes": config.location_types,
            "locationMerits": config.location_merits,
            "equipmentTypes": config.equipment_types,
        }

    # Assignable entities for workspace assignment (with merits/PS for dice pool config)
    data["assignableCharacters"] = [
        {
            "id": c.id, "name": c.name, "username": c.owner.username,
            "merits": [
                {"name": cm.merit.name, "rating": cm.rating}
                for cm in c.character_merits.select_related("merit").all()
            ],
            "autoSuccessMerits": [
                {
                    "name": cm.merit.name, "rating": cm.rating,
                    "used": (c.merit_uses or {}).get(cm.merit.name, 0),
                    "remaining": cm.rating - (c.merit_uses or {}).get(cm.merit.name, 0),
                }
                for cm in c.character_merits.select_related("merit").all()
                if cm.merit.effects.get("auto_success")
            ],
            "pullingStrings": [
                {
                    "name": cps.pulling_string.name,
                    "linkedNpc": cps.linked_npc.name if cps.linked_npc else None,
                    "linkedNpcClass": cps.linked_npc.character_class if cps.linked_npc else None,
                    "linkedNpcBonus": (1 + (cps.linked_npc.experience or 0) // 15) if cps.linked_npc else 0,
                }
                for cps in c.character_pulling_strings.select_related("pulling_string", "linked_npc").all()
            ],
        }
        for c in Character.objects.select_related("owner").prefetch_related(
            "character_merits__merit", "character_pulling_strings__pulling_string",
            "character_pulling_strings__linked_npc",
        ).all().order_by("name")
    ]
    # NPCs belonging to this agency (includes personal NPCs now that they have agency set)
    data["assignableNpcs"] = [
        {
            "id": n.id, "name": n.name, "experience": n.experience or 0,
            "bonus": 1 + (n.experience or 0) // 15,
            "assignedTo": n.assigned_to.username if n.assigned_to else None,
        }
        for n in NPC.objects.filter(agency=agency).select_related("assigned_to").order_by("name")
    ]

    # Child prodigy NPCs available for assignment to fringe projects
    prodigy_assigned = {}
    for i, proj in enumerate(agency.projects or []):
        if isinstance(proj, dict) and proj.get("assignedProdigyId"):
            prodigy_assigned[proj["assignedProdigyId"]] = proj.get("name", "")
    data["childProdigies"] = [
        {
            "id": n.id,
            "name": n.name,
            "assignedTo": prodigy_assigned.get(n.id, None),
        }
        for n in NPC.objects.filter(agency=agency, is_child_prodigy=True)
    ]

    # Linked dossiers: characters assigned to workspaces + NPC dossiers
    char_ids = set()
    for b in bases_qs:
        for w in (b.workspaces or []):
            if w.get("assignedType") == "character" and w.get("assignedTo"):
                char_ids.add(w["assignedTo"])
    linked_characters = [
        {"id": c.id, "name": c.name, "type": "character"}
        for c in Character.objects.filter(id__in=char_ids).order_by("name").only("id", "name")
    ] if char_ids else []
    linked_npcs = [
        {"id": n.id, "name": n.name, "type": "npc", "agencyName": n.agency.name if n.agency else None, "agencyId": n.agency_id}
        for n in NPC.objects.filter(agency=agency).select_related("agency").order_by("name").only("id", "name", "agency")
    ]
    # All NPC dossiers from other visible agencies (for contact dossier browsing)
    other_npcs = []
    if is_admin:
        other_npcs = [
            {"id": n.id, "name": n.name, "type": "npc", "agencyName": n.agency.name if n.agency else None, "agencyId": n.agency_id}
            for n in NPC.objects.filter(is_npc_dossier=True).exclude(agency=agency).select_related("agency").order_by("agency__name", "name").only("id", "name", "agency")
        ]
    data["linkedDossiers"] = linked_characters + linked_npcs + other_npcs

    # FTL project assignments with progress + dice pool
    ftl_chars = None
    ftl_bases = None
    ftl_assignments = list(agency.ftl_assignments.select_related("ftl_project").all())
    if any(afp.metadata.get("dicePoolConfig") for afp in ftl_assignments if afp.metadata):
        ftl_chars = {
            c.name: c for c in Character.objects.prefetch_related(
                "character_merits__merit", "character_pulling_strings__pulling_string"
            ).all()
        }
        ftl_bases = list(agency.bases.all())
    data["ftlProjects"] = [
        serialize_agency_ftl_project(afp, agency, ftl_chars, ftl_bases)
        for afp in ftl_assignments
    ]

    # XP transfer log for player agencies
    if agency.is_player_agency:
        from characters.models import XpTransferLog
        transfers = XpTransferLog.objects.filter(agency=agency).select_related(
            "character", "character__owner"
        ).order_by("-created_at")[:30]
        data["xpTransfers"] = [
            {
                "characterName": t.character.name,
                "playerName": t.character.owner.username,
                "amount": t.amount,
                "agencyReceived": t.agency_received,
                "date": t.created_at.isoformat(),
            }
            for t in transfers
        ]

    # Base XP log
    from .models import BaseXpLog
    base_xp_logs = BaseXpLog.objects.filter(agency=agency).select_related("base").order_by("-created_at")[:20]
    data["baseXpLogs"] = [
        {
            "id": log.id,
            "baseName": log.base.name if log.base else "Unknown",
            "amount": log.amount,
            "reason": log.reason,
            "date": log.created_at.isoformat(),
        }
        for log in base_xp_logs
    ]

    # Include visibility map and change request counts for admins
    if is_admin:
        data["fieldVisibility"] = agency.field_visibility

    return data


# ---------------------------------------------------------------------------
# Section-scoped serializers (Phase 1/2 multi-player concurrency)
# ---------------------------------------------------------------------------

# Maps an agency-level section_key (the URL slug + payload key) to the value
# we expose on the model. Keep this in sync with the section view dispatcher
# in views.py — both must agree on the canonical names.
AGENCY_SECTION_VALUE_GETTERS = {
    "header": lambda a: {
        "name": a.name,
        "motto": a.motto,
        "headquarters": a.headquarters,
    },
    "alliance": lambda a: a.alliance,
    "notes": lambda a: a.notes,
    "integrity": lambda a: a.integrity,
    "attributes": lambda a: a.attributes,
    "specializations": lambda a: a.specializations,
    "merits": lambda a: a.merits,
    "flaws": lambda a: a.flaws,
    "assets": lambda a: a.assets,
    "fleet": lambda a: a.fleet,
    "history": lambda a: a.history,
    # ``projects`` round-trips the raw JSON list — callers can either
    # full-replace via the section endpoint or mutate via the per-project
    # endpoints (which share the same version slot through
    # ``_with_projects_cas``). Computed fields (``computedPool``) are NOT
    # added here; the section endpoint is for raw round-trips. Use
    # ``GET /api/agencies/<id>/`` to receive the enriched view.
    "projects": lambda a: a.projects or [],
    "admin-flags": lambda a: {
        "mapColor": a.map_color,
        "isNuclearPower": a.is_nuclear_power,
        "isHidden": a.is_hidden,
        "sweepPool": a.sweep_pool,
        "zeroDayPool": a.zero_day_pool,
    },
}


def serialize_agency_section(agency, section_key, user=None):
    """Lightweight serializer for the per-section PATCH endpoints.

    Returns ``{<section_key>: <value>, "version": <n>}`` — no heavy
    computed fields (project dice pools, sweep info, base config lookups,
    etc.) so a save-and-respond round-trip stays cheap.

    `user` is accepted for symmetry with the heavy serializer but is not
    used for redaction here: the section endpoints are gated by view-level
    permission checks, so by the time we serialize the caller is allowed
    to see the value.
    """
    getter = AGENCY_SECTION_VALUE_GETTERS.get(section_key)
    if getter is None:
        raise ValueError(f"Unknown agency section_key: {section_key!r}")
    versions = agency.section_versions or {}
    return {
        section_key: getter(agency),
        "version": int(versions.get(section_key, 0)),
    }


def serialize_base_section(base, section_key):
    """Section-scoped serializer for per-base PATCH endpoints.

    Returns ``{<section_key>: <value>, "version": <n>}``.
    """
    getter = BASE_SECTION_VALUE_GETTERS.get(section_key)
    if getter is None:
        raise ValueError(f"Unknown base section_key: {section_key!r}")
    return {
        section_key: getter(base),
        "version": int(base.version or 0),
    }


# Per-base section value lookups. ``geo`` returns the lat/lon pair; the
# frontend sends them together so they share one version slot.
BASE_SECTION_VALUE_GETTERS = {
    "name": lambda b: b.name,
    "location": lambda b: b.location_type,
    "merits": lambda b: b.merits,
    "facilities": lambda b: b.facilities,
    "workspaces": lambda b: b.workspaces,
    "equipment": lambda b: b.equipment,
    "departments": lambda b: b.departments,
    "notes": lambda b: b.notes,
    "geo": lambda b: {"latitude": b.latitude, "longitude": b.longitude},
    "hidden": lambda b: b.is_hidden,
    "classified": lambda b: b.hidden_sections or [],
}


def serialize_agency_summary(agency, user):
    """Brief agency data for list views."""
    is_admin = user.is_superuser
    show_all = agency.is_player_agency or is_admin

    def vis(field_path, value):
        if show_all:
            return value
        if is_field_visible(agency, field_path):
            return value
        return CLASSIFIED

    data = {
        "id": agency.id,
        "name": agency.name,
        "alliance": vis("alliance", agency.alliance),
        "isPlayerAgency": agency.is_player_agency,
        "motto": vis("motto", agency.motto),
    }
    if is_admin:
        data["isHidden"] = agency.is_hidden
    return data


def serialize_global_flaw(gf):
    """Serialize a GlobalFlaw model instance."""
    return {
        "id": gf.id,
        "name": gf.name,
        "value": gf.value,
        "description": gf.description,
        "order": gf.order,
    }


def serialize_ftl_project(fp):
    """Serialize an FTLProject model instance."""
    return {
        "id": fp.id,
        "name": fp.name,
        "description": fp.description,
        "pros": fp.pros,
        "cons": fp.cons,
        "requiredSuccesses": fp.required_successes,
    }


def serialize_agency_ftl_project(afp, agency=None, characters_by_name=None, bases_list=None):
    """Serialize an AgencyFTLProject join record with nested project data."""
    meta = afp.metadata or {}
    data = {
        **serialize_ftl_project(afp.ftl_project),
        "assignmentId": afp.id,
        "currentSuccesses": afp.current_successes,
        "player": afp.player,
        "baseId": afp.base_id,
        "baseName": afp.base_name,
        "fringe": meta.get("fringe", False),
        "metadata": meta,
    }
    # Build a fake project dict for dice pool computation
    if meta.get("dicePoolConfig") and agency and characters_by_name is not None:
        fake_project = {
            "player": afp.player,
            "baseId": afp.base_id,
            "dicePoolConfig": meta.get("dicePoolConfig"),
            "assignedNpcs": meta.get("assignedNpcs", []),
        }
        # Copy fringe dice fields from metadata
        for field_key, _, _ in FRINGE_DICE_FIELDS:
            if field_key in meta:
                fake_project[field_key] = meta[field_key]
        data["computedPool"] = _compute_project_dice_pool(
            fake_project, agency, characters_by_name, bases_list or []
        )
    return data


def serialize_council_item(ci, user=None):
    """Serialize a CouncilItem model instance, including votes when voting."""
    from .models import Agency

    data = {
        "id": ci.id,
        "name": ci.name,
        "itemType": ci.item_type,
        "description": ci.description,
        "status": ci.status,
        "proposedBy": ci.proposed_by,
        "notes": ci.notes,
        "order": ci.order,
    }

    # Include votes and tally for items that have been through voting
    if ci.status in ("voting", "active", "suspended", "repealed"):
        data.update(_build_live_tally(ci))
    elif ci.status == "emergency_suspended" and ci.vote_record:
        # Frozen snapshot from when the vote was emergency-suspended
        data["votes"] = ci.vote_record.get("votes", [])
        data["tally"] = ci.vote_record.get("tally", {})

    # Superuser-only: predicted votes
    if user and user.is_superuser and ci.predicted_votes:
        data["predictedVotes"] = ci.predicted_votes

    return data


def _build_live_tally(ci):
    """Build live vote tally from the database for a council item."""
    from .models import Agency

    votes = list(ci.votes.select_related("agency").all())
    members = list(
        Agency.objects.filter(is_council_member=True).order_by("name")
    )
    total_members = len(members)
    present_members = [m for m in members if m.is_council_present]
    total_present = len(present_members)
    votes_for = sum(1 for v in votes if v.vote == "for")
    votes_against = sum(1 for v in votes if v.vote == "against")
    votes_abstain = sum(1 for v in votes if v.vote == "abstain")
    total_voted = len(votes)
    quorum_needed = (total_members // 2) + 1
    quorum_met = total_present >= quorum_needed

    chairman = next((m for m in members if m.is_council_chairman), None)
    chairman_vote = None
    if chairman:
        cv = next((v for v in votes if v.agency_id == chairman.id), None)
        if cv:
            chairman_vote = cv.vote

    # Determine result
    if not quorum_met:
        result = "no_quorum"
    elif votes_for > votes_against:
        result = "passed"
    elif votes_against > votes_for:
        result = "failed"
    else:
        if chairman_vote == "for":
            result = "passed_chairman"
        elif chairman_vote == "against":
            result = "failed_chairman"
        else:
            result = "tied"

    vote_list = [
        {
            "agencyId": v.agency_id,
            "agencyName": v.agency.name,
            "vote": v.vote,
        }
        for v in votes
    ]

    tally = {
        "totalMembers": total_members,
        "totalPresent": total_present,
        "votesFor": votes_for,
        "votesAgainst": votes_against,
        "votesAbstain": votes_abstain,
        "totalVoted": total_voted,
        "quorumNeeded": quorum_needed,
        "quorumMet": quorum_met,
        "result": result,
        "chairmanAgencyId": chairman.id if chairman else None,
    }

    return {"votes": vote_list, "tally": tally}


def build_vote_record(ci):
    """Build a frozen vote snapshot including 'did not vote' entries."""
    from .models import Agency

    data = _build_live_tally(ci)
    members = list(
        Agency.objects.filter(is_council_member=True).order_by("name")
    )
    voted_ids = {v["agencyId"] for v in data["votes"]}
    # Add "did not vote" entries for members who haven't voted
    for m in members:
        if m.id not in voted_ids:
            data["votes"].append({
                "agencyId": m.id,
                "agencyName": m.name,
                "vote": "did_not_vote",
            })
    return data


def serialize_change_request(cr):
    """Serialize a change request for the approval queue."""
    return {
        "id": cr.id,
        "agencyId": cr.agency_id,
        "agencyName": cr.agency.name,
        "requester": cr.requester.username,
        "fieldName": cr.field_name,
        "description": cr.description,
        "proposedChanges": cr.proposed_changes,
        "status": cr.status,
        "adminNote": cr.admin_note,
        "reviewedBy": cr.reviewed_by.username if cr.reviewed_by else None,
        "createdAt": cr.created_at.isoformat(),
        "reviewedAt": cr.reviewed_at.isoformat() if cr.reviewed_at else None,
    }


def _resolve_workspace_names(workspaces):
    """Resolve assignedTo IDs to names for display."""
    char_ids = [w["assignedTo"] for w in workspaces if w.get("assignedType") == "character" and w.get("assignedTo")]
    npc_ids = [w["assignedTo"] for w in workspaces if w.get("assignedType") == "npc" and w.get("assignedTo")]
    char_names = {c.id: c.name for c in Character.objects.filter(id__in=char_ids).only("id", "name")} if char_ids else {}
    npc_names = {n.id: n.name for n in NPC.objects.filter(id__in=npc_ids).only("id", "name")} if npc_ids else {}
    result = []
    for w in workspaces:
        entry = {**w}
        if w.get("assignedType") == "character":
            entry["assignedName"] = char_names.get(w.get("assignedTo"), "Unknown")
        elif w.get("assignedType") == "npc":
            entry["assignedName"] = npc_names.get(w.get("assignedTo"), "Unknown")
        else:
            entry["assignedName"] = None
        result.append(entry)
    return result


def _filter_equipment_by_hidden(equipment, hidden_sections):
    """Remove equipment items whose category is hidden.

    Maps hidden section keys to equipment category names and filters out
    matching equipment keys using BaseConfig.
    """
    cat_key_map = {"aviationUnits": "Aviation Units", "baseDefenses": "Base Defenses"}
    hidden_cats = {cat_key_map[k] for k in hidden_sections if k in cat_key_map}
    if not hidden_cats:
        return equipment

    config = BaseConfig.load()
    hidden_eq_keys = {
        eq["key"]
        for eq in (config.equipment_types or [])
        if (eq.get("category") or "Other") in hidden_cats
    }
    return [k for k in equipment if k not in hidden_eq_keys]


def serialize_base(base, is_admin=True, character_class=None, base_config=None, agency=None):
    """Serialize a Base model instance.

    `hidden_sections` is a GM-side redaction tool for NPC bases — it should
    not apply when the viewer owns the agency (player agency members see
    their own bases in full). Admins bypass too.
    When character_class is provided, built items are filtered by class visibility.
    base_config is needed to look up required_class for built items.
    """
    show_all = is_admin or bool(agency and agency.is_player_agency)
    hidden = set(base.hidden_sections or [])

    # Filter equipment by category-level hidden sections for non-admins
    if show_all:
        equipment = base.equipment
    else:
        equipment = _filter_equipment_by_hidden(base.equipment or [], hidden)

    loc_type = base.location_type if (show_all or "locationType" not in hidden) else ""
    merits = base.merits if (show_all or "merits" not in hidden) else []
    facilities = base.facilities if (show_all or "facilities" not in hidden) else []
    workspaces = _resolve_workspace_names(base.workspaces or []) if (show_all or "workspaces" not in hidden) else []

    data = {
        "id": base.id,
        "name": base.name,
        "locationType": loc_type,
        "merits": merits,
        "facilities": facilities,
        "workspaces": workspaces,
        "equipment": equipment,
        "departments": [],
        "thriveGlobal": None,
        "notes": base.notes if (show_all or "notes" not in hidden) else "",
        "isHidden": base.is_hidden,
        "hiddenSections": (base.hidden_sections or []) if is_admin else [],
        "latitude": base.latitude if (show_all or "coordinates" not in hidden) else None,
        "longitude": base.longitude if (show_all or "coordinates" not in hidden) else None,
        # Optimistic concurrency token; bumped on every successful section save.
        "version": base.version,
    }

    # Auto-calculate department thrive from facilities
    if show_all or "departments" not in hidden:
        thrive_depts, thrive_mod, thrive_reasons = compute_base_thrive(base, agency=agency)
        data["departments"] = thrive_depts
        data["thriveGlobal"] = {"mod": thrive_mod, "reasons": thrive_reasons}

    # Add classified markers for redacted sections
    if not show_all:
        for section in hidden:
            key = section[0].upper() + section[1:]
            data[f"classified{key}"] = True

    return data


def _class_visible(item, character_class, unlocked_classes=None):
    """Check if a config item is visible to the given character class.

    Items with required_class 'general' or no required_class are visible to all.
    Admins pass character_class=None to bypass filtering.
    If unlocked_classes[rc] is True, the class restriction is bypassed for all
    characters (campaign has no character of that class — unlock the mechanics).
    """
    if character_class is None:
        return True
    rc = item.get("required_class", "general")
    if rc == "general":
        return True
    if unlocked_classes and unlocked_classes.get(rc):
        return True
    return rc == character_class


def serialize_base_config(config, character_class=None):
    """Serialize the BaseConfig singleton.

    When character_class is provided, filters options to only those
    visible to that class. Pass None (admin) to show all. Honors the
    SiteSettings.class_unlock_flags toggle so GMs can open up class-locked
    mechanics when no player has that class.
    """
    unlocked = None
    if character_class is not None:
        from exodus.models import SiteSettings
        unlocked = SiteSettings.load().class_unlock_flags or {}
    return {
        "locationTypes": [lt for lt in config.location_types if _class_visible(lt, character_class, unlocked)],
        "locationMerits": [lm for lm in config.location_merits if _class_visible(lm, character_class, unlocked)],
        "facilityTypes": [ft for ft in config.facility_types if _class_visible(ft, character_class, unlocked)],
        "equipmentTypes": [eq for eq in config.equipment_types if _class_visible(eq, character_class, unlocked)],
        "departments": BASE_DEPARTMENTS,
        "thriveLabels": THRIVE_LABELS,
    }
