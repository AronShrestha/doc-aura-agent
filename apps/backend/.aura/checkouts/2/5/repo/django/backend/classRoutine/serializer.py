from rest_framework import serializers
from .models import classRoutine
from subject.models import ClassCode, SubjectCode
from subject.serializers import SubjectCodeSerializer, ClassCodeSerializer
# from user.models import User,Teacher
from user.serializers import TeacherSerializer 

class ClassRoutineSerializer(serializers.ModelSerializer):
    print("In list")
    subjectcode = SubjectCodeSerializer() 
    classcode = ClassCodeSerializer()

    

    

    class Meta:
        model = classRoutine
        fields = '__all__'


class RoutineCreateSerializer(serializers.ModelSerializer):
   
    classcode = ClassCodeSerializer()
    subjectcode = SubjectCodeSerializer()
    print("In routine")

    class Meta:
        model = classRoutine
        fields = '__all__'

    def get_object(self, validated_data, type):
        print('In get')
        code = validated_data.get(type).get('code').strip()
        print(code)
        code = ''.join((l.upper() for l in code.split()))
        print(code)
        validated_data.pop(type)

        if type == 'subjectcode':
            try:
                obj = SubjectCode.objects.get(code='COMP303')
                print(obj)
            except: 
                obj = None
        elif type == 'classcode':
            try:
                obj = ClassCode.objects.get(code='CE18')
                print(obj)
            except:
                obj = None

                
        return obj, validated_data

    def create(self, validated_data):
        print("creating routine")
      

        c_code, validated_data = self.get_object(validated_data,'classcode')
        s_code, validated_data = self.get_object(validated_data,'subjectcode')
        print(s_code)
        print(c_code)

        if c_code and s_code:
            print(s_code)
            print(c_code)
            return classRoutine.objects.create(**validated_data, classcode=c_code, subjectcode = s_code)
        else:
            return classRoutine.objects.create(**validated_data)