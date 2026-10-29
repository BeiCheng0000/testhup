from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ApiCaseDraftViewSet, ApiCaseGenerationTaskViewSet

router = DefaultRouter()
router.register(r'ai-case-tasks', ApiCaseGenerationTaskViewSet, basename='apicasegenerationtask')
router.register(r'ai-case-drafts', ApiCaseDraftViewSet, basename='apicasedraft')

urlpatterns = [
    path('api-testing/', include(router.urls)),
]
