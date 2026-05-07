from .models import Notice
from .serializers import NoticeSerializer, NoticeCreateSerializer

from user.models import User
from subject.models import ClassCode
from user.views import UseJWTAuthentication

from rest_framework import generics
from rest_framework import permissions

def filterNotice(user, size = None):
    if user.is_student:
        print('is a student')
        faculty = user.faculty
        batch = user.student.batch

        classcode = ClassCode.objects.get(faculty=faculty, batch=batch)
        print(classcode)
        objects = Notice.objects.filter(classcode=classcode)
        # objects = Notice.objects.filter(classcode="CS18")
    elif user.is_teacher:
        objects = Notice.objects.filter(author=user)

        # classcode = self.request.query_params.get('classcode')
        # if classcode is not None:
        #     classcode = ClassCode.objects.get(faculty=faculty, batch=batch)
        #     objects = objects.filter(classcode=classcode)
    
    objects = objects[::-1]

    if size:
        objects = objects[:size]

    return objects


class LatestNotice(generics.ListAPIView):
    serializer_class = NoticeSerializer
    permission_class = [permissions.IsAuthenticated, ]
    authentication_class = UseJWTAuthentication

    def get_queryset(self):
        user = self.request.user

        return filterNotice(user, 3)

class NoticeList(generics.ListAPIView):
    serializer_class = NoticeSerializer
    permission_class = [permissions.IsAuthenticated, ]
    authentication_class = UseJWTAuthentication

    def get_queryset(self):
        ''' filtering objects with respect to user and query parameters '''

        user = self.request.user

        objects = filterNotice(user)
        # if user.is_authenticated:
        #     # user = User.objects.first()        
        subject = self.request.query_params.get('subject')

        # if subject is not None:
        #     objects = objects.filter(subj_code = subject)
            
        return objects
        

class NoticeCreate(generics.CreateAPIView):
    serializer_class = NoticeCreateSerializer
    permission_class = [permissions.IsAuthenticated, ]
    authentication_class = UseJWTAuthentication
    print("I n Notice")
        
class NoticeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Notice.objects.all()
    serializer_class = NoticeSerializer




# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from rest_framework.parsers import JSONParser
# from rest_framework import status


# # Create your views here.

# @api_view(['GET', 'POST'])
# def notice_list(request):
#     if request.method == 'GET':
#         notices = Notice.objects.all()
#         s = NoticeSerializer(notices, many=True)
#         return Response(s.data)
    
#     elif request.method == 'POST':
#         # data = JSONParser.parse(request)

#         s = NoticeSerializer(data = request.data)
#         if s.is_valid():
#             print(s.validated_data)
#             s.save()
#             return Response(s.data, status.HTTP_201_CREATED)
#         return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

# @api_view(['GET', 'PATCH', 'DELETE'])
# def notice_detail(request, pk):
#     try:
#         n = Notice.objects.get(pk=pk)
#     except Notice.DoesNotExist:
#         return Response(status=status.HTTP_404_NOT_FOUND)
    
#     if request.method == 'GET':
#         s = NoticeSerializer(n)
#         return Response(s.data)
#     elif request.method == 'PATCH':
#         # data = JSONParser.parse(request)
#         print(request.data)
#         s = NoticeSerializer(n, data=request.data)
#         if s.is_valid():
#             s.save()
#             return Response(s.data)
#         return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
#     elif request.method == "DELETE":
#         n.delete()
#         return Response(status=status.HTTP_201_CREATED)