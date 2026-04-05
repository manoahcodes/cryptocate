"""
Accounts app URL patterns.
Reference: https://docs.djangoproject.com/en/5.2/topics/http/views/
"""

from django.urls import path

from .views import DashboardView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="account_register_ww"),
    path("dashboard/", DashboardView.as_view(), name="account_dashboard"),
]
