from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Q
from .models import TestCaseReview, ReviewAssignment, TestCaseReviewComment, ReviewTemplate, ReviewCase, ReviewCaseHistory
from .serializers import (
    TestCaseReviewSerializer, TestCaseReviewCreateSerializer,
    ReviewAssignmentSerializer, TestCaseReviewCommentSerializer, 
    TestCaseReviewCommentCreateSerializer,
    ReviewTemplateSerializer, ReviewTemplateCreateSerializer,
    ReviewCaseSerializer, ReviewCaseListSerializer,
    ReviewCaseHistorySerializer
)
from apps.testcases.models import TestCase
from apps.users.models import User
from apps.projects.helpers import get_user_accessible_projects


class TestCaseReviewViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return TestCaseReviewCreateSerializer
        return TestCaseReviewSerializer
    
    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        
        queryset = TestCaseReview.objects.select_related('creator').prefetch_related(
            'projects', 'testcases', 'reviewers', 'comments', 'reviewassignment_set__reviewer'
        ).filter(
            projects__in=accessible_projects
        ).distinct()
        
        # 过滤参数
        project_id = self.request.query_params.get('project', None)
        status_param = self.request.query_params.get('status', None)
        reviewer_id = self.request.query_params.get('reviewer', None)
        
        if project_id:
            queryset = queryset.filter(projects__id=project_id)
        if status_param:
            queryset = queryset.filter(status=status_param)
        if reviewer_id:
            queryset = queryset.filter(reviewers__id=reviewer_id)
            
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)
    
    @action(detail=True, methods=['post'])
    def assign_reviewers(self, request, pk=None):
        """分配评审人员"""
        review = self.get_object()
        reviewer_ids = request.data.get('reviewer_ids', [])
        
        for reviewer_id in reviewer_ids:
            try:
                reviewer = User.objects.get(id=reviewer_id)
                ReviewAssignment.objects.get_or_create(
                    review=review,
                    reviewer=reviewer,
                    defaults={'assigned_at': timezone.now()}
                )
            except User.DoesNotExist:
                continue
                
        return Response({'message': '评审人员分配成功'})
    
    @action(detail=True, methods=['post'])
    def submit_review(self, request, pk=None):
        """提交评审结果"""
        review = self.get_object()
        try:
            assignment = ReviewAssignment.objects.get(
                review=review, 
                reviewer=request.user
            )
            assignment.status = request.data.get('status', 'approved')
            assignment.comment = request.data.get('comment', '')
            assignment.checklist_results = request.data.get('checklist_results', {})
            assignment.reviewed_at = timezone.now()
            assignment.save()
            
            # 检查是否所有评审人都已完成评审
            pending_count = ReviewAssignment.objects.filter(
                review=review, 
                status='pending'
            ).count()
            
            if pending_count == 0:
                # 检查评审结果，如果所有人都通过则设为已通过
                approved_count = ReviewAssignment.objects.filter(
                    review=review, 
                    status='approved'
                ).count()
                total_count = ReviewAssignment.objects.filter(review=review).count()
                
                if approved_count == total_count:
                    review.status = 'approved'
                else:
                    review.status = 'rejected'
                    
                review.completed_at = timezone.now()
                review.save()
                
            return Response({'message': '评审提交成功'})
            
        except ReviewAssignment.DoesNotExist:
            return Response(
                {'error': '您未被分配为此评审的评审人'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    @action(detail=False, methods=['get'])
    def my_reviews(self, request):
        """获取我的评审任务"""
        reviews = TestCaseReview.objects.filter(
            reviewers=request.user
        ).select_related('creator').prefetch_related('projects')
        
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def sync_review_cases(self, request, pk=None):
        """同步评审用例：根据模块名重新查询所有用例，刷新ReviewCase记录"""
        review = self.get_object()
        modules = review.modules or []
        
        if not modules:
            return Response({'message': '评审未设置模块，无需同步', 'synced_count': 0})
        
        from apps.testcases.models import TestCase
        project_ids = list(review.projects.values_list('id', flat=True))
        
        # 查询模块下所有用例ID
        testcase_ids = list(TestCase.objects.filter(
            project_id__in=project_ids,
            module__in=modules
        ).values_list('id', flat=True).distinct())
        
        # 更新 M2M
        review.testcases.set(testcase_ids)
        
        # 同步 ReviewCase：添加新用例，删除已移除的
        existing_ids = set(ReviewCase.objects.filter(review=review).values_list('testcase_id', flat=True))
        new_ids = [tid for tid in testcase_ids if tid not in existing_ids]
        
        if new_ids:
            testcases = TestCase.objects.filter(id__in=new_ids)
            ReviewCase.objects.bulk_create([ReviewCase(review=review, testcase=tc) for tc in testcases])
        
        removed_count = ReviewCase.objects.filter(review=review).exclude(testcase_id__in=testcase_ids).count()
        ReviewCase.objects.filter(review=review).exclude(testcase_id__in=testcase_ids).delete()
        
        return Response({
            'message': '同步完成',
            'total_cases': len(testcase_ids),
            'added': len(new_ids),
            'removed': removed_count,
            'modules': modules
        })


class TestCaseReviewCommentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return TestCaseReviewCommentCreateSerializer
        return TestCaseReviewCommentSerializer
    
    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        
        review_id = self.request.query_params.get('review', None)
        testcase_id = self.request.query_params.get('testcase', None)
        
        queryset = TestCaseReviewComment.objects.select_related('author', 'testcase', 'review').filter(
            review__projects__in=accessible_projects
        ).distinct()
        
        if review_id:
            queryset = queryset.filter(review_id=review_id)
        if testcase_id:
            queryset = queryset.filter(testcase_id=testcase_id)
            
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ReviewTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ReviewTemplateCreateSerializer
        return ReviewTemplateSerializer
    
    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        
        project_id = self.request.query_params.get('project', None)
        queryset = ReviewTemplate.objects.select_related('creator').prefetch_related('project', 'default_reviewers').filter(
            project__in=accessible_projects
        ).distinct()
        
        if project_id:
            queryset = queryset.filter(project__id=project_id)
            
        return queryset.filter(is_active=True)
    
    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)


class ReviewCaseViewSet(viewsets.ModelViewSet):
    """逐用例评审 ViewSet"""
    permission_classes = [permissions.IsAuthenticated]
    queryset = ReviewCase.objects.all()
    pagination_class = None  # 禁用分页，让前端获取全部用例自行分页
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ReviewCaseListSerializer
        return ReviewCaseSerializer
    
    def get_queryset(self):
        review_id = self.request.query_params.get('review', None)
        queryset = ReviewCase.objects.select_related('testcase', 'reviewed_by').prefetch_related('history')
        if review_id:
            queryset = queryset.filter(review_id=review_id)
        return queryset.order_by('testcase__id')
    
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """更新评审状态"""
        review_case = self.get_object()
        new_status = request.data.get('status')
        comments = request.data.get('comments', '')
        
        if new_status not in dict(ReviewCase.STATUS_CHOICES):
            return Response({'error': '无效的评审状态'}, status=status.HTTP_400_BAD_REQUEST)
        
        review_case.status = new_status
        review_case.comments = comments
        review_case.reviewed_by = request.user
        review_case.reviewed_at = timezone.now()
        review_case.save()
        
        # 记录历史
        ReviewCaseHistory.objects.create(
            review_case=review_case,
            status=new_status,
            comments=comments,
            reviewed_by=request.user
        )
        
        # 更新评审整体状态
        self._update_review_status(review_case.review)
        
        serializer = ReviewCaseSerializer(review_case)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """获取评审历史"""
        review_case = self.get_object()
        history = review_case.history.all()
        return Response(ReviewCaseHistorySerializer(history, many=True).data)
    
    @action(detail=True, methods=['patch'])
    def update_testcase(self, request, pk=None):
        """更新关联的测试用例内容"""
        review_case = self.get_object()
        testcase = review_case.testcase
        
        allowed_fields = ['title', 'preconditions', 'steps', 'expected_result', 'priority']
        for field in allowed_fields:
            if field in request.data:
                setattr(testcase, field, request.data[field])
        
        testcase.save()
        serializer = ReviewCaseListSerializer(review_case)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], url_path='batch_update_status')
    def batch_update_status(self, request):
        """批量更新评审用例状态（优化版：bulk_create + update + 聚合统计）"""
        ids = request.data.get('ids', [])
        new_status = request.data.get('status')
        comments = request.data.get('comments', '')
        
        if not ids:
            return Response({'error': '请提供要更新的用例ID列表'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status not in dict(ReviewCase.STATUS_CHOICES):
            return Response({'error': '无效的评审状态'}, status=status.HTTP_400_BAD_REQUEST)
        
        now = timezone.now()
        
        # 先获取 review_case 的 id 和 review_id 用于创建历史和后续聚合
        review_cases_qs = ReviewCase.objects.filter(id__in=ids).values('id', 'review_id')
        review_cases = list(review_cases_qs)
        if not review_cases:
            return Response({'error': '未找到匹配的评审用例'}, status=status.HTTP_404_NOT_FOUND)
        
        # 1. 批量创建历史记录（1条SQL）
        history_objects = [
            ReviewCaseHistory(
                review_case_id=rc['id'],
                status=new_status,
                comments=comments,
                reviewed_by=request.user,
                reviewed_at=now
            )
            for rc in review_cases
        ]
        ReviewCaseHistory.objects.bulk_create(history_objects)
        
        # 2. 批量更新状态（1条SQL）
        updated_count = ReviewCase.objects.filter(id__in=ids).update(
            status=new_status,
            comments=comments,
            reviewed_by=request.user,
            reviewed_at=now,
            updated_at=now
        )
        
        # 3. 收集受影响的 review_ids 并批量更新评审状态
        review_ids = list(set(rc['review_id'] for rc in review_cases))
        self._batch_update_review_statuses(review_ids)
        
        return Response({
            'message': '批量状态更新完成',
            'updated_count': updated_count,
            'status': new_status
        })
    
    def _batch_update_review_statuses(self, review_ids):
        """批量更新多个评审的整体状态（聚合查询 + bulk_update）"""
        if not review_ids:
            return
        
        # 一次聚合查询获取所有评审的统计信息
        stats = ReviewCase.objects.filter(review_id__in=review_ids).values('review_id').annotate(
            total=Count('id'),
            unreviewed=Count('id', filter=Q(status='unreviewed')),
            failed=Count('id', filter=Q(status='failed')),
        )
        
        # 一次查询加载所有涉及的评审
        reviews_map = TestCaseReview.objects.in_bulk(
            [s['review_id'] for s in stats], field_name='id'
        )
        
        now = timezone.now()
        reviews_to_update = []
        
        for stat in stats:
            review_id = stat['review_id']
            review = reviews_map.get(review_id)
            if not review:
                continue
            
            total = stat['total']
            if total == 0:
                continue
            
            unreviewed = stat['unreviewed']
            failed = stat['failed']
            reviewed = total - unreviewed
            
            if reviewed == 0:
                continue  # 没有已评审的，保持原状态
            
            review.updated_at = now
            
            if reviewed < total:
                review.status = 'in_progress'
                review.completed_at = None
            elif failed > 0:
                review.status = 'rejected'
                review.completed_at = now
            else:
                review.status = 'approved'
                review.completed_at = now
            
            reviews_to_update.append(review)
        
        if reviews_to_update:
            TestCaseReview.objects.bulk_update(
                reviews_to_update, 
                ['status', 'completed_at', 'updated_at']
            )
    
    def _update_review_status(self, review):
        """根据逐用例评审结果更新整体评审状态（单个用）"""
        total = review.review_cases.count()
        if total == 0:
            return
        reviewed = review.review_cases.exclude(status='unreviewed').count()
        if reviewed == 0:
            return
        
        failed = review.review_cases.filter(status='failed').count()
        
        if reviewed < total:
            review.status = 'in_progress'
        elif failed > 0:
            review.status = 'rejected'
        else:
            review.status = 'approved'
        
        if reviewed == total:
            review.completed_at = timezone.now()
        else:
            review.completed_at = None
        
        review.save()