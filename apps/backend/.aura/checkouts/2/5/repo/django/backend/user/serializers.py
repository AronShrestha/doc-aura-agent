from rest_framework import serializers
from .models import User, Teacher, Student
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'name','username', 'is_student', 'is_teacher', 'faculty', 'photo')

class TeacherSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    class Meta:
        model = Teacher
        fields = '__all__'

class StudentSerializer(serializers.ModelSerializer):
    user = UserSerializer()

    class Meta:
        model = Student
        fields = '__all__'
    
class RegisterSerializer(serializers.ModelSerializer):

    class RegisterStudentSerializer(serializers.ModelSerializer):
        registration_no = serializers.IntegerField( required = False)
        batch = serializers.IntegerField(required = False)
        is_CR = serializers.BooleanField(required = False)
        class Meta:
            model = Student
            fields = ('registration_no', 'batch', 'is_CR',)

    class RegisterTeacherSerializer(serializers.ModelSerializer):
        email = serializers.EmailField(required = False)
        class Meta:
            model = Teacher
            fields = ('email',)

    student = RegisterStudentSerializer()
    teacher = RegisterTeacherSerializer()
    photo = serializers.ImageField(required = False)
    class Meta: 
        model = User
        fields = ('id', 'name', 'username', 'password', 'is_student', 'is_teacher', 'faculty', 'photo','student', 'teacher')
        extra_kwargs = {'password':{'write_only':True}}

    def create(self, validated_data):
        user = User.objects.create_user(
            username = validated_data['username'],
            name = validated_data['name'],
            password = validated_data['password'],
            is_student = validated_data['is_student'],
            is_teacher = validated_data['is_teacher'],
            faculty = validated_data['faculty'],
            # photo = validated_data['photo']
            photo = validated_data.get('photo', None)
        )
        is_student = validated_data['is_student']
        is_teacher = validated_data['is_teacher']
        print(user)

        if is_student:
            student_data = validated_data.pop('student')
            create_student = Student.objects.create(
                user = user,
                **student_data,
            )
            print(student_data)

        elif is_teacher:
            teacher_data = validated_data.pop('teacher')
            create_teacher = Teacher.objects.create(
                user = user,
                **teacher_data,
            )
            print(teacher_data)

        else:
            print("Nothing.")

        return user


class LoginSerializer(TokenObtainPairSerializer):
    
    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = self.get_token(self.user)
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)
        

        # Add extra responses here
        data['id'] = self.user.id
        data['is_student'] = self.user.is_student
        data['is_teacher'] = self.user.is_teacher

        # if self.user.is_student:
        #     data['registration_no'] = student.registration_no
        # elif self.user.is_teacher:
        #     data['email'] = self.user.email
        # else:
        #     data['name'] = self.user.name

        return data








        
