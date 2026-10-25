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
    path(
        "workflows/<str:workflow_id>/batches",
        views.WorkflowBatchesView.as_view(),
        name="workflow-batches",
    ),
    path("batches/<str:batch_id>", views.BatchDetailView.as_view(), name="batch-detail"),
    path(
        "batches/<str:batch_id>/results.csv", views.BatchResultsView.as_view(), name="batch-results"
    ),
    path(
        "batches/<str:batch_id>/approve-all",
        views.BatchApproveAllView.as_view(),
        name="batch-approve-all",
    ),
    path("batches/<str:batch_id>/cancel", views.BatchCancelView.as_view(), name="batch-cancel"),
    path("heals/<str:heal_id>", views.HealDetailView.as_view(), name="heal-detail"),
    path("heals/<str:heal_id>/decision", views.HealDecisionView.as_view(), name="heal-decision"),
]
