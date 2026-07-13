# -*- coding: utf-8 -*-
"""APP自动化项目管理视图"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django_filters.rest_framework import DjangoFilterBackend
from django.db import models
import logging

from .test_case_views import AppPagination
from ..models import AppProject
from ..serializers import (
    AppProjectSerializer,
    AppProjectCreateSerializer,
    AppProjectUpdateSerializer,
)

logger = logging.getLogger(__name__)


class AppProjectViewSet(viewsets.ModelViewSet):
    """APP自动化项目 ViewSet"""
    queryset = AppProject.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return AppProjectCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AppProjectUpdateSerializer
        return AppProjectSerializer

    def get_queryset(self):
        user = self.request.user
        return AppProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        """软删除项目（只有项目负责人才能删除）"""
        if instance.owner != self.request.user:
            from rest_framework import permissions
            raise permissions.exceptions.PermissionDenied({'error': '只有项目负责人才能删除项目'})
        instance.soft_delete()

    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        """恢复已删除的项目"""
        try:
            instance = AppProject.all_objects.get(pk=pk)
            if instance.owner != request.user:
                return Response({'error': '只有项目负责人才能恢复项目'}, status=status.HTTP_403_FORBIDDEN)
            if not instance.is_deleted:
                return Response({'error': '项目未被删除，无需恢复'}, status=status.HTTP_400_BAD_REQUEST)
            instance.restore()
            return Response({'message': '项目已恢复'})
        except AppProject.DoesNotExist:
            return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='hard-delete')
    def hard_delete(self, request, pk=None):
        """彻底删除项目（物理删除，只有责任人可操作）"""
        try:
            instance = AppProject.all_objects.get(pk=pk)
            if instance.owner != request.user:
                return Response({'error': '只有项目负责人才能彻底删除项目'}, status=status.HTTP_403_FORBIDDEN)
            instance.hard_delete()
            return Response({'message': '项目已彻底删除，无法恢复'})
        except AppProject.DoesNotExist:
            return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], url_path='deleted')
    def deleted_list(self, request):
        """获取当前用户的已删除项目列表（回收站）"""
        user = request.user
        deleted = AppProject.all_objects.filter(
            is_deleted=True, owner=user
        ).order_by('-deleted_at')
        serializer = self.get_serializer(deleted, many=True)
        return Response(serializer.data)
