"""Serializers for the starmap application."""


# Scan level thresholds: successes needed to reach each level
SCAN_THRESHOLDS = {0: 3, 1: 5, 2: 8}  # current_level: successes_needed_for_next


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
    }

    # Claim info — visible to all
    if star.claimed_by_id:
        data["claimedBy"] = {
            "agencyId": star.claimed_by_id,
            "agencyName": star.claimed_by.name if star.claimed_by else None,
        }

    # GM sees ground truth
    if is_gm:
        data["scanLevelTruth"] = star.scan_level_truth
        data["resources"] = _serialize_resources_gm(star.resources or {}, rt_map)
        data["planets"] = star.planets

    # Agency-specific scan data
    scan = None
    if agency_scans is not None:
        scan = agency_scans.get(star.id)
    elif agency:
        scan = star.agency_scans.filter(agency=agency).first()

    if scan and scan.scan_level > 0:
        data["scanLevel"] = scan.scan_level
        data["scannedResources"] = scan.scanned_resources
        data["planets"] = star.planets
    elif not is_gm:
        data["scanLevel"] = 0

    return data


def serialize_agency_scan(scan):
    """Serialize an AgencyScan for the agency's scan project list."""
    return {
        "id": scan.id,
        "starSystemId": scan.star_system_id,
        "starSystemName": scan.star_system.name if scan.star_system else "",
        "scanLevel": scan.scan_level,
        "scannedResources": scan.scanned_resources,
        "currentSuccesses": scan.current_successes,
        "requiredSuccesses": scan.required_successes,
        "player": scan.player,
        "baseId": scan.base_id,
        "baseName": scan.base_name,
        "metadata": scan.metadata,
        "scannedAt": scan.scanned_at.isoformat() if scan.scanned_at else None,
    }