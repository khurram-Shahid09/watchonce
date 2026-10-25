from django.urls import path

from . import views

R = "runs/<str:run_id>"

urlpatterns = [
    path(
        "workflows/<str:workflow_id>/runs", views.WorkflowRunsView.as_view(), name="workflow-runs"
    ),
    path("runs", views.RunListView.as_view(), name="run-list"),
    path(R, views.RunDetailView.as_view(), name="run-detail"),
    path(R + "/cancel", views.RunCancelView.as_view(), name="run-cancel"),
    path(
        R + "/checkpoints/<str:step_id>",
        views.CheckpointDecisionView.as_view(),
        name="run-checkpoint",
    ),
    path(R + "/screenshots/<str:name>", views.RunScreenshotView.as_view(), name="run-screenshot"),
    path(R + "/events", views.run_events, name="run-events"),
    path("heals", views.HealListView.as_view(), name="heal-list"),
    path("heals/<str:heal_id>", views.HealDetailView.as_view(), name="heal-detail"),
    path("heals/<str:heal_id>/decision", views.HealDecisionView.as_view(), name="heal-decision"),
]
