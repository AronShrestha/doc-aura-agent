from django.urls import path
from user.views import RegisterAPI, LoginAPI, UserAPI, StudentAPI, TeacherAPI, RegisterPhotoAPI
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
    path('register/', RegisterAPI.as_view(), name='register'),
    path('upload_photo/<int:id>', RegisterPhotoAPI.as_view(), name = 'upload photo'),
    path('login/', LoginAPI.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('user/<int:id>', UserAPI.as_view(), name='homepage'),
    path('student/<int:user>/', StudentAPI.as_view(), name='student homepage'),
    path('teacher/<int:user>', TeacherAPI.as_view(), name='teacher homepage'),
]