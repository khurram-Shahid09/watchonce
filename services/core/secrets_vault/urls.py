from django.urls import path

from . import views

urlpatterns = [
    path("secrets", views.SecretListView.as_view(), name="secret-list"),
    path("secrets/<str:secret_id>", views.SecretDetailView.as_view(), name="secret-detail"),
]
