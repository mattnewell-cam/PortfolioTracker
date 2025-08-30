from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect

from portfolios.models import Portfolio


def register(request):
    """Register a new user and log them in."""
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            Portfolio.objects.create(user=user, name="My Portfolio")
            return redirect("portfolios:portfolio-detail")
    else:
        form = UserCreationForm()
    return render(request, "registration/register.html", {"form": form})
