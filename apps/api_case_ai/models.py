"""AI 接口用例：生成任务 / 草稿 / 审核流水。

设计原则：全部为**新增模型**，只通过外键引用 api_testing 的既有模型，
不修改 ApiRequest / TestSuite / reviews / testcases 等任何既有模型与逻辑。
"""
from django.conf import settings
from django.db import models

from apps.api_testing.models import (
    ApiProject, ApiCollection, ApiRequest, TestSuite, default_status_assertions,
)


class ApiCaseGenerationTask(models.Model):
    """AI 生成接口用例的任务"""

    STATUS_CHOICES = [
        ('pending', '待生成'),
        ('running', '生成中'),
        ('success', '生成完成'),
        ('partial', '部分完成'),
        ('failed', '生成失败'),
    ]

    SOURCE_CHOICES = [
        ('text', '文本描述'),
        ('api_doc', 'API文档'),
        ('requirement', '需求描述'),
        ('interfaces', '接口管理已有接口'),
    ]

    name = models.CharField(max_length=200, verbose_name='任务名称')
    project = models.ForeignKey(ApiProject, on_delete=models.CASCADE,
                                related_name='ai_case_tasks', verbose_name='所属项目')
    collection = models.ForeignKey(ApiCollection, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='ai_case_tasks', verbose_name='目标集合')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='text',
                                   verbose_name='输入类型')
    source_content = models.TextField(blank=True, verbose_name='输入内容')
    focus = models.CharField(max_length=500, blank=True, verbose_name='测试关注点')

    # 执行环境：生成时用其变量渲染 URL/鉴权，执行时作为套件环境
    environment = models.ForeignKey('api_testing.Environment', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='ai_case_tasks',
                                    verbose_name='执行环境')

    # 生成前预跑：先用真实请求打通接口，把真实响应交给模型写断言
    probe_enabled = models.BooleanField(default=True, verbose_name='生成前预跑接口')
    probe_results = models.JSONField(default=list, blank=True, verbose_name='接口预跑结果')

    # 来源：接口管理中勾选的已有接口
    source_requests = models.ManyToManyField(
        'api_testing.ApiRequest', blank=True, related_name='ai_case_tasks',
        verbose_name='来源接口')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                              verbose_name='任务状态')
    progress = models.IntegerField(default=0, verbose_name='进度百分比')
    total_generated = models.IntegerField(default=0, verbose_name='生成用例数')
    ai_config_snapshot = models.JSONField(default=dict, blank=True, verbose_name='AI配置快照')
    error_message = models.TextField(blank=True, null=True, verbose_name='错误信息')

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='api_case_ai_tasks', verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')

    class Meta:
        db_table = 'api_ai_case_generation_tasks'
        verbose_name = 'AI接口用例生成任务'
        verbose_name_plural = 'AI接口用例生成任务'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['project']),
        ]

    def __str__(self):
        return self.name

    @property
    def approved_count(self):
        return self.drafts.filter(status='approved').count()

    @property
    def adopted_count(self):
        return self.drafts.filter(adopted_request__isnull=False).count()


class ApiCaseDraft(models.Model):
    """AI 生成的接口用例草稿（可人工修改、可审核、可采纳为 ApiRequest）"""

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('pending_review', '待审核'),
        ('approved', '审核通过'),
        ('rejected', '已驳回'),
        ('needs_revision', '待修订'),
    ]

    PRIORITY_CHOICES = [
        ('P0', 'P0'),
        ('P1', 'P1'),
        ('P2', 'P2'),
        ('P3', 'P3'),
    ]

    task = models.ForeignKey(ApiCaseGenerationTask, on_delete=models.CASCADE,
                             related_name='drafts', verbose_name='所属任务')
    name = models.CharField(max_length=200, verbose_name='用例名称')
    method = models.CharField(max_length=10, default='GET', verbose_name='请求方法')
    url = models.TextField(blank=True, verbose_name='请求URL')
    headers = models.JSONField(default=dict, blank=True, verbose_name='请求头')
    params = models.JSONField(default=dict, blank=True, verbose_name='URL参数')
    body = models.JSONField(default=dict, blank=True, verbose_name='请求体')
    auth = models.JSONField(default=dict, blank=True, verbose_name='认证信息')
    pre_request_script = models.TextField(blank=True, verbose_name='请求前脚本')
    post_request_script = models.TextField(blank=True, verbose_name='请求后脚本')
    assertions = models.JSONField(default=default_status_assertions, verbose_name='断言规则')

    description = models.TextField(blank=True, verbose_name='用例描述')
    expected_result = models.TextField(blank=True, verbose_name='预期结果')
    priority = models.CharField(max_length=5, choices=PRIORITY_CHOICES, default='P1',
                                verbose_name='优先级')
    ai_rationale = models.TextField(blank=True, verbose_name='AI设计说明')
    ai_raw = models.JSONField(default=dict, blank=True, verbose_name='AI原始输出')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_review',
                              verbose_name='状态')
    review_comment = models.TextField(blank=True, verbose_name='审核意见')

    # AI 自检：试跑一次 + 按真实响应自纠正断言
    self_check_result = models.JSONField(default=dict, blank=True, verbose_name='AI自检结果')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='api_case_ai_reviews',
                                    verbose_name='审核人')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='审核时间')

    # 来源接口（来自接口管理），用于追溯
    source_request = models.ForeignKey(ApiRequest, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='ai_source_drafts', verbose_name='来源接口')

    # 采纳后落点
    adopted_request = models.ForeignKey(ApiRequest, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='ai_drafts', verbose_name='已采纳的接口')
    test_suite = models.ForeignKey(TestSuite, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='ai_case_drafts', verbose_name='所属测试套件')

    order = models.IntegerField(default=0, verbose_name='排序')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='api_case_ai_drafts', verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'api_ai_case_drafts'
        verbose_name = 'AI接口用例草稿'
        verbose_name_plural = 'AI接口用例草稿'
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['task']),
        ]

    def __str__(self):
        return self.name

    @property
    def status_display(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def is_adopted(self):
        return self.adopted_request_id is not None


class ApiCaseDraftReview(models.Model):
    """草稿审核流水（AI 自审 + 人工审核，支持多轮）"""

    ACTION_CHOICES = [
        ('submit', '提交审核'),
        ('ai_review', 'AI审核'),
        ('approve', '审核通过'),
        ('reject', '驳回'),
        ('request_revision', '要求修订'),
        ('comment', '评论'),
        ('adopt', '采纳为接口'),
    ]

    draft = models.ForeignKey(ApiCaseDraft, on_delete=models.CASCADE,
                              related_name='reviews', verbose_name='所属草稿')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='api_case_ai_review_logs',
                                 verbose_name='审核人')
    reviewer_name = models.CharField(max_length=100, blank=True, verbose_name='审核人名称')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='comment',
                              verbose_name='动作')
    comment = models.TextField(blank=True, verbose_name='意见')
    previous_status = models.CharField(max_length=20, blank=True, verbose_name='变更前状态')
    new_status = models.CharField(max_length=20, blank=True, verbose_name='变更后状态')
    extra = models.JSONField(default=dict, blank=True, verbose_name='附加信息')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='审核时间')

    class Meta:
        db_table = 'api_ai_case_draft_reviews'
        verbose_name = 'AI接口用例审核记录'
        verbose_name_plural = 'AI接口用例审核记录'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['draft']),
        ]

    def __str__(self):
        return f"{self.draft_id} - {self.action}"

    @property
    def action_display(self):
        return dict(self.ACTION_CHOICES).get(self.action, self.action)
