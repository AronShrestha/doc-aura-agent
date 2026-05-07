from django.contrib import admin
from .models import ClassCode, SubjectCode, Subject

# Register your models here.
admin.site.register(ClassCode)
admin.site.register(SubjectCode)
admin.site.register(Subject)