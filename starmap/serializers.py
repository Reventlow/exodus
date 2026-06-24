"""Serializers for the starmap application."""


# Scan level thresholds: successes needed to reach each level (LEGACY — the
# active system uses the difficulty-target + uncertainty model below).
SCAN_THRESHOLDS = {0: 3, 1: 5, 2: 8}  # current_level: successes_needed_for_next

# --- Star-intel scanning math (single source of truth) ---
SCAN_BASE_DIFFICULTY = 15        # base target successes for a perfect (0% uncertainty) read
UNCERTAINTY_PER_SUCCESS = 25     # uncertainty% added per success short of target (UNCAPPED — can exceed 100%)
FALSE_DATA_PENALTY = 3           # each active false public record adds this to the target
FALSE_DATA_PENALTY_CAP = 15      # max total disinformation penalty per system
LIVABLE_REVEAL_UNCERTAINTY = 60  # at/below this uncertainty%, the livable flag is revealed


def base_scan_target(star):
    """Per-system base target successes = 15 + difficulty_mod, clamped 5..25."""
    return max(5, min(25, SCAN_BASE_DIFFICULTY + int(getattr(star, "difficulty_mod", 0) or 0)))


def effective_scan_target(star, false_count=0):
    """Base target plus disinformation penalty (capped). false_count = number of
    active false public records for the system."""
    penalty = min(FALSE_DATA_PENALTY_CAP, max(0, int(false_count)) * FALSE_DATA_PENALTY)
    return base_scan_target(star) + penalty


def scan_uncertainty(accumulated, target):
    """Uncertainty% = max(0, (target - accumulated) * UNCERTAINTY_PER_SUCCESS).
    0 = perfect (at/over target); UNCAPPED above, so being far off can read
    well over 100% ("no idea")."""
    return max(0, (int(target) - int(accumulated)) * UNCERTAINTY_PER_SUCCESS)


def observatory_dice(level):
    """Dice for one observatory: 5 base + 5 (Ground Telescope, level>=1)
    + 5 (Deep-Space Tracking, level>=2). 5/10/15."""
    lvl = int(level or 0)
    return 5 + (5 if lvl >= 1 else 0) + (5 if lvl >= 2 else 0)


def list_agency_observatories(agency):
    """One scannable observatory per base that has an Observatory facility.
    A base's stacked observatory (Ground Telescope + Deep-Space Tracking) is a
    single observatory whose dice come from its highest observatory level.
    Returns [{baseId, baseName, level, dice}]."""
    out = []
    for base in agency.bases.all():
        levels = [int(f.get("level", 0) or 0) for f in (base.facilities or [])
                  if f.get("key") == "observatory"]
        if not levels:
            continue
        lvl = max(levels)
        out.append({
            "baseId": base.id,
            "baseName": base.name,
            "level": lvl,
            "dice": observatory_dice(lvl),
        })
    return out


def approx_resources(resources, uncertainty, seed, rt_map=None):
    """Player-facing approximate readout: ground truth fuzzed by uncertainty%.
    At 0% uncertainty lo=hi=truth (exact); higher uncertainty widens a
    deterministic ± window so the same (agency, system) reads consistently."""
    rt_map = rt_map if rt_map is not None else _resource_type_map()
    out = {}
    s = seed
    # Uncapped: frac can exceed 1.0, widening the window past the base bracket.
    frac = max(0, int(uncertainty)) / 100.0
    for key, rt in rt_map.items():
        base = int(resources.get(key, 0) or 0)
        if frac <= 0:
            out[key] = {"min": base, "max": base, "unit": rt.unit_label}
            continue
        window = max(1, int(round((rt.scan_bracket_wide or 40) * frac)))
        s = (s * 9301 + 49297) % 233280
        offset = int(((s / 233280) - 0.5) * window)
        lo = max(0, base - window + offset)
        hi = max(lo, base + window + offset)
        out[key] = {"min": lo, "max": hi, "unit": rt.unit_label}
    return out


def _resource_type_map():
    """Return {key: ResourceType} for all configured resources."""
    from .models import ResourceType
    return {rt.key: rt for rt in ResourceType.objects.all()}


def compute_scan_brackets(resources, scan_level, seed, resource_types=None):
    """Return {key: {min, max, unit}} brackets for a scan result.

    resources: ground-truth dict on StarSystem, integers in absolute units.
    scan_level: 1=survey (wide), 2=focused (narrow), 3=deep (exact).
    seed: deterministic offset so a given (agency, system) always brackets
          ground truth the same way.
    """
    if scan_level <= 0:
        return {}

    rt_map = resource_types if resource_types is not None else _resource_type_map()
    result = {}
    s = seed
    for key, rt in rt_map.items():
        base = int(resources.get(key, 0) or 0)
        if scan_level >= 3:
            lo, hi = base, base
        else:
            bracket = rt.scan_bracket_wide if scan_level == 1 else rt.scan_bracket_narrow
            # Deterministic offset in [-bracket/2, +bracket/2] — shifts the
            # window so the truth isn't always dead centre.
            s = (s * 9301 + 49297) % 233280
            offset = int(((s / 233280) - 0.5) * bracket)
            lo = max(0, base - bracket + offset)
            hi = max(lo, base + bracket + offset)
            s += 1
        result[key] = {"min": lo, "max": hi, "unit": rt.unit_label}
    return result


def _serialize_resources_gm(resources, rt_map):
    """GM view: exact integers plus unit labels."""
    out = {}
    for key, rt in rt_map.items():
        out[key] = {
            "value": int(resources.get(key, 0) or 0),
            "unit": rt.unit_label,
        }
    return out


def serialize_star_system(star, agency=None, user=None, agency_scans=None, resource_types=None):
    """Serialize a StarSystem. Scan data included per agency."""
    is_gm = user and user.is_superuser
    rt_map = resource_types if resource_types is not None else _resource_type_map()

    data = {
        "id": star.id,
        "name": star.name,
        "x": star.x,
        "y": star.y,
        "z": star.z,
        "dist": star.distance,
        "spectral": star.spectral_type,
        "isSol": star.is_sol,
        "isEndgame": star.is_endgame,
        "discovered": star.discovered,
        "scanTarget": base_scan_target(star),
    }

    # Claim info — visible to all
    if star.claimed_by_id:
        data["claimedBy"] = {
            "agencyId": star.claimed_by_id,
            "agencyName": star.claimed_by.name if star.claimed_by else None,
        }

    # GM sees ground truth (incl. the single-source-of-truth star-intel fields)
    if is_gm:
        data["scanLevelTruth"] = star.scan_level_truth
        data["resources"] = _serialize_resources_gm(star.resources or {}, rt_map)
        data["planets"] = star.planets
        data["hasLivablePlanet"] = star.has_livable_planet
        data["difficultyMod"] = star.difficulty_mod

    # Agency-specific scan data (the agency's private, approximate readout)
    scan = None
    if agency_scans is not None:
        scan = agency_scans.get(star.id)
    elif agency:
        scan = star.agency_scans.filter(agency=agency).first()

    if scan and scan.current_successes > 0:
        target = scan.required_successes or base_scan_target(star)
        uncertainty = scan_uncertainty(scan.current_successes, target)
        data["scanAccumulated"] = scan.current_successes
        data["scanTarget"] = target
        data["scanUncertainty"] = uncertainty
        data["scannedResources"] = scan.scanned_resources
        data["scanLevel"] = scan.scan_level  # vestigial, kept for legacy callers
        if uncertainty <= LIVABLE_REVEAL_UNCERTAINTY:
            data["hasLivablePlanet"] = star.has_livable_planet
        data["planets"] = star.planets
    elif not is_gm:
        data["scanLevel"] = 0

    return data


def serialize_agency_scan(scan):
    """Serialize an AgencyScan for the agency's scan project list."""
    target = scan.required_successes or (base_scan_target(scan.star_system) if scan.star_system else SCAN_BASE_DIFFICULTY)
    return {
        "id": scan.id,
        "starSystemId": scan.star_system_id,
        "starSystemName": scan.star_system.name if scan.star_system else "",
        "scanLevel": scan.scan_level,
        "scannedResources": scan.scanned_resources,
        "currentSuccesses": scan.current_successes,
        "requiredSuccesses": scan.required_successes,
        "accumulated": scan.current_successes,
        "target": target,
        "uncertainty": scan_uncertainty(scan.current_successes, target),
        "player": scan.player,
        "baseId": scan.base_id,
        "baseName": scan.base_name,
        "metadata": scan.metadata,
        "scannedAt": scan.scanned_at.isoformat() if scan.scanned_at else None,
    }

def gather_star_intel():
    """GM oversight data for the star-intel system, as JSON-serializable dicts.
    Per discovered system: ground truth, base vs effective target (incl. the
    disinformation penalty), every agency's real accuracy, and the public
    records (with is_false exposed). Shared by the /gm/star-intel/ page and the
    MCP API endpoint."""
    from .models import StarSystem
    rt_map = _resource_type_map()
    out = []
    qs = (StarSystem.objects.filter(discovered=True)
          .prefetch_related("agency_scans__agency", "public_records__agency")
          .order_by("distance", "name"))
    for star in qs:
        false_count = sum(1 for r in star.public_records.all() if r.is_false)
        eff = effective_scan_target(star, false_count)
        scans = [{
            "agency": sc.agency.name if sc.agency else "?",
            "accumulated": sc.current_successes,
            "target": sc.required_successes or eff,
            "uncertainty": scan_uncertainty(sc.current_successes, sc.required_successes or eff),
        } for sc in star.agency_scans.all() if sc.current_successes > 0]
        records = [{
            "agency": r.agency.name if r.agency else "?",
            "is_false": r.is_false,
            "uncertainty": r.uncertainty,
        } for r in star.public_records.all()]
        out.append({
            "id": star.id,
            "name": star.name,
            "discovered": star.discovered,
            "has_livable_planet": star.has_livable_planet,
            "difficulty_mod": star.difficulty_mod,
            "base_target": base_scan_target(star),
            "effective_target": eff,
            "false_count": false_count,
            "resources": {k: int((star.resources or {}).get(k, 0) or 0) for k in rt_map},
            "truth": ", ".join(f"{rt.name}: {int((star.resources or {}).get(k, 0) or 0)}"
                               for k, rt in rt_map.items()),
            "scans": sorted(scans, key=lambda s: s["uncertainty"]),
            "records": records,
        })
    return out
