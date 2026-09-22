from django.urls import path

from inspection import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.list_view, name="list"),
    path("inspections/new/", views.create_view, name="create"),
    path("inspections/<int:pk>/", views.detail_view, name="detail"),
    path("batch/new/", views.batch_create_view, name="batch_create"),
    path("batch/tickets/", views.tickets_view, name="tickets"),
    path("batch/failed/", views.failed_attempts_view, name="failed_attempts"),
    path("batch/<str:ticket>/", views.ticket_view, name="ticket"),
]
