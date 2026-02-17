"""Manual JSON serialization for Character model. No DRF dependency."""


def serialize_character(character):
    """Full character data for API responses."""
    return {
        "id": character.id,
        "owner": character.owner.username,
        "owner_id": character.owner.id,
        "name": character.name,
        "concept": character.concept,
        "chronicle": character.chronicle,
        "virtue": character.virtue,
        "vice": character.vice,
        "dossier": character.dossier,
        "profilePicture": character.profile_picture.url if character.profile_picture else None,
        "attributes": character.attributes,
        "skills": character.skills,
        "health": {
            "bashing": character.health_bashing,
            "lethal": character.health_lethal,
            "aggravated": character.health_aggravated,
        },
        "size": character.size,
        "mentalLoad": character.mental_load,
        "merits": character.merits,
        "flaws": character.flaws,
        "pullingStrings": character.pulling_strings,
        "inventory": character.inventory,
        "experience": character.experience,
        "willpower": {"current": character.willpower_current},
    }


def serialize_character_summary(character):
    """Brief character data for list views."""
    return {
        "id": character.id,
        "owner": character.owner.username,
        "name": character.name,
        "concept": character.concept,
        "profilePicture": character.profile_picture.url if character.profile_picture else None,
    }
