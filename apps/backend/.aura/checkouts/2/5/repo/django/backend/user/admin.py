from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Teacher, Student

# Register your models here.
class MyUserAdmin(UserAdmin):
    model = User
    fieldsets = UserAdmin.fieldsets + ((None,{'fields' : ('name','faculty', 'is_student', 'is_teacher', 'photo')}),)
    list_display = ['id', 'name', 'faculty', 'is_student', 'is_teacher' ]
    list_editable = ['faculty']
    search_fields = ['name']
    list_filter = ['faculty', 'is_student', 'is_teacher']
    ordering = ['id']

class TeacherAdmin(admin.ModelAdmin):
    model = Teacher
    list_display = ['user', 'email']
    search_fields = ['user__name', 'user__faculty']
    ordering = ['user__id']

class StudentAdmin(admin.ModelAdmin):
    model = Student
    list_display = ['user', 'registration_no', 'batch', 'is_CR']
    list_filter = ['is_CR', 'batch', 'user__faculty']
    search_fields = ['user__name', 'batch', 'user__faculty']
    ordering = ['user__id']


admin.site.register(User, MyUserAdmin)
admin.site.register(Teacher, TeacherAdmin)
admin.site.register(Student, StudentAdmin)


