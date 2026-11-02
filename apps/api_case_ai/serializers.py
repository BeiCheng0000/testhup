from django.db import models
from rest_framework import serializers

from apps.api_testing.models import ApiRequest

from .models import ApiCaseGenerationTask, ApiCaseDraft, ApiCaseDraftReview


class ApiCaseDraftReviewSerializer(serializers.ModelSerializer):
    action_display = serializers.ReadOnlyField()

    class Meta:
        model = ApiCaseDraftReview
        fields = ['id', 'draft', 'reviewer', 'reviewer_name', 'action', 'action_display',
                  'comment', 'previous_status', 'new_status', 'extra', 'created_at']
        read_only_fields = ['created_at']


class ApiCaseDraftSerializer(serializers.ModelSerializer):
    status_display = serializers.ReadOnlyField()
    is_adopted = serializers.ReadOnlyField()
    adopted_request_id = serializers.IntegerField(source='adopted_request.id', read_only=True)
    source_request_name = serializers.SerializerMethodField()
    source_request_method = serializers.SerializerMethodField()
    reviews = ApiCaseDraftReviewSerializer(many=True, read_only=True)
    latest_ai_review = serializers.SerializerMethodField()

    class Meta:
        model = ApiCaseDraft
        fields = [
            'id', 'task', 'name', 'method', 'url', 'headers', 'params', 'body', 'auth',
            'pre_request_script', 'post_request_script', 'assertions',
            'description', 'expected_result', 'priority', 'ai_rationale', 'ai_raw',
            'status', 'status_display', 'review_comment', 'reviewed_by', 'reviewed_at',
            'self_check_result', 'latest_ai_review',
            'source_request', 'source_request_name', 'source_request_method',
            'adopted_request', 'adopted_request_id', 'test_suite', 'is_adopted',
            'order', 'created_by', 'created_at', 'updated_at', 'reviews',
        ]
        read_only_fields = ['task', 'created_by', 'created_at', 'updated_at', 'reviewed_by',
                            'reviewed_at', 'source_request', 'adopted_request', 'test_suite']

    def get_source_request_name(self, obj):
        return obj.source_request.name if obj.source_request_id else ''

    def get_source_request_method(self, obj):
        return obj.source_request.method if obj.source_request_id else ''

    def get_latest_ai_review(self, obj):
        """最新一条 AI 审核结论（action=ai_review 且 reviewer_name=AI）。"""
        from .models import ApiCaseDraftReview
        review = ApiCaseDraftReview.objects.filter(
            draft=obj, action='ai_review', reviewer_name='AI'
        ).order_by('-id').first()
        if not review:
            return None
        return {
            'comment': review.comment,
            'suggestion': (review.extra or {}).get('suggestion'),
            'created_at': review.created_at,
        }


class ApiCaseGenerationTaskSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    collection_name = serializers.CharField(source='collection.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    approved_count = serializers.ReadOnlyField()
    adopted_count = serializers.ReadOnlyField()
    draft_count = serializers.SerializerMethodField()

    source_requests = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ApiRequest.objects.all(), required=False)
    source_request_count = serializers.SerializerMethodField()
    source_requests_detail = serializers.SerializerMethodField()
    environment_name = serializers.SerializerMethodField()
    probe_summary = serializers.SerializerMethodField()

    class Meta:
        model = ApiCaseGenerationTask
        fields = [
            'id', 'name', 'project', 'project_name', 'collection', 'collection_name',
            'source_type', 'source_type_display', 'source_content', 'focus',
            'environment', 'environment_name',
            'probe_enabled', 'probe_results', 'probe_summary',
            'source_requests', 'source_request_count', 'source_requests_detail',
            'status', 'status_display', 'progress', 'total_generated',
            'ai_config_snapshot', 'ai_review_running', 'error_message', 'created_by', 'created_by_name',
            'created_at', 'updated_at', 'finished_at',
            'approved_count', 'adopted_count', 'draft_count',
        ]
        read_only_fields = ['status', 'progress', 'total_generated', 'ai_config_snapshot',
                            'probe_results', 'ai_review_running', 'error_message', 'created_by',
                            'created_at', 'updated_at', 'finished_at']
        extra_kwargs = {
            'source_content': {'required': False, 'allow_blank': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 来源接口按当前用户可见范围过滤，避免越权勾选他人接口
        request = self.context.get('request')
        field = self.fields.get('source_requests')
        if field is not None and request is not None and request.user.is_authenticated:
            field.queryset = ApiRequest.objects.filter(
                models.Q(collection__project__owner=request.user)
                | models.Q(collection__project__members=request.user)
                | models.Q(created_by=request.user)
            ).distinct()

    def get_source_request_count(self, obj):
        return obj.source_requests.count()

    def get_environment_name(self, obj):
        return obj.environment.name if obj.environment_id else ''

    def get_probe_summary(self, obj):
        """预跑概览：已探测数 / 返回 2xx 的数量。"""
        results = obj.probe_results or []
        if not results:
            return {'total': 0, 'ok': 0}
        return {
            'total': len(results),
            'ok': sum(1 for p in results
                      if p.get('ok') and 200 <= (p.get('status_code') or 0) < 300),
        }

    def get_source_requests_detail(self, obj):
        return [
            {'id': r.id, 'name': r.name, 'method': r.method, 'url': r.url}
            for r in obj.source_requests.all()[:100]
        ]

    def get_created_by_name(self, obj):
        user = obj.created_by
        if not user:
            return ''
        return getattr(user, 'username', '') or getattr(user, 'first_name', '') or str(user)

    def get_draft_count(self, obj):
        return obj.drafts.count()
