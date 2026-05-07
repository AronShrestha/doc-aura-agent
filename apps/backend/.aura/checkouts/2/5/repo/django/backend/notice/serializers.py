from django.db.models import fields
from .models import Notice 
from subject.models import ClassCode, SubjectCode
from user.serializers import UserSerializer

from subject.serializers import SubjectCodeSerializer, ClassCodeSerializer
from rest_framework import serializers

class NoticeSerializer(serializers.ModelSerializer):
    subjectcode = SubjectCodeSerializer() 
    classcode = ClassCodeSerializer()
    author = UserSerializer()
    date_posted = serializers.DateTimeField(read_only = True, format = '%Y-%m-%d')
    time_posted = serializers.SerializerMethodField('get_time')

    def get_time(self, obj):
        return obj.date_posted.time().strftime('%H-%M')

    class Meta:
        model = Notice
        fields = ('id', 'title', 'description', 'date_posted', 'classcode', 'subjectcode', 'author', 'time_posted')

class NoticeCreateSerializer(serializers.ModelSerializer):
    classcode = ClassCodeSerializer()
    subjectcode = SubjectCodeSerializer()

    class Meta:
        model = Notice
        fields = 'title', 'description', 'classcode', 'subjectcode', 'author'

    def get_object(self, validated_data, type):
        # print("I n get_obje")
        code = validated_data.get(type).get('code').strip()
        code = ''.join((l.upper() for l in code.split()))
        validated_data.pop(type)

        if type == 'subjectcode':
            try:
                obj = SubjectCode.objects.get(code=code)
            except: 
                obj = None
        elif type == 'classcode':
            try:
                obj = ClassCode.objects.get(code=code)
            except:
                obj = None
                
        return obj, validated_data

    def create(self, validated_data):
        # print("In create_obje")
        c_code, validated_data = self.get_object(validated_data, 'classcode')
        s_code, validated_data = self.get_object(validated_data, 'subjectcode')

        if c_code and s_code:
            return Notice.objects.create(**validated_data, classcode=c_code, subjectcode = s_code)
        else:
            return Notice.objects.create(**validated_data)
