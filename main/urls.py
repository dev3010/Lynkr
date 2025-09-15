from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("shorten", views.shorten_post, name="shorten_post"),
    path("shorten/<str:url>", views.shorten, name="shorten"),
    path("<str:url_hash>", views.redirect_hash, name="redirect"),
    path("stats/<str:url_hash>/", views.stats, name="stats"),
    path("deactivate/<str:url_hash>/", views.deactivate_link, name="deactivate_link"),
    path("activate/<str:url_hash>/", views.activate_link, name="activate_link"),
]
