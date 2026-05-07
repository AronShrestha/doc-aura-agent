from rest_framework import generics, permissions, viewsets
from rest_framework.response import Response
from .models import Student, Teacher, User
from .serializers import StudentSerializer, TeacherSerializer, UserSerializer, RegisterSerializer, LoginSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


# Create your views here.
class RegisterAPI(generics.GenericAPIView):
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data = request.data)
        serializer.is_valid(raise_exception = True)
        user = serializer.save()
        return Response({
            "user": UserSerializer(user, context = self.get_serializer_context()).data,
        })

class RegisterPhotoAPI(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_class = [permissions.AllowAny]
 
    def get_object(self):
        id = self.kwargs["id"]
        return User.objects.all().filter(id=id)[0]



class LoginAPI(TokenObtainPairView):
    serializer_class = LoginSerializer


class UseJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        try:
            return super().authenticate(request=request)
        except InvalidToken:
            return None

class UserAPI(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_class = [permissions.IsAuthenticated]
    authentication_class = UseJWTAuthentication

    def get_object(self):
        id = self.kwargs["id"]
        return User.objects.all().filter(id=id)[0]

class StudentAPI(generics.RetrieveAPIView):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_class = [permissions.IsAuthenticated]
    authentication_class = UseJWTAuthentication
    lookup_field = 'user'


class TeacherAPI(generics.RetrieveAPIView):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    permission_class = [permissions.IsAuthenticated]
    authentication_class = UseJWTAuthentication
    lookup_field = 'user'

 