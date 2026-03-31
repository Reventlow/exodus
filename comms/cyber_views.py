"""Views for the cyber terminal feature.

Provides API endpoints for cyber actions: eligibility check,
performing actions (gain access, deploy, defend, detect),
thread effects, session state, and intercepted thread listings.
"""

import json
import random

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from characters.models import Character
from npcs.models import NPC

from .dice import get_cyber_pool, roll_dice
from .models import (
    CyberAction, CyberSession, Thread, ThreadEffect, ThreadMembership,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_defender_agency(thread, actor):
    """Resolve defender's agency ID and name from thread membership."""
    from agencies.models import Agency
    for m in ThreadMembership.objects.filter(thread=thread, hidden=False).exclude(user=actor):
        # Check NPC alias
        if m.alias_type == "npc" and m.alias_id:
            npc = NPC.objects.filter(pk=m.alias_id).first()
            if npc and npc.agency_id:
                ag = Agency.objects.filter(pk=npc.agency_id).first()
                if ag:
                    return ag.id, ag.name
        # Fall back to user's player agency
        player_agency = Agency.objects.filter(is_player_agency=True).first()
        if player_agency:
            return player_agency.id, player_agency.name
    return None, "target"


def _mark_intrusion_detected(thread):
    """Permanently mark a thread as having had an intrusion detected."""
    if not thread.intrusion_detected:
        thread.intrusion_detected = True
        thread.save(update_fields=["intrusion_detected"])


def _post_system_alert(thread, message_text):
    """Post a system alert message to a thread and broadcast via WebSocket."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from .models import Message
    from .serializers import serialize_message

    # Get or create system user
    system_user, _ = User.objects.get_or_create(
        username="__system__", defaults={"is_active": False},
    )

    msg = Message.objects.create(
        thread=thread,
        sender=system_user,
        content=message_text,
        posted_as_type="system",
        posted_as_name="SYSTEM",
    )

    # Broadcast to all non-hidden members
    msg_data = serialize_message(msg)
    channel_layer = get_channel_layer()
    memberships = thread.memberships.filter(hidden=False).select_related("user")
    for m in memberships:
        async_to_sync(channel_layer.group_send)(
            f"user_{m.user_id}",
            {"type": "chat.message", "message": msg_data},
        )


def _get_actor_stats(user, persona_type=None, persona_id=None):
    """Get attributes, skills, specialisations, and merits for the acting entity.

    Returns (attributes, skills, specialisations, computer_skill, name, merits) or None.
    """
    if persona_type == "npc" and persona_id:
        npc = NPC.objects.filter(pk=persona_id).first()
        if npc:
            comp = npc.skills.get("mental", {}).get("Computer", 0)
            npc_merits = [{"name": nm.merit.name, "rating": nm.rating}
                          for nm in npc.npc_merits.select_related("merit").all()]
            npc_ps = [{"name": ps.pulling_string.name}
                      for ps in npc.npc_pulling_strings.select_related("pulling_string").all()]
            return npc.attributes, npc.skills, npc.specialisations, comp, npc.name, npc_merits, npc_ps, npc.agency_id, npc.mental_load
        return None
    char = Character.objects.filter(owner=user).first()
    if char:
        comp = char.skills.get("mental", {}).get("Computer", 0)
        char_merits = [{"name": cm.merit.name, "rating": cm.rating}
                       for cm in char.character_merits.select_related("merit").all()]
        char_ps = [{"name": ps.pulling_string.name}
                   for ps in char.character_pulling_strings.select_related("pulling_string").all()]
        return char.attributes, char.skills, char.specialisations, comp, char.name, char_merits, char_ps, None, char.mental_load
    return None


def _get_defender_stats(thread, attacker):
    """Get the defender's Resolve + Computer for passive detection.

    Returns (resolve, computer, name) or None if defender has no Computer skill.
    """
    # Find the other member(s) of the thread who aren't the attacker
    memberships = ThreadMembership.objects.filter(
        thread=thread, hidden=False,
    ).exclude(user=attacker).select_related("user")

    for m in memberships:
        # Check alias first — NPC alias
        if m.alias_type == "npc" and m.alias_id:
            npc = NPC.objects.filter(pk=m.alias_id).first()
            if npc:
                comp = npc.skills.get("mental", {}).get("Computer", 0)
                resolve = npc.attributes.get("resistance", {}).get("mental", 1)
                return resolve, comp, npc.name
        # Check user's character
        char = Character.objects.filter(owner=m.user).first()
        if char:
            comp = char.skills.get("mental", {}).get("Computer", 0)
            resolve = char.attributes.get("resistance", {}).get("mental", 1)
            return resolve, comp, char.name
    return None


def _passive_detect(thread, attacker, difficulty, defender_bonus=0):
    """Roll passive detection for the defender.

    Returns (detected: bool, roll_result, defender_name) or None if no passive roll.
    """
    defender = _get_defender_stats(thread, attacker)
    if not defender:
        return None
    resolve, computer, name = defender
    if computer < 1:
        return None  # Unskilled get no passive roll
    thread_defense = thread.defense_bonus if hasattr(thread, 'defense_bonus') else 0
    pool = resolve + computer + defender_bonus + thread_defense
    result = roll_dice(pool)
    detected = result.successes >= difficulty
    return detected, result, name


def _detect_helper(session, thread, actor):
    """Run detection against the helper NPC. Returns message string."""
    from .dice import get_concealment_max, get_concealment_defender_bonus
    if not session.helper_npc_id:
        return ""
    helper_npc = NPC.objects.filter(pk=session.helper_npc_id).first()
    if not helper_npc:
        return ""
    c_max = get_concealment_max(helper_npc)
    c_bonus = get_concealment_defender_bonus(session.helper_concealment_damage, c_max)

    # Defender rolls against helper with concealment bonus
    passive = _passive_detect(thread, actor, session.gain_access_successes, c_bonus)
    if not passive:
        return f" Helper {helper_npc.name}: no detection (defender unskilled)."

    detected, det_result, def_name = passive
    if detected and det_result.successes > 0:
        # Mark concealment boxes
        session.helper_concealment_damage = min(
            session.helper_concealment_damage + det_result.successes, c_max
        )
        session.save(update_fields=["helper_concealment_damage"])
        if session.helper_concealment_damage >= c_max:
            session.detected = True
            session.save(update_fields=["detected"])
            _post_system_alert(thread, f"⚠ INTRUSION DETECTED — Helper operative {helper_npc.name} compromised!")
            return f" ⚠ Helper {helper_npc.name}: EXPOSED! Concealment {session.helper_concealment_damage}/{c_max} — intrusion detected!"
        new_bonus = get_concealment_defender_bonus(session.helper_concealment_damage, c_max)
        bonus_text = f" (defender +{new_bonus})" if new_bonus > 0 else ""
        return f" Helper {helper_npc.name}: concealment {session.helper_concealment_damage}/{c_max}{bonus_text}."
    return f" Helper {helper_npc.name}: concealment {session.helper_concealment_damage}/{c_max} — undetected."


def _get_defense_messages(successes, actor_name):
    """Return defense alert messages based on number of successes."""
    messages = []
    if successes >= 1:
        messages.append(f"{actor_name} hardened their encryption")
    if successes >= 2:
        messages.append("Rerouting through secure network protocols")
    if successes >= 3:
        messages.append("Adding monitoring bots")
    if successes >= 4:
        messages.append("Starting honey pots")
    if successes >= 5:
        messages.append("Activating machine learning monitoring")
    return messages


def _log_action(thread, actor, action_type, pool, result, outcome,
                persona_type="", persona_id=None, persona_name="",
                target_user=None, gm_modifier=0, notes=""):
    """Create a CyberAction log entry."""
    return CyberAction.objects.create(
        thread=thread, actor=actor,
        actor_persona_type=persona_type,
        actor_persona_id=persona_id,
        actor_persona_name=persona_name,
        target_user=target_user,
        action_type=action_type,
        dice_pool=pool,
        dice_results=result.rolls if result else [],
        successes=result.successes if result else 0,
        is_exceptional=result.is_exceptional if result else False,
        is_dramatic_failure=result.is_dramatic_failure if result else False,
        gm_modifier=gm_modifier,
        outcome=outcome,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

@login_required
@require_GET
def cyber_eligible(request):
    """Check if current user/persona can use the cyber terminal."""
    persona_type = request.GET.get("personaType", "")
    persona_id = request.GET.get("personaId")
    if persona_id:
        try:
            persona_id = int(persona_id)
        except (ValueError, TypeError):
            persona_id = None

    stats = _get_actor_stats(request.user, persona_type, persona_id)
    if not stats:
        if request.user.is_superuser:
            return JsonResponse({"eligible": True, "reason": "GM access", "modifiers": []})
        return JsonResponse({"eligible": False, "reason": "No character found"})

    _, _, specialisations, computer_skill, name, merits, pulling_strings, agency_id, mental_load = stats
    eligible = computer_skill >= 4 or request.user.is_superuser

    # Build active modifiers list
    from .dice import CYBER_MERITS
    active_mods = []
    for m in merits:
        m_name = (m.get("name") or "").lower()
        if m_name in CYBER_MERITS:
            bonus_type, bonus_val, applicable = CYBER_MERITS[m_name]
            if bonus_type == "flat":
                active_mods.append({"name": m["name"], "bonus": f"+{bonus_val}", "applies": ", ".join(applicable)})
            else:
                active_mods.append({"name": m["name"], "bonus": f"+{m.get('rating', 1)}", "applies": ", ".join(applicable)})
        elif m_name == "distributed consciousness":
            active_mods.append({"name": m["name"], "bonus": "x2 deploys", "applies": "gain_access"})

    for ps in pulling_strings:
        ps_name = (ps.get("name") or "").lower()
        if ps_name == "bot farm":
            active_mods.append({"name": "Bot Farm", "bonus": "+4 gain access", "applies": "defender +2 detect"})
        elif ps_name in ("compromise firmware", "digital payload"):
            active_mods.append({"name": ps["name"], "bonus": "free action", "applies": "sabotage (+4 close diff)"})
        elif ps_name == "government zero-day repository":
            # Fetch remaining pool from agency
            zd_remaining = 0
            if agency_id:
                from agencies.models import Agency as Ag
                ag = Ag.objects.filter(pk=agency_id).first()
                zd_remaining = ag.zero_day_pool if ag else 0
            active_mods.append({"name": "Zero-Day Repository", "bonus": "+6", "applies": "attack (consumes pool)", "remaining": zd_remaining})

    # Check for relevant specialisations
    cyber_specs = ["hacking", "encryption", "network security", "intrusion",
                   "cybersecurity", "cyber warfare", "digital forensics"]
    for spec in (specialisations or []):
        spec_name = spec.get("name", str(spec)) if isinstance(spec, dict) else str(spec)
        if spec_name.lower() in cyber_specs:
            active_mods.append({"name": f"Spec: {spec_name}", "bonus": "+1", "applies": "all actions"})
            break

    resp = {
        "eligible": eligible,
        "computerSkill": computer_skill,
        "name": name,
        "reason": f"Computer {computer_skill}" + (" (need 4+)" if not eligible else ""),
        "modifiers": active_mods,
    }
    # Available helpers: agency dossiers + personal contacts with Computer 4+
    from .dice import get_helper_bonus, get_concealment_max
    helpers = []
    seen_ids = set()
    # Agency dossiers
    if agency_id:
        for npc in NPC.objects.filter(agency_id=agency_id, is_npc_dossier=True):
            comp = npc.skills.get("mental", {}).get("Computer", 0)
            if comp >= 4 and npc.name != name:
                helpers.append({
                    "npcId": npc.id,
                    "name": f"{npc.name} (agency)",
                    "bonus": get_helper_bonus(npc),
                    "concealmentMax": get_concealment_max(npc),
                })
                seen_ids.add(npc.id)
    # Personal contacts assigned to this user
    for npc in NPC.objects.filter(assigned_to=request.user, is_npc_dossier=False):
        if npc.id in seen_ids:
            continue
        comp = npc.skills.get("mental", {}).get("Computer", 0)
        if comp >= 4 and npc.name != name:
            helpers.append({
                "npcId": npc.id,
                "name": f"{npc.name} (contact)",
                "bonus": get_helper_bonus(npc),
                "concealmentMax": get_concealment_max(npc),
            })
            seen_ids.add(npc.id)
    if mental_load > 0:
        active_mods.append({"name": "Mental Load", "bonus": f"-{mental_load}", "applies": "all actions"})
    resp["helpers"] = helpers
    return JsonResponse(resp)


# ---------------------------------------------------------------------------
# Thread cyber status
# ---------------------------------------------------------------------------

@login_required
@require_GET
def thread_cyber_status(request, thread_id):
    """Get cyber status: effects, action log, and active session state."""
    thread = get_object_or_404(Thread, pk=thread_id)

    effects = ThreadEffect.objects.filter(thread=thread, is_active=True)
    effects_data = [
        {
            "id": e.pk, "type": e.effect_type, "level": e.level,
            "sourceAgencyId": e.source_agency_id,
            "targetAgencyId": e.target_agency_id,
            "createdAt": e.created_at.isoformat(),
        }
        for e in effects
    ]

    # Action log: GM sees all, players see only their own
    if request.user.is_superuser:
        actions = CyberAction.objects.filter(thread=thread)[:50]
    else:
        actions = CyberAction.objects.filter(thread=thread, actor=request.user)[:50]

    actions_data = [
        {
            "id": a.pk,
            "actorName": a.actor_persona_name or a.actor.username,
            "actionType": a.action_type,
            "dicePool": a.dice_pool,
            "diceResults": a.dice_results,
            "successes": a.successes,
            "isExceptional": a.is_exceptional,
            "isDramaticFailure": a.is_dramatic_failure,
            "outcome": a.outcome,
            "createdAt": a.created_at.isoformat(),
        }
        for a in actions
    ]

    # Active session for current user
    session = CyberSession.objects.filter(
        thread=thread, attacker=request.user, is_active=True,
    ).first()
    session_data = None
    if session:
        from .dice import get_concealment_max, get_concealment_defender_bonus
        helper_data = None
        if session.helper_npc_id:
            helper_npc = NPC.objects.filter(pk=session.helper_npc_id).first()
            if helper_npc:
                c_max = get_concealment_max(helper_npc)
                c_bonus = get_concealment_defender_bonus(session.helper_concealment_damage, c_max)
                helper_data = {
                    "npcId": session.helper_npc_id,
                    "name": helper_npc.name,
                    "concealmentDamage": session.helper_concealment_damage,
                    "concealmentMax": c_max,
                    "defenderBonus": c_bonus,
                }
        session_data = {
            "id": session.pk,
            "gainAccessSuccesses": session.gain_access_successes,
            "deploysRemaining": session.deploys_remaining,
            "hasBackdoor": session.has_backdoor,
            "detected": session.detected,
            "isActive": session.is_active,
            "difficultyPenalty": session.difficulty_penalty,
            "helper": helper_data,
        }

    # Resolve defender's agency and bases for target pickers
    defender_agency = None
    defender_bases = []
    from agencies.models import Agency, Base
    for m in ThreadMembership.objects.filter(thread=thread, hidden=False).exclude(user=request.user):
        agency_id = None
        # Check NPC alias first
        if m.alias_type == "npc" and m.alias_id:
            npc = NPC.objects.filter(pk=m.alias_id).first()
            if npc and npc.agency_id:
                agency_id = npc.agency_id
        # Fall back to user's character agency
        if not agency_id:
            char = Character.objects.filter(owner=m.user).first()
            if char:
                # Character doesn't have agency_id directly — find via player agency
                player_agency = Agency.objects.filter(is_player_agency=True).first()
                if player_agency:
                    agency_id = player_agency.id
        if agency_id:
            ag = Agency.objects.filter(pk=agency_id).first()
            if ag:
                defender_agency = {"id": ag.id, "name": ag.name}
                defender_bases = [
                    {"id": b.id, "name": b.name}
                    for b in Base.objects.filter(agency=ag, is_hidden=False)
                ]
            break

    # Declassified projects from defender's agency
    defender_projects = []
    if defender_agency:
        from agencies.models import Agency
        ag = Agency.objects.filter(pk=defender_agency["id"]).first()
        if ag and ag.projects:
            defender_projects = [
                {"index": i, "name": p.get("name", f"Project {i+1}")}
                for i, p in enumerate(ag.projects)
                if isinstance(p, dict) and not p.get("classified", True)
            ]

    return JsonResponse({
        "effects": effects_data,
        "actions": actions_data,
        "session": session_data,
        "isConnectionClosed": thread.is_connection_closed,
        "defenseActive": thread.defense_active,
        "defenseBonus": thread.defense_bonus,
        "intrusionDetected": thread.intrusion_detected,
        "defenderAgency": defender_agency,
        "defenderBases": defender_bases,
        "defenderProjects": defender_projects,
    })


# ---------------------------------------------------------------------------
# Main roll endpoint
# ---------------------------------------------------------------------------

@login_required
@require_POST
def cyber_roll(request, thread_id):
    """Perform a cyber action on a thread."""
    thread = get_object_or_404(Thread, pk=thread_id)

    if thread.is_connection_closed:
        return JsonResponse({"error": "Connection closed — no further actions possible."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    action_type = body.get("actionType", "")
    if action_type not in ("gain_access", "deploy", "defend", "detect"):
        return JsonResponse({"error": "Invalid action type"}, status=400)

    deploy_action = body.get("deployAction", "")
    persona_type = body.get("personaType", "")
    persona_id = body.get("personaId")
    persona_name = body.get("personaName", "")
    gm_modifier = int(body.get("gmModifier", 0))
    target_user_id = body.get("targetUserId")
    target_agency_id = body.get("targetAgencyId")
    target_base_id = body.get("targetBaseId")
    infra_target = body.get("infraTarget", "")
    helper_npc_id = body.get("helperNpcId")
    target_project_index = body.get("targetProjectIndex")

    target_user = User.objects.filter(pk=target_user_id).first() if target_user_id else None

    # Get actor stats and pool
    ps_flags = {}
    if request.user.is_superuser and persona_type == "gm":
        pool = 10 + gm_modifier
        pool_desc = f"GM base 10 + modifier {gm_modifier:+d} = {pool} dice"
    else:
        stats = _get_actor_stats(request.user, persona_type, persona_id)
        if not stats:
            return JsonResponse({"error": "No character found"}, status=400)
        attributes, skills, specialisations, computer_skill, name, actor_merits, actor_ps, actor_agency_id, actor_mental_load = stats
        if computer_skill < 4 and not request.user.is_superuser:
            return JsonResponse({"error": "Computer skill too low (need 4+)"}, status=403)
        if not persona_name:
            persona_name = name
        use_zero_day = body.get("useZeroDay", False)
        pool, pool_desc, ps_flags = get_cyber_pool(
            action_type, attributes, skills, specialisations, gm_modifier,
            deploy_action=deploy_action, merits=actor_merits,
            pulling_strings=actor_ps, use_zero_day=use_zero_day,
            mental_load=actor_mental_load,
        )
        # Consume zero-day from agency pool
        if ps_flags.get("zero_day_used") and actor_agency_id:
            from agencies.models import Agency
            agency = Agency.objects.filter(pk=actor_agency_id).first()
            if agency and agency.zero_day_pool > 0:
                agency.zero_day_pool -= 1
                agency.save(update_fields=["zero_day_pool"])
            else:
                return JsonResponse({"error": "No zero-day vulnerabilities remaining in agency pool."}, status=400)

    # Intercepted thread penalty: -4 to all rolls
    is_intercepted = ThreadMembership.objects.filter(
        thread=thread, user=request.user, hidden=True,
    ).exists()
    if is_intercepted:
        pool -= 4
        pool_desc = pool_desc.rsplit("=", 1)[0] + f"+ Intercepted -4 = {pool} dice"

    # Apply helper bonus
    helper_bonus_desc = ""
    if helper_npc_id and action_type in ("gain_access", "deploy"):
        from .dice import get_helper_bonus
        helper_npc = NPC.objects.filter(pk=helper_npc_id).first()
        if helper_npc:
            hb = get_helper_bonus(helper_npc)
            pool += hb
            helper_bonus_desc = f" + {helper_npc.name} +{hb}"
            pool_desc = pool_desc.rsplit("=", 1)[0] + helper_bonus_desc + f" = {pool} dice"

    # Dispatch to action handler
    if action_type == "gain_access":
        return _handle_gain_access(
            thread, request.user, target_user, pool, pool_desc,
            persona_type, persona_id, persona_name, gm_modifier, ps_flags,
            helper_npc_id=helper_npc_id,
        )
    elif action_type == "deploy":
        return _handle_deploy(
            thread, request.user, deploy_action, pool, pool_desc,
            persona_type, persona_id, persona_name, gm_modifier,
            target_agency_id, target_base_id, infra_target, ps_flags,
            target_project_index=target_project_index,
        )
    elif action_type == "defend":
        return _handle_defend(
            thread, request.user, pool, pool_desc,
            persona_type, persona_id, persona_name, gm_modifier,
        )
    elif action_type == "detect":
        return _handle_detect(
            thread, request.user, pool, pool_desc,
            persona_type, persona_id, persona_name, gm_modifier,
        )

    return JsonResponse({"error": "Unknown action"}, status=400)


# ---------------------------------------------------------------------------
# Gain Access
# ---------------------------------------------------------------------------

def _handle_gain_access(thread, actor, target_user, pool, pool_desc,
                        persona_type, persona_id, persona_name, gm_modifier, ps_flags=None,
                        helper_npc_id=None):
    """Handle Gain Access with session creation and passive detection."""
    ps_flags = ps_flags or {}

    # Check difficulty escalation from prior closed sessions
    prior_closes = CyberSession.objects.filter(
        thread=thread, attacker=actor, is_active=False,
    ).count()

    # Apply difficulty penalty (reduce pool)
    effective_pool = pool - prior_closes
    if prior_closes:
        pool_desc += f" - {prior_closes} prior close(s) = {effective_pool} dice"

    result = roll_dice(effective_pool)

    if result.is_dramatic_failure:
        outcome = "Dramatic failure — intrusion attempt detected and traced."
        _log_action(thread, actor, "gain_access", effective_pool, result, outcome,
                    persona_type, persona_id, persona_name, target_user, gm_modifier)
        return _roll_response("gain_access", pool_desc, result, outcome)

    if result.successes == 0:
        outcome = "Failure — no access gained."
        _log_action(thread, actor, "gain_access", effective_pool, result, outcome,
                    persona_type, persona_id, persona_name, target_user, gm_modifier)
        return _roll_response("gain_access", pool_desc, result, outcome)

    s = result.successes
    exceptional = result.is_exceptional  # 5+

    # Create session
    deploys = s // 2

    # Distributed Consciousness doubles deploy actions
    actor_stats = _get_actor_stats(actor, persona_type, persona_id)
    if actor_stats:
        _, _, _, _, _, actor_merits, _, _, _ = actor_stats
        has_distributed = any(m.get("name", "").lower() == "distributed consciousness" for m in actor_merits)
        if has_distributed:
            deploys *= 2

    session = CyberSession.objects.create(
        thread=thread,
        attacker=actor,
        attacker_persona_name=persona_name,
        gain_access_successes=s,
        is_exceptional=exceptional,
        deploys_remaining=deploys,
        difficulty_penalty=prior_closes,
        detect_stale=True,
        helper_npc_id=helper_npc_id,
        helper_concealment_damage=0,
    )

    # Grant hidden thread access
    granted = 0
    if target_user:
        target_memberships = ThreadMembership.objects.filter(
            user=target_user, hidden=False,
        ).select_related("thread")
        su_ids = set(User.objects.filter(is_superuser=True).values_list("pk", flat=True))
        for tm in target_memberships:
            members = list(ThreadMembership.objects.filter(
                thread=tm.thread, hidden=False,
            ).values_list("user_id", flat=True))
            if actor.pk in members:
                continue
            non_su = [uid for uid in members if uid not in su_ids]
            if len(non_su) <= 1:
                continue
            _, created = ThreadMembership.objects.get_or_create(
                thread=tm.thread, user=actor,
                defaults={"hidden": True},
            )
            if created:
                granted += 1

    # Passive detection (only for 1-4 successes, skip if THIS session already detected)
    detection_msg = ""
    if session.detected:
        detection_msg = " Intrusion already detected."
    elif not exceptional:
        defender_bonus = ps_flags.get("defender_bonus", 0)
        passive = _passive_detect(thread, actor, s, defender_bonus)
        if passive:
            detected, det_result, def_name = passive
            if detected:
                session.detected = True
                _mark_intrusion_detected(thread)
                session.save(update_fields=["detected"])
                detection_msg = f" WARNING: Passive detection by {def_name} succeeded — intrusion detected!"
                _post_system_alert(thread, "⚠ INTRUSION DETECTED — Unauthorized access to this channel has been identified.")
            else:
                detection_msg = f" Passive detection by {def_name} failed — undetected."
        else:
            detection_msg = " No passive detection possible (defender unskilled)."
    else:
        detection_msg = " Exceptional success — no passive detection triggered."

    # Helper concealment detection
    helper_msg = ""
    if helper_npc_id and not exceptional:
        helper_msg = _detect_helper(session, thread, actor)

    parts = [f"{s} successes — access gained. {deploys} deploy action(s) available."]
    if granted:
        parts.append(f"Hidden access to {granted} thread(s).")
    parts.append(detection_msg.strip())
    if helper_msg:
        parts.append(helper_msg)

    outcome = " ".join(parts)
    _log_action(thread, actor, "gain_access", effective_pool, result, outcome,
                persona_type, persona_id, persona_name, target_user, gm_modifier)
    return _roll_response("gain_access", pool_desc, result, outcome, session_data={
        "id": session.pk,
        "gainAccessSuccesses": s,
        "deploysRemaining": deploys,
        "hasBackdoor": False,
        "detected": session.detected,
        "isActive": True,
        "difficultyPenalty": prior_closes,
    })


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

def _handle_deploy(thread, actor, deploy_action, pool, pool_desc,
                   persona_type, persona_id, persona_name, gm_modifier,
                   target_agency_id, target_base_id, infra_target="", ps_flags=None,
                   target_project_index=None):
    """Handle deploy with session tracking and passive detection."""
    from agencies.models import Agency
    ps_flags = ps_flags or {}
    free_deploy = ps_flags.get("free_deploy", False)

    session = CyberSession.objects.filter(
        thread=thread, attacker=actor, is_active=True,
    ).first()

    if not session and not actor.is_superuser:
        return JsonResponse({"error": "No active session — Gain Access required first."}, status=400)

    # Check deploys remaining (unless backdoor or GM)
    if session and not session.has_backdoor and session.deploys_remaining <= 0 and not actor.is_superuser:
        session.is_active = False
        session.save(update_fields=["is_active"])
        return JsonResponse({"error": "No deploy actions remaining. Connection auto-closed."}, status=400)

    # Close Connection — no roll, no passive detection, just clean exit
    if deploy_action == "close_connection":
        removed_hidden = ThreadMembership.objects.filter(
            thread=thread, user=actor, hidden=True,
        ).delete()[0]
        removed_backdoors = ThreadEffect.objects.filter(
            thread=thread, source_user=actor, effect_type="backdoor", is_active=True,
        ).update(is_active=False)
        if session:
            session.is_active = False
            session.save(update_fields=["is_active"])
        parts = ["Connection closed cleanly"]
        if removed_hidden:
            parts.append(f"{removed_hidden} hidden access(es) removed")
        if removed_backdoors:
            parts.append(f"{removed_backdoors} backdoor(s) removed")
        outcome = "; ".join(parts) + ". All traces erased."
        _log_action(thread, actor, "deploy:close_connection", 0, None, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("deploy", "No roll required", None, outcome, hide_dice=True,
                              session_data={"id": 0, "gainAccessSuccesses": 0, "deploysRemaining": 0,
                                            "hasBackdoor": False, "detected": False, "isActive": False, "difficultyPenalty": 0})

    result = roll_dice(pool)

    if result.is_dramatic_failure:
        outcome = "Dramatic failure — deploy attempt detected and traced."
        if session:
            session.is_active = False
            session.save(update_fields=["is_active"])
        _log_action(thread, actor, f"deploy:{deploy_action}", pool, result, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("deploy", pool_desc, result, outcome)

    if result.successes == 0:
        outcome = "Failure — deploy had no effect."
        if session and not session.has_backdoor:
            session.deploys_remaining = max(0, session.deploys_remaining - 1)
            session.detect_stale = False
            session.save(update_fields=["deploys_remaining", "detect_stale"])
            if session.deploys_remaining <= 0:
                session.is_active = False
                session.save(update_fields=["is_active"])
                outcome += " No deploy actions remaining — connection auto-closed."
        _log_action(thread, actor, f"deploy:{deploy_action}", pool, result, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("deploy", pool_desc, result, outcome)

    # Resolve the deploy sub-action
    outcome = _resolve_deploy(deploy_action, result, thread, actor,
                              target_agency_id, target_base_id, infra_target,
                              target_project_index=target_project_index)

    # Track backdoor for unlimited deploys
    if deploy_action == "backdoor" and result.successes > 0:
        if session:
            session.has_backdoor = True
            session.save(update_fields=["has_backdoor"])

    # Decrement deploys (unless backdoor or free deploy from pulling string)
    if session and not session.has_backdoor and not free_deploy:
        session.deploys_remaining = max(0, session.deploys_remaining - 1)
        session.detect_stale = False
        session.save(update_fields=["deploys_remaining", "detect_stale"])

    # Passive detection on each deploy (skip if THIS session already detected)
    detection_msg = ""
    if session and not session.detected:
        passive = _passive_detect(thread, actor, session.gain_access_successes, ps_flags.get("defender_bonus", 0))
        if passive:
            detected, det_result, def_name = passive
            if detected:
                session.detected = True
                _mark_intrusion_detected(thread)
                session.save(update_fields=["detected"])
                detection_msg = f" ⚠ Passive detection by {def_name} — INTRUSION DETECTED!"
                _post_system_alert(thread, "⚠ INTRUSION DETECTED — Unauthorized activity detected on this channel.")
            else:
                detection_msg = f" Passive detection by {def_name} — still undetected."
        else:
            detection_msg = " No passive detection (defender unskilled)."
    elif session and session.detected:
        detection_msg = " Intrusion already detected."

    if session:
        session.detect_stale = False
        session.save(update_fields=["detect_stale"])
        # Helper concealment detection on every deploy
        if session.helper_npc_id:
            helper_msg = _detect_helper(session, thread, actor)
            if helper_msg:
                detection_msg += helper_msg

    # Auto-close if deploys exhausted
    if session and not session.has_backdoor and session.deploys_remaining <= 0:
        session.is_active = False
        session.save(update_fields=["is_active"])
        detection_msg += " No deploy actions remaining — connection auto-closed."

    outcome += detection_msg

    _log_action(thread, actor, f"deploy:{deploy_action}", pool, result, outcome,
                persona_type, persona_id, persona_name, None, gm_modifier,
                notes=json.dumps({"deployAction": deploy_action,
                                  "targetAgencyId": target_agency_id,
                                  "targetBaseId": target_base_id}))

    # Return updated session
    session_data = None
    if session:
        session.refresh_from_db()
        session_data = {
            "id": session.pk,
            "gainAccessSuccesses": session.gain_access_successes,
            "deploysRemaining": session.deploys_remaining,
            "hasBackdoor": session.has_backdoor,
            "detected": session.detected,
            "isActive": session.is_active,
            "difficultyPenalty": session.difficulty_penalty,
        }

    return _roll_response("deploy", pool_desc, result, outcome, session_data=session_data)


# ---------------------------------------------------------------------------
# Defend
# ---------------------------------------------------------------------------

def _handle_defend(thread, actor, pool, pool_desc,
                   persona_type, persona_id, persona_name, gm_modifier):
    """Handle defend: activate defense systems, add detection bonus."""

    # Can only defend once per thread
    if thread.defense_active:
        return JsonResponse({"error": "Defense systems already running on this channel."}, status=400)

    result = roll_dice(pool)

    if result.successes == 0:
        outcome = "Failure — defense systems failed to activate."
        _log_action(thread, actor, "defend", pool, result, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("defend", pool_desc, result, outcome)

    s = result.successes

    # Set defense bonus and mark as active
    thread.defense_bonus = s
    thread.defense_active = True
    thread.save(update_fields=["defense_bonus", "defense_active"])

    # Build outcome with escalating messages (only shown to executor)
    actor_name = persona_name or actor.username
    defense_messages = _get_defense_messages(s, actor_name)

    # At 6+ don't reveal exact score
    if s >= 6:
        outcome = "Defense systems fully activated. All countermeasures deployed."
    else:
        outcome = f"{s} successes — defense systems activated (+{s} to all detection rolls)."

    outcome += "\n" + "\n".join(f"🛡 {m}" for m in defense_messages)

    _log_action(thread, actor, "defend", pool, result, outcome,
                persona_type, persona_id, persona_name, None, gm_modifier)
    return _roll_response("defend", pool_desc, result, outcome)


# ---------------------------------------------------------------------------
# Detect (active)
# ---------------------------------------------------------------------------

def _handle_detect(thread, actor, pool, pool_desc,
                   persona_type, persona_id, persona_name, gm_modifier):
    """Handle active detect: Resolve + Computer + 2 vs attacker successes.

    Only shows 'INTRUSION DETECTED' or 'NO INTRUSION DETECTED'.
    Same result returned if no new attacker action since last detect.
    """
    # Check if the actor is an attacker trying to detect defense systems
    own_session = CyberSession.objects.filter(
        thread=thread, is_active=True,
    )
    if persona_name:
        own_session = own_session.filter(attacker_persona_name=persona_name).first()
    else:
        own_session = own_session.filter(attacker=actor).first()

    if own_session and thread.defense_active and thread.defense_bonus > 0:
        # Attacker is scanning for defense — roll against defense successes
        detect_pool = pool + 2
        result = roll_dice(detect_pool)
        defense_s = thread.defense_bonus
        if result.successes >= defense_s:
            # Reveal defense messages up to 5
            msgs = _get_defense_messages(min(defense_s, 5), "Target")
            outcome = "DEFENSE SYSTEMS DETECTED:\n" + "\n".join(f"🛡 {m}" for m in msgs)
        else:
            outcome = "NO DEFENSE SYSTEMS DETECTED"
        _log_action(thread, actor, "detect", detect_pool, result, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("detect", pool_desc, None, outcome, hide_dice=True)

    # Find any active attacker session on this thread (not by this persona)
    # For NPC-vs-NPC threads, both sides may be the same user (GM),
    # so exclude by persona name rather than user when a persona is set.
    sessions_qs = CyberSession.objects.filter(thread=thread, is_active=True)
    if persona_name:
        attacker_session = sessions_qs.exclude(attacker_persona_name=persona_name).first()
    else:
        attacker_session = sessions_qs.exclude(attacker=actor).first()

    if not attacker_session:
        # No active session — check for dormant threats (backdoors, hidden members)
        # Exclude threats placed by the detecting actor themselves
        backdoors = ThreadEffect.objects.filter(thread=thread, effect_type="backdoor", is_active=True).exclude(source_user=actor)
        hidden = ThreadMembership.objects.filter(thread=thread, hidden=True).exclude(user=actor)
        has_threats = backdoors.exists() or hidden.exists()
        if not has_threats:
            outcome = "NO INTRUSION DETECTED"
        else:
            # Roll to detect dormant threats — difficulty 3 (moderate)
            detect_pool = pool + 2
            result = roll_dice(detect_pool)
            outcome = "INTRUSION DETECTED" if result.successes >= 3 else "NO INTRUSION DETECTED"
        _log_action(thread, actor, "detect", 0, None, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("detect", pool_desc, None, outcome, hide_dice=True)

    # If detect is stale (no new attacker action), return cached result
    if attacker_session.detect_stale and attacker_session.last_detect_result:
        outcome = attacker_session.last_detect_result
        _log_action(thread, actor, "detect", 0, None, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("detect", pool_desc, None, outcome, hide_dice=True)

    # Active detect roll: pool + 2 bonus + thread defense bonus vs attacker's gain_access successes
    thread_defense = thread.defense_bonus if hasattr(thread, 'defense_bonus') else 0
    detect_pool = pool + 2 + thread_defense
    defense_text = f" + defense {thread_defense}" if thread_defense else ""
    detect_desc = pool_desc.rsplit("=", 1)[0] + f"+ 2 bonus{defense_text} = {detect_pool} dice"
    result = roll_dice(detect_pool)

    difficulty = attacker_session.gain_access_successes
    detected = result.successes >= difficulty

    if detected:
        outcome = "INTRUSION DETECTED"
        attacker_session.detected = True
        _mark_intrusion_detected(thread)
    else:
        outcome = "NO INTRUSION DETECTED"

    attacker_session.last_detect_result = outcome
    attacker_session.detect_stale = True
    attacker_session.save(update_fields=["detected", "last_detect_result", "detect_stale"])

    # Log but hide the dice from the player
    _log_action(thread, actor, "detect", detect_pool, result, outcome,
                persona_type, persona_id, persona_name, None, gm_modifier)
    return _roll_response("detect", detect_desc, None, outcome, hide_dice=True)


# ---------------------------------------------------------------------------
# Close Connection
# ---------------------------------------------------------------------------

@login_required
@require_POST
def close_connection(request, thread_id):
    """Close a connection — no further messages or terminal actions."""
    thread = get_object_or_404(Thread, pk=thread_id)

    thread.is_connection_closed = True
    thread.save(update_fields=["is_connection_closed"])

    # Close all sessions (active and inactive) and remove hidden memberships
    all_sessions = CyberSession.objects.filter(thread=thread)
    attacker_ids = set(all_sessions.values_list("attacker_id", flat=True))
    for attacker_id in attacker_ids:
        ThreadMembership.objects.filter(user_id=attacker_id, hidden=True).delete()
    all_sessions.filter(is_active=True).update(is_active=False)

    # Notify all parties
    _post_system_alert(thread, "🔒 CONNECTION TERMINATED — This channel has been permanently locked.")

    return JsonResponse({"status": "closed"})


# ---------------------------------------------------------------------------
# Deploy sub-action resolution
# ---------------------------------------------------------------------------

def _resolve_deploy(deploy_action, result, thread, actor,
                    target_agency_id=None, target_base_id=None, infra_target="",
                    target_project_index=None):
    """Handle deploy sub-action outcomes."""
    from agencies.models import Agency
    s = result.successes

    if deploy_action == "backdoor":
        ThreadEffect.objects.create(
            thread=thread, effect_type="backdoor",
            level=min(s, 3), source_user=actor,
            target_agency_id=target_agency_id,
        )
        return f"{s} successes — permanent backdoor deployed." + (" Exceptional — extremely difficult to detect." if result.is_exceptional else "")

    elif deploy_action == "ransomware":
        defender_agency_id, defender_agency_name = _resolve_defender_agency(thread, actor)
        base_name = ""
        if target_base_id:
            from agencies.models import Base
            base = Base.objects.filter(pk=target_base_id).first()
            base_name = f" — base: {base.name}" if base else ""
        # Create agency condition
        if defender_agency_id:
            from agencies.models import AgencyCondition
            desc = f"Ransomware attack{base_name} — systems locked"
            AgencyCondition.objects.create(
                agency_id=defender_agency_id,
                condition_type="ransomware",
                description=desc,
                difficulty=s,
                target_base_id=target_base_id,
            )
        return f"{s} successes — ransomware deployed on {defender_agency_name}{base_name}. Condition created (difficulty {s} to clear)."

    elif deploy_action == "bad_deals":
        defender_agency_id, defender_agency_name = _resolve_defender_agency(thread, actor)
        if defender_agency_id:
            from agencies.models import AgencyCondition
            AgencyCondition.objects.create(
                agency_id=defender_agency_id,
                condition_type="bad_deals",
                description=f"Fraudulent trade orders placed on the UTC on behalf of {defender_agency_name}",
                difficulty=s,
            )
        return f"{s} successes — fraudulent trade orders placed on the UTC on behalf of {defender_agency_name}. Condition created (difficulty {s} to clear)."

    elif deploy_action == "steal_intel":
        if not target_agency_id:
            return f"{s} successes — but no target agency specified."
        agency = Agency.objects.filter(pk=target_agency_id).first()
        if not agency:
            return f"{s} successes — target agency not found."
        visibility = agency.field_visibility or {}
        classified_fields = [k for k, v in visibility.items() if v is False]
        if not classified_fields:
            return f"{s} successes — no classified intel remaining on {agency.name}."
        revealed = random.choice(classified_fields)
        visibility[revealed] = True
        agency.field_visibility = visibility
        agency.save(update_fields=["field_visibility"])
        field_display = revealed.replace(".", " > ").replace("_", " ").title()
        return f"{s} successes — classified data extracted from {agency.name}: [{field_display}] has been unlocked."

    elif deploy_action == "discover_base":
        # Find a random hidden base belonging to the defender's agency
        defender_agency_id = None
        for m in ThreadMembership.objects.filter(thread=thread, hidden=False).exclude(user=actor):
            if m.alias_type == "npc" and m.alias_id:
                npc = NPC.objects.filter(pk=m.alias_id).first()
                if npc and npc.agency_id:
                    defender_agency_id = npc.agency_id
                    break
        if defender_agency_id:
            from agencies.models import Base
            hidden_bases = list(Base.objects.filter(agency_id=defender_agency_id, is_hidden=True))
            if hidden_bases:
                base = random.choice(hidden_bases)
                base.is_hidden = False
                base.save(update_fields=["is_hidden"])
                return f"{s} successes — hidden base discovered: {base.name}. Base is now visible."
            return f"{s} successes — no hidden bases found for this agency."
        return f"{s} successes — could not determine defender's agency."

    elif deploy_action == "base_access":
        if not target_base_id:
            return f"{s} successes — but no target base specified."
        from agencies.models import Base, AgencyCondition
        base = Base.objects.filter(pk=target_base_id).first()
        if not base:
            return f"{s} successes — target base not found."
        # Unhide all hidden sections on this base
        revealed = []
        if base.hidden_sections:
            revealed = list(base.hidden_sections)
            base.hidden_sections = []
            base.save(update_fields=["hidden_sections"])
        # Create condition on defender agency
        defender_agency_id, defender_agency_name = _resolve_defender_agency(thread, actor)
        if defender_agency_id:
            AgencyCondition.objects.create(
                agency_id=defender_agency_id,
                condition_type="base_access",
                description=f"Base systems compromised: {base.name}",
                difficulty=s,
                target_base_id=target_base_id,
            )
        if revealed:
            return f"{s} successes — gained access to {base.name}. Revealed: {', '.join(revealed)}. Condition created (difficulty {s})."
        return f"{s} successes — gained access to {base.name}. Condition created (difficulty {s})."

    elif deploy_action == "plant_intel":
        return f"{s} successes — false intelligence planted. GM determines what the target sees."


    elif deploy_action == "sabotage":
        defender_agency_id, defender_agency_name = _resolve_defender_agency(thread, actor)
        project_name = "unknown project"
        old_score = 0
        new_score = 0
        if defender_agency_id:
            ag = Agency.objects.filter(pk=defender_agency_id).first()
            if ag and target_project_index is not None and ag.projects:
                try:
                    idx = int(target_project_index)
                    if 0 <= idx < len(ag.projects):
                        project_name = ag.projects[idx].get("name", f"Project {idx+1}")
                        old_score = int(ag.projects[idx].get("completionScore", 0))
                        new_score = max(0, old_score - s)
                        ag.projects[idx]["completionScore"] = new_score
                        ag.save(update_fields=["projects"])
                except (ValueError, IndexError):
                    pass
        return f"{s} successes — '{project_name}' in {defender_agency_name} sabotaged. Completion reduced from {old_score} to {new_score} (-{old_score - new_score})."

    elif deploy_action == "shutdown_infra":
        defender_agency_id, defender_agency_name = _resolve_defender_agency(thread, actor)
        infra_names = {
            "power": "Power Grid", "water": "Water Systems", "logistics": "Logistics Network",
            "transport": "Transport Infrastructure", "media": "Media Channels", "comms": "Communications",
        }
        infra_name = infra_names.get(infra_target, infra_target or "unknown system")
        condition_type = f"shutdown_{infra_target}" if infra_target else "custom"
        if defender_agency_id:
            from agencies.models import AgencyCondition
            AgencyCondition.objects.create(
                agency_id=defender_agency_id,
                condition_type=condition_type,
                description=f"{infra_name} disabled",
                difficulty=s,
                infra_type=infra_target,
            )
        return f"{s} successes — {infra_name} shut down in {defender_agency_name}. Condition created (difficulty {s} to clear)."

    # close_connection is handled by early return in _handle_deploy, not here

    return f"{s} successes — deployed."


# ---------------------------------------------------------------------------
# Response helper
# ---------------------------------------------------------------------------

def _roll_response(action_type, pool_desc, result, outcome,
                   session_data=None, hide_dice=False):
    """Build the standard JSON response for a roll."""
    data = {
        "action": {
            "actionType": action_type,
            "poolDescription": pool_desc,
            "outcome": outcome,
        },
    }
    if result and not hide_dice:
        data["action"]["roll"] = result.to_dict()
    elif hide_dice:
        data["action"]["roll"] = {"dicePool": 0, "rolls": [], "successes": 0,
                                   "isExceptional": False, "isDramaticFailure": False}
    if session_data:
        data["session"] = session_data
    return JsonResponse(data)


# ---------------------------------------------------------------------------
# Intercepted threads
# ---------------------------------------------------------------------------

@login_required
@require_GET
def intercepted_threads(request):
    """List threads where the user has hidden (shadow) membership."""
    from .serializers import serialize_thread_summary
    hidden_memberships = ThreadMembership.objects.filter(
        user=request.user, hidden=True,
    ).select_related("thread")
    threads = [m.thread for m in hidden_memberships]
    data = [serialize_thread_summary(t, request.user) for t in threads]
    for d in data:
        d["intercepted"] = True
    return JsonResponse(data, safe=False)


# ---------------------------------------------------------------------------
# GM modify effects
# ---------------------------------------------------------------------------

@login_required
@require_POST
def cyber_modify(request, thread_id):
    """GM manually adds/removes effects on a thread. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)

    thread = get_object_or_404(Thread, pk=thread_id)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    action = body.get("action", "")

    if action == "add_effect":
        effect_type = body.get("effectType", "")
        level = int(body.get("level", 1))
        if effect_type not in ("encrypted", "obfuscated", "backdoor", "compromised", "locked"):
            return JsonResponse({"error": "Invalid effect type"}, status=400)
        effect = ThreadEffect.objects.create(
            thread=thread, effect_type=effect_type, level=level,
            source_user=request.user,
            source_agency_id=body.get("sourceAgencyId"),
            target_agency_id=body.get("targetAgencyId"),
        )
        return JsonResponse({"status": "ok", "effectId": effect.pk})

    elif action == "remove_effect":
        effect_id = body.get("effectId")
        ThreadEffect.objects.filter(pk=effect_id, thread=thread).update(is_active=False)
        return JsonResponse({"status": "ok"})

    elif action == "clear_all":
        ThreadEffect.objects.filter(thread=thread, is_active=True).update(is_active=False)
        ThreadMembership.objects.filter(thread=thread, hidden=True).delete()
        CyberSession.objects.filter(thread=thread, is_active=True).update(is_active=False)
        return JsonResponse({"status": "ok"})

    elif action == "reopen":
        thread.is_connection_closed = False
        thread.save(update_fields=["is_connection_closed"])
        return JsonResponse({"status": "ok"})

    return JsonResponse({"error": "Unknown action"}, status=400)


# ---------------------------------------------------------------------------
# Delete thread (moved here for import convenience)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def delete_thread(request, thread_id):
    """Delete a thread. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    thread = get_object_or_404(Thread, pk=thread_id)
    thread.delete()
    return JsonResponse({"status": "deleted"})
