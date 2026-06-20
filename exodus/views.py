"""Core views for Exodus site settings."""

import json
from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import (
    MeritDefinition,
    PullingString,
    SiteSettings,
    _clamp_again,
    _clamp_close_range_penalty,
    _clamp_reach,
)

User = get_user_model()


@login_required
@require_GET
def starmap_demo(request):
    """3D star map demo — superuser only."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("ACCESS DENIED. Superuser clearance required.")
    return render(request, "starmap/demo.html")


@staff_member_required
def site_settings(request):
    """Allow staff to update site-wide settings."""
    settings_obj = SiteSettings.load()

    if request.method == "POST":
        date_value = request.POST.get("next_game_date", "").strip()
        settings_obj.next_game_date = date_value or None
        settings_obj.charter_text = request.POST.get("charter_text", "")
        settings_obj.lock_comms = "lock_comms" not in request.POST
        settings_obj.show_world_map = "show_world_map" in request.POST
        settings_obj.show_star_map = "show_star_map" in request.POST
        settings_obj.show_starships = "show_starships" in request.POST
        # Star-map tech gates. Guarded by a hidden marker (like class_unlock
        # below) so a POST from a different settings form — weapons, armor,
        # etc., which all hit this same view — can't silently reset them.
        if "map_vis_submitted" in request.POST:
            settings_obj.show_ftl_route_planning = "show_ftl_route_planning" in request.POST
            settings_obj.show_exotic_matter = "show_exotic_matter" in request.POST
            settings_obj.show_ftl_jumps = "show_ftl_jumps" in request.POST
            # FTL-jump economy tuning. Merge over current config so keys not on
            # the form (the Phase-2 coefficients) are preserved.
            je = settings_obj.get_jump_economy()

            def _je_num(name, default, cast):
                raw = request.POST.get(name, "").strip()
                if raw == "":
                    return default
                try:
                    return cast(raw)
                except (TypeError, ValueError):
                    return default

            je["maint_wear_per_jump"] = max(0.0, _je_num("jump_maint_wear", je["maint_wear_per_jump"], float))
            je["resupply_amount"] = max(0, _je_num("jump_resupply_amount", je["resupply_amount"], int))
            je["max_jump_ly"] = max(0, _je_num("jump_max_ly", je["max_jump_ly"], int))
            settings_obj.jump_economy_config = je
        settings_obj.show_council = "show_council" in request.POST
        settings_obj.council_mode = request.POST.get("council_mode", "agency")
        settings_obj.enforce_ship_slot_budget = "enforce_ship_slot_budget" in request.POST
        # Per-class base-building unlocks. The form always POSTs the full set
        # so an unchecked checkbox correctly lands as False.
        if "class_unlock_submitted" in request.POST:
            settings_obj.class_unlock_flags = {
                cls: f"class_unlock_{cls}" in request.POST
                for cls in ("soldier", "science", "engineer", "fixer", "ai")
            }
        # Clearance Gate tweaks. Like class_unlock_flags above we only touch
        # the JSON blob when the TWEAKS tab POSTs its hidden marker, so saves
        # from other tabs don't clobber the Clearance Gate settings.
        if "tweaks_submitted" in request.POST:
            tw = settings_obj.get_tweaks()
            valid_palettes = {"emerald", "amber", "ice", "blood", "bone"}
            valid_backdrops = {"ops_map", "code_rain", "plain"}
            valid_rain = {"katakana", "hex", "binary", "ascii"}

            pal = request.POST.get("tweaks_palette", "").strip().lower()
            if pal in valid_palettes:
                tw["palette"] = pal
            bd = request.POST.get("tweaks_backdrop", "").strip().lower()
            if bd in valid_backdrops:
                tw["backdrop"] = bd
            rs = request.POST.get("tweaks_rain_style", "").strip().lower()
            if rs in valid_rain:
                tw["rain_style"] = rs

            def _slider(field, default):
                """Map slider value (0..100) -> 0.0..1.0 with safe coercion."""
                raw = request.POST.get(field, "").strip()
                try:
                    v = float(raw)
                except (TypeError, ValueError):
                    return default
                return max(0.0, min(1.0, v / 100.0))

            tw["map_intensity"] = _slider("tweaks_map_intensity", tw["map_intensity"])
            tw["rain_density"] = _slider("tweaks_rain_density", tw["rain_density"])
            tw["rain_speed"] = _slider("tweaks_rain_speed", tw["rain_speed"])

            tw["show_radar"] = "tweaks_show_radar" in request.POST
            tw["show_nodes"] = "tweaks_show_nodes" in request.POST
            tw["scanlines"] = "tweaks_scanlines" in request.POST
            tw["vignette"] = "tweaks_vignette" in request.POST
            tw["show_rails"] = "tweaks_show_rails" in request.POST

            tw["agency_name"] = (request.POST.get("tweaks_agency_name", "").strip()
                                 or "BLACKLOG.NET")[:50]
            tw["op_codename"] = (request.POST.get("tweaks_op_codename", "").strip()
                                 or "OMEGA-7")[:50]
            # Timezone for the header-strip clock. Validated against the
            # zoneinfo database so a malformed POST can't break the JS
            # clock with an invalid IANA name.
            tz_raw = request.POST.get("tweaks_timezone", "").strip()
            if tz_raw:
                try:
                    from zoneinfo import ZoneInfo, available_timezones
                    if tz_raw == "UTC" or tz_raw in available_timezones():
                        ZoneInfo(tz_raw)  # final sanity check
                        tw["timezone"] = tz_raw
                except Exception:
                    pass
            settings_obj.tweaks = tw
        for lbl in ["dispatch", "players", "agencies", "council", "npcs", "comms"]:
            val = request.POST.get(f"label_{lbl}", "").strip()
            if val:
                setattr(settings_obj, f"label_{lbl}", val)

        # COMBAT NPC TEMPLATES. Stock stat blocks the GM can spawn as
        # mooks. Same parallel-array pattern as weapons/armor/cover —
        # one set of arrays per category. Empty-name rows are dropped.
        if "combat_npcs_submitted" in request.POST:
            npc_categories = ("guard", "razor", "corp", "cultist", "drone")
            new_npcs = []
            for cat in npc_categories:
                names = request.POST.getlist(f"combat_npcs_{cat}_name")
                pools = request.POST.getlist(f"combat_npcs_{cat}_combat_pool")
                defenses = request.POST.getlist(f"combat_npcs_{cat}_defense")
                hps = request.POST.getlist(f"combat_npcs_{cat}_health_max")
                armors = request.POST.getlist(f"combat_npcs_{cat}_armor_rating")
                weapons_in = request.POST.getlist(f"combat_npcs_{cat}_weapon")
                notes_list = request.POST.getlist(f"combat_npcs_{cat}_notes")
                for i, raw_name in enumerate(names):
                    name = (raw_name or "").strip()[:80]
                    if not name:
                        continue
                    new_npcs.append({
                        "name": name,
                        "category": cat,
                        "combat_pool": (pools[i] if i < len(pools) else "").strip()[:8],
                        "defense": (defenses[i] if i < len(defenses) else "").strip()[:8],
                        "health_max": (hps[i] if i < len(hps) else "").strip()[:8],
                        "armor_rating": (armors[i] if i < len(armors) else "").strip()[:16],
                        "weapon": (weapons_in[i] if i < len(weapons_in) else "").strip()[:120],
                        "notes": (notes_list[i] if i < len(notes_list) else "").strip()[:240],
                    })
            settings_obj.combat_npcs = new_npcs

        # COVER catalogue. Same shape as weapons/armor — parallel arrays
        # per tier. Empty-name rows are dropped.
        if "cover_submitted" in request.POST:
            tiers = ("light", "heavy", "full")
            new_cover = []
            for tier in tiers:
                names = request.POST.getlist(f"cover_{tier}_name")
                durabilities = request.POST.getlist(f"cover_{tier}_durability")
                healths = request.POST.getlist(f"cover_{tier}_health")
                notes_list = request.POST.getlist(f"cover_{tier}_notes")
                for i, raw_name in enumerate(names):
                    name = (raw_name or "").strip()[:80]
                    if not name:
                        continue
                    new_cover.append({
                        "name": name,
                        "tier": tier,
                        "durability": (durabilities[i] if i < len(durabilities) else "").strip()[:8],
                        "health": (healths[i] if i < len(healths) else "").strip()[:8],
                        "notes": (notes_list[i] if i < len(notes_list) else "").strip()[:240],
                    })
            settings_obj.cover = new_cover

        # ARMOR catalogue. Same shape as weapons — parallel arrays per
        # category. Empty-name rows are dropped.
        if "armor_submitted" in request.POST:
            arm_categories = ("light", "medium", "heavy", "vacuum")
            new_armor = []
            for cat in arm_categories:
                names = request.POST.getlist(f"armor_{cat}_name")
                ratings = request.POST.getlist(f"armor_{cat}_rating")
                str_mins = request.POST.getlist(f"armor_{cat}_str_min")
                penalties = request.POST.getlist(f"armor_{cat}_penalty")
                notes_list = request.POST.getlist(f"armor_{cat}_notes")
                for i, raw_name in enumerate(names):
                    name = (raw_name or "").strip()[:80]
                    if not name:
                        continue
                    new_armor.append({
                        "name": name,
                        "category": cat,
                        "rating": (ratings[i] if i < len(ratings) else "").strip()[:32],
                        "str_min": (str_mins[i] if i < len(str_mins) else "").strip()[:16],
                        "penalty": (penalties[i] if i < len(penalties) else "").strip()[:48],
                        "notes": (notes_list[i] if i < len(notes_list) else "").strip()[:240],
                    })
            settings_obj.armor = new_armor

        # WEAPONS catalogue. Submitted as parallel arrays per category
        # (name / damage / range / capacity / notes). Empty-name rows
        # are dropped so the editor's add-row button can leave blank
        # rows without saving them.
        #
        # v0.15.14 — firearms additionally carry an ``auto_capable``
        # column. Each firearm row submits a parallel hidden input
        # ``weapons_firearm_auto_capable_flag`` carrying "1" / "0";
        # the visible checkbox toggles the hidden input via a small
        # change handler in the template so both stay in lock-step.
        # Using a parallel array (rather than checkbox-by-index) makes
        # the field robust against row deletions — the i-th flag
        # always pairs with the i-th name regardless of how the rows
        # have been re-ordered or pruned in the editor.
        if "weapons_submitted" in request.POST:
            # v0.15.29 — added "grenade" as a fifth category. Same
            # parallel-array shape as the existing categories; grenades
            # add radius / effect_duration_rounds via the editor (other
            # grenade fields stay catalogue-fixed and are read at hydrate
            # time only, so a settings round-trip preserves them
            # unmodified).
            categories = ("melee", "improvised", "firearm", "thrown", "grenade")
            firearm_auto_flags = request.POST.getlist(
                "weapons_firearm_auto_capable_flag"
            )
            # v0.15.15 — magazine size parallel-array. Same shape as
            # the auto_capable flag — paired row-for-row with the
            # firearm column blocks, length-defensive on read.
            firearm_magazines = request.POST.getlist(
                "weapons_firearm_magazine"
            )
            # v0.15.19 — X-again explosion threshold parallel-array.
            # Same parallel-array pattern as the magazine / auto flag.
            # Each entry is one of {8, 9, 10}; ``_clamp_again`` defends
            # against bad input by collapsing to 10 (classic behaviour).
            firearm_again_thresholds = request.POST.getlist(
                "weapons_firearm_again"
            )
            # v0.15.26 — knockdown_capable parallel-array. "1" / "0"
            # paired row-for-row with the rest of the firearm columns.
            # Surfaces as the KO column in the editor and seeds True
            # on Shotgun / Twin-Barrel / Auto Shotgun by default.
            firearm_knockdown_flags = request.POST.getlist(
                "weapons_firearm_knockdown_flag"
            )
            # v0.15.33 — close_range_penalty parallel-array. Signed
            # integer paired row-for-row with the rest of the firearm
            # columns. ``_clamp_close_range_penalty`` enforces the
            # ±10 bounds and collapses bad input to 0. Surfaces as the
            # CR PEN column in the editor; seeds DMR -2 / Scoped Rifle
            # -3 by default with all other firearms at 0.
            firearm_close_range_penalties = request.POST.getlist(
                "weapons_firearm_close_range_penalty"
            )
            # v0.15.29 — grenade-specific parallel arrays. ``radius`` and
            # ``effect_duration_rounds`` are the two GM-tweakable fields
            # surfaced in the editor; the rest of the grenade fields
            # (effect_tag, damage_dice, damage_type, cover_resists) stay
            # catalogue-fixed and are preserved by name lookup against
            # the previous saved entry. New rows added in the editor
            # default to a benign no-effect grenade until the GM edits
            # the JSON via the API / admin.
            grenade_radii = request.POST.getlist(
                "weapons_grenade_radius"
            )
            grenade_durations = request.POST.getlist(
                "weapons_grenade_effect_duration"
            )
            # Index existing grenades by name so we can preserve the
            # catalogue-fixed fields on a settings round-trip without
            # exposing them in the editor.
            existing_grenades_by_name = {}
            for w in settings_obj.get_weapons():
                if isinstance(w, dict) and w.get("category") == "grenade":
                    existing_grenades_by_name[w.get("name", "")] = w
            new_weapons = []
            for cat in categories:
                names = request.POST.getlist(f"weapons_{cat}_name")
                damages = request.POST.getlist(f"weapons_{cat}_damage")
                ranges = request.POST.getlist(f"weapons_{cat}_range")
                capacities = request.POST.getlist(f"weapons_{cat}_capacity")
                notes_list = request.POST.getlist(f"weapons_{cat}_notes")
                # v0.15.34 — REACH parallel-array per category. Stored
                # as a non-negative integer (0..5) on the JSONField. The
                # combat resolver compares attacker vs target reach to
                # grant +1 dice when both are at engaged range. Length-
                # defensive: a partial POST collapses the missing entry
                # to 0 (the no-bonus default) rather than raising
                # IndexError, mirroring the close_range_penalty pattern.
                reach_values = request.POST.getlist(f"weapons_{cat}_reach")
                # Per-category counter for the grenade parallel arrays.
                # Indexed independently of i (which iterates names per
                # category) so the radius / duration arrays only consume
                # entries when cat == "grenade".
                grenade_idx = 0
                for i, raw_name in enumerate(names):
                    name = (raw_name or "").strip()[:80]
                    if not name:
                        continue
                    entry = {
                        "name": name,
                        "category": cat,
                        "damage": (damages[i] if i < len(damages) else "").strip()[:48],
                        "range": (ranges[i] if i < len(ranges) else "").strip()[:48],
                        "capacity": (capacities[i] if i < len(capacities) else "").strip()[:48],
                        "notes": (notes_list[i] if i < len(notes_list) else "").strip()[:240],
                        # v0.15.34 — reach. Length-defensive on read;
                        # missing entry collapses to 0 (no bonus) via
                        # ``_clamp_reach``. Bounded ``[0, 5]`` server-
                        # side; bad input also collapses to 0.
                        "reach": _clamp_reach(
                            reach_values[i] if i < len(reach_values) else 0
                        ),
                    }
                    if cat == "firearm":
                        # v0.15.14 — read the parallel auto_capable
                        # flag for this row. Defensive against length
                        # mismatch (legacy rows submitted before the
                        # field was added would only carry the visible
                        # columns, in which case the missing flag
                        # collapses to False).
                        flag_raw = (
                            firearm_auto_flags[i]
                            if i < len(firearm_auto_flags) else "0"
                        )
                        entry["auto_capable"] = (flag_raw == "1")
                        # v0.15.15 — read the parallel magazine size.
                        # Coerce to a non-negative int; bad data falls
                        # back to 0 (which the combat layer reads as
                        # "no ammo tracking"). Hard cap at 999 to
                        # mirror the editor input's max attribute and
                        # prevent absurd JSON payloads from a tampered
                        # POST.
                        mag_raw = (
                            firearm_magazines[i]
                            if i < len(firearm_magazines) else "0"
                        )
                        try:
                            mag_val = int(mag_raw)
                        except (TypeError, ValueError):
                            mag_val = 0
                        if mag_val < 0:
                            mag_val = 0
                        if mag_val > 999:
                            mag_val = 999
                        entry["magazine"] = mag_val
                        # v0.15.19 — pull this row's X-again threshold
                        # from the parallel array and clamp to one of
                        # {8, 9, 10}. Missing / bad input collapses to
                        # 10 so existing catalogues survive a partial
                        # POST without changing semantics.
                        again_raw = (
                            firearm_again_thresholds[i]
                            if i < len(firearm_again_thresholds) else 10
                        )
                        entry["again"] = _clamp_again(again_raw)
                        # v0.15.26 — knockdown_capable parallel-array.
                        # "1" / "0" string semantics mirror auto_capable;
                        # length-defensive on read so a partial POST
                        # (or a row-deletion mid-edit) collapses cleanly
                        # to False rather than raising IndexError.
                        ko_raw = (
                            firearm_knockdown_flags[i]
                            if i < len(firearm_knockdown_flags) else "0"
                        )
                        entry["knockdown_capable"] = (ko_raw == "1")
                        # v0.15.33 — close_range_penalty parallel-array.
                        # Length-defensive on read; missing entry → 0
                        # (default no-penalty). ``_clamp_close_range_penalty``
                        # enforces the ±10 bound and collapses any
                        # garbage input back to 0 — mirroring the
                        # ``_clamp_again`` defensive pattern.
                        crp_raw = (
                            firearm_close_range_penalties[i]
                            if i < len(firearm_close_range_penalties) else 0
                        )
                        entry["close_range_penalty"] = (
                            _clamp_close_range_penalty(crp_raw)
                        )
                    if cat == "grenade":
                        # v0.15.29 — preserve catalogue-fixed fields by
                        # name lookup. New rows (no prior entry) get
                        # safe defaults so a fresh add doesn't crash
                        # the throw resolver.
                        prev = existing_grenades_by_name.get(name, {})
                        radius_raw = (
                            grenade_radii[grenade_idx]
                            if grenade_idx < len(grenade_radii) else ""
                        )
                        radius = (radius_raw or "").strip().lower()[:16]
                        if radius not in ("close", "medium", "large"):
                            radius = (prev.get("radius", "medium") or "medium")
                        entry["radius"] = radius
                        dur_raw = (
                            grenade_durations[grenade_idx]
                            if grenade_idx < len(grenade_durations) else "0"
                        )
                        try:
                            dur_val = int(dur_raw)
                        except (TypeError, ValueError):
                            dur_val = 0
                        if dur_val < 0:
                            dur_val = 0
                        if dur_val > 99:
                            dur_val = 99
                        entry["effect_duration_rounds"] = dur_val
                        # Catalogue-fixed fields preserved verbatim from
                        # the prior entry. Defaults apply only when the
                        # editor adds a brand-new row.
                        entry["effect_tag"] = (prev.get("effect_tag", "") or "")
                        try:
                            dd = int(prev.get("damage_dice", 0) or 0)
                        except (TypeError, ValueError):
                            dd = 0
                        entry["damage_dice"] = max(0, dd)
                        entry["damage_type"] = (prev.get("damage_type", "none") or "none")
                        entry["cover_resists"] = bool(prev.get("cover_resists", True))
                        # Match the firearm row in carrying inert flags
                        # so other code that scans the catalogue (e.g.
                        # the get_weapons hydrator) doesn't have to
                        # special-case this category.
                        entry.setdefault("auto_capable", False)
                        entry.setdefault("magazine", 0)
                        entry.setdefault("again", 10)
                        entry.setdefault("knockdown_capable", False)
                        grenade_idx += 1
                    new_weapons.append(entry)
            settings_obj.weapons = new_weapons

        settings_obj.save()
        messages.success(request, "Settings updated.")
        return redirect("site-settings")

    from agencies.models import Agency
    users = User.objects.filter(is_active=True).order_by("username")
    impersonating = request.session.get("_impersonate_real_user_id")
    all_agencies = Agency.objects.order_by("name")
    player_agencies = all_agencies.filter(is_player_agency=True)
    npc_agencies = all_agencies.filter(is_player_agency=False)
    # Pre-grouped weapons sections for the structured editor.
    # v0.15.29 — added "grenade" as a fifth category. Edited fields:
    # radius + effect_duration_rounds. Other grenade fields (effect_tag,
    # damage_dice, damage_type, cover_resists) stay catalogue-fixed
    # and round-trip via the name-lookup preserve path.
    weapons_by_cat = {
        "melee": [], "improvised": [], "firearm": [],
        "thrown": [], "grenade": [],
    }
    for w in settings_obj.get_weapons():
        if isinstance(w, dict) and w.get("category") in weapons_by_cat:
            weapons_by_cat[w["category"]].append(w)
    weapons_sections = [
        {"cat": "melee", "label": "MELEE",
         "hint": "Strength + Brawl / Weaponry · close-combat tools",
         "rows": weapons_by_cat["melee"]},
        {"cat": "improvised", "label": "IMPROVISED",
         "hint": "Strength + Brawl · −1 weapon mod · breaks on 2+ successes",
         "rows": weapons_by_cat["improvised"]},
        {"cat": "firearm", "label": "FIREARM",
         "hint": "Dexterity + Firearms · range bands per weapon",
         "rows": weapons_by_cat["firearm"]},
        {"cat": "thrown", "label": "THROWN",
         "hint": "Dexterity + Athletics · Strength × range",
         "rows": weapons_by_cat["thrown"]},
        {"cat": "grenade", "label": "GRENADE",
         "hint": "Dexterity + Athletics · AOE blast · effect tags applied to every target in radius",
         "rows": weapons_by_cat["grenade"]},
    ]

    # Pre-grouped armor sections for the structured editor.
    armor_by_cat = {"light": [], "medium": [], "heavy": [], "vacuum": []}
    for a in settings_obj.get_armor():
        if isinstance(a, dict) and a.get("category") in armor_by_cat:
            armor_by_cat[a["category"]].append(a)
    armor_sections = [
        {"cat": "light", "label": "LIGHT",
         "hint": "Concealable. Minimal penalty.",
         "rows": armor_by_cat["light"]},
        {"cat": "medium", "label": "MEDIUM",
         "hint": "Visible. Moderate protection, moderate penalty.",
         "rows": armor_by_cat["medium"]},
        {"cat": "heavy", "label": "HEAVY",
         "hint": "Full ballistic / plate. Significant penalty.",
         "rows": armor_by_cat["heavy"]},
        {"cat": "vacuum", "label": "VACUUM",
         "hint": "Sealed pressure suit. Includes life support.",
         "rows": armor_by_cat["vacuum"]},
    ]

    # Pre-grouped cover sections for the structured editor.
    cover_by_tier = {"light": [], "heavy": [], "full": []}
    for c in settings_obj.get_cover():
        if isinstance(c, dict) and c.get("tier") in cover_by_tier:
            cover_by_tier[c["tier"]].append(c)
    cover_sections = [
        {"tier": "light", "label": "LIGHT COVER",
         "hint": "−2 to attacker · ≤ 50% body shielded",
         "rows": cover_by_tier["light"]},
        {"tier": "heavy", "label": "HEAVY COVER",
         "hint": "−4 to attacker · ≥ 75% body shielded",
         "rows": cover_by_tier["heavy"]},
        {"tier": "full", "label": "FULL COVER",
         "hint": "Cannot target directly · target must expose to be attacked",
         "rows": cover_by_tier["full"]},
    ]

    # Pre-grouped combat NPC sections for the structured editor.
    npc_by_cat = {"guard": [], "razor": [], "corp": [], "cultist": [], "drone": []}
    for n in settings_obj.get_combat_npcs():
        if isinstance(n, dict) and n.get("category") in npc_by_cat:
            npc_by_cat[n["category"]].append(n)
    combat_npcs_sections = [
        {"cat": "guard", "label": "GUARD",
         "hint": "Untrained civilian / building security · low pool, no armor",
         "rows": npc_by_cat["guard"]},
        {"cat": "razor", "label": "RAZOR",
         "hint": "Street fighters and mercs · mid pool, mixed armor",
         "rows": npc_by_cat["razor"]},
        {"cat": "corp", "label": "CORPORATE",
         "hint": "Trained corporate security ladder · solid pool + armor",
         "rows": npc_by_cat["corp"]},
        {"cat": "cultist", "label": "CULTIST",
         "hint": "Zealous fighters, no morale · low to high tier",
         "rows": npc_by_cat["cultist"]},
        {"cat": "drone", "label": "DRONE / NON-HUMAN",
         "hint": "Autonomous / animal · cannot be intimidated",
         "rows": npc_by_cat["drone"]},
    ]

    return render(request, "site_settings.html", {
        "settings_obj": settings_obj,
        "users": users,
        "impersonating": impersonating,
        "player_agencies": player_agencies,
        "npc_agencies": npc_agencies,
        "tweaks": settings_obj.get_tweaks(),
        "weapons_sections": weapons_sections,
        "armor_sections": armor_sections,
        "cover_sections": cover_sections,
        "combat_npcs_sections": combat_npcs_sections,
    })


@login_required
@require_POST
def impersonate_user(request):
    """Log in as another user (superuser only). Stores real user ID in session."""
    if not request.user.is_superuser and "_impersonate_real_user_id" not in request.session:
        return HttpResponseForbidden("ACCESS DENIED.")

    target_id = request.POST.get("user_id")
    if not target_id:
        return redirect("site-settings")

    target = User.objects.filter(pk=target_id).first()
    if not target:
        messages.error(request, "User not found.")
        return redirect("site-settings")

    # Store real superuser ID before switching
    real_user_id = request.session.get("_impersonate_real_user_id") or request.user.pk

    login(request, target, backend="django.contrib.auth.backends.ModelBackend")
    # Restore after login() flushes the session
    request.session["_impersonate_real_user_id"] = real_user_id
    messages.success(request, f"Now viewing as {target.username}.")
    return redirect("/")


@login_required
def stop_impersonation(request):
    """Return to the real superuser account."""
    real_user_id = request.session.get("_impersonate_real_user_id")
    if real_user_id:
        real_user = User.objects.filter(pk=real_user_id).first()
        if real_user:
            del request.session["_impersonate_real_user_id"]
            login(request, real_user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, f"Returned to {real_user.username}.")
            return redirect("site-settings")

    # Fallback: if no impersonation session, try to find the superuser
    superuser = User.objects.filter(is_superuser=True).first()
    if superuser:
        request.session.pop("_impersonate_real_user_id", None)
        login(request, superuser, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Returned to {superuser.username}.")
        return redirect("site-settings")

    return redirect("/")


@login_required
@require_POST
def api_transfer_player_to_agency(request):
    """Transfer a player's character and NPCs to another agency as NPC dossiers."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    from django.db import transaction
    from django.core.files.base import ContentFile
    from characters.models import Character
    from npcs.models import NPC, NpcMerit, NpcPullingString
    from agencies.models import Agency, Base

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    source_user_id = body.get("sourceUserId")
    target_agency_id = body.get("targetAgencyId")
    source_agency_id = body.get("sourceAgencyId")
    transfer_xp = body.get("transferXp", False)

    source_user = User.objects.filter(pk=source_user_id).first()
    if not source_user:
        return JsonResponse({"error": "Source user not found."}, status=400)

    character = Character.objects.filter(owner=source_user).first()
    if not character:
        return JsonResponse({"error": "Source user has no character."}, status=400)

    target_agency = Agency.objects.filter(pk=target_agency_id).first()
    if not target_agency:
        return JsonResponse({"error": "Target agency not found."}, status=400)

    source_agency = None
    if source_agency_id:
        source_agency = Agency.objects.filter(pk=source_agency_id).first()

    with transaction.atomic():
        # Create NPC dossier from character
        npc = NPC.objects.create(
            name=character.name,
            character_class=character.character_class,
            bio=character.dossier or "",
            attributes=character.attributes,
            skills=character.skills,
            health_bashing=getattr(character, "health_bashing", 0),
            health_lethal=getattr(character, "health_lethal", 0),
            health_aggravated=getattr(character, "health_aggravated", 0),
            size=character.size,
            mental_load=character.mental_load or 0,
            willpower_current=character.willpower_current or 0,
            experience=character.experience or 0,
            experience_used=character.experience_used or 0,
            flaws=character.flaws or [],
            specialisations=character.specialisations if hasattr(character, "specialisations") else [],
            is_npc_dossier=True,
            agency=target_agency,
            created_by=request.user,
            state="active",
        )

        # Copy profile picture
        if character.profile_picture:
            try:
                name = character.profile_picture.name.split("/")[-1]
                npc.image.save(name, ContentFile(character.profile_picture.read()), save=True)
            except Exception:
                pass

        # Copy merits
        for cm in character.character_merits.select_related("merit").all():
            NpcMerit.objects.create(npc=npc, merit=cm.merit, rating=cm.rating)

        # Copy pulling strings
        for cps in character.character_pulling_strings.select_related("pulling_string").all():
            NpcPullingString.objects.create(npc=npc, pulling_string=cps.pulling_string)

        # Transfer existing player NPCs to target agency
        npcs_moved = NPC.objects.filter(assigned_to=source_user).update(
            is_npc_dossier=True, agency=target_agency, assigned_to=None
        )

        # Clean up workspace assignments referencing this character
        char_id = character.id
        for base in Base.objects.all():
            if base.workspaces:
                cleaned = [
                    ws for ws in base.workspaces
                    if not (ws.get("assignedType") == "character" and ws.get("assignedTo") == char_id)
                ]
                if len(cleaned) != len(base.workspaces):
                    base.workspaces = cleaned
                    base.save(update_fields=["workspaces"])

        # Transfer XP and merits from source agency
        xp_transferred = 0
        merits_transferred = 0
        if transfer_xp and source_agency:
            xp_transferred = source_agency.experience
            target_agency.experience = (target_agency.experience or 0) + xp_transferred
            source_agency.experience = 0
            # Transfer merits
            src_merits = source_agency.merits or []
            tgt_merits = target_agency.merits or []
            merits_transferred = len(src_merits)
            target_agency.merits = tgt_merits + src_merits
            source_agency.merits = []
            source_agency.save(update_fields=["experience", "merits"])
            target_agency.save(update_fields=["experience", "merits"])

        # Delete the character
        char_name = character.name
        character.delete()

    return JsonResponse({
        "status": "Transfer complete.",
        "character": char_name,
        "npcDossierId": npc.id,
        "npcsMoved": npcs_moved,
        "xpTransferred": xp_transferred,
        "meritsTransferred": merits_transferred,
        "targetAgency": target_agency.name,
    })


@login_required
def rules_page(request):
    """RULES landing — clearance-gate hub that groups rule sub-systems
    (merits, pulling strings, combat, future: flaws, conditions, etc.)."""
    return render(request, "rules.html", {
        "is_admin": request.user.is_superuser,
    })


@login_required
def base_building_page(request):
    """RULES → BASE BUILDING — player-facing reference for how facilities,
    equipment, location types, and living conditions drive each department's
    thrive score.

    Every table here is generated from the live thrive constants in
    ``agencies.serializers`` (the same maps ``compute_base_thrive`` uses) plus
    the editable ``BaseConfig`` names — so the page can never drift out of sync
    with the actual scoring. The GLOBAL CONDITIONS section is prose that mirrors
    the hardcoded thresholds in ``compute_base_thrive``; keep the two together
    when those thresholds change.
    """
    from agencies.serializers import (
        FACILITY_DEPT_BONUSES,
        EQUIPMENT_DEPT_BONUSES,
        LOCATION_THRIVE_PENALTIES,
        MILITARY_FACILITY_KEYS,
        SCIENCE_FACILITY_KEYS,
        DIPLOMATIC_FACILITY_KEYS,
        ENGINEERING_FACILITY_KEYS,
    )
    from agencies.models import BaseConfig, BASE_DEPARTMENTS, THRIVE_LABELS

    cfg = BaseConfig.load()
    fac_names = {f["key"]: f.get("name", f["key"]) for f in (cfg.facility_types or [])}
    eq_names = {e["key"]: e.get("name", e["key"]) for e in (cfg.equipment_types or [])}
    loc_names = {l["key"]: l.get("name", l["key"]) for l in (cfg.location_types or [])}
    dept_names = {d["key"]: d["name"] for d in BASE_DEPARTMENTS}

    # Departments that participate in base thrive, in the order compute uses.
    dept_order = [
        "military", "intelligence", "engineering_ops",
        "science_ops", "diplomatic_corps", "admin",
    ]

    def fmt_effects(mapping):
        items = sorted(
            mapping.items(),
            key=lambda kv: dept_order.index(kv[0]) if kv[0] in dept_order else 99,
        )
        return [
            {
                "dept": dept_names.get(k, k.replace("_", " ").title()),
                "bonus": v,
                "positive": v > 0,
            }
            for k, v in items
        ]

    def pretty(key, lookup):
        return lookup.get(key, key.replace("_", " ").title())

    facility_rows = sorted(
        (
            {"name": pretty(key, fac_names), "effects": fmt_effects(mapping)}
            for key, mapping in FACILITY_DEPT_BONUSES.items()
        ),
        key=lambda r: r["name"].lower(),
    )
    equipment_rows = sorted(
        (
            {"name": pretty(key, eq_names), "effects": fmt_effects(mapping)}
            for key, mapping in EQUIPMENT_DEPT_BONUSES.items()
        ),
        key=lambda r: r["name"].lower(),
    )
    location_rows = sorted(
        (
            {
                "name": pretty(key, loc_names),
                "penalties": fmt_effects(conf.get("penalty_per_facility", {})),
                "bonuses": fmt_effects(conf.get("bonus", {})),
            }
            for key, conf in LOCATION_THRIVE_PENALTIES.items()
        ),
        key=lambda r: r["name"].lower(),
    )

    def names_for(keyset):
        return sorted(pretty(k, fac_names) for k in keyset)

    penalty_groups = [
        {"label": "Military", "facilities": names_for(MILITARY_FACILITY_KEYS)},
        {"label": "Science", "facilities": names_for(SCIENCE_FACILITY_KEYS)},
        {"label": "Diplomatic", "facilities": names_for(DIPLOMATIC_FACILITY_KEYS)},
        {"label": "Engineering", "facilities": names_for(ENGINEERING_FACILITY_KEYS)},
    ]

    thrive_scale = [
        {
            "score": s,
            "label": THRIVE_LABELS[s],
            "mod": (lambda m: f"+{m}" if m > 0 else (str(m) if m < 0 else "0"))((s - 5) // 2),
        }
        for s in range(1, 11)
    ]

    return render(request, "base_building.html", {
        "departments": [dept_names[k] for k in dept_order],
        "facility_rows": facility_rows,
        "equipment_rows": equipment_rows,
        "location_rows": location_rows,
        "penalty_groups": penalty_groups,
        "thrive_scale": thrive_scale,
    })


@require_http_methods(["GET", "POST"])
def api_cover(request):
    """List or create cover entries.

    GET → ``{"count", "cover": [...]}``. POST creates a new entry.
    Body: ``{name, tier, durability?, health?, notes?}``. 409 on duplicate name.
    Admin / MCP-superuser only.
    """
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)
    settings_obj = SiteSettings.load()
    cover_list = list(settings_obj.get_cover())

    if request.method == "GET":
        return JsonResponse({"count": len(cover_list), "cover": cover_list})

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "'name' is required."}, status=400)
    tier = (body.get("tier") or "").strip().lower()
    if tier not in ("light", "heavy", "full"):
        return JsonResponse({
            "error": "'tier' must be one of: light, heavy, full.",
        }, status=400)
    if any((c.get("name") or "").lower() == name.lower() for c in cover_list):
        return JsonResponse({
            "error": f"Cover named '{name}' already exists. Use PUT on the detail URL to update.",
        }, status=409)

    new_c = {
        "name": name[:80],
        "tier": tier,
        "durability": (body.get("durability") or "").strip()[:8],
        "health": (body.get("health") or "").strip()[:8],
        "notes": (body.get("notes") or "").strip()[:240],
    }
    cover_list.append(new_c)
    settings_obj.cover = cover_list
    settings_obj.save(update_fields=["cover"])
    return JsonResponse(new_c, status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_cover_detail(request, name):
    """Get / update / delete a single cover entry by (case-insensitive) name."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)
    settings_obj = SiteSettings.load()
    cover_list = list(settings_obj.get_cover())

    idx = next(
        (i for i, c in enumerate(cover_list)
         if (c.get("name") or "").lower() == name.lower()),
        None,
    )
    if idx is None:
        return JsonResponse({"error": f"Cover '{name}' not found."}, status=404)

    if request.method == "GET":
        return JsonResponse(cover_list[idx])

    if request.method == "DELETE":
        removed = cover_list.pop(idx)
        settings_obj.cover = cover_list
        settings_obj.save(update_fields=["cover"])
        return JsonResponse({"deleted": removed})

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    c = dict(cover_list[idx])
    if "name" in body:
        new_name = (body["name"] or "").strip()
        if new_name:
            if any(
                i != idx and (other.get("name") or "").lower() == new_name.lower()
                for i, other in enumerate(cover_list)
            ):
                return JsonResponse({
                    "error": f"Cover named '{new_name}' already exists.",
                }, status=409)
            c["name"] = new_name[:80]
    if "tier" in body:
        tier = (body["tier"] or "").strip().lower()
        if tier in ("light", "heavy", "full"):
            c["tier"] = tier
    for field, limit in (("durability", 8), ("health", 8),
                         ("notes", 240)):
        if field in body:
            c[field] = (body[field] or "").strip()[:limit]
    cover_list[idx] = c
    settings_obj.cover = cover_list
    settings_obj.save(update_fields=["cover"])
    return JsonResponse(c)


# ---------------------------------------------------------------------------
# Combat NPC template catalogue (admin-only)
# ---------------------------------------------------------------------------

# Categories accepted by the combat NPC catalogue. Centralised so the
# list and detail handlers stay in lock-step.
_NPC_CATEGORIES = ("guard", "razor", "corp", "cultist", "drone")


@require_http_methods(["GET", "POST"])
def api_combat_npcs(request):
    """List or create combat NPC templates.

    GET → ``{"count", "combat_npcs": [...]}``. POST creates a new entry.
    Body: ``{name, category, combat_pool?, defense?, health_max?,
    armor_rating?, weapon?, notes?}``. 409 on duplicate name (case-insensitive).
    Admin / MCP-superuser only.
    """
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    settings_obj = SiteSettings.load()
    npc_list = list(settings_obj.get_combat_npcs())

    if request.method == "GET":
        return JsonResponse({"count": len(npc_list), "combat_npcs": npc_list})

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "'name' is required."}, status=400)
    cat = (body.get("category") or "").strip().lower()
    if cat not in _NPC_CATEGORIES:
        return JsonResponse({
            "error": f"'category' must be one of: {', '.join(_NPC_CATEGORIES)}.",
        }, status=400)
    if any((n.get("name") or "").lower() == name.lower() for n in npc_list):
        return JsonResponse({
            "error": f"Combat NPC named '{name}' already exists. Use PUT on the detail URL to update.",
        }, status=409)

    new_n = {
        "name": name[:80],
        "category": cat,
        "combat_pool": (body.get("combat_pool") or "").strip()[:8],
        "defense": (body.get("defense") or "").strip()[:8],
        "health_max": (body.get("health_max") or "").strip()[:8],
        "armor_rating": (body.get("armor_rating") or "").strip()[:16],
        "weapon": (body.get("weapon") or "").strip()[:120],
        "notes": (body.get("notes") or "").strip()[:240],
    }
    npc_list.append(new_n)
    settings_obj.combat_npcs = npc_list
    settings_obj.save(update_fields=["combat_npcs"])
    return JsonResponse(new_n, status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_combat_npc_detail(request, name):
    """Get / update / delete a single combat NPC template by
    (case-insensitive) name. PUT body is partial — only the fields you
    include are changed. Pass ``name`` to rename; collision is rejected
    with 409."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    settings_obj = SiteSettings.load()
    npc_list = list(settings_obj.get_combat_npcs())

    idx = next(
        (i for i, n in enumerate(npc_list)
         if (n.get("name") or "").lower() == name.lower()),
        None,
    )
    if idx is None:
        return JsonResponse({"error": f"Combat NPC '{name}' not found."}, status=404)

    if request.method == "GET":
        return JsonResponse(npc_list[idx])

    if request.method == "DELETE":
        removed = npc_list.pop(idx)
        settings_obj.combat_npcs = npc_list
        settings_obj.save(update_fields=["combat_npcs"])
        return JsonResponse({"deleted": removed})

    # PUT — partial update
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    n = dict(npc_list[idx])
    if "name" in body:
        new_name = (body["name"] or "").strip()
        if new_name:
            if any(
                i != idx and (other.get("name") or "").lower() == new_name.lower()
                for i, other in enumerate(npc_list)
            ):
                return JsonResponse({
                    "error": f"Combat NPC named '{new_name}' already exists.",
                }, status=409)
            n["name"] = new_name[:80]
    if "category" in body:
        cat = (body["category"] or "").strip().lower()
        if cat in _NPC_CATEGORIES:
            n["category"] = cat
    for field, limit in (("combat_pool", 8), ("defense", 8),
                         ("health_max", 8), ("armor_rating", 16),
                         ("weapon", 120), ("notes", 240)):
        if field in body:
            n[field] = (body[field] or "").strip()[:limit]
    npc_list[idx] = n
    settings_obj.combat_npcs = npc_list
    settings_obj.save(update_fields=["combat_npcs"])
    return JsonResponse(n)


@require_http_methods(["GET", "POST"])
def api_armor(request):
    """List or create armor in the site catalogue.

    GET   → ``{"count": N, "armor": [...]}``
    POST  → create new. Body: ``{name, category, rating?, str_min?,
            penalty?, notes?}``. 409 on duplicate name.

    Admin / MCP-superuser only.
    """
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    settings_obj = SiteSettings.load()
    armor_list = list(settings_obj.get_armor())

    if request.method == "GET":
        return JsonResponse({"count": len(armor_list), "armor": armor_list})

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "'name' is required."}, status=400)
    cat = (body.get("category") or "").strip().lower()
    if cat not in ("light", "medium", "heavy", "vacuum"):
        return JsonResponse({
            "error": "'category' must be one of: light, medium, heavy, vacuum.",
        }, status=400)
    if any((a.get("name") or "").lower() == name.lower() for a in armor_list):
        return JsonResponse({
            "error": f"Armor named '{name}' already exists. Use PUT on the detail URL to update.",
        }, status=409)

    new_a = {
        "name": name[:80],
        "category": cat,
        "rating": (body.get("rating") or "").strip()[:32],
        "str_min": (body.get("str_min") or "").strip()[:16],
        "penalty": (body.get("penalty") or "").strip()[:48],
        "notes": (body.get("notes") or "").strip()[:240],
    }
    armor_list.append(new_a)
    settings_obj.armor = armor_list
    settings_obj.save(update_fields=["armor"])
    return JsonResponse(new_a, status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_armor_detail(request, name):
    """Get / update / delete a single armor entry by (case-insensitive) name."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    settings_obj = SiteSettings.load()
    armor_list = list(settings_obj.get_armor())

    idx = next(
        (i for i, a in enumerate(armor_list)
         if (a.get("name") or "").lower() == name.lower()),
        None,
    )
    if idx is None:
        return JsonResponse({"error": f"Armor '{name}' not found."}, status=404)

    if request.method == "GET":
        return JsonResponse(armor_list[idx])

    if request.method == "DELETE":
        removed = armor_list.pop(idx)
        settings_obj.armor = armor_list
        settings_obj.save(update_fields=["armor"])
        return JsonResponse({"deleted": removed})

    # PUT — partial
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    a = dict(armor_list[idx])
    if "name" in body:
        new_name = (body["name"] or "").strip()
        if new_name:
            if any(
                i != idx and (other.get("name") or "").lower() == new_name.lower()
                for i, other in enumerate(armor_list)
            ):
                return JsonResponse({
                    "error": f"Armor named '{new_name}' already exists.",
                }, status=409)
            a["name"] = new_name[:80]
    if "category" in body:
        cat = (body["category"] or "").strip().lower()
        if cat in ("light", "medium", "heavy", "vacuum"):
            a["category"] = cat
    for field, limit in (("rating", 32), ("str_min", 16),
                         ("penalty", 48), ("notes", 240)):
        if field in body:
            a[field] = (body[field] or "").strip()[:limit]
    armor_list[idx] = a
    settings_obj.armor = armor_list
    settings_obj.save(update_fields=["armor"])
    return JsonResponse(a)


@require_http_methods(["GET", "POST"])
def api_weapons(request):
    """List or create weapons in the site catalogue.

    GET   → ``{"count": N, "weapons": [...]}``
    POST  → create a new weapon. Body: ``{name, category, damage?,
            range?, capacity?, notes?}``. Returns the created entry
            (201). 409 if a weapon with that name already exists.

    Admin / MCP-superuser only.
    """
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    settings_obj = SiteSettings.load()
    weapons = list(settings_obj.get_weapons())

    if request.method == "GET":
        return JsonResponse({"count": len(weapons), "weapons": weapons})

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "'name' is required."}, status=400)
    cat = (body.get("category") or "").strip().lower()
    if cat not in ("melee", "improvised", "firearm", "thrown"):
        return JsonResponse({
            "error": "'category' must be one of: melee, improvised, firearm, thrown.",
        }, status=400)
    if any((w.get("name") or "").lower() == name.lower() for w in weapons):
        return JsonResponse({
            "error": f"A weapon named '{name}' already exists. Use PUT on the detail URL to update.",
        }, status=409)

    new_w = {
        "name": name[:80],
        "category": cat,
        "damage": (body.get("damage") or "").strip()[:48],
        "range": (body.get("range") or "").strip()[:48],
        "capacity": (body.get("capacity") or "").strip()[:48],
        "notes": (body.get("notes") or "").strip()[:240],
    }
    # v0.15.14 — only firearms persist the auto_capable flag. The MCP
    # client may send the field for non-firearms; we silently ignore
    # it there to keep the schema clean.
    # v0.15.15 — same treatment for the ``magazine`` field. Firearm-
    # only, coerced to a non-negative int, capped at 999. Non-firearm
    # POSTs that include the field have it silently dropped.
    if cat == "firearm":
        new_w["auto_capable"] = bool(body.get("auto_capable", False))
        try:
            mag_val = int(body.get("magazine", 0) or 0)
        except (TypeError, ValueError):
            mag_val = 0
        if mag_val < 0:
            mag_val = 0
        if mag_val > 999:
            mag_val = 999
        new_w["magazine"] = mag_val
        # v0.15.19 — X-again threshold (firearms only). Defaults to 10
        # if the field is absent; ``_clamp_again`` enforces the {8,9,10}
        # set. MCP / API clients sending the field for non-firearms
        # have it silently dropped, mirroring auto_capable / magazine.
        new_w["again"] = _clamp_again(body.get("again", 10))
        # v0.15.26 — knockdown_capable flag (firearms only). True on
        # shotgun-class weapons by default seed; arbitrary firearms
        # opt-in via this flag. Bool coercion mirrors auto_capable.
        new_w["knockdown_capable"] = bool(body.get("knockdown_capable", False))
        # v0.15.33 — close_range_penalty (firearms only). Signed int
        # clamped ±10 via ``_clamp_close_range_penalty``; bad / missing
        # input collapses to 0 (default no-penalty). Mirrors the
        # ``again`` field's silent-drop behaviour for non-firearm POSTs.
        new_w["close_range_penalty"] = _clamp_close_range_penalty(
            body.get("close_range_penalty", 0)
        )
    weapons.append(new_w)
    settings_obj.weapons = weapons
    settings_obj.save(update_fields=["weapons"])
    return JsonResponse(new_w, status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_weapon_detail(request, name):
    """Get / update / delete a single weapon by its (case-insensitive) name.

    PUT body is partial — only the fields you include are changed.
    Allowed fields: ``name`` (rename), ``category``, ``damage``,
    ``range``, ``capacity``, ``notes``, ``auto_capable`` (firearm only,
    v0.15.14), ``magazine`` (firearm only, v0.15.15), ``again`` (firearm
    only, v0.15.19; one of 8 / 9 / 10), ``knockdown_capable`` (firearm
    only, v0.15.26), ``close_range_penalty`` (firearm only, v0.15.33;
    signed int clamped ±10).

    Admin / MCP-superuser only.
    """
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    settings_obj = SiteSettings.load()
    weapons = list(settings_obj.get_weapons())

    idx = next(
        (i for i, w in enumerate(weapons)
         if (w.get("name") or "").lower() == name.lower()),
        None,
    )
    if idx is None:
        return JsonResponse({"error": f"Weapon '{name}' not found."}, status=404)

    if request.method == "GET":
        return JsonResponse(weapons[idx])

    if request.method == "DELETE":
        removed = weapons.pop(idx)
        settings_obj.weapons = weapons
        settings_obj.save(update_fields=["weapons"])
        return JsonResponse({"deleted": removed})

    # PUT
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    w = dict(weapons[idx])
    if "name" in body:
        new_name = (body["name"] or "").strip()
        if new_name:
            # Block rename collision against another existing weapon.
            if any(
                i != idx and (other.get("name") or "").lower() == new_name.lower()
                for i, other in enumerate(weapons)
            ):
                return JsonResponse({
                    "error": f"A weapon named '{new_name}' already exists.",
                }, status=409)
            w["name"] = new_name[:80]
    if "category" in body:
        cat = (body["category"] or "").strip().lower()
        if cat in ("melee", "improvised", "firearm", "thrown"):
            w["category"] = cat
    for field in ("damage", "range", "capacity"):
        if field in body:
            w[field] = (body[field] or "").strip()[:48]
    if "notes" in body:
        w["notes"] = (body["notes"] or "").strip()[:240]
    # v0.15.14 — auto_capable flag (firearms only). Sent as a bool;
    # non-firearm rows silently drop the field on PUT.
    if "auto_capable" in body and w.get("category") == "firearm":
        w["auto_capable"] = bool(body["auto_capable"])
    # v0.15.15 — magazine size (firearms only). Coerced to a non-
    # negative int and capped at 999, mirroring the form-editor and
    # POST-create code paths. Silently dropped on non-firearm PUTs.
    if "magazine" in body and w.get("category") == "firearm":
        try:
            mag_val = int(body["magazine"] or 0)
        except (TypeError, ValueError):
            mag_val = 0
        if mag_val < 0:
            mag_val = 0
        if mag_val > 999:
            mag_val = 999
        w["magazine"] = mag_val
    # v0.15.19 — X-again threshold (firearms only). ``_clamp_again``
    # enforces the {8, 9, 10} set; bad / missing input collapses to 10.
    # Silently dropped on non-firearm PUTs to keep the schema clean.
    if "again" in body and w.get("category") == "firearm":
        w["again"] = _clamp_again(body["again"])
    # v0.15.26 — knockdown_capable (firearms only). Sent as a bool.
    # Non-firearm rows silently drop the field on PUT, mirroring the
    # auto_capable / magazine / again gating.
    if "knockdown_capable" in body and w.get("category") == "firearm":
        w["knockdown_capable"] = bool(body["knockdown_capable"])
    # v0.15.33 — close_range_penalty (firearms only). Signed int clamped
    # ±10 via ``_clamp_close_range_penalty``; bad input collapses to 0.
    # Silently dropped on non-firearm PUTs to keep the schema clean.
    if "close_range_penalty" in body and w.get("category") == "firearm":
        w["close_range_penalty"] = _clamp_close_range_penalty(
            body["close_range_penalty"]
        )
    weapons[idx] = w
    settings_obj.weapons = weapons
    settings_obj.save(update_fields=["weapons"])
    return JsonResponse(w)


@login_required
def combat_page(request):
    """RULES → COMBAT — quick reference for WoD 2.0 personal combat,
    plus the live weapons catalogue (rendered as a per-category table)."""
    settings_obj = SiteSettings.load()
    weapons_by_cat = {
        "melee": [], "improvised": [], "firearm": [],
        "thrown": [], "grenade": [],
    }
    for w in settings_obj.get_weapons():
        if isinstance(w, dict) and w.get("category") in weapons_by_cat:
            weapons_by_cat[w["category"]].append(w)
    sections = [
        {"cat": "melee", "label": "MELEE",
         "hint": "Strength + Brawl / Weaponry",
         "rows": weapons_by_cat["melee"]},
        {"cat": "improvised", "label": "IMPROVISED",
         "hint": "Strength + Brawl · −1 weapon mod · breaks on hit",
         "rows": weapons_by_cat["improvised"]},
        {"cat": "firearm", "label": "FIREARM",
         "hint": "Dexterity + Firearms · range bands per weapon",
         "rows": weapons_by_cat["firearm"]},
        {"cat": "thrown", "label": "THROWN",
         "hint": "Dexterity + Athletics · Strength × range",
         "rows": weapons_by_cat["thrown"]},
        # v0.15.29 — grenade catalogue.
        {"cat": "grenade", "label": "GRENADE",
         "hint": "Dexterity + Athletics · AOE · effect tags",
         "rows": weapons_by_cat["grenade"]},
    ]

    armor_by_cat = {"light": [], "medium": [], "heavy": [], "vacuum": []}
    for a in settings_obj.get_armor():
        if isinstance(a, dict) and a.get("category") in armor_by_cat:
            armor_by_cat[a["category"]].append(a)
    armor_sections = [
        {"cat": "light", "label": "LIGHT",
         "hint": "Concealable. Minimal penalty.",
         "rows": armor_by_cat["light"]},
        {"cat": "medium", "label": "MEDIUM",
         "hint": "Visible. Moderate protection.",
         "rows": armor_by_cat["medium"]},
        {"cat": "heavy", "label": "HEAVY",
         "hint": "Full ballistic / plate. Significant penalty.",
         "rows": armor_by_cat["heavy"]},
        {"cat": "vacuum", "label": "VACUUM",
         "hint": "Sealed. Includes life support.",
         "rows": armor_by_cat["vacuum"]},
    ]

    cover_by_tier = {"light": [], "heavy": [], "full": []}
    for c in settings_obj.get_cover():
        if isinstance(c, dict) and c.get("tier") in cover_by_tier:
            cover_by_tier[c["tier"]].append(c)
    combat_cover_sections = [
        {"tier": "light", "label": "LIGHT", "penalty": "−2",
         "rows": cover_by_tier["light"]},
        {"tier": "heavy", "label": "HEAVY", "penalty": "−4",
         "rows": cover_by_tier["heavy"]},
        {"tier": "full", "label": "FULL", "penalty": "cannot target",
         "rows": cover_by_tier["full"]},
    ]

    # Combat NPC templates — pre-grouped by category for the dynamic
    # STOCK ADVERSARIES section on /rules/combat/.
    combat_npcs_by_cat = {
        "guard": [], "razor": [], "corp": [], "cultist": [], "drone": [],
    }
    for n in settings_obj.get_combat_npcs():
        if isinstance(n, dict) and n.get("category") in combat_npcs_by_cat:
            combat_npcs_by_cat[n["category"]].append(n)
    combat_npc_sections = [
        {"cat": "guard", "label": "GUARD",
         "hint": "Untrained civilian / building security",
         "rows": combat_npcs_by_cat["guard"]},
        {"cat": "razor", "label": "RAZOR",
         "hint": "Street fighters and mercs",
         "rows": combat_npcs_by_cat["razor"]},
        {"cat": "corp", "label": "CORPORATE",
         "hint": "Trained corporate security ladder",
         "rows": combat_npcs_by_cat["corp"]},
        {"cat": "cultist", "label": "CULTIST",
         "hint": "Zealous fighters · no morale",
         "rows": combat_npcs_by_cat["cultist"]},
        {"cat": "drone", "label": "DRONE / NON-HUMAN",
         "hint": "Autonomous machines & attack animals · cannot be intimidated",
         "rows": combat_npcs_by_cat["drone"]},
    ]

    return render(request, "combat.html", {
        "weapons_by_cat": weapons_by_cat,
        "combat_weapon_sections": sections,
        "armor_by_cat": armor_by_cat,
        "combat_armor_sections": armor_sections,
        "cover_by_tier": cover_by_tier,
        "combat_cover_sections": combat_cover_sections,
        "combat_npcs_by_cat": combat_npcs_by_cat,
        "combat_npc_sections": combat_npc_sections,
    })


@login_required
def pulling_strings_page(request):
    """Pulling strings catalog page. Staff can edit, players can view."""
    # Get player's character class for filtering
    char_class = ""
    if not request.user.is_superuser:
        from characters.models import Character
        char = Character.objects.filter(owner=request.user).first()
        if char:
            char_class = char.character_class
    return render(request, "pulling_strings_manage.html", {
        "is_admin": request.user.is_superuser,
        "character_class": char_class,
    })


@login_required
def merits_page(request):
    """Merit catalog page. Staff can edit, players can view."""
    char_class = ""
    if not request.user.is_superuser:
        from characters.models import Character
        char = Character.objects.filter(owner=request.user).first()
        if char:
            char_class = char.character_class
    return render(request, "merits_manage.html", {
        "is_admin": request.user.is_superuser,
        "character_class": char_class,
    })


@login_required
@require_GET
def api_status(request):
    """Return game state overview: version, game date, entity counts."""
    from agencies.models import Agency, CouncilItem, GlobalFlaw, FTLProject
    from characters.models import Character
    from comms.models import Thread
    from django.contrib.auth.models import User
    from npcs.models import NPC

    settings_obj = SiteSettings.load()
    version_file = Path(__file__).resolve().parent.parent / "version.txt"
    version = version_file.read_text().strip() if version_file.exists() else "unknown"

    return JsonResponse({
        "appVersion": version,
        "nextGameDate": str(settings_obj.next_game_date) if settings_obj.next_game_date else None,
        "charterTextLength": len(settings_obj.charter_text or ""),
        "counts": {
            "users": User.objects.count(),
            "characters": Character.objects.count(),
            "playerAgencies": Agency.objects.filter(is_player_agency=True).count(),
            "npcAgencies": Agency.objects.filter(is_player_agency=False).count(),
            "npcs": NPC.objects.count(),
            "activeNpcs": NPC.objects.filter(state="active").count(),
            "councilItems": CouncilItem.objects.count(),
            "votingItems": CouncilItem.objects.filter(status="voting").count(),
            "globalFlaws": GlobalFlaw.objects.count(),
            "ftlProjects": FTLProject.objects.count(),
            "threads": Thread.objects.count(),
            "pullingStrings": PullingString.objects.count(),
        },
    })


# ---------------------------------------------------------------------------
# Pulling Strings catalog API
# ---------------------------------------------------------------------------

def _serialize_ps(ps):
    """Serialize a PullingString catalog entry."""
    return {
        "id": ps.id,
        "name": ps.name,
        "description": ps.description,
        "cost": ps.cost,
        "category": ps.category,
        "isLinkable": ps.is_linkable,
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_pulling_strings(request):
    """GET: list all pulling strings. POST: create (admin only)."""
    if request.method == "GET":
        qs = PullingString.objects.all()
        # Non-superusers cannot see AI-category pulling strings
        if not request.user.is_superuser:
            qs = qs.exclude(category="ai")
        return JsonResponse([_serialize_ps(ps) for ps in qs], safe=False)

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    valid_categories = [c[0] for c in PullingString.CATEGORY_CHOICES]
    category = data.get("category", "general")
    if category not in valid_categories:
        return JsonResponse({"error": f"Invalid category. Use: {valid_categories}"}, status=400)

    ps = PullingString.objects.create(
        name=data.get("name", ""),
        description=data.get("description", ""),
        cost=data.get("cost", 0),
        category=category,
        is_linkable=bool(data.get("isLinkable", False)),
    )
    return JsonResponse(_serialize_ps(ps), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_pulling_string_detail(request, pk):
    """GET: single pulling string. PUT/DELETE: admin only."""
    from django.shortcuts import get_object_or_404
    ps = get_object_or_404(PullingString, pk=pk)

    if request.method == "GET":
        if ps.category == "ai" and not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED."}, status=403)
        return JsonResponse(_serialize_ps(ps))

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        for field in ("name", "description"):
            if field in data:
                setattr(ps, field, data[field])
        if "cost" in data:
            ps.cost = data["cost"]
        if "category" in data:
            valid_categories = [c[0] for c in PullingString.CATEGORY_CHOICES]
            if data["category"] in valid_categories:
                ps.category = data["category"]
        if "isLinkable" in data:
            ps.is_linkable = bool(data["isLinkable"])
        ps.save()
        return JsonResponse(_serialize_ps(ps))

    if request.method == "DELETE":
        ps.delete()
        return JsonResponse({"status": "Record terminated."})


# ---------------------------------------------------------------------------
# Merits catalog API
# ---------------------------------------------------------------------------

def _serialize_merit(m):
    """Serialize a MeritDefinition catalog entry."""
    return {
        "id": m.id,
        "name": m.name,
        "description": m.description,
        "cost": m.cost,
        "minCost": m.min_cost,
        "category": m.category,
        "classRestriction": m.class_restriction,
        "prerequisites": m.prerequisites,
        "effects": m.effects,
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_merits(request):
    """GET: list all merit definitions. POST: create (admin only)."""
    if request.method == "GET":
        return JsonResponse(
            [_serialize_merit(m) for m in MeritDefinition.objects.all()],
            safe=False,
        )

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    valid_categories = [c[0] for c in MeritDefinition.CATEGORY_CHOICES]
    category = data.get("category", "physical")
    if category not in valid_categories:
        return JsonResponse(
            {"error": f"Invalid category. Use: {valid_categories}"}, status=400
        )

    cost = data.get("cost", 1)
    min_cost = data.get("minCost", cost)

    m = MeritDefinition.objects.create(
        name=data.get("name", ""),
        description=data.get("description", ""),
        cost=cost,
        min_cost=min_cost,
        category=category,
        class_restriction=data.get("classRestriction", ""),
        prerequisites=data.get("prerequisites", ""),
        effects=data.get("effects", {}),
    )
    return JsonResponse(_serialize_merit(m), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_merit_detail(request, pk):
    """GET: single merit. PUT/DELETE: admin only."""
    from django.shortcuts import get_object_or_404

    m = get_object_or_404(MeritDefinition, pk=pk)

    if request.method == "GET":
        return JsonResponse(_serialize_merit(m))

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        for field in ("name", "description", "prerequisites"):
            if field in data:
                setattr(m, field, data[field])
        if "cost" in data:
            m.cost = data["cost"]
        if "minCost" in data:
            m.min_cost = data["minCost"]
        if "category" in data:
            valid_categories = [c[0] for c in MeritDefinition.CATEGORY_CHOICES]
            if data["category"] in valid_categories:
                m.category = data["category"]
        if "classRestriction" in data:
            m.class_restriction = data["classRestriction"]
        if "effects" in data:
            m.effects = data["effects"]
        m.save()
        return JsonResponse(_serialize_merit(m))

    if request.method == "DELETE":
        m.delete()
        return JsonResponse({"status": "Record terminated."})
