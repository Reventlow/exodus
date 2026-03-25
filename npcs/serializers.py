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


def serialize_npc(npc, is_admin=False):
    """Full NPC data for API responses.

    Stats (attributes, skills, health, etc.) are only included for superusers.
    """
    # Class visibility: show as CLASSIFIED for non-admins when flagged
    if is_admin or not npc.class_classified:
        char_class = npc.character_class
    else:
        char_class = "classified"

    data = {
        "id": npc.id,
        "name": npc.name,
        "characterClass": char_class,
        "classClassified": npc.class_classified if is_admin else None,
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

    # Stats — superuser only
    if is_admin:
        data["attributes"] = npc.attributes
        data["skills"] = npc.skills
        data["health"] = {
            "bashing": npc.health_bashing,
            "lethal": npc.health_lethal,
            "aggravated": npc.health_aggravated,
        }
        data["size"] = npc.size
        data["mentalLoad"] = npc.mental_load
        data["willpowerCurrent"] = npc.willpower_current
        data["experience"] = npc.experience
        data["merits"] = npc.merits
        data["flaws"] = npc.flaws
        data["specialisations"] = npc.specialisations

    return data


def serialize_npc_summary(npc, is_admin=False):
    """Brief NPC data for list views."""
    if is_admin or not npc.class_classified:
        char_class = npc.character_class
    else:
        char_class = "classified"

    return {
        "id": npc.id,
        "name": npc.name,
        "characterClass": char_class,
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
