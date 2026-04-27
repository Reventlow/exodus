"""Views for the personal combat app.

Phase 0: two GM-only placeholder pages so the URL conf resolves and
the route table is populated. Phase 1 introduces participant-aware
permissions and the real list / detail UI.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render


@login_required
def encounter_list_page(request):
    """Phase 0 placeholder. GM-only."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("ACCESS DENIED.")
    return render(request, "combat/list.html", {})


@login_required
def encounter_page(request, pk):
    """Phase 0 placeholder. GM-only."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("ACCESS DENIED.")
    return render(request, "combat/encounter.html", {"encounter_id": pk})
