"""Manual JSON serialization for Agency models. No DRF dependency."""

from characters.models import Character
from npcs.models import NPC
from .models import GlobalFlaw, FTLProject, AgencyFTLProject, CouncilItem, BaseConfig, Base

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
        "isCouncilMember": agency.is_council_member,
        "isCouncilChairman": agency.is_council_chairman,
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

    # Global flaws — visible to everyone, not editable per-agency
    data["globalFlaws"] = [serialize_global_flaw(gf) for gf in GlobalFlaw.objects.all()]

    # Council items — visible to everyone, not editable per-agency
    data["councilItems"] = [serialize_council_item(ci) for ci in CouncilItem.objects.all()]

    # Bases + config for cost lookups (with per-base visibility for NPC agencies)
    if show_all:
        data["bases"] = [serialize_base(b) for b in agency.bases.all()]
    elif is_field_visible(agency, "bases"):
        serialized_bases = []
        for b in agency.bases.all():
            base_path = f"bases.{b.id}"
            if not is_field_visible(agency, base_path):
                serialized_bases.append({"id": b.id, "name": b.name, "classified": True})
            else:
                sb = serialize_base(b)
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
    config = BaseConfig.load()
    data["baseConfig"] = serialize_base_config(config)

    # Assignable entities for workspace assignment
    data["assignableCharacters"] = [
        {"id": c.id, "name": c.name} for c in Character.objects.all().order_by("name").only("id", "name")
    ]
    data["assignableNpcs"] = [
        {"id": n.id, "name": n.name}
        for n in NPC.objects.filter(agency=agency).order_by("name").only("id", "name")
    ]

    # FTL project assignments with progress
    data["ftlProjects"] = [
        {
            **serialize_ftl_project(afp.ftl_project),
            "assignmentId": afp.id,
            "currentSuccesses": afp.current_successes,
        }
        for afp in agency.ftl_assignments.select_related("ftl_project").all()
    ]

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


def serialize_agency_ftl_project(afp):
    """Serialize an AgencyFTLProject join record with nested project data."""
    return {
        **serialize_ftl_project(afp.ftl_project),
        "assignmentId": afp.id,
        "currentSuccesses": afp.current_successes,
    }


def serialize_council_item(ci):
    """Serialize a CouncilItem model instance."""
    return {
        "id": ci.id,
        "name": ci.name,
        "itemType": ci.item_type,
        "description": ci.description,
        "status": ci.status,
        "proposedBy": ci.proposed_by,
        "notes": ci.notes,
        "order": ci.order,
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


def serialize_base(base):
    """Serialize a Base model instance."""
    return {
        "id": base.id,
        "name": base.name,
        "locationType": base.location_type,
        "merits": base.merits,
        "facilities": base.facilities,
        "workspaces": _resolve_workspace_names(base.workspaces or []),
        "equipment": base.equipment,
        "notes": base.notes,
    }


def serialize_base_config(config):
    """Serialize the BaseConfig singleton."""
    return {
        "locationTypes": config.location_types,
        "locationMerits": config.location_merits,
        "facilityTypes": config.facility_types,
        "equipmentTypes": config.equipment_types,
    }
