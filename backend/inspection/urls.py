from django.urls import path

from inspection import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.list_view, name="list"),
    path("inspections/new/", views.create_view, name="create"),
    path("inspections/<int:pk>/", views.detail_view, name="detail"),
    path("batches/new/", views.batch_create_view, name="batch_create"),
    path("batches/", views.batch_list_view, name="batch_list"),
    path("batches/attempts/", views.batch_attempts_view, name="batch_attempts"),
    path("batches/<int:pk>/", views.batch_detail_view, name="batch_detail"),
]
