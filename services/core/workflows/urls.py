from django.urls import path

from . import views

W = "workflows/<str:workflow_id>"
V = W + "/versions/<int:version>"

urlpatterns = [
    path("workflows", views.WorkflowListView.as_view(), name="workflow-list"),
    path(W, views.WorkflowDetailView.as_view(), name="workflow-detail"),
    path(W + "/versions", views.VersionListView.as_view(), name="version-list"),
    path(V, views.VersionDetailView.as_view(), name="version-detail"),
    path(V + "/activate", views.VersionActivateView.as_view(), name="version-activate"),
    path(V + "/sop", views.VersionSopView.as_view(), name="version-sop"),
    path(
        W + "/screenshots/<path:name>", views.ScreenshotView.as_view(), name="workflow-screenshot"
    ),
]
