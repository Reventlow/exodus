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

def _get_actor_stats(user, persona_type=None, persona_id=None):
    """Get attributes, skills, and specialisations for the acting entity."""
    if persona_type == "npc" and persona_id:
        npc = NPC.objects.filter(pk=persona_id).first()
        if npc:
            comp = npc.skills.get("mental", {}).get("Computer", 0)
            return npc.attributes, npc.skills, npc.specialisations, comp, npc.name
        return None
    char = Character.objects.filter(owner=user).first()
    if char:
        comp = char.skills.get("mental", {}).get("Computer", 0)
        return char.attributes, char.skills, char.specialisations, comp, char.name
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


def _passive_detect(thread, attacker, difficulty):
    """Roll passive detection for the defender.

    Returns (detected: bool, roll_result, defender_name) or None if no passive roll.
    """
    defender = _get_defender_stats(thread, attacker)
    if not defender:
        return None
    resolve, computer, name = defender
    if computer < 1:
        return None  # Unskilled get no passive roll
    pool = resolve + computer
    result = roll_dice(pool)
    detected = result.successes >= difficulty
    return detected, result, name


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
    if request.user.is_superuser:
        return JsonResponse({"eligible": True, "reason": "GM access"})

    persona_type = request.GET.get("personaType", "")
    persona_id = request.GET.get("personaId")
    if persona_id:
        try:
            persona_id = int(persona_id)
        except (ValueError, TypeError):
            persona_id = None

    stats = _get_actor_stats(request.user, persona_type, persona_id)
    if not stats:
        return JsonResponse({"eligible": False, "reason": "No character found"})

    _, _, _, computer_skill, name = stats
    eligible = computer_skill >= 4
    return JsonResponse({
        "eligible": eligible,
        "computerSkill": computer_skill,
        "name": name,
        "reason": f"Computer {computer_skill}" + (" (need 4+)" if not eligible else ""),
    })


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
        session_data = {
            "id": session.pk,
            "gainAccessSuccesses": session.gain_access_successes,
            "deploysRemaining": session.deploys_remaining,
            "hasBackdoor": session.has_backdoor,
            "detected": session.detected,
            "isActive": session.is_active,
            "difficultyPenalty": session.difficulty_penalty,
        }

    return JsonResponse({
        "effects": effects_data,
        "actions": actions_data,
        "session": session_data,
        "isConnectionClosed": thread.is_connection_closed,
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

    target_user = User.objects.filter(pk=target_user_id).first() if target_user_id else None

    # Get actor stats and pool
    if request.user.is_superuser and persona_type == "gm":
        pool = 10 + gm_modifier
        pool_desc = f"GM base 10 + modifier {gm_modifier:+d} = {pool} dice"
    else:
        stats = _get_actor_stats(request.user, persona_type, persona_id)
        if not stats:
            return JsonResponse({"error": "No character found"}, status=400)
        attributes, skills, specialisations, computer_skill, name = stats
        if computer_skill < 4 and not request.user.is_superuser:
            return JsonResponse({"error": "Computer skill too low (need 4+)"}, status=403)
        if not persona_name:
            persona_name = name
        pool, pool_desc = get_cyber_pool(
            action_type, attributes, skills, specialisations, gm_modifier,
            deploy_action=deploy_action,
        )

    # Dispatch to action handler
    if action_type == "gain_access":
        return _handle_gain_access(
            thread, request.user, target_user, pool, pool_desc,
            persona_type, persona_id, persona_name, gm_modifier,
        )
    elif action_type == "deploy":
        return _handle_deploy(
            thread, request.user, deploy_action, pool, pool_desc,
            persona_type, persona_id, persona_name, gm_modifier,
            target_agency_id, target_base_id,
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
                        persona_type, persona_id, persona_name, gm_modifier):
    """Handle Gain Access with session creation and passive detection."""

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
    deploys = 0 if not exceptional else s // 2
    if not exceptional:
        deploys = s // 2

    session = CyberSession.objects.create(
        thread=thread,
        attacker=actor,
        attacker_persona_name=persona_name,
        gain_access_successes=s,
        is_exceptional=exceptional,
        deploys_remaining=deploys,
        difficulty_penalty=prior_closes,
        detect_stale=True,
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

    # Passive detection (only for 1-4 successes)
    detection_msg = ""
    if not exceptional:
        passive = _passive_detect(thread, actor, s)
        if passive:
            detected, det_result, def_name = passive
            if detected:
                session.detected = True
                session.save(update_fields=["detected"])
                detection_msg = f" WARNING: Passive detection by {def_name} succeeded — intrusion detected!"
            else:
                detection_msg = f" Passive detection by {def_name} failed — undetected."
        else:
            detection_msg = " No passive detection possible (defender unskilled)."
    else:
        detection_msg = " Exceptional success — no passive detection triggered."

    parts = [f"{s} successes — access gained. {deploys} deploy action(s) available."]
    if granted:
        parts.append(f"Hidden access to {granted} thread(s).")
    parts.append(detection_msg.strip())

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
                   target_agency_id, target_base_id):
    """Handle deploy with session tracking and passive detection."""
    from agencies.models import Agency

    session = CyberSession.objects.filter(
        thread=thread, attacker=actor, is_active=True,
    ).first()

    if not session and not actor.is_superuser:
        return JsonResponse({"error": "No active session — Gain Access required first."}, status=400)

    # Check deploys remaining (unless backdoor or GM)
    if session and not session.has_backdoor and session.deploys_remaining <= 0 and not actor.is_superuser:
        # Auto-close session
        session.is_active = False
        session.save(update_fields=["is_active"])
        return JsonResponse({"error": "No deploy actions remaining. Connection auto-closed."}, status=400)

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
                              target_agency_id, target_base_id)

    # Track backdoor for unlimited deploys
    if deploy_action == "backdoor" and result.successes > 0:
        if session:
            session.has_backdoor = True
            session.save(update_fields=["has_backdoor"])

    # Decrement deploys (unless backdoor)
    if session and not session.has_backdoor:
        session.deploys_remaining = max(0, session.deploys_remaining - 1)
        session.detect_stale = False
        session.save(update_fields=["deploys_remaining", "detect_stale"])

    # Passive detection on each deploy
    detection_msg = ""
    if session:
        passive = _passive_detect(thread, actor, session.gain_access_successes)
        if passive:
            detected, det_result, def_name = passive
            if detected:
                session.detected = True
                session.save(update_fields=["detected"])
                detection_msg = f" ⚠ Passive detection by {def_name} — INTRUSION DETECTED!"
            else:
                detection_msg = f" Passive detection by {def_name} — still undetected."
        else:
            detection_msg = " No passive detection (defender unskilled)."
        session.detect_stale = False
        session.save(update_fields=["detect_stale"])

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
    """Handle defend: strengthen encryption, sweep threats."""
    result = roll_dice(pool)

    if result.successes == 0:
        outcome = "Failure — no effect."
        _log_action(thread, actor, "defend", pool, result, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("defend", pool_desc, result, outcome)

    # Raise encryption
    existing = ThreadEffect.objects.filter(
        thread=thread, effect_type="encrypted", is_active=True,
    ).first()
    if existing:
        existing.level = min(existing.level + 1, 3)
        existing.save(update_fields=["level"])
    else:
        ThreadEffect.objects.create(
            thread=thread, effect_type="encrypted",
            level=min(result.successes, 3), source_user=actor,
        )

    # Sweep: remove backdoors, hidden members, and close attacker sessions
    removed_backdoors = ThreadEffect.objects.filter(
        thread=thread, effect_type="backdoor", is_active=True,
    ).update(is_active=False)
    removed_hidden = ThreadMembership.objects.filter(
        thread=thread, hidden=True,
    ).delete()[0]
    closed_sessions = CyberSession.objects.filter(
        thread=thread, is_active=True,
    ).exclude(attacker=actor).update(is_active=False)

    parts = [f"{result.successes} successes — encryption strengthened"]
    if removed_backdoors:
        parts.append(f"{removed_backdoors} backdoor(s) removed")
    if removed_hidden:
        parts.append(f"{removed_hidden} intruder(s) expelled")
    if closed_sessions:
        parts.append(f"{closed_sessions} active session(s) terminated")

    outcome = "; ".join(parts) + "."
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
    # Find any active attacker session on this thread (not by this actor)
    attacker_session = CyberSession.objects.filter(
        thread=thread, is_active=True,
    ).exclude(attacker=actor).first()

    if not attacker_session:
        # Check for any hidden members or effects
        has_threats = (
            ThreadEffect.objects.filter(thread=thread, effect_type="backdoor", is_active=True).exists()
            or ThreadMembership.objects.filter(thread=thread, hidden=True).exists()
        )
        if has_threats:
            outcome = "INTRUSION DETECTED"
        else:
            outcome = "NO INTRUSION DETECTED"
        _log_action(thread, actor, "detect", 0, None, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("detect", pool_desc, None, outcome, hide_dice=True)

    # If detect is stale (no new attacker action), return cached result
    if attacker_session.detect_stale and attacker_session.last_detect_result:
        outcome = attacker_session.last_detect_result
        _log_action(thread, actor, "detect", 0, None, outcome,
                    persona_type, persona_id, persona_name, None, gm_modifier)
        return _roll_response("detect", pool_desc, None, outcome, hide_dice=True)

    # Active detect roll: pool + 2 bonus vs attacker's gain_access successes
    detect_pool = pool + 2
    detect_desc = pool_desc.rsplit("=", 1)[0] + f"+ 2 bonus = {detect_pool} dice"
    result = roll_dice(detect_pool)

    difficulty = attacker_session.gain_access_successes
    detected = result.successes >= difficulty

    if detected:
        outcome = "INTRUSION DETECTED"
        attacker_session.detected = True
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

    # Close all active sessions
    CyberSession.objects.filter(thread=thread, is_active=True).update(is_active=False)

    return JsonResponse({"status": "closed"})


# ---------------------------------------------------------------------------
# Deploy sub-action resolution
# ---------------------------------------------------------------------------

def _resolve_deploy(deploy_action, result, thread, actor,
                    target_agency_id=None, target_base_id=None):
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
        ThreadEffect.objects.create(
            thread=thread, effect_type="locked",
            level=min(s, 3), source_user=actor,
            target_agency_id=target_agency_id,
        )
        agency_name = ""
        if target_agency_id:
            ag = Agency.objects.filter(pk=target_agency_id).first()
            agency_name = f" on {ag.name}" if ag else ""
        return f"{s} successes — ransomware deployed{agency_name}. Systems locked until swept."

    elif deploy_action == "bad_deals":
        agency_name = "unknown"
        if target_agency_id:
            ag = Agency.objects.filter(pk=target_agency_id).first()
            agency_name = ag.name if ag else "unknown"
        return f"{s} successes — fraudulent trade orders placed on the UTC on behalf of {agency_name}. GM determines economic impact."

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
        return f"{s} successes — hidden base location discovered. GM reveals the base."

    elif deploy_action == "base_access":
        base_info = ""
        if target_base_id:
            from agencies.models import Base
            base = Base.objects.filter(pk=target_base_id).first()
            base_info = f" ({base.name})" if base else ""
        return f"{s} successes — gained access to base systems{base_info}. Facilities, equipment, and operations exposed."

    elif deploy_action == "plant_intel":
        return f"{s} successes — false intelligence planted. GM determines what the target sees."

    elif deploy_action == "exfil_comms":
        return f"{s} successes — communications exfiltrated. GM applies hidden access to target agency threads."

    elif deploy_action == "sabotage":
        return f"{s} successes — project sabotaged. Inform GM for narrative resolution."

    elif deploy_action == "corrupt_data":
        agency_name = "unknown"
        if target_agency_id:
            ag = Agency.objects.filter(pk=target_agency_id).first()
            agency_name = ag.name if ag else "unknown"
        return f"{s} successes — data corruption deployed against {agency_name}. GM adjusts integrity."

    elif deploy_action == "close_connection":
        removed_hidden = ThreadMembership.objects.filter(
            thread=thread, user=actor, hidden=True,
        ).delete()[0]
        removed_backdoors = ThreadEffect.objects.filter(
            thread=thread, source_user=actor, effect_type="backdoor", is_active=True,
        ).update(is_active=False)
        # Close session
        CyberSession.objects.filter(
            thread=thread, attacker=actor, is_active=True,
        ).update(is_active=False)
        parts = [f"{s} successes — connection closed cleanly"]
        if removed_hidden:
            parts.append(f"{removed_hidden} hidden access(es) removed")
        if removed_backdoors:
            parts.append(f"{removed_backdoors} backdoor(s) cleaned")
        return "; ".join(parts) + ". All traces removed."

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
