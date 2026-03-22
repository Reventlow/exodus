"""Manual JSON serialization for NPC model. No DRF dependency."""


def serialize_npc_note(note):
    """Single note data."""
    return {
        "id": note.id,
        "author": note.author.username,
        "authorId": note.author.id,
        "text": note.text,
        "createdAt": note.created_at.isoformat(),
        "updatedAt": note.updated_at.isoformat(),
    }


def serialize_npc(npc):
    """Full NPC data for API responses."""
    data = {
        "id": npc.id,
        "name": npc.name,
        "image": npc.image.url if npc.image else None,
        "age": npc.age,
        "sex": npc.sex,
        "pronouns": npc.pronouns,
        "nationality": npc.nationality,
        "occupation": npc.occupation,
        "state": npc.state,
        "bio": npc.bio,
        "assignedTo": npc.assigned_to.username if npc.assigned_to else None,
        "assignedToId": npc.assigned_to.id if npc.assigned_to else None,
        "createdBy": npc.created_by.username if npc.created_by else None,
        "createdAt": npc.created_at.isoformat(),
        "updatedAt": npc.updated_at.isoformat(),
        "isNpcDossier": npc.is_npc_dossier,
        "agencyId": npc.agency_id,
        "agencyName": npc.agency.name if npc.agency else None,
        "isHidden": npc.is_hidden,
    }

    # Include notes for NPC dossiers
    if npc.is_npc_dossier:
        notes = npc.notes.select_related("author").all()
        data["notes"] = [serialize_npc_note(n) for n in notes]

    return data


def serialize_npc_summary(npc):
    """Brief NPC data for list views."""
    return {
        "id": npc.id,
        "name": npc.name,
        "image": npc.image.url if npc.image else None,
        "nationality": npc.nationality,
        "occupation": npc.occupation,
        "state": npc.state,
        "assignedTo": npc.assigned_to.username if npc.assigned_to else None,
        "assignedToIsAdmin": npc.assigned_to.is_superuser if npc.assigned_to else False,
        "isNpcDossier": npc.is_npc_dossier,
        "agencyName": npc.agency.name if npc.agency else None,
        "isHidden": npc.is_hidden,
    }
