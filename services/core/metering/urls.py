from django.urls import path

from . import views

urlpatterns = [
    path("analytics/summary", views.AnalyticsSummaryView.as_view(), name="analytics-summary"),
]
