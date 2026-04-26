"""Views for the news application."""

import datetime as _dt
import json
import os

from dateutil import parser as _dateutil_parser
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from .models import NewsArticle, NewsAttachment
from .serializers import serialize_article, serialize_article_summary

User = get_user_model()


def _coerce_game_date_sort(value):
    """Parse a client-supplied gameDateSort into a datetime (or None).

    Accepts ISO-8601 strings (including a trailing 'Z'), existing datetime
    instances, or None. Returns None for anything unparseable so a bad value
    never gets written straight into a DateTimeField as a string.
    """
    if value is None or value == "":
        return None
    if hasattr(value, "isoformat"):
        return value
    if isinstance(value, str):
        # Django's parse_datetime doesn't accept the 'Z' suffix.
        normalised = value.replace("Z", "+00:00")
        return parse_datetime(normalised)
    return None


def _derive_sort_from_game_date(game_date):
    """Best-effort parse of the free-text game_date into a sortable datetime.

    The UI's IN-GAME DATE field is free-form text ("May 5, 2036",
    "9 February 2036, Evening", "2036-05-05"). We use dateutil.parser with
    fuzzy=True so trailing words like "Evening" don't break parsing, and
    anchor missing time components to midday UTC so chronological ordering
    is stable across articles that only specify a day.

    Returns a timezone-aware datetime, or None if nothing parseable is found.
    """
    if not game_date or not isinstance(game_date, str):
        return None
    default = _dt.datetime(2036, 1, 1, 12, 0, 0, tzinfo=_dt.timezone.utc)
    try:
        parsed = _dateutil_parser.parse(game_date, fuzzy=True, default=default)
    except (ValueError, OverflowError, _dateutil_parser.ParserError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@login_required
def news_list_page(request):
    """Landing page showing news articles."""
    return render(request, "news/list.html")


@login_required
def news_detail_page(request, slug):
    """Single article view."""
    article = get_object_or_404(NewsArticle, slug=slug)
    if not article.is_visible_to(request.user):
        return render(request, "news/list.html")  # Redirect to list silently
    return render(request, "news/detail.html", {"article_slug": slug})


# ---------------------------------------------------------------------------
# API views
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_news_list(request):
    """List visible articles or create a new one (superuser only)."""
    if request.method == "GET":
        user = request.user
        if user.is_superuser:
            articles = NewsArticle.objects.all()
        else:
            from django.db.models import Q
            articles = NewsArticle.objects.filter(
                Q(visibility="public")
                | Q(visibility="eyes_only", eyes_only_player=user)
                | Q(visibility="eyes_only", shared_with=user)
            ).distinct()

        articles = articles.select_related("author", "eyes_only_player").prefetch_related("attachments")
        data = [serialize_article_summary(a, user=user) for a in articles]
        return JsonResponse(data, safe=False)

    # POST — create article (superuser only)
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    title = body.get("title", "Untitled")
    content = body.get("content", "")
    visibility = body.get("visibility", "hidden")
    game_date = body.get("gameDate", "")
    # Prefer an explicit client-supplied sort; otherwise derive one from the
    # free-text game_date so UI-created articles slot into the timeline.
    if "gameDateSort" in body:
        game_date_sort = _coerce_game_date_sort(body.get("gameDateSort"))
    else:
        game_date_sort = _derive_sort_from_game_date(game_date)
    eyes_only_player_id = body.get("eyesOnlyPlayerId")

    if visibility not in ("hidden", "eyes_only", "public"):
        return JsonResponse({"error": "Invalid visibility"}, status=400)

    eyes_only_player = None
    if visibility == "eyes_only" and eyes_only_player_id:
        try:
            eyes_only_player = User.objects.get(pk=eyes_only_player_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "Player not found"}, status=400)

    article = NewsArticle.objects.create(
        title=title,
        content=content,
        visibility=visibility,
        game_date=game_date,
        game_date_sort=game_date_sort,
        eyes_only_player=eyes_only_player,
        author=request.user,
    )
    return JsonResponse(serialize_article(article, user=request.user), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_news_detail(request, pk):
    """Get, update, or delete a single article."""
    article = get_object_or_404(
        NewsArticle.objects.select_related("author", "eyes_only_player").prefetch_related("attachments"),
        pk=pk,
    )

    if request.method == "GET":
        if not article.is_visible_to(request.user):
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse(serialize_article(article, user=request.user))

    # PUT / DELETE — superuser only
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "DELETE":
        # Clean up featured image
        if article.featured_image:
            path = article.featured_image.path
            if os.path.exists(path):
                os.remove(path)
        # Clean up attachments
        for att in article.attachments.all():
            if att.file and os.path.exists(att.file.path):
                os.remove(att.file.path)
        article.delete()
        return JsonResponse({"ok": True})

    # PUT — update
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    if "title" in body:
        article.title = body["title"]
    if "content" in body:
        article.content = body["content"]
    if "gameDate" in body:
        article.game_date = body["gameDate"]
        # If the caller updates the display date but doesn't also send an
        # explicit sort key, re-derive it from the new text.
        if "gameDateSort" not in body:
            article.game_date_sort = _derive_sort_from_game_date(body["gameDate"])
    if "gameDateSort" in body:
        article.game_date_sort = _coerce_game_date_sort(body["gameDateSort"])
    if "featuredImageFull" in body:
        article.featured_image_full = body["featuredImageFull"]
    if "visibility" in body:
        new_vis = body["visibility"]
        if new_vis in ("hidden", "eyes_only", "public"):
            article.visibility = new_vis
            if new_vis == "public" and not article.published_at:
                article.published_at = timezone.now()
    if "eyesOnlyPlayerId" in body:
        pid = body["eyesOnlyPlayerId"]
        if pid:
            try:
                article.eyes_only_player = User.objects.get(pk=pid)
            except User.DoesNotExist:
                pass
        else:
            article.eyes_only_player = None

    article.save()
    return JsonResponse(serialize_article(article, user=request.user))


@login_required
@require_http_methods(["POST"])
def api_news_release(request, pk):
    """Release an eyes-only article to public visibility."""
    article = get_object_or_404(NewsArticle, pk=pk)

    if not article.can_release(request.user):
        return JsonResponse({"error": "Permission denied"}, status=403)

    article.visibility = "public"
    article.released_at = timezone.now()
    if not article.published_at:
        article.published_at = timezone.now()
    article.save()
    return JsonResponse(serialize_article(article, user=request.user))


@login_required
@require_http_methods(["POST"])
def api_news_share(request, pk):
    """Share an eyes-only article with specific players. Permanent — cannot be revoked."""
    article = get_object_or_404(NewsArticle, pk=pk)

    if not article.can_release(request.user):
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user_ids = body.get("userIds", [])
    if not user_ids:
        return JsonResponse({"error": "No users specified"}, status=400)

    users = User.objects.filter(pk__in=user_ids)
    for u in users:
        article.shared_with.add(u)

    return JsonResponse(serialize_article(article, user=request.user))


@login_required
@require_http_methods(["POST"])
def api_news_image(request, pk):
    """Upload or replace the featured image for an article."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    article = get_object_or_404(NewsArticle, pk=pk)
    image = request.FILES.get("image")

    if not image:
        return JsonResponse({"error": "No image provided"}, status=400)

    if image.size > 10 * 1024 * 1024:
        return JsonResponse({"error": "Image too large (max 10MB)"}, status=400)

    allowed_types = ("image/jpeg", "image/png", "image/webp", "image/gif")
    if image.content_type not in allowed_types:
        return JsonResponse({"error": "Invalid image type"}, status=400)

    # Remove old image
    if article.featured_image:
        old_path = article.featured_image.path
        if os.path.exists(old_path):
            os.remove(old_path)

    article.featured_image = image
    article.save()
    return JsonResponse({"featuredImage": article.featured_image.url})


@login_required
@require_http_methods(["POST"])
def api_news_attachment(request, pk):
    """Upload an attachment to an article."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    article = get_object_or_404(NewsArticle, pk=pk)
    uploaded_file = request.FILES.get("file")

    if not uploaded_file:
        return JsonResponse({"error": "No file provided"}, status=400)

    if uploaded_file.size > 20 * 1024 * 1024:
        return JsonResponse({"error": "File too large (max 20MB)"}, status=400)

    attachment = NewsAttachment.objects.create(
        article=article,
        file=uploaded_file,
        filename=uploaded_file.name,
    )
    return JsonResponse({
        "id": attachment.id,
        "filename": attachment.filename,
        "url": attachment.file.url,
    }, status=201)


@login_required
@require_http_methods(["DELETE"])
def api_news_attachment_delete(request, pk, attachment_pk):
    """Delete an attachment from an article."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    attachment = get_object_or_404(NewsAttachment, pk=attachment_pk, article_id=pk)
    if attachment.file and os.path.exists(attachment.file.path):
        os.remove(attachment.file.path)
    attachment.delete()
    return JsonResponse({"ok": True})
