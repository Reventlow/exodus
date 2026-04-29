"""Test data factories for the combat test suite.

These are intentionally minimal Python helpers — not pytest fixtures,
not factory_boy / model-bakery — to keep the v0.15.35 test infrastructure
free of new dependencies. Each helper builds a single ORM row with
sensible defaults and lets the caller override anything they care about
via ``**kwargs``.

Helpers:

* :func:`make_user`        — auth user (player or GM via ``is_superuser``)
* :func:`make_character`   — :class:`characters.Character` with WoD 2.0
                              attribute / skill defaults
* :func:`make_npc`         — :class:`npcs.NPC` mirror of make_character
* :func:`make_encounter`   — :class:`combat.Encounter` (defaults to
                              ``setup`` status, visible)
* :func:`make_participant` — :class:`combat.Participant` (kind =
                              character / npc / mook)
* :func:`make_merit`       — :class:`exodus.MeritDefinition` row
* :func:`attach_merit`     — wire a merit to a Character/NPC at ``rating``
"""

from django.contrib.auth.models import User

from characters.models import Character, CharacterMerit
from combat.models import Encounter, Participant
from exodus.models import MeritDefinition
from npcs.models import NPC, NpcMerit


_USER_COUNTER = {"n": 0}


def _next_username(prefix):
    """Return a unique username so tests in the same TestCase don't clash.

    Django's ``TestCase`` wraps each method in a transaction that's
    rolled back at teardown, so the counter resets per process — the
    monotonic increment is just a defensive uniqueness aid.
    """
    _USER_COUNTER["n"] += 1
    return f"{prefix}{_USER_COUNTER['n']}"


def make_user(username=None, is_superuser=False, **kwargs):
    """Return a saved :class:`auth.User`.

    ``username`` is auto-generated when omitted (e.g. ``"gm17"``,
    ``"player18"``) so callers don't have to coordinate names across
    setup blocks. ``is_superuser=True`` also sets ``is_staff`` so the
    user passes both flags the GM-only views check.
    """
    if username is None:
        username = _next_username("gm" if is_superuser else "player")
    return User.objects.create_user(
        username=username,
        password=kwargs.pop("password", "x"),
        is_superuser=is_superuser,
        is_staff=is_superuser or kwargs.pop("is_staff", False),
        **kwargs,
    )


def _attrs(power=2, finesse=2, resistance=2):
    """Return a WoD 2.0 attributes dict with all nine values set.

    Two dots across the board is enough to drive the attack pool / wound
    penalty / initiative math without zeroing anything out. Callers
    that need a specific tier override can pass kwargs after creating
    the character (``character.attributes["power"]["physical"] = 4``).
    """
    return {
        "power":      {"mental": power, "physical": power, "social": power},
        "finesse":    {"mental": finesse, "physical": finesse, "social": finesse},
        "resistance": {"mental": resistance, "physical": resistance, "social": resistance},
    }


def _skills(brawl=2, firearms=2, athletics=2, weaponry=2):
    """Return a WoD 2.0 skills dict with the combat-relevant values set.

    All other skills default to 0 so the resolver's tier cascade
    (physical → mental → social) lands deterministically on physical.
    """
    return {
        "mental": {
            "Academics": 0, "Computer": 0, "Crafts": 0, "Investigation": 0,
            "Medicine": 0, "Occult": 0, "Politics": 0, "Science": 0,
        },
        "physical": {
            "Athletics": athletics, "Brawl": brawl, "Drive": 0,
            "Firearms": firearms, "Larceny": 0, "Stealth": 0,
            "Survival": 0, "Weaponry": weaponry,
        },
        "social": {
            "AnimalKen": 0, "Empathy": 0, "Expression": 0, "Intimidation": 0,
            "Persuasion": 0, "Socialize": 0, "Streetwise": 0, "Subterfuge": 0,
        },
    }


def make_character(owner, name="Test Char", character_class="soldier", **kwargs):
    """Return a saved :class:`characters.Character`.

    Defaults give the character ``size=5`` (WoD 2.0 human baseline) and
    enough attributes / skills to roll an attack pool. ``owner`` is the
    auth user the character belongs to — ownership-gated views use the
    FK chain ``Character.owner_id == request.user.id``.
    """
    defaults = dict(
        owner=owner,
        name=name,
        character_class=character_class,
        size=5,
        attributes=_attrs(),
        skills=_skills(),
    )
    defaults.update(kwargs)
    return Character.objects.create(**defaults)


def make_npc(name="Test NPC", character_class="soldier", **kwargs):
    """Return a saved :class:`npcs.NPC`.

    Same shape as :func:`make_character` minus the owner FK (NPCs are
    GM-only, no owner). Defaults to a non-dossier, non-hidden,
    ``active`` state row so it surfaces in catalogue queries.
    """
    defaults = dict(
        name=name,
        character_class=character_class,
        size=5,
        attributes=_attrs(),
        skills=_skills(),
    )
    defaults.update(kwargs)
    return NPC.objects.create(**defaults)


def make_encounter(gm=None, status="setup", is_hidden=False,
                   round_number=0, title="Test Encounter", **kwargs):
    """Return a saved :class:`combat.Encounter`.

    Defaults to a published (``is_hidden=False``) setup-phase encounter.
    Pass ``status="active"`` + ``round_number=1`` to skip the lifecycle
    transition for tests that want to drive a mid-fight branch directly.
    """
    defaults = dict(
        title=title,
        status=status,
        round_number=round_number,
        gm=gm,
        is_hidden=is_hidden,
    )
    defaults.update(kwargs)
    return Encounter.objects.create(**defaults)


def make_participant(encounter, character=None, npc=None, name="P",
                     kind="character", **kwargs):
    """Return a saved :class:`combat.Participant`.

    Auto-fills the ``character``/``npc`` FK based on ``kind``. Mooks
    require ``mook_combat_pool`` (passed via ``**kwargs``); the helper
    defaults it to 5 so a kind="mook" call without that kwarg still
    yields a valid row.
    """
    defaults = dict(
        encounter=encounter,
        participant_kind=kind,
        name=name,
        faction=kwargs.pop("faction", "hostile"),
        health_max=kwargs.pop("health_max", 7),
    )
    if kind == "character":
        defaults["character"] = character
    elif kind == "npc":
        defaults["npc"] = npc
    elif kind == "mook":
        defaults["mook_combat_pool"] = kwargs.pop("mook_combat_pool", 5)
        defaults["mook_defense"] = kwargs.pop("mook_defense", 2)
    defaults.update(kwargs)
    return Participant.objects.create(**defaults)


def make_merit(name, category="physical", min_cost=1, cost=5, **kwargs):
    """Return a saved :class:`exodus.MeritDefinition`.

    Variable-rating merits use ``min_cost=1, cost=5``; fixed-cost merits
    pass ``min_cost == cost``. Used by tests that exercise wound-penalty
    overrides (Pain Tolerance / Increased Pain Threshold) and Gun Fu.
    """
    defaults = dict(
        name=name, category=category, min_cost=min_cost, cost=cost,
    )
    defaults.update(kwargs)
    return MeritDefinition.objects.create(**defaults)


def attach_merit(target, merit, rating=1):
    """Wire ``merit`` to a Character or NPC via the through-row.

    Auto-detects which through-table to use by introspecting ``target``.
    Returns the freshly-created :class:`CharacterMerit` /
    :class:`NpcMerit` row so callers can mutate ``rating`` later.
    """
    if isinstance(target, Character):
        return CharacterMerit.objects.create(
            character=target, merit=merit, rating=rating,
        )
    if isinstance(target, NPC):
        return NpcMerit.objects.create(npc=target, merit=merit, rating=rating)
    raise TypeError(f"attach_merit: unsupported target type {type(target)}")
