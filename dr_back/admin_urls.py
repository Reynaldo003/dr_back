from django.urls import path

from .admin_views import AdminLoginAPIView, AdminLogoutAPIView, AdminMeAPIView

urlpatterns = [
    path("admin/auth/login/", AdminLoginAPIView.as_view(), name="admin-auth-login"),
    path("admin/auth/me/", AdminMeAPIView.as_view(), name="admin-auth-me"),
    path("admin/auth/logout/", AdminLogoutAPIView.as_view(), name="admin-auth-logout"),
]