"""Manual JSON serialization for Agency models. No DRF dependency."""

from characters.models import Character
from npcs.models import NPC
from .models import GlobalFlaw, FTLProject, AgencyFTLProject, CouncilItem, CouncilVote, BaseConfig, Base

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
    # Hidden bases are only visible to superusers
    bases_qs = agency.bases.all() if is_admin else agency.bases.filter(is_hidden=False)
    if show_all:
        data["bases"] = [serialize_base(b, is_admin=is_admin) for b in bases_qs]
    elif is_field_visible(agency, "bases"):
        serialized_bases = []
        for b in bases_qs:
            base_path = f"bases.{b.id}"
            if not is_field_visible(agency, base_path):
                serialized_bases.append({"id": b.id, "name": b.name, "classified": True})
            else:
                sb = serialize_base(b, is_admin=is_admin)
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
        {"id": n.id, "name": n.name, "type": "npc"}
        for n in NPC.objects.filter(agency=agency).order_by("name").only("id", "name")
    ]
    data["linkedDossiers"] = linked_characters + linked_npcs

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


def serialize_base(base, is_admin=True):
    """Serialize a Base model instance.

    When is_admin is False, sections listed in hidden_sections are redacted.
    """
    hidden = set(base.hidden_sections or [])

    # Filter equipment by category-level hidden sections for non-admins
    if is_admin:
        equipment = base.equipment
    else:
        equipment = _filter_equipment_by_hidden(base.equipment or [], hidden)

    data = {
        "id": base.id,
        "name": base.name,
        "locationType": base.location_type if (is_admin or "locationType" not in hidden) else "",
        "merits": base.merits if (is_admin or "merits" not in hidden) else [],
        "facilities": base.facilities if (is_admin or "facilities" not in hidden) else [],
        "workspaces": _resolve_workspace_names(base.workspaces or []) if (is_admin or "workspaces" not in hidden) else [],
        "equipment": equipment,
        "notes": base.notes if (is_admin or "notes" not in hidden) else "",
        "isHidden": base.is_hidden,
        "hiddenSections": (base.hidden_sections or []) if is_admin else [],
    }

    # Add classified markers for redacted sections
    if not is_admin:
        for section in hidden:
            key = section[0].upper() + section[1:]
            data[f"classified{key}"] = True

    return data


def serialize_base_config(config):
    """Serialize the BaseConfig singleton."""
    return {
        "locationTypes": config.location_types,
        "locationMerits": config.location_merits,
        "facilityTypes": config.facility_types,
        "equipmentTypes": config.equipment_types,
    }
