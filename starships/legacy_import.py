"""Import the legacy Agency.fleet JSONField into real starship records.

The old schema stored fleets as a JSON list on each Agency row:

    Agency.fleet = [{shipClass, role, quantity, notes}, ...]

We keep that JSON untouched so existing code paths continue to work
(Release G will hide it once we're confident the real records are
authoritative). This helper reads the blob and creates matching
StarshipClass + Starship records in the new tables.

Idempotency — each Starship created by the importer carries a marker
tag in notes ('[legacy-import]'). On a second run an Agency is
considered already-migrated if any of its Starship rows carry the
marker; it is skipped unless force=True.

Fuzzy class → ShipType mapping — the legacy shipClass field is free-
text, so we do substring matching against both the key and the name of
each ShipType row. Unmatched entries fall back to a configurable
default ship type (cruiser) and are flagged in the report so GMs can
reassign them.
"""

LEGACY_MARKER = "[legacy-import]"

# Ordered matcher rules: lowercased needle -> ship_type.key
# First match wins. Rules run after a direct key/name exact match.
FUZZY_RULES = [
    ("drone", "drone"),
    ("solo", "solo"),
    ("fighter", "solo"),
    ("interceptor", "solo"),
    ("courier", "solo"),
    ("shuttle", "shuttle"),
    ("transport", "shuttle"),
    ("cruiser", "cruiser"),
    ("frigate", "cruiser"),
    ("destroyer", "cruiser"),
    ("corvette", "cruiser"),
    ("support", "support"),
    ("tender", "support"),
    ("tanker", "support"),
    ("science", "support"),
    ("repair", "support"),
    ("carrier", "carrier"),
    ("hangar", "carrier"),
    ("dreadnaught", "dreadnaught"),
    ("dreadnought", "dreadnaught"),
    ("battleship", "dreadnaught"),
    ("flagship", "dreadnaught"),
]

DEFAULT_SHIP_TYPE_KEY = "cruiser"


def _match_ship_type(raw_name, ship_types_by_key, ship_types_by_name_lower):
    """Pick a ShipType for a legacy class string. Returns (type, confidence)."""
    if not raw_name:
        return ship_types_by_key.get(DEFAULT_SHIP_TYPE_KEY), "default"

    needle = raw_name.strip().lower()
    # Exact key
    if needle in ship_types_by_key:
        return ship_types_by_key[needle], "exact-key"
    # Exact display name
    if needle in ship_types_by_name_lower:
        return ship_types_by_name_lower[needle], "exact-name"
    # Fuzzy substring
    for pattern, key in FUZZY_RULES:
        if pattern in needle and key in ship_types_by_key:
            return ship_types_by_key[key], f"fuzzy:{pattern}"
    # Fall back to default
    return ship_types_by_key.get(DEFAULT_SHIP_TYPE_KEY), "default"


def legacy_status():
    """Return a summary of how much legacy data is waiting to be imported.

    Counts entries per agency and flags agencies that already have at
    least one legacy-tagged Starship. The settings UI calls this to
    label its button.
    """
    from agencies.models import Agency
    from .models import Starship

    agencies_with_marker = set(
        Starship.objects.filter(notes__contains=LEGACY_MARKER)
        .values_list("agency_id", flat=True)
        .distinct()
    )

    pending_entries = 0
    already_imported = 0
    agencies_pending = []
    for agency in Agency.objects.all():
        entries = agency.fleet or []
        if not entries:
            continue
        if agency.id in agencies_with_marker:
            already_imported += len(entries)
            continue
        pending_entries += len(entries)
        agencies_pending.append({
            "agency_id": agency.id,
            "agency_name": agency.name,
            "entries": len(entries),
        })

    return {
        "pending_entries": pending_entries,
        "already_imported": already_imported,
        "agencies_pending": agencies_pending,
    }


def import_agency_fleet(agency, dry_run=False, force=False):
    """Import one agency's legacy fleet JSON into real records.

    Returns a report dict. Never raises — errors become items in
    `errors` so the caller can continue processing other agencies.
    """
    from django.db import transaction
    from .models import ShipType, Starship, StarshipClass

    report = {
        "agency_id": agency.id,
        "agency_name": agency.name,
        "processed_entries": 0,
        "created_classes": 0,
        "reused_classes": 0,
        "created_ships": 0,
        "skipped": False,
        "dry_run": dry_run,
        "warnings": [],
        "errors": [],
    }

    entries = agency.fleet or []
    if not entries:
        report["skipped"] = True
        report["warnings"].append("No legacy fleet entries.")
        return report

    # Idempotency check
    has_marker = Starship.objects.filter(
        agency=agency, notes__contains=LEGACY_MARKER,
    ).exists()
    if has_marker and not force:
        report["skipped"] = True
        report["warnings"].append(
            "Agency already has legacy-tagged ships; use force=True to re-run."
        )
        return report

    # Preload ship type index
    ship_types = list(ShipType.objects.all())
    by_key = {t.key: t for t in ship_types}
    by_name_lower = {t.name.lower(): t for t in ship_types}

    if not ship_types:
        report["errors"].append("No ShipType rows configured; cannot import.")
        return report

    def _do_import():
        for entry in entries:
            raw_class = (entry.get("shipClass") or "").strip()
            quantity = int(entry.get("quantity") or 1)
            role = (entry.get("role") or "").strip()
            legacy_notes = (entry.get("notes") or "").strip()
            report["processed_entries"] += 1

            if not raw_class:
                report["warnings"].append(
                    f"Skipped entry with blank shipClass: {entry!r}"
                )
                continue

            ship_type, confidence = _match_ship_type(raw_class, by_key, by_name_lower)
            if ship_type is None:
                report["errors"].append(
                    f"Could not resolve ship type for '{raw_class}'."
                )
                continue
            if confidence == "default":
                report["warnings"].append(
                    f"'{raw_class}' defaulted to {ship_type.name}; review manually."
                )

            # Find or create a class. Per-agency owned class named after
            # the legacy string so the GM can tune it after import.
            cls_qs = StarshipClass.objects.filter(
                created_by=agency, name=raw_class, ship_type=ship_type,
            )
            cls = cls_qs.first()
            if cls is None:
                cls = StarshipClass(
                    name=raw_class,
                    ship_type=ship_type,
                    created_by=agency,
                    size=ship_type.min_size,
                    description=(
                        f"Imported from legacy Agency.fleet ({confidence} match). "
                        + (f"Role: {role}. " if role else "")
                        + (f"Legacy notes: {legacy_notes}" if legacy_notes else "")
                    ).strip(),
                )
                if not dry_run:
                    cls.save()
                report["created_classes"] += 1
            else:
                report["reused_classes"] += 1

            # Create N Starship rows
            for i in range(1, max(1, quantity) + 1):
                hull_name = f"{raw_class} {i}" if quantity > 1 else raw_class
                hull_number = f"LEG-{agency.id:03d}-{report['created_ships'] + 1:04d}"
                if dry_run:
                    report["created_ships"] += 1
                    continue
                Starship.objects.create(
                    name=hull_name,
                    hull_number=hull_number,
                    starship_class=cls,
                    agency=agency,
                    status="active",
                    notes=(
                        f"{LEGACY_MARKER} imported from Agency.fleet. "
                        + (f"Role: {role}. " if role else "")
                        + (f"Legacy notes: {legacy_notes}" if legacy_notes else "")
                    ).strip(),
                )
                report["created_ships"] += 1

    if dry_run:
        _do_import()
    else:
        with transaction.atomic():
            _do_import()
    return report


def import_all_legacy_fleets(dry_run=False, force=False, agency_id=None):
    """Run the import across every agency (or a single one).

    Returns a list of per-agency report dicts plus a summary block.
    """
    from agencies.models import Agency

    qs = Agency.objects.all()
    if agency_id is not None:
        qs = qs.filter(pk=agency_id)

    reports = []
    totals = {
        "agencies_processed": 0,
        "agencies_skipped": 0,
        "entries_processed": 0,
        "classes_created": 0,
        "classes_reused": 0,
        "ships_created": 0,
        "errors": 0,
        "warnings": 0,
    }
    for agency in qs.order_by("name"):
        r = import_agency_fleet(agency, dry_run=dry_run, force=force)
        reports.append(r)
        if r["skipped"]:
            totals["agencies_skipped"] += 1
            continue
        totals["agencies_processed"] += 1
        totals["entries_processed"] += r["processed_entries"]
        totals["classes_created"] += r["created_classes"]
        totals["classes_reused"] += r["reused_classes"]
        totals["ships_created"] += r["created_ships"]
        totals["errors"] += len(r["errors"])
        totals["warnings"] += len(r["warnings"])

    return {"totals": totals, "reports": reports, "dry_run": dry_run}
