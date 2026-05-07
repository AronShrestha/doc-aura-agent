from rest_framework import serializers

from user.serializers import UserSerializer
from subject.serializers import ClassCodeSerializer

from subject.models import ClassCode

from . import models

class NotesSerializers(serializers.ModelSerializer):
    author = UserSerializer()

    class Meta:
        model = models.Notes
        fields = '__all__'

class NotesCreateSerializer(serializers.ModelSerializer):
    # classcode = ClassCodeSerializer()
    classcode = serializers.CharField()

    class Meta:
        model = models.Notes
        fields = ('author', 'description', 'file', 'classcode')
    
    def create(self, validate_data):
        # print(validate_data)
        code = validate_data.get('classcode')
        code = ''.join([l.lower() for l in code.split()])

        validate_data.pop('classcode')
        print(code)
        print(validate_data)

        if code:
            return models.Notes.objects.create(classcode=ClassCode.objects.get(code=code), **validate_data)
        else:
            return models.Notes.objects.create(**validate_data)