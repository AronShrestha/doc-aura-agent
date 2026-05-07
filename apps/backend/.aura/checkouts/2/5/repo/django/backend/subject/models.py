from django.db import models
from user.models import Teacher


# Create your models here.
class ClassCode(models.Model):
    faculty = models.CharField(max_length=150)
    batch = models.CharField(max_length=100)
    code = models.CharField(default = 'ce18', max_length=10)

    # @property
    # def code(self):
    #     return ''.join((str(l[0]).lower() for l in self.faculty.split())) + str(self.batch)[-2:]
    
    def __str__(self):
        return f'{self.faculty}: {self.batch}'

    # Computer Engineering -> CE 
    # 2018 -> 18
    # CE18


class SubjectCode(models.Model):
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=250)

    def __str__(self):
        return f'{self.code}'

class Subject(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    subjectcode = models.ForeignKey(SubjectCode, on_delete=models.CASCADE)
    classcode = models.ForeignKey(ClassCode, on_delete=models.CASCADE)

   








 