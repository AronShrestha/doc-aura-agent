from django.db import models
from user.models import User
from subject.models import ClassCode, SubjectCode
  
class Notice(models.Model):
    title = models.CharField(max_length=150, default="This is the title")
    description = models.TextField()
    subjectcode = models.ForeignKey(SubjectCode, default=1 ,  on_delete=models.CASCADE)
    classcode = models.ForeignKey(ClassCode, default=2 ,on_delete=models.CASCADE)
    date_posted = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User, default=1, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.classcode}: {self.title}"