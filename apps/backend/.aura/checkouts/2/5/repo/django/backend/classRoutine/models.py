from django.db import models
from django.db.models import Model
from subject.models import ClassCode,SubjectCode

from django.utils import timezone

# Create your models here.


class classRoutine(models.Model):
    subjectTeacher = models.CharField(max_length= 100,null=True)
    subjectcode = models.ForeignKey(SubjectCode, default=1 ,  on_delete=models.CASCADE)
    classcode = models.ForeignKey(ClassCode, default=2 ,on_delete=models.CASCADE)
    time = models.CharField(max_length = 100,default='25')
    # days = ArrayField(models.CharField(max_length=10),blank=True,default=list)
    days = models.CharField(max_length = 200)
    room_no = models.CharField(max_length = 200)
    link = models.URLField(max_length =  200)
 
    def __str__(self):
        return f"It's {self.subjectTeacher} class"











