from django.contrib import admin
from .models import Notice

# Register your models here.

class NoticeAdmin(admin.ModelAdmin):
    model = Notice
    list_filter = ('classcode', 'subjectcode', 'author')
    list_display = ('title', 'classcode', 'subjectcode', 'author')
    # search_fields = ('author', 'title')

admin.site.register(Notice, NoticeAdmin)
