from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    AnnouncementTypePreferenceForm,
    CompanyPreferenceForm,
    WatchlistCompanyForm,
    WatchlistForm,
)
from .models import AnnouncementType, Company, Watchlist
from .services import (
    get_user_companies,
    get_user_feed,
    get_user_watchlists,
)


@login_required
def feed(request):
    user = request.user
    search = request.GET.get("q") or ""
    watchlist_id = request.GET.get("watchlist")
    watchlist_id = int(watchlist_id) if watchlist_id and watchlist_id.isdigit() else None
    type_code = request.GET.get("type") or ""
    company_id = request.GET.get("company")
    company_id = int(company_id) if company_id and company_id.isdigit() else None

    announcements = get_user_feed(
        user,
        search=search,
        watchlist_id=watchlist_id,
        announcement_type_code=type_code or None,
        company_id=company_id,
    )
    paginator = Paginator(announcements, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    watchlists = get_user_watchlists(user)
    companies = get_user_companies(user, watchlist_id=watchlist_id)
    announcement_types = AnnouncementType.objects.order_by("label")

    context = {
        "page_obj": page_obj,
        "announcements": page_obj.object_list,
        "search": search,
        "watchlists": watchlists,
        "announcement_types": announcement_types,
        "companies": companies,
        "selected_watchlist": watchlist_id,
        "selected_type": type_code,
        "selected_company": company_id,
    }
    return render(request, "announcements/feed.html", context)


@login_required
def watchlist_index(request):
    watchlists = (
        Watchlist.objects.filter(user=request.user)
        .prefetch_related("entries__company")
        .order_by("name")
    )
    create_form = WatchlistForm()
    return render(
        request,
        "announcements/watchlists.html",
        {"watchlists": watchlists, "create_form": create_form},
    )


@login_required
@require_POST
def watchlist_create(request):
    form = WatchlistForm(request.POST)
    if form.is_valid():
        watchlist = form.save(commit=False)
        watchlist.user = request.user
        watchlist.save()
        messages.success(request, "Watchlist created.")
    else:
        messages.error(request, "Could not create watchlist. Please fix the errors.")
    return redirect("announcements:watchlist-index")


@login_required
def watchlist_detail(request, pk: int):
    watchlist = get_object_or_404(Watchlist, pk=pk, user=request.user)
    form = WatchlistCompanyForm()
    if request.method == "POST":
        form = WatchlistCompanyForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                company = form.save(user=request.user, watchlist=watchlist)
            messages.success(
                request, f"{company.name} ({company.ticker}) added to {watchlist.name}."
            )
            return redirect("announcements:watchlist-detail", pk=watchlist.pk)
        else:
            messages.error(request, "Unable to add company. Please review the errors below.")

    entries = watchlist.entries.select_related("company").order_by("company__name")
    rename_form = WatchlistForm(instance=watchlist)
    return render(
        request,
        "announcements/watchlist_detail.html",
        {
            "watchlist": watchlist,
            "entries": entries,
            "form": form,
            "rename_form": rename_form,
        },
    )


@login_required
@require_POST
def watchlist_rename(request, pk: int):
    watchlist = get_object_or_404(Watchlist, pk=pk, user=request.user)
    form = WatchlistForm(request.POST, instance=watchlist)
    if form.is_valid():
        form.save()
        messages.success(request, "Watchlist renamed.")
    else:
        messages.error(request, "Unable to rename watchlist.")
    return redirect("announcements:watchlist-detail", pk=pk)


@login_required
@require_POST
def watchlist_delete(request, pk: int):
    watchlist = get_object_or_404(Watchlist, pk=pk, user=request.user)
    watchlist.delete()
    messages.success(request, "Watchlist deleted.")
    return redirect("announcements:watchlist-index")


@login_required
@require_POST
def watchlist_remove_company(request, pk: int, company_id: int):
    watchlist = get_object_or_404(Watchlist, pk=pk, user=request.user)
    watchlist.entries.filter(company_id=company_id).delete()
    messages.success(request, "Company removed from watchlist.")
    return redirect("announcements:watchlist-detail", pk=pk)


@login_required
def preferences(request):
    user = request.user
    form_type = request.POST.get("form_type") if request.method == "POST" else None

    if request.method == "POST" and form_type == "global":
        global_form = AnnouncementTypePreferenceForm(request.POST, user=user)
        if global_form.is_valid():
            global_form.save()
            messages.success(request, "Default announcement preferences updated.")
            return redirect("announcements:preferences")
    else:
        global_form = AnnouncementTypePreferenceForm(user=user)

    company_initial = {}
    initial_company_id = request.GET.get("company")
    if initial_company_id and initial_company_id.isdigit():
        try:
            company_initial["company"] = get_user_companies(user).get(
                pk=int(initial_company_id)
            )
        except (Company.DoesNotExist, ValueError):
            pass

    if request.method == "POST" and form_type == "company":
        company_form = CompanyPreferenceForm(request.POST, user=user)
        if company_form.is_valid():
            company = company_form.cleaned_data["company"]
            company_form.save()
            messages.success(
                request,
                f"Preferences updated for {company.name} ({company.ticker}).",
            )
            return redirect(f"{reverse('announcements:preferences')}?company={company.pk}")
    else:
        company_form = CompanyPreferenceForm(user=user, initial=company_initial)

    return render(
        request,
        "announcements/preferences.html",
        {
            "global_form": global_form,
            "company_form": company_form,
        },
    )
