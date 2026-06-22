# -*- coding: utf-8 -*-
from django.urls import path, include
from django.http import FileResponse, Http404
from django.conf import settings
import os
from .views.execution_views import serve_report_file
from rest_framework.routers import DefaultRouter

from .views import (
    AppProjectViewSet,
    AppConfigViewSet,
    AppDeviceViewSet,
    AppElementViewSet,
    AppComponentViewSet,
    AppCustomComponentViewSet,
    AppComponentPackageViewSet,
    AppPackageViewSet,
    AppTestCaseViewSet,
    AppTestSuiteViewSet,
    AppScheduledTaskViewSet,
    AppNotificationLogViewSet,
    AppTestExecutionViewSet,
    AppDashboardViewSet,
)


def download_agent(request):
    """下载 ADB Agent 脚本 - 供远程主机一键获取"""
    agent_path = os.path.join(settings.BASE_DIR, 'adb_agent.py')
    if not os.path.exists(agent_path):
        raise Http404('Agent 脚本文件不存在')
    response = FileResponse(
        open(agent_path, 'rb'),
        content_type='text/plain; charset=utf-8',
        as_attachment=True,
        filename='adb_agent.py'
    )
    return response


def download_agent_requirements(request):
    """下载 Agent 依赖文件"""
    req_path = os.path.join(settings.BASE_DIR, 'requirements-agent.txt')
    if not os.path.exists(req_path):
        raise Http404('Agent 依赖文件不存在')
    response = FileResponse(
        open(req_path, 'rb'),
        content_type='text/plain; charset=utf-8',
        as_attachment=True,
        filename='requirements-agent.txt'
    )
    return response


router = DefaultRouter()

# 注册ViewSets
router.register(r'projects', AppProjectViewSet, basename='app-project')
router.register(r'config', AppConfigViewSet, basename='app-config')
router.register(r'dashboard', AppDashboardViewSet, basename='app-dashboard')
router.register(r'devices', AppDeviceViewSet, basename='app-device')
router.register(r'elements', AppElementViewSet, basename='app-element')
router.register(r'components', AppComponentViewSet, basename='app-component')
router.register(r'custom-components', AppCustomComponentViewSet, basename='app-custom-component')
router.register(r'component-packages', AppComponentPackageViewSet, basename='app-component-package')
router.register(r'packages', AppPackageViewSet, basename='app-package')
router.register(r'test-cases', AppTestCaseViewSet, basename='app-test-case')
router.register(r'test-suites', AppTestSuiteViewSet, basename='app-test-suite')
router.register(r'scheduled-tasks', AppScheduledTaskViewSet, basename='app-scheduled-task')
router.register(r'notification-logs', AppNotificationLogViewSet, basename='app-notification-log')
router.register(r'executions', AppTestExecutionViewSet, basename='app-execution')

urlpatterns = [
    path('', include(router.urls)),
    path('executions/<int:execution_id>/report/', serve_report_file, name='app-execution-report'),
    path('executions/<int:execution_id>/report/<path:file_path>', serve_report_file, name='app-execution-report-file'),
    # Agent 下载端点
    path('agent/download/', download_agent, name='download-agent'),
    path('agent/requirements/', download_agent_requirements, name='download-agent-requirements'),
]
