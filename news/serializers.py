"""Serializers for the news application."""


def _character_name(user):
    """Get the character name for a user, or fall back to username."""
    if not user:
        return None
    char = user.characters.first()
    return char.name if char else user.username


def serialize_attachment(attachment):
    """Serialize a NewsAttachment to a dict."""
    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "url": attachment.file.url,
        "uploadedAt": attachment.uploaded_at.isoformat(),
    }


def serialize_article(article, user=None):
    """Serialize a NewsArticle to a dict."""
    is_admin = user and user.is_superuser if user else False

    data = {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "content": article.content,
        "visibility": article.visibility,
        "gameDate": article.game_date,
        "gameDateSort": article.game_date_sort.isoformat() if article.game_date_sort else None,
        "featuredImage": article.featured_image.url if article.featured_image else None,
        "featuredImageFull": article.featured_image_full,
        "publishedAt": article.published_at.isoformat() if article.published_at else None,
        "createdAt": article.created_at.isoformat(),
        "updatedAt": article.updated_at.isoformat(),
        "author": article.author.username if article.author else None,
        "attachments": [
            serialize_attachment(a) for a in article.attachments.all()
        ],
        "canRelease": article.can_release(user) if user else False,
        "releasedAt": article.released_at.isoformat() if article.released_at else None,
        "sharedWith": [
            {"id": u.id, "name": _character_name(u)}
            for u in article.shared_with.all()
        ],
    }

    # Show eyes-only player on released articles (for everyone), active eyes-only, or admin
    if article.released_at and article.eyes_only_player:
        data["eyesOnlyPlayer"] = _character_name(article.eyes_only_player)
    elif is_admin:
        data["eyesOnlyPlayer"] = _character_name(article.eyes_only_player)
        data["eyesOnlyPlayerId"] = (
            article.eyes_only_player.id if article.eyes_only_player else None
        )
    elif article.visibility == "eyes_only" and user:
        if user == article.eyes_only_player:
            data["eyesOnlyPlayer"] = _character_name(article.eyes_only_player)

    return data


def serialize_article_summary(article, user=None):
    """Serialize a NewsArticle summary for list view (no full content)."""
    is_admin = user and user.is_superuser if user else False

    # Create excerpt from content (first ~200 chars of markdown)
    excerpt = article.content[:200]
    if len(article.content) > 200:
        excerpt = excerpt.rsplit(" ", 1)[0] + "..."

    data = {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "excerpt": excerpt,
        "visibility": article.visibility,
        "gameDate": article.game_date,
        "gameDateSort": article.game_date_sort.isoformat() if article.game_date_sort else None,
        "featuredImage": article.featured_image.url if article.featured_image else None,
        "featuredImageFull": article.featured_image_full,
        "publishedAt": article.published_at.isoformat() if article.published_at else None,
        "createdAt": article.created_at.isoformat(),
        "author": article.author.username if article.author else None,
        "canRelease": article.can_release(user) if user else False,
        "releasedAt": article.released_at.isoformat() if article.released_at else None,
        "attachmentCount": article.attachments.count(),
    }

    if article.released_at and article.eyes_only_player:
        data["eyesOnlyPlayer"] = _character_name(article.eyes_only_player)
    elif is_admin or (
        article.visibility == "eyes_only"
        and user
        and user == article.eyes_only_player
    ):
        data["eyesOnlyPlayer"] = _character_name(article.eyes_only_player)

    return data
