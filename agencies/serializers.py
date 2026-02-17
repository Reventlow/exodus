"""Manual JSON serialization for Agency models. No DRF dependency."""

CLASSIFIED = "CLASSIFIED"


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
        "attributes": vis_attributes(agency.attributes),
        "specializations": vis("specializations", agency.specializations),
        "merits": vis("merits", agency.merits),
        "flaws": vis("flaws", agency.flaws),
        "assets": vis("assets", agency.assets),
        "fleet": vis("fleet", agency.fleet),
        "conditions": vis("conditions", agency.conditions),
        "projects": vis("projects", agency.projects),
        "history": vis("history", agency.history),
    }

    # Include visibility map and change request counts for admins
    if is_admin:
        data["fieldVisibility"] = agency.field_visibility

    return data


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

    return {
        "id": agency.id,
        "name": agency.name,
        "alliance": vis("alliance", agency.alliance),
        "isPlayerAgency": agency.is_player_agency,
        "motto": vis("motto", agency.motto),
    }


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
