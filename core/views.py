from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect


def register(request):
    """Register a new user and log them in."""
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("portfolios:portfolio-list")
    else:
        form = UserCreationForm()
    return render(request, "registration/register.html", {"form": form})