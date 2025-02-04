from django.urls import path
from userauths import views as userauths_views
from store import views as store_views
from api import views as users_profiles


app_name = 'api'  # Add this line to specify the app namespace


urlpatterns = [
    path('', userauths_views.getRoutes),


    #     ALL-USERS-AND-PROFILE
    path('users/profile', users_profiles.USERSPROFILELISTVIEW.as_view(), name='ALL-USERS-AND-PROFILE'),

    # Userauths API Endpoints
    path('user/profile/<str:pid>/', userauths_views.ProfileView.as_view(), name='user_profile'),
    path('user/password-reset/<email>/', userauths_views.PasswordEmailVerify.as_view(), name='password_reset'),
    path('user/password-change/', userauths_views.PasswordChangeView.as_view(), name='password_reset'),

    # Adoon Endpoint
    path('addon/', store_views.ConfigSettingsDetailView.as_view(), name='addon'),
]