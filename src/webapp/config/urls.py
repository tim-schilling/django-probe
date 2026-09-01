from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from ingest import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/submissions/", views.submissions, name="submissions"),
    path("style-guide/", views.style_guide, name="style-guide"),
    path("token/", views.token, name="token"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
]
