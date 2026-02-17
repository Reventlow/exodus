"""Manual JSON serialization for NPC model. No DRF dependency."""


def serialize_npc(npc):
    """Full NPC data for API responses."""
    return {
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
        "assignedTo": npc.assigned_to.username,
        "assignedToId": npc.assigned_to.id,
        "createdBy": npc.created_by.username if npc.created_by else None,
        "createdAt": npc.created_at.isoformat(),
        "updatedAt": npc.updated_at.isoformat(),
    }


def serialize_npc_summary(npc):
    """Brief NPC data for list views."""
    return {
        "id": npc.id,
        "name": npc.name,
        "image": npc.image.url if npc.image else None,
        "occupation": npc.occupation,
        "state": npc.state,
        "assignedTo": npc.assigned_to.username,
    }
