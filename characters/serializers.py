"""Manual JSON serialization for Character model. No DRF dependency."""


def serialize_character_pulling_string(cps):
    """Serialize a through-table entry (pulling string + optional NPC link)."""
    ps = cps.pulling_string
    data = {
        "id": cps.id,  # through-table ID (unique per character instance)
        "pullingStringId": ps.id,
        "name": ps.name,
        "description": ps.description,
        "cost": ps.cost,
        "category": ps.category,
        "isLinkable": ps.is_linkable,
    }
    if cps.linked_npc:
        data["linkedNpc"] = {
            "id": cps.linked_npc.id,
            "name": cps.linked_npc.name,
            "image": cps.linked_npc.image.url if cps.linked_npc.image else None,
        }
    else:
        data["linkedNpc"] = None
    return data


def serialize_character_merit(cm):
    """Serialize a through-table entry (merit + chosen rating)."""
    m = cm.merit
    return {
        "id": cm.id,
        "meritId": m.id,
        "name": m.name,
        "description": m.description,
        "category": m.category,
        "classRestriction": m.class_restriction,
        "rating": cm.rating,
        "maxRating": m.cost,
        "minRating": m.min_cost,
        "prerequisites": m.prerequisites,
        "effects": m.effects,
    }


def serialize_character(character, user=None):
    """Full character data for API responses."""
    cps_entries = character.character_pulling_strings.select_related(
        "pulling_string", "linked_npc"
    ).all()

    cm_entries = character.character_merits.select_related("merit").all()

    return {
        "id": character.id,
        "owner": character.owner.username,
        "owner_id": character.owner.id,
        "name": character.name,
        "characterClass": character.character_class,
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
        "merits": [serialize_character_merit(cm) for cm in cm_entries],
        "flaws": character.flaws,
        "pullingStrings": [
            serialize_character_pulling_string(cps)
            for cps in cps_entries
        ],
        "inventory": character.inventory,
        "specialisations": character.specialisations,
        "experience": character.experience,
        "experienceUsed": character.experience_used,
        "pullingStringsCost": sum(cps.pulling_string.cost for cps in cps_entries),
        "classifiedNotes": character.classified_notes if (
            user and (user == character.owner or user.is_superuser)
        ) else None,
        "willpower": {"current": character.willpower_current},
        "xpTransfers": [
            {
                "amount": t.amount,
                "agencyReceived": t.agency_received,
                "agencyName": t.agency.name,
                "date": t.created_at.isoformat(),
            }
            for t in character.xp_transfers.select_related("agency").all()[:20]
        ],
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
