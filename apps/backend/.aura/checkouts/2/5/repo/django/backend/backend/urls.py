from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static



urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('user.urls')),
    path('notes/',include('notes.urls')),
    path('notice/', include('notice.urls')),
    path('classRoutine/',include('classRoutine.urls')),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
