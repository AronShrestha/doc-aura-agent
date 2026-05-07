from django.contrib import admin
from .models import classRoutine

# Register your models here.
@admin.register(classRoutine)
class NotesAdmin(admin.ModelAdmin):
    list_display = ('subjectTeacher','time','room_no')