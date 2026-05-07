from . import models
from subject.models import ClassCode

from user.models import User
from user.views import UseJWTAuthentication

from django.shortcuts import render
from .serializer import NotesSerializers, NotesCreateSerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response 
from rest_framework.parsers import FileUploadParser
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny


# Create your views here.
class ListNotes(generics.ListCreateAPIView):
    serializer_class =  NotesSerializers
    permission_class = [IsAuthenticated, ]
    queryset =  models.Notes.objects.all()
    # filter_backends = [DjangoFilterBackend]
    authentication_class = UseJWTAuthentication

    def get_queryset(self):
        # user = self.request.user
        user = User.objects.first()
        if user.is_student == True:
            faculty = user.faculty
            batch = user.student.batch

            classcode = ClassCode.objects.get(faculty=faculty, batch=batch)
            print(classcode)

            return models.Notes.objects.filter(classcode = classcode)[::-1]
        else:
            return models.Notes.objects.filter(author=user)[::-1]
     
    # filterset_fields = ['title']
    # def get_queryset(self):
    #     if self.request.user == "student" :
    #         dataFiltered = models.Notes.objects.filter(classcode='xyz')
    #         #having 1 classcode we get access to all the subjects in the classs so we be getting notes of all subjects futher on this later 


    #         return dataFiltered
    
class ListUserNotes(generics.ListAPIView):
    serializer_class = NotesSerializers
    permission_classes = [IsAuthenticated, ]
    
    def get_queryset(self):
        print(self.request.GET["id"])
        id = self.request.GET["id"]
        return models.Notes.objects.filter(author__id= id)



class DetailNotes(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = NotesSerializers
    queryset =  models.Notes.objects.all()


class UploadView(generics.CreateAPIView):
    authentiation_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = NotesCreateSerializer
