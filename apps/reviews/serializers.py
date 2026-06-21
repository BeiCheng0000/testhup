from rest_framework import serializers
from .models import TestCaseReview, ReviewAssignment, TestCaseReviewComment, ReviewTemplate, ReviewCase, ReviewCaseHistory


# 简化的序列化器，避免循环导入
class SimpleUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class SimpleProjectSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()


class SimpleTestCaseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    test_type = serializers.CharField()
    priority = serializers.CharField()
    status = serializers.CharField()
    module = serializers.CharField()
    author = SimpleUserSerializer()


class ReviewAssignmentSerializer(serializers.ModelSerializer):
    reviewer = SimpleUserSerializer(read_only=True)
    
    class Meta:
        model = ReviewAssignment
        fields = ['id', 'reviewer', 'status', 'comment', 'checklist_results', 'reviewed_at', 'assigned_at']


class TestCaseReviewCommentSerializer(serializers.ModelSerializer):
    author = SimpleUserSerializer(read_only=True)
    testcase = SimpleTestCaseSerializer(read_only=True)
    
    class Meta:
        model = TestCaseReviewComment
        fields = ['id', 'testcase', 'author', 'comment_type', 'content', 'step_number', 
                 'is_resolved', 'created_at', 'updated_at']


class TestCaseReviewCommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestCaseReviewComment
        fields = ['review', 'testcase', 'comment_type', 'content', 'step_number']
        extra_kwargs = {
            'testcase': {'required': False, 'allow_null': True}
        }


class ReviewTemplateSerializer(serializers.ModelSerializer):
    creator = SimpleUserSerializer(read_only=True)
    project = SimpleProjectSerializer(many=True, read_only=True)
    default_reviewers = SimpleUserSerializer(many=True, read_only=True)
    
    class Meta:
        model = ReviewTemplate
        fields = ['id', 'name', 'description', 'project', 'creator', 'checklist',
                 'default_reviewers', 'is_active', 'created_at', 'updated_at']


class ReviewCaseHistorySerializer(serializers.ModelSerializer):
    reviewed_by = SimpleUserSerializer(read_only=True)
    
    class Meta:
        model = ReviewCaseHistory
        fields = ['id', 'status', 'comments', 'reviewed_by', 'reviewed_at']


class ReviewCaseSerializer(serializers.ModelSerializer):
    testcase = SimpleTestCaseSerializer(read_only=True)
    reviewed_by = SimpleUserSerializer(read_only=True)
    
    class Meta:
        model = ReviewCase
        fields = ['id', 'review', 'testcase', 'status', 'comments', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at']


class ReviewCaseListSerializer(serializers.ModelSerializer):
    """评审执行列表使用的轻量序列化器，包含关联用例的详细字段"""
    testcase_id = serializers.IntegerField(source='testcase.id', read_only=True)
    title = serializers.CharField(source='testcase.title', read_only=True)
    module = serializers.CharField(source='testcase.module', read_only=True)
    priority = serializers.CharField(source='testcase.priority', read_only=True)
    preconditions = serializers.CharField(source='testcase.preconditions', read_only=True)
    steps = serializers.CharField(source='testcase.steps', read_only=True)
    expected_result = serializers.CharField(source='testcase.expected_result', read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ReviewCase
        fields = ['id', 'review', 'testcase_id', 'status', 'comments', 'reviewed_by_id',
                  'reviewed_by_name', 'reviewed_at', 'created_at', 'updated_at',
                  'title', 'module', 'priority', 'preconditions', 'steps', 'expected_result']
    
    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.username
        return None


class TestCaseReviewSerializer(serializers.ModelSerializer):
    creator = SimpleUserSerializer(read_only=True)
    projects = SimpleProjectSerializer(many=True, read_only=True)
    testcases = SimpleTestCaseSerializer(many=True, read_only=True)
    template = ReviewTemplateSerializer(read_only=True)
    assignments = ReviewAssignmentSerializer(source='reviewassignment_set', many=True, read_only=True)
    comments = TestCaseReviewCommentSerializer(many=True, read_only=True)
    review_cases = ReviewCaseSerializer(many=True, read_only=True)
    
    class Meta:
        model = TestCaseReview
        fields = ['id', 'title', 'description', 'projects', 'modules', 'testcases', 'creator', 
                 'template', 'status', 'priority', 'deadline', 'created_at', 'updated_at', 
                 'completed_at', 'assignments', 'comments', 'review_cases']


# 创建和更新用的简化序列化器
class TestCaseReviewCreateSerializer(serializers.ModelSerializer):
    reviewers = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    projects = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    modules = serializers.ListField(child=serializers.CharField(), write_only=True)
    template = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = TestCaseReview
        fields = ['title', 'description', 'projects', 'priority', 'deadline', 'modules', 'reviewers', 'template']
    
    def _resolve_testcase_ids(self, modules, project_ids):
        """根据模块名和项目ID查询所有用例ID"""
        from apps.testcases.models import TestCase
        if not modules or not project_ids:
            return []
        return list(TestCase.objects.filter(
            project_id__in=project_ids,
            module__in=modules
        ).values_list('id', flat=True).distinct())
    
    def _create_review_cases(self, review, testcases_ids):
        """为评审创建逐用例评审记录"""
        from apps.testcases.models import TestCase
        existing = set(ReviewCase.objects.filter(review=review).values_list('testcase_id', flat=True))
        new_ids = [tid for tid in testcases_ids if tid not in existing]
        if new_ids:
            testcases = TestCase.objects.filter(id__in=new_ids)
            review_cases = [ReviewCase(review=review, testcase=tc) for tc in testcases]
            ReviewCase.objects.bulk_create(review_cases)
        # 删除不在新列表中的 ReviewCase
        ReviewCase.objects.filter(review=review).exclude(testcase_id__in=testcases_ids).delete()

    def _handle_relations(self, review, validated_data):
        """处理项目和模板关联"""
        projects_ids = validated_data.pop('projects', [])
        template_id = validated_data.pop('template', None)
        
        # 设置项目关联
        if projects_ids:
            review.projects.set(projects_ids)
        
        # 设置模板关联
        if template_id:
            try:
                from .models import ReviewTemplate
                template = ReviewTemplate.objects.get(id=template_id)
                review.template = template
                review.save()
            except ReviewTemplate.DoesNotExist:
                review.template = None
                review.save()
        elif 'template' not in validated_data:
            # 不传 template 时保持原值，不做处理
            pass

        return review

    def _handle_testcases_and_reviewers(self, review, validated_data):
        """处理模块关联的测试用例和评审人员关联"""
        modules = validated_data.pop('modules', [])
        reviewers_ids = validated_data.pop('reviewers', [])
        
        # 根据模块名查询关联项目的所有用例ID
        project_ids = list(review.projects.values_list('id', flat=True))
        testcases_ids = self._resolve_testcase_ids(modules, project_ids)
        
        # 保存模块名
        review.modules = modules
        
        # 设置测试用例
        review.testcases.set(testcases_ids)
        # 同步 ReviewCase 记录
        self._create_review_cases(review, testcases_ids)
        review.save()
        
        # 设置评审人员
        if reviewers_ids:
            from apps.users.models import User
            ReviewAssignment.objects.filter(review=review).delete()
            for reviewer_id in reviewers_ids:
                try:
                    reviewer = User.objects.get(id=reviewer_id)
                    ReviewAssignment.objects.create(review=review, reviewer=reviewer)
                except User.DoesNotExist:
                    continue
        return review
    
    def create(self, validated_data):
        projects_ids = validated_data.pop('projects', [])
        modules = validated_data.pop('modules', [])
        reviewers_ids = validated_data.pop('reviewers', [])
        template_id = validated_data.pop('template', None)
        
        review = TestCaseReview.objects.create(**validated_data)
        
        # 添加项目关联
        if projects_ids:
            review.projects.set(projects_ids)
        
        # 添加模板关联
        if template_id:
            try:
                from .models import ReviewTemplate
                template = ReviewTemplate.objects.get(id=template_id)
                review.template = template
                review.save()
            except ReviewTemplate.DoesNotExist:
                pass
        
        # 根据模块名查询所有用例ID
        testcases_ids = self._resolve_testcase_ids(modules, projects_ids)
        
        # 保存模块名
        review.modules = modules
        
        # 添加测试用例
        if testcases_ids:
            review.testcases.set(testcases_ids)
            self._create_review_cases(review, testcases_ids)
        review.save()
        
        # 添加评审人员
        if reviewers_ids:
            from apps.users.models import User
            for reviewer_id in reviewers_ids:
                try:
                    reviewer = User.objects.get(id=reviewer_id)
                    ReviewAssignment.objects.create(review=review, reviewer=reviewer)
                except User.DoesNotExist:
                    continue
        
        return review
    
    def update(self, instance, validated_data):
        # 更新基本字段
        instance.title = validated_data.get('title', instance.title)
        instance.description = validated_data.get('description', instance.description)
        instance.priority = validated_data.get('priority', instance.priority)
        instance.deadline = validated_data.get('deadline', instance.deadline)
        instance.save()
        
        # 处理项目和模板关联
        self._handle_relations(instance, validated_data)
        
        # 处理测试用例和评审人员
        self._handle_testcases_and_reviewers(instance, validated_data)
        
        return instance


class ReviewTemplateCreateSerializer(serializers.ModelSerializer):
    default_reviewers = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)
    project = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    
    class Meta:
        model = ReviewTemplate
        fields = ['name', 'description', 'project', 'checklist', 'default_reviewers']
    
    def create(self, validated_data):
        default_reviewers_ids = validated_data.pop('default_reviewers', [])
        project_ids = validated_data.pop('project', [])
        template = ReviewTemplate.objects.create(**validated_data)
        
        # 添加项目关联
        if project_ids:
            template.project.set(project_ids)
        
        if default_reviewers_ids:
            template.default_reviewers.set(default_reviewers_ids)
        
        return template