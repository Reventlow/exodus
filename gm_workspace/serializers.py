"""Serializers for the GM workspace."""
from django.contrib.auth import get_user_model

User = get_user_model()


def _character_name(user):
    """Return the user's first character name, falling back to username."""
    if not user:
        return None
    char = user.characters.first() if hasattr(user, "characters") else None
    return char.name if char else user.username


def serialize_user_option(user):
    """Minimal user serialisation for the share-with multiselect."""
    return {
        "id": user.id,
        "username": user.username,
        "displayName": _character_name(user),
    }


def serialize_story_idea(idea, user=None, include_content=True):
    """Serialize a StoryIdea. `include_content=False` returns a summary."""
    data = {
        "id": idea.id,
        "title": idea.title,
        "tags": idea.tags,
        "pinned": idea.pinned,
        "createdBy": idea.created_by.username if idea.created_by else None,
        "createdAt": idea.created_at.isoformat(),
        "updatedAt": idea.updated_at.isoformat(),
        "isShared": idea.shared_with.exists(),
    }
    if include_content:
        data["content"] = idea.content
    else:
        excerpt = (idea.content or "")[:200]
        if len(idea.content or "") > 200:
            excerpt = excerpt.rsplit(" ", 1)[0] + "..."
        data["excerpt"] = excerpt

    # Only expose the shared_with roster to GMs
    is_admin = bool(user and user.is_superuser)
    if is_admin:
        data["sharedWith"] = [
            {"id": u.id, "username": u.username, "displayName": _character_name(u)}
            for u in idea.shared_with.all()
        ]
    return data


def serialize_timeline_event(ev, include_description=True):
    data = {
        "id": ev.id,
        "title": ev.title,
        "eventType": ev.event_type,
        "gameDate": ev.game_date,
        "gameDateSort": ev.game_date_sort.isoformat() if ev.game_date_sort else None,
        "tags": ev.tags,
        "createdBy": ev.created_by.username if ev.created_by else None,
        "createdAt": ev.created_at.isoformat(),
        "updatedAt": ev.updated_at.isoformat(),
    }
    if include_description:
        data["description"] = ev.description
    else:
        excerpt = (ev.description or "")[:160]
        if len(ev.description or "") > 160:
            excerpt = excerpt.rsplit(" ", 1)[0] + "..."
        data["excerpt"] = excerpt
    return data


def serialize_campaign_session(session, include_summary=True):
    data = {
        "id": session.id,
        "sessionNumber": session.session_number,
        "title": session.title,
        "playedAt": session.played_at.isoformat() if session.played_at else None,
        "gameDate": session.game_date,
        "tags": session.tags,
        "createdBy": session.created_by.username if session.created_by else None,
        "createdAt": session.created_at.isoformat(),
        "updatedAt": session.updated_at.isoformat(),
    }
    if include_summary:
        data["summary"] = session.summary
    else:
        excerpt = (session.summary or "")[:200]
        if len(session.summary or "") > 200:
            excerpt = excerpt.rsplit(" ", 1)[0] + "..."
        data["excerpt"] = excerpt
    return data


def serialize_brief(idea, user=None, include_content=True):
    """Player-facing serialisation — no sharedWith roster exposed."""
    data = {
        "id": idea.id,
        "title": idea.title,
        "tags": idea.tags,
        "createdAt": idea.created_at.isoformat(),
        "updatedAt": idea.updated_at.isoformat(),
    }
    if include_content:
        data["content"] = idea.content
    else:
        excerpt = (idea.content or "")[:200]
        if len(idea.content or "") > 200:
            excerpt = excerpt.rsplit(" ", 1)[0] + "..."
        data["excerpt"] = excerpt
    return data
