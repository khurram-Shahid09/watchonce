from django.urls import path

from . import views

urlpatterns = [
    path("recordings", views.RecordingListView.as_view(), name="recording-list"),
    path(
        "recordings/<str:recording_id>",
        views.RecordingDetailView.as_view(),
        name="recording-detail",
    ),
    path(
        "recordings/<str:recording_id>/complete",
        views.RecordingCompleteView.as_view(),
        name="recording-complete",
    ),
    path(
        "recordings/<str:recording_id>/compile",
        views.RecordingCompileView.as_view(),
        name="recording-compile",
    ),
    path(
        "recordings/<str:recording_id>/candidates",
        views.RecordingCandidatesView.as_view(),
        name="recording-candidates",
    ),
]
