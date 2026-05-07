from user.models import User
from subject.models import ClassCode

from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils import timezone
from django.core.validators import FileExtensionValidator


# Create your models here.
class Notes(models.Model):
    date_posted = models.DateTimeField(auto_now_add= True) 
    author = models.ForeignKey(User, on_delete=models.CASCADE, null= True)
    classcode = models.ForeignKey(ClassCode, on_delete=models.CASCADE, default=1)
    description =  models.TextField()
    # files = ArrayField(null = True, base_field =  models.FileField(upload_to='documents/',validators=[
    #     FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'ppt', 'xlsx','docx'])]), size = 4)  
     
    file = models.FileField(upload_to='documents/',validators=[
        FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'ppt', 'xlsx','docx'])], null=True)

