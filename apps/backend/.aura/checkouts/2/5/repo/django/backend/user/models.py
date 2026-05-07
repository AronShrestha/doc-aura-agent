from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
class User(AbstractUser):
    name = models.CharField(max_length = 150, default = 'my_username', verbose_name = 'name')
    faculty = models.CharField(max_length=100)
    is_student = models.BooleanField('student', default = False)
    is_teacher = models.BooleanField('teacher', default = False)
    photo = models.ImageField(upload_to='photos/')
    def __str__(self):
        return str(self.name)

class Teacher(models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    email = models.EmailField( primary_key = True)
    def __str__(self):
        return str(self.user)

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    registration_no = models.IntegerField( primary_key = True)
    batch = models.IntegerField()
    is_CR = models.BooleanField('Class Representative', default = False)
    def __str__(self):
        return str(self.user)

