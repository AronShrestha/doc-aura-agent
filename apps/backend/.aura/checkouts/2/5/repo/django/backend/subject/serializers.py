from .models import ClassCode, SubjectCode, Subject
from rest_framework import serializers

class SubjectCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubjectCode
        fields = "code", "name"

class ClassCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassCode
        fields = "faculty", "batch", "code"