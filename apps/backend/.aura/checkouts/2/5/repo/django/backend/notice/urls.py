from django.urls import path
from .views import NoticeCreate, NoticeDetail, NoticeList, LatestNotice

urlpatterns = [
    path('', NoticeList.as_view(), name="Notices"),
    path('latest/', LatestNotice.as_view(), name="Latest notices"),
    path('create/', NoticeCreate.as_view(), name="Create Notice"),
    path('<int:pk>/', NoticeDetail.as_view(), name="Notice Detail"),
]