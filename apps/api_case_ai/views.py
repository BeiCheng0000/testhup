import threading
from datetime import timedelta

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

# 超过该时长仍标记为「审核中」视为异常残留（如进程被杀），允许重新抢占
AI_REVIEW_STALE_MINUTES = 30


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

    # filter_backends=[] 必须显式关掉：viewset 上配了 filterset_fields = ['status', ...]，
    # 那个 status 是「任务状态」(pending/running/success/partial/failed)，
    # 会让 ?status=approved 这类草稿状态直接被判为无效选项返回 400。
    # 草稿列表的过滤在下面方法体内自己处理。
    @action(detail=True, methods=['get'], url_path='drafts', filter_backends=[])
    def drafts(self, request, pk=None):
        """任务下的草稿列表（支持 ?status= / ?source_request= 过滤）"""
        task = self.get_object()
        qs = task.drafts.all().select_related('adopted_request', 'test_suite')
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        # 按来源接口筛选：一个任务多个接口时，只看某个接口生成的用例
        source_request = request.query_params.get('source_request')
        if source_request:
            if source_request == 'none':
                qs = qs.filter(source_request__isnull=True)
            else:
                qs = qs.filter(source_request_id=source_request)

        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ApiCaseDraftSerializer(page, many=True).data)
        return Response(ApiCaseDraftSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'], url_path='add-draft')
    def add_draft(self, request, pk=None):
        """手动添加用例：不经过 AI 生成，直接在该任务下补一条草稿（状态为草稿）。"""
        task = self.get_object()
        name = (request.data.get('name') or '').strip()
        url = (request.data.get('url') or '').strip()
        if not name:
            return Response({'error': '用例名称不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if not url:
            return Response({'error': '请求 URL 不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        source = None
        source_id = request.data.get('source_request')
        if source_id:
            source = ApiRequest.objects.filter(id=source_id).first()

        draft = ApiCaseDraft.objects.create(
            task=task,
            name=name,
            method=request.data.get('method') or 'GET',
            url=url,
            headers=request.data.get('headers') or {},
            params=request.data.get('params') or {},
            body=request.data.get('body') or {},
            auth=request.data.get('auth') or {},
            assertions=request.data.get('assertions') or [],
            description=request.data.get('description') or '',
            expected_result=request.data.get('expected_result') or '',
            priority=request.data.get('priority') or 'P1',
            source_request=source,
            status='draft',
            created_by=request.user,
        )
        return Response(ApiCaseDraftSerializer(draft).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='ai-review')
    def ai_review(self, request, pk=None):
        """AI 自审：逐条试跑 → 按真实响应校验并修正断言 → 模型复核意见"""
        task = self.get_object()

        # 并发防护：同一任务同时只允许一个 AI 审核；只有「未超时且仍在跑」才拒绝
        stale_before = timezone.now() - timedelta(minutes=AI_REVIEW_STALE_MINUTES)
        claimed = ApiCaseGenerationTask.objects.filter(pk=task.pk).exclude(
            ai_review_running=True, ai_review_started_at__gt=stale_before,
        ).update(ai_review_running=True, ai_review_started_at=timezone.now())
        if not claimed:
            return Response(
                {'message': '该任务正在执行 AI 审核，请等审核结束后再启动'},
                status=status.HTTP_409_CONFLICT,
            )

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
        # 传了 ids 则只处理勾选的用例（不限当前状态，便于把驳回/待修订的重新通过）
        ids = request.data.get('ids')
        if ids:
            qs = task.drafts.filter(id__in=ids)
        else:
            qs = task.drafts.filter(status='pending_review')

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
        """批量采纳「审核通过」的用例并汇总进测试套件（可传 ids 只采纳勾选项）"""
        task = self.get_object()
        suite_name = request.data.get('suite_name') or None
        ids = request.data.get('ids') or None
        try:
            suite, count = adopt_task(task, request.user, suite_name, draft_ids=ids)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        requested = len(ids) if ids else task.drafts.filter(status='approved').count()

        if count == 0:
            return Response({
                'message': f'没有可采纳的用例：勾选的 {requested} 条都还未通过审核，请先执行「批量通过」',
                'suite_id': None,
                'suite_name': '',
                'adopted_count': 0,
            })

        message = f'已采纳 {count} 条用例'
        if requested > count:
            message += f'，另有 {requested - count} 条未通过审核已跳过'

        return Response({
            'message': message,
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

    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate(self, request, pk=None):
        """复制用例：内容照搬，状态回到「草稿」，不继承采纳结果，需重新审核。"""
        import re

        draft = self.get_object()
        base = re.sub(r'(副本\s*\d*)$', '', draft.name).strip()
        name = f'{base} 副本'

        copy = ApiCaseDraft.objects.create(
            task=draft.task,
            name=name,
            method=draft.method,
            url=draft.url,
            headers=draft.headers or {},
            params=draft.params or {},
            body=draft.body or {},
            auth=draft.auth or {},
            pre_request_script=draft.pre_request_script or '',
            post_request_script=draft.post_request_script or '',
            assertions=draft.assertions or [],
            description=draft.description or '',
            expected_result=draft.expected_result or '',
            priority=draft.priority,
            source_request=draft.source_request,
            status='draft',
            created_by=request.user,
        )
        return Response(ApiCaseDraftSerializer(copy).data, status=status.HTTP_201_CREATED)

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
            # persist=False：试运行只在内存里跑，不落地 ApiRequest、不写请求历史，
            # 避免未审核的用例提前出现在「接口管理」里；只有采纳后才入库
            result = run_draft(draft, request.user, environment, persist=False)
            result['adopted'] = bool(draft.adopted_request_id)
        except Exception as exc:
            return Response({'error': f'执行失败：{exc}'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
