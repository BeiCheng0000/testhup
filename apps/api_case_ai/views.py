import threading

from django.db import models
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api_testing.models import ApiRequest, Environment, TestSuite
from apps.api_testing.views import StandardPagination

from .models import ApiCaseDraft, ApiCaseDraftReview, ApiCaseGenerationTask
from .serializers import (
    ApiCaseDraftReviewSerializer,
    ApiCaseDraftSerializer,
    ApiCaseGenerationTaskSerializer,
)
from .services import (
    adopt_draft,
    adopt_task,
    run_ai_review,
    run_draft,
    run_generation,
    start_execution,
)

REVIEW_ACTION_MAP = {
    'approve': 'approved',
    'reject': 'rejected',
    'request_revision': 'needs_revision',
}


def _display_name(user):
    if not user:
        return ''
    return getattr(user, 'username', '') or getattr(user, 'first_name', '') or str(user)


class ApiCaseGenerationTaskViewSet(viewsets.ModelViewSet):
    """AI 接口用例生成任务"""

    permission_classes = [IsAuthenticated]
    serializer_class = ApiCaseGenerationTaskSerializer
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'project', 'source_type']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return ApiCaseGenerationTask.objects.filter(
            models.Q(project__owner=user)
            | models.Q(project__members=user)
            | models.Q(created_by=user)
        ).distinct().select_related('project', 'collection', 'created_by')

    def perform_create(self, serializer):
        task = serializer.save(created_by=self.request.user)
        threading.Thread(
            target=run_generation, args=(task.id, self.request.user.id), daemon=True
        ).start()

    @action(detail=False, methods=['get'], url_path='available-requests')
    def available_requests(self, request):
        """供前端选择：接口管理中当前用户可见的接口。

        支持 ?project=<id>&collection=<id>&search=<kw>
        """
        project_id = request.query_params.get('project')
        collection_id = request.query_params.get('collection')
        search = request.query_params.get('search')

        qs = ApiRequest.objects.select_related('collection').filter(
            models.Q(collection__project__owner=request.user)
            | models.Q(collection__project__members=request.user)
            | models.Q(created_by=request.user)
        ).distinct()

        if project_id:
            qs = qs.filter(collection__project_id=project_id)
        if collection_id:
            qs = qs.filter(collection_id=collection_id)
        if search:
            qs = qs.filter(models.Q(name__icontains=search) | models.Q(url__icontains=search))

        qs = qs.order_by('collection_id', 'order', 'id')[:500]
        data = [{
            'id': r.id,
            'name': r.name,
            'method': r.method,
            'url': r.url,
            'collection': r.collection_id,
            'collection_name': r.collection.name if r.collection_id else '',
        } for r in qs]
        return Response(data)

    @action(detail=True, methods=['get'], url_path='drafts')
    def drafts(self, request, pk=None):
        """任务下的草稿列表（支持 ?status= 过滤）"""
        task = self.get_object()
        qs = task.drafts.all().select_related('adopted_request', 'test_suite')
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ApiCaseDraftSerializer(page, many=True).data)
        return Response(ApiCaseDraftSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'], url_path='ai-review')
    def ai_review(self, request, pk=None):
        """AI 自审：逐条试跑 → 按真实响应校验并修正断言 → 模型复核意见"""
        task = self.get_object()

        def _flag(name, default):
            value = request.data.get(name, default)
            if isinstance(value, str):
                return value.lower() not in ('false', '0', '', 'no')
            return bool(value)

        threading.Thread(
            target=run_ai_review,
            args=(task.id, request.user.id,
                  _flag('auto_fix', True),
                  _flag('fix_values', False),
                  _flag('approve_on_pass', False)),
            daemon=True).start()
        return Response({'message': 'AI 审核已启动：将逐条试跑并按真实响应校验断言'})

    @action(detail=True, methods=['post'], url_path='regenerate')
    def regenerate(self, request, pk=None):
        """清空旧草稿并重新生成"""
        task = self.get_object()
        task.drafts.all().delete()
        task.status = 'pending'
        task.progress = 0
        task.total_generated = 0
        task.error_message = None
        task.save()
        threading.Thread(
            target=run_generation, args=(task.id, request.user.id), daemon=True
        ).start()
        return Response({'message': '重新生成已启动'})

    @action(detail=True, methods=['post'], url_path='bulk-review')
    def bulk_review(self, request, pk=None):
        """批量审核：approve / reject / request_revision"""
        task = self.get_object()
        action_name = request.data.get('action', 'approve')
        comment = request.data.get('comment', '') or ''
        if action_name not in REVIEW_ACTION_MAP:
            return Response(
                {'error': 'action 必须是 approve / reject / request_revision'},
                status=status.HTTP_400_BAD_REQUEST)

        new_status = REVIEW_ACTION_MAP[action_name]
        qs = task.drafts.filter(status='pending_review')
        ids = request.data.get('ids')
        if ids:
            qs = qs.filter(id__in=ids)

        count = 0
        for draft in qs:
            previous = draft.status
            draft.status = new_status
            draft.review_comment = comment
            draft.reviewed_by = request.user
            draft.reviewed_at = timezone.now()
            draft.save()
            ApiCaseDraftReview.objects.create(
                draft=draft, reviewer=request.user, reviewer_name=_display_name(request.user),
                action=action_name, comment=comment,
                previous_status=previous, new_status=new_status)
            count += 1

        return Response({'message': f'已{self._action_label(action_name)} {count} 条用例',
                         'count': count})

    @staticmethod
    def _action_label(action_name):
        return {'approve': '通过', 'reject': '驳回', 'request_revision': '要求修订'}.get(
            action_name, '处理')

    @action(detail=True, methods=['post'], url_path='adopt-all')
    def adopt_all(self, request, pk=None):
        """批量采纳「审核通过」的用例并汇总进测试套件"""
        task = self.get_object()
        suite_name = request.data.get('suite_name') or None
        try:
            suite, count = adopt_task(task, request.user, suite_name)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'message': f'已采纳 {count} 条用例',
            'suite_id': suite.id,
            'suite_name': suite.name,
            'adopted_count': count,
        })

    @action(detail=True, methods=['post'], url_path='execute')
    def execute(self, request, pk=None):
        """采纳后自动化执行（复用既有执行引擎）"""
        task = self.get_object()
        suite = None

        suite_id = request.data.get('suite_id')
        if suite_id:
            suite = TestSuite.objects.filter(id=suite_id, project=task.project).first()

        if not suite:
            suite_id = task.drafts.filter(test_suite__isnull=False) \
                .values_list('test_suite', flat=True).first()
            if suite_id:
                suite = TestSuite.objects.filter(id=suite_id).first()

        if not suite:
            return Response(
                {'error': '尚未采纳任何用例，请先审核通过并执行「批量采纳」'},
                status=status.HTTP_400_BAD_REQUEST)

        execution = start_execution(suite, request.user)
        return Response({
            'message': '执行已启动',
            'execution_id': execution.id,
            'test_suite_id': suite.id,
            'test_suite_name': suite.name,
            'status': execution.status,
            'total_requests': execution.total_requests,
        })


class ApiCaseDraftViewSet(viewsets.ModelViewSet):
    """AI 接口用例草稿：人工修改 / 审核 / 采纳"""

    permission_classes = [IsAuthenticated]
    serializer_class = ApiCaseDraftSerializer
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['task', 'status']
    ordering = ['order', 'id']

    def get_queryset(self):
        user = self.request.user
        return ApiCaseDraft.objects.filter(
            models.Q(task__project__owner=user)
            | models.Q(task__project__members=user)
            | models.Q(created_by=user)
        ).distinct().select_related('task', 'adopted_request', 'test_suite')

    def perform_update(self, serializer):
        draft = serializer.save()
        ApiCaseDraftReview.objects.create(
            draft=draft, reviewer=self.request.user,
            reviewer_name=_display_name(self.request.user), action='comment',
            comment='人工修改用例内容', previous_status=draft.status, new_status=draft.status)

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        """单条审核：approve / reject / request_revision"""
        draft = self.get_object()
        action_name = request.data.get('action')
        comment = request.data.get('comment', '') or ''
        if action_name not in REVIEW_ACTION_MAP:
            return Response(
                {'error': 'action 必须是 approve / reject / request_revision'},
                status=status.HTTP_400_BAD_REQUEST)

        previous = draft.status
        draft.status = REVIEW_ACTION_MAP[action_name]
        draft.review_comment = comment
        draft.reviewed_by = request.user
        draft.reviewed_at = timezone.now()
        draft.save()

        ApiCaseDraftReview.objects.create(
            draft=draft, reviewer=request.user, reviewer_name=_display_name(request.user),
            action=action_name, comment=comment,
            previous_status=previous, new_status=draft.status)

        return Response(ApiCaseDraftSerializer(draft).data)

    @action(detail=True, methods=['post'], url_path='adopt')
    def adopt(self, request, pk=None):
        """单条采纳为 ApiRequest"""
        draft = self.get_object()
        if draft.status != 'approved':
            return Response(
                {'error': '只有「审核通过」的用例才能采纳'},
                status=status.HTTP_400_BAD_REQUEST)

        api_request = adopt_draft(draft, request.user)
        return Response({
            'message': '已采纳为接口用例',
            'request_id': api_request.id,
            'name': api_request.name,
        })

    @action(detail=True, methods=['get'], url_path='reviews')
    def reviews(self, request, pk=None):
        """审核流水"""
        draft = self.get_object()
        qs = draft.reviews.all()
        return Response(ApiCaseDraftReviewSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'], url_path='run')
    def run(self, request, pk=None):
        """单条试运行：审核阶段即可验证用例是否可执行"""
        draft = self.get_object()
        environment = None
        env_id = request.data.get('environment_id')
        if env_id:
            environment = Environment.objects.filter(id=env_id).first()

        try:
            result = run_draft(draft, request.user, environment)
        except Exception as exc:
            return Response({'error': f'执行失败：{exc}'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
