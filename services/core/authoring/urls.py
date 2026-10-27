from django.urls import path

from . import views

S = "authoring/<str:session_id>"

urlpatterns = [
    path("authoring", views.AuthoringListCreateView.as_view(), name="authoring-list"),
    path(S, views.AuthoringDetailView.as_view(), name="authoring-detail"),
    path(S + "/decision", views.AuthoringDecisionView.as_view(), name="authoring-decision"),
    path(S + "/cancel", views.AuthoringCancelView.as_view(), name="authoring-cancel"),
    path(S + "/events", views.authoring_events, name="authoring-events"),
]
