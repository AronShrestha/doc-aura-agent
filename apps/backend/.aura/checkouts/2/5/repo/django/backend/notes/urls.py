from django.urls import path 
from .views import *

urlpatterns =[
    path('',ListNotes.as_view()),
    path('<int:pk>/',DetailNotes.as_view()),
    path('own/', ListUserNotes.as_view()),
    path('create/',UploadView.as_view(),name='Upload Files')
]
 