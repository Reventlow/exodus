"""Views for the cyber terminal feature.

Provides API endpoints for cyber actions: eligibility check,
performing actions (gain access, deploy, defend, detect),
thread effects, and intercepted thread listings.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from characters.models import Character
from npcs.models import NPC

from .dice import get_cyber_pool, roll_dice
from .models import (
    CyberAction, Thread, ThreadEffect, ThreadMembership,
)


def _get_actor_stats(user, persona_type=None, persona_id=None):
    """Get attributes, skills, and specialisations for the acting entity.

    Returns (attributes, skills, specialisations, computer_skill, display_name) or None.
    """
    if persona_type == "npc" and persona_id:
        npc = NPC.objects.filter(pk=persona_id).first()
        if npc:
            comp = npc.skills.get("mental", {}).get("Computer", 0)
            return npc.attributes, npc.skills, npc.specialisations, comp, npc.name
        return None
    # Default: use the user's character
    char = Character.objects.filter(owner=user).first()
    if char:
        comp = char.skills.get("mental", {}).get("Computer", 0)
        return char.attributes, char.skills, char.specialisations, comp, char.name
    return None


@login_required
@require_GET
def cyber_eligible(request):
    """Check if current user/persona can use the cyber terminal.

    Query params:
        personaType: 'npc' or empty (use own character)
        personaId: NPC id (when personaType=npc)
    """
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


@login_required
@require_GET
def thread_cyber_status(request, thread_id):
    """Get cyber status of a thread: active effects and action log."""
    thread = get_object_or_404(Thread, pk=thread_id)

    effects = ThreadEffect.objects.filter(thread=thread, is_active=True)
    effects_data = [
        {
            "id": e.pk,
            "type": e.effect_type,
            "level": e.level,
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

    return JsonResponse({"effects": effects_data, "actions": actions_data})


@login_required
@require_POST
def cyber_roll(request, thread_id):
    """Perform a cyber action on a thread.

    Request body:
        actionType: gain_access | deploy | defend | detect
        targetUserId: (optional) user ID of the target
        personaType: '' | 'npc' | 'character' | 'gm'
        personaId: (optional) NPC/character ID
        personaName: (optional) display name
        gmModifier: (optional) bonus/penalty dice from GM
    """
    thread = get_object_or_404(Thread, pk=thread_id)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    action_type = body.get("actionType", "")
    if action_type not in ("gain_access", "deploy", "defend", "detect"):
        return JsonResponse({"error": "Invalid action type"}, status=400)

    deploy_action = body.get("deployAction", "")
    if action_type == "deploy" and deploy_action:
        valid_deploy = [
            "backdoor", "ransomware", "bad_deals", "steal_intel",
            "discover_base", "base_access", "plant_intel", "exfil_comms",
            "sabotage", "corrupt_data", "close_connection",
        ]
        if deploy_action not in valid_deploy:
            return JsonResponse({"error": f"Invalid deploy action: {deploy_action}"}, status=400)

    persona_type = body.get("personaType", "")
    persona_id = body.get("personaId")
    persona_name = body.get("personaName", "")
    gm_modifier = int(body.get("gmModifier", 0))
    target_user_id = body.get("targetUserId")
    target_agency_id = body.get("targetAgencyId")
    target_base_id = body.get("targetBaseId")

    # Get actor stats
    if request.user.is_superuser and persona_type == "gm":
        # GM rolling — use a default high pool or let them set modifier
        pool = 10 + gm_modifier  # GM gets a base pool of 10
        pool_desc = f"GM base 10 + modifier {gm_modifier:+d} = {pool} dice"
        specialisations = []
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

    # Roll the dice
    result = roll_dice(pool)

    # Resolve target user
    target_user = None
    if target_user_id:
        from django.contrib.auth.models import User
        target_user = User.objects.filter(pk=target_user_id).first()

    # Determine outcome
    outcome = _resolve_outcome(
        action_type, result, thread, request.user, target_user,
        persona_type, persona_id, persona_name,
        deploy_action=deploy_action,
        target_agency_id=target_agency_id,
        target_base_id=target_base_id,
    )

    # Log the action
    log_type = f"deploy:{deploy_action}" if deploy_action else action_type
    action = CyberAction.objects.create(
        thread=thread,
        actor=request.user,
        actor_persona_type=persona_type,
        actor_persona_id=persona_id,
        actor_persona_name=persona_name,
        target_user=target_user,
        action_type=log_type,
        dice_pool=pool,
        dice_results=result.rolls,
        successes=result.successes,
        is_exceptional=result.is_exceptional,
        is_dramatic_failure=result.is_dramatic_failure,
        gm_modifier=gm_modifier,
        outcome=outcome,
        notes=json.dumps({"deployAction": deploy_action, "targetAgencyId": target_agency_id, "targetBaseId": target_base_id}) if deploy_action else "",
    )

    return JsonResponse({
        "action": {
            "id": action.pk,
            "actionType": action_type,
            "poolDescription": pool_desc,
            "roll": result.to_dict(),
            "outcome": outcome,
        },
    })


def _resolve_deploy(deploy_action, result, thread, actor,
                    target_agency_id=None, target_base_id=None):
    """Handle deploy sub-action outcomes."""
    from agencies.models import Agency
    s = result.successes
    exc = result.is_exceptional

    if deploy_action == "backdoor":
        ThreadEffect.objects.create(
            thread=thread, effect_type="backdoor",
            level=min(s, 3), source_user=actor,
            target_agency_id=target_agency_id,
        )
        return f"{s} successes — permanent backdoor deployed." + (" Exceptional — extremely difficult to detect." if exc else "")

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
        return f"{s} successes — classified data extracted. A random classified field on the target agency has been unlocked. GM reveals the intel."

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
        return f"{s} successes — communications exfiltrated. Hidden access granted to target agency's NPC dossier threads. GM applies access."

    elif deploy_action == "sabotage":
        return f"{s} successes — project sabotaged. Inform GM of success for narrative resolution."

    elif deploy_action == "corrupt_data":
        agency_name = "unknown"
        if target_agency_id:
            ag = Agency.objects.filter(pk=target_agency_id).first()
            agency_name = ag.name if ag else "unknown"
        return f"{s} successes — data corruption deployed against {agency_name}. GM adjusts integrity."

    elif deploy_action == "close_connection":
        # Remove own hidden memberships and backdoors placed by this actor
        removed_hidden = ThreadMembership.objects.filter(
            thread=thread, user=actor, hidden=True,
        ).delete()[0]
        removed_backdoors = ThreadEffect.objects.filter(
            thread=thread, source_user=actor, effect_type="backdoor", is_active=True,
        ).update(is_active=False)
        parts = [f"{s} successes — connection closed"]
        if removed_hidden:
            parts.append(f"{removed_hidden} hidden access(es) removed")
        if removed_backdoors:
            parts.append(f"{removed_backdoors} backdoor(s) cleaned")
        return "; ".join(parts) + ". All traces removed."

    # Fallback for old-style deploy without sub-action
    ThreadEffect.objects.create(
        thread=thread, effect_type="backdoor",
        level=min(s, 3), source_user=actor,
    )
    return f"{s} successes — backdoor deployed."


def _resolve_outcome(action_type, result, thread, actor, target_user,
                     persona_type, persona_id, persona_name,
                     deploy_action="", target_agency_id=None, target_base_id=None):
    """Apply the mechanical effects of a cyber action and return outcome text."""
    from agencies.models import Agency

    if result.is_dramatic_failure:
        return "Dramatic failure — your intrusion attempt is detected and traced."

    if result.successes == 0:
        return "Failure — no effect."

    if action_type == "gain_access":
        if not target_user:
            return f"{result.successes} successes — but no target specified."
        # Get all threads the target is in (excluding GM-direct threads)
        target_memberships = ThreadMembership.objects.filter(
            user=target_user, hidden=False,
        ).select_related("thread")
        granted = 0
        for tm in target_memberships:
            members = ThreadMembership.objects.filter(
                thread=tm.thread, hidden=False,
            ).values_list("user_id", flat=True)
            if actor.pk in members:
                continue
            from django.contrib.auth.models import User
            su_ids = set(User.objects.filter(is_superuser=True).values_list("pk", flat=True))
            non_su_members = [uid for uid in members if uid not in su_ids]
            if len(non_su_members) <= 1:
                continue
            _, created = ThreadMembership.objects.get_or_create(
                thread=tm.thread, user=actor,
                defaults={"hidden": True},
            )
            if created:
                granted += 1
        if granted:
            return f"{result.successes} successes — gained hidden access to {granted} thread(s)."
        return f"{result.successes} successes — target has no accessible threads."

    elif action_type == "deploy":
        return _resolve_deploy(deploy_action, result, thread, actor,
                               target_agency_id, target_base_id)

    elif action_type == "defend":
        if result.successes >= 1:
            # Raise encryption or sweep
            existing = ThreadEffect.objects.filter(
                thread=thread, effect_type="encrypted", is_active=True,
            ).first()
            if existing:
                existing.level = min(existing.level + 1, 3)
                existing.save(update_fields=["level"])
            else:
                ThreadEffect.objects.create(
                    thread=thread,
                    effect_type="encrypted",
                    level=min(result.successes, 3),
                    source_user=actor,
                )
            # Sweep: remove backdoors and hidden memberships
            removed_backdoors = ThreadEffect.objects.filter(
                thread=thread, effect_type="backdoor", is_active=True,
            ).update(is_active=False)
            removed_hidden = ThreadMembership.objects.filter(
                thread=thread, hidden=True,
            ).delete()[0]
            parts = [f"{result.successes} successes — encryption strengthened"]
            if removed_backdoors:
                parts.append(f"{removed_backdoors} backdoor(s) removed")
            if removed_hidden:
                parts.append(f"{removed_hidden} intruder(s) expelled")
            return "; ".join(parts) + "."
        return "Failure — no effect."

    elif action_type == "detect":
        effects = ThreadEffect.objects.filter(thread=thread, is_active=True)
        hidden = ThreadMembership.objects.filter(thread=thread, hidden=True)
        if not effects.exists() and not hidden.exists():
            return f"{result.successes} successes — thread appears clean."
        parts = [f"{result.successes} successes — threats detected:"]
        for e in effects:
            parts.append(f"  - {e.get_effect_type_display()} (level {e.level})")
        for h in hidden:
            char = Character.objects.filter(owner=h.user).first()
            name = char.name if char else h.user.username
            parts.append(f"  - Hidden intruder: {name}")
        return "\n".join(parts)

    return f"{result.successes} successes."


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
    # Mark them as intercepted
    for d in data:
        d["intercepted"] = True
    return JsonResponse(data, safe=False)


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
            thread=thread,
            effect_type=effect_type,
            level=level,
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
        return JsonResponse({"status": "ok"})

    return JsonResponse({"error": "Unknown action"}, status=400)
