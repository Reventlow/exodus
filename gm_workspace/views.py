"""Views for the GM workspace.

- GM-only endpoints at /gm/* and /api/gm/*
- Player-only read endpoints at /my-briefs/* and /api/my-briefs/*
"""
import datetime as _dt
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods

from dateutil import parser as _dateutil_parser

from .models import CampaignSession, StoryIdea, TimelineEvent
from .serializers import (
    serialize_brief,
    serialize_campaign_session,
    serialize_story_idea,
    serialize_timeline_event,
    serialize_user_option,
)

User = get_user_model()


def _derive_sort_from_game_date(game_date):
    """Best-effort parse of a free-text in-game date into a sortable datetime.

    Mirrors `news.views._derive_sort_from_game_date`. Keeping a local copy
    avoids a cross-app import just for a utility.
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
# GM-only pages
# ---------------------------------------------------------------------------


@login_required
def workspace_landing(request):
    """Redirect /gm/ to the default tool (story ideas) for superusers."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Forbidden")
    return redirect("gm_workspace:ideas-page")


@login_required
def story_ideas_page(request):
    """Render the GM Story Ideas SPA. Superuser only."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Forbidden")
    return render(request, "gm_workspace/workspace.html", {"active_tool": "ideas"})


# ---------------------------------------------------------------------------
# GM-only API
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def api_story_ideas_list(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    if request.method == "GET":
        qs = StoryIdea.objects.all().prefetch_related("shared_with").select_related("created_by")
        data = [
            serialize_story_idea(idea, user=request.user, include_content=False)
            for idea in qs
        ]
        # Also return the roster of players who can receive briefs (everyone who is not a superuser)
        players = User.objects.filter(is_active=True, is_superuser=False).order_by("username")
        return JsonResponse({
            "ideas": data,
            "players": [serialize_user_option(u) for u in players],
        })

    # POST — create
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    idea = StoryIdea.objects.create(
        title=body.get("title", "Untitled"),
        content=body.get("content", ""),
        tags=body.get("tags", ""),
        pinned=bool(body.get("pinned", False)),
        created_by=request.user,
    )
    shared_ids = body.get("sharedWithIds") or []
    if shared_ids:
        idea.shared_with.set(
            User.objects.filter(pk__in=shared_ids, is_active=True, is_superuser=False)
        )
    return JsonResponse(serialize_story_idea(idea, user=request.user), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_story_ideas_detail(request, pk):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    idea = get_object_or_404(StoryIdea, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_story_idea(idea, user=request.user))

    if request.method == "DELETE":
        idea.delete()
        return JsonResponse({"ok": True})

    # PUT — update
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    if "title" in body:
        idea.title = body["title"]
    if "content" in body:
        idea.content = body["content"]
    if "tags" in body:
        idea.tags = body["tags"]
    if "pinned" in body:
        idea.pinned = bool(body["pinned"])
    idea.save()

    if "sharedWithIds" in body:
        shared_ids = body["sharedWithIds"] or []
        idea.shared_with.set(
            User.objects.filter(pk__in=shared_ids, is_active=True, is_superuser=False)
        )

    return JsonResponse(serialize_story_idea(idea, user=request.user))


# ---------------------------------------------------------------------------
# Player-facing briefs
# ---------------------------------------------------------------------------


@login_required
def briefs_page(request):
    """Render the player briefs SPA. Any authenticated user; superusers get redirected to the GM view."""
    if request.user.is_superuser:
        return redirect("gm_workspace:ideas-page")
    return render(request, "gm_workspace/briefs.html")


@login_required
@require_http_methods(["GET"])
def api_briefs_list(request):
    qs = (
        StoryIdea.objects
        .filter(shared_with=request.user)
        .distinct()
        .select_related("created_by")
    )
    data = [serialize_brief(idea, user=request.user, include_content=False) for idea in qs]
    return JsonResponse({"briefs": data})


@login_required
@require_http_methods(["GET"])
def api_briefs_detail(request, pk):
    # Use .filter().first() so non-shared records return 404 without leaking existence
    idea = StoryIdea.objects.filter(pk=pk, shared_with=request.user).first()
    if not idea:
        return JsonResponse({"error": "Not found"}, status=404)
    return JsonResponse(serialize_brief(idea, user=request.user))


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


@login_required
def timeline_page(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Forbidden")
    return render(request, "gm_workspace/timeline.html", {"active_tool": "timeline"})


@login_required
@require_http_methods(["GET", "POST"])
def api_timeline_list(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    if request.method == "GET":
        qs = TimelineEvent.objects.all().select_related("created_by")
        return JsonResponse({
            "events": [serialize_timeline_event(ev, include_description=False) for ev in qs],
        })

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    game_date = body.get("gameDate", "") or ""
    event = TimelineEvent.objects.create(
        title=body.get("title", "Untitled"),
        description=body.get("description", ""),
        event_type=body.get("eventType", "note"),
        game_date=game_date,
        game_date_sort=_derive_sort_from_game_date(game_date),
        tags=body.get("tags", ""),
        created_by=request.user,
    )
    return JsonResponse(serialize_timeline_event(event), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_timeline_detail(request, pk):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    event = get_object_or_404(TimelineEvent, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_timeline_event(event))

    if request.method == "DELETE":
        event.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    if "title" in body:
        event.title = body["title"]
    if "description" in body:
        event.description = body["description"]
    if "eventType" in body:
        event.event_type = body["eventType"]
    if "gameDate" in body:
        event.game_date = body["gameDate"]
        event.game_date_sort = _derive_sort_from_game_date(body["gameDate"])
    if "tags" in body:
        event.tags = body["tags"]
    event.save()

    return JsonResponse(serialize_timeline_event(event))


# ---------------------------------------------------------------------------
# Campaign Log
# ---------------------------------------------------------------------------


@login_required
def campaign_log_page(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Forbidden")
    return render(request, "gm_workspace/campaign_log.html", {"active_tool": "log"})


def _coerce_date(value):
    if not value:
        return None
    if isinstance(value, _dt.date):
        return value
    try:
        return parse_date(value)
    except Exception:
        return None


@login_required
@require_http_methods(["GET", "POST"])
def api_campaign_sessions_list(request):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    if request.method == "GET":
        qs = CampaignSession.objects.all().select_related("created_by")
        return JsonResponse({
            "sessions": [serialize_campaign_session(s, include_summary=False) for s in qs],
        })

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    session_number = body.get("sessionNumber")
    if session_number in ("", None):
        session_number = None
    else:
        try:
            session_number = int(session_number)
        except (TypeError, ValueError):
            session_number = None

    session = CampaignSession.objects.create(
        session_number=session_number,
        title=body.get("title", "Untitled session"),
        summary=body.get("summary", ""),
        played_at=_coerce_date(body.get("playedAt")),
        game_date=body.get("gameDate", ""),
        tags=body.get("tags", ""),
        created_by=request.user,
    )
    return JsonResponse(serialize_campaign_session(session), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_campaign_sessions_detail(request, pk):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    session = get_object_or_404(CampaignSession, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_campaign_session(session))

    if request.method == "DELETE":
        session.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    if "sessionNumber" in body:
        raw = body["sessionNumber"]
        if raw in ("", None):
            session.session_number = None
        else:
            try:
                session.session_number = int(raw)
            except (TypeError, ValueError):
                pass
    if "title" in body:
        session.title = body["title"]
    if "summary" in body:
        session.summary = body["summary"]
    if "playedAt" in body:
        session.played_at = _coerce_date(body["playedAt"])
    if "gameDate" in body:
        session.game_date = body["gameDate"]
    if "tags" in body:
        session.tags = body["tags"]
    session.save()

    return JsonResponse(serialize_campaign_session(session))


@login_required
def star_intel_page(request):
    """GM oversight of the star-intel scanning system: ground truth + every
    agency's real accuracy + public records (with disinformation exposed).
    Superuser only."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Forbidden")

    from starmap.models import StarSystem, PublicScanRecord
    from starmap.serializers import (
        base_scan_target, effective_scan_target, scan_uncertainty, _resource_type_map,
    )

    rt_map = _resource_type_map()
    systems = []
    qs = (StarSystem.objects.filter(discovered=True)
          .prefetch_related("agency_scans__agency", "public_records__agency")
          .order_by("distance", "name"))
    for star in qs:
        false_count = sum(1 for r in star.public_records.all() if r.is_false)
        eff = effective_scan_target(star, false_count)
        scans = [{
            "agency": sc.agency.name if sc.agency else "?",
            "accumulated": sc.current_successes,
            "target": sc.required_successes or eff,
            "uncertainty": scan_uncertainty(sc.current_successes, sc.required_successes or eff),
        } for sc in star.agency_scans.all() if sc.current_successes > 0]
        records = [{
            "agency": r.agency.name if r.agency else "?",
            "is_false": r.is_false,
            "uncertainty": r.uncertainty,
        } for r in star.public_records.all()]
        truth = ", ".join(
            f"{rt.name}: {int((star.resources or {}).get(k, 0) or 0)}"
            for k, rt in rt_map.items()
        )
        systems.append({
            "star": star,
            "truth": truth,
            "base_target": base_scan_target(star),
            "effective_target": eff,
            "false_count": false_count,
            "scans": sorted(scans, key=lambda s: s["uncertainty"]),
            "records": records,
        })
    return render(request, "gm_workspace/star_intel.html", {
        "systems": systems, "active_tool": "star_intel",
    })
