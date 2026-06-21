from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from django.db import transaction
from django.db import models
from django.db.models import Count, Q
from .models import TestPlan, TestRun, TestRunCase, TestRunCaseHistory
from apps.testcases.models import TestCase
from apps.projects.models import Project
from apps.projects.helpers import get_user_accessible_projects
from .serializers import (TestPlanSerializer, TestRunSerializer, TestRunCaseSerializer, 
                         TestPlanDetailSerializer, TestRunCaseDetailSerializer, 
                         TestRunCaseHistorySerializer)

class TestPlanViewSet(viewsets.ModelViewSet):
    """
    测试计划视图集
    """
    queryset = TestPlan.objects.all().order_by('-created_at')
    serializer_class = TestPlanSerializer

    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        return TestPlan.objects.filter(
            projects__in=accessible_projects
        ).distinct().order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TestPlanDetailSerializer
        return TestPlanSerializer

    def _sync_test_runs(self, test_plan, project_ids, testcase_ids):
        if not project_ids:
            test_plan.projects.clear()
            test_plan.test_runs.all().delete()
            return

        valid_projects = list(Project.objects.filter(id__in=project_ids))
        valid_project_ids = [project.id for project in valid_projects]
        test_plan.projects.set(valid_project_ids)

        testcase_queryset = TestCase.objects.filter(
            id__in=testcase_ids,
            project_id__in=valid_project_ids
        ).select_related('project')
        testcase_map = {testcase.id: testcase for testcase in testcase_queryset}

        existing_runs = {test_run.project_id: test_run for test_run in test_plan.test_runs.all()}

        for project_id, test_run in list(existing_runs.items()):
            if project_id not in valid_project_ids:
                test_run.delete()
                existing_runs.pop(project_id, None)

        for project in valid_projects:
            test_run = existing_runs.get(project.id)
            if not test_run:
                test_run = TestRun.objects.create(
                    name=f"{test_plan.name} - {project.name} Execution",
                    test_plan=test_plan,
                    project=project,
                    version=test_plan.version,
                    creator=test_plan.creator,
                    assignee=test_plan.creator
                )
                existing_runs[project.id] = test_run
            else:
                test_run.name = f"{test_plan.name} - {project.name} Execution"
                test_run.version = test_plan.version
                test_run.save(update_fields=['name', 'version', 'updated_at'])

            run_testcases = [testcase for testcase in testcase_queryset if testcase.project_id == project.id]
            TestRunCase.objects.filter(test_run=test_run).exclude(
                testcase_id__in=[testcase.id for testcase in run_testcases]
            ).delete()

            existing_case_ids = set(
                TestRunCase.objects.filter(test_run=test_run).values_list('testcase_id', flat=True)
            )
            new_cases = [
                TestRunCase(
                    test_run=test_run,
                    testcase=testcase,
                    priority=testcase.priority
                )
                for testcase in run_testcases
                if testcase.id not in existing_case_ids
            ]
            if new_cases:
                TestRunCase.objects.bulk_create(new_cases)

            test_run.testcases.set([testcase.id for testcase in run_testcases])

    def perform_create(self, serializer):
        # 在创建TestPlan时，设置creator并自动为每个项目创建TestRun和TestRunCase
        # 获取版本信息
        version_id = self.request.data.get('version')
        version = None
        if version_id:
            from apps.versions.models import Version
            try:
                version = Version.objects.get(id=version_id)
            except Version.DoesNotExist:
                pass
        
        test_plan = serializer.save(creator=self.request.user, version=version)

        # 只允许用户有权限的项目
        accessible_projects = get_user_accessible_projects(self.request.user)
        accessible_project_ids = set(accessible_projects.values_list('id', flat=True))
        project_ids = [pid for pid in self.request.data.get('projects', []) if int(pid) in accessible_project_ids]
        testcase_ids = self.request.data.get('testcases', [])
        self._sync_test_runs(test_plan, project_ids, testcase_ids)

    @action(detail=False, methods=['get'])
    def testcases_by_projects(self, request):
        """
        根据项目获取测试用例
        """
        project_ids = request.query_params.getlist('project_ids')
        if not project_ids:
            return Response({
                'error': '请先选择项目',
                'detail': '请先选择项目后再选择测试用例'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 过滤数字字符串和空值
            project_ids = [int(pid) for pid in project_ids if pid and pid.isdigit()]
            
            if not project_ids:
                return Response({
                    'error': '无效的项目 ID',
                    'detail': '请选择有效的项目'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 只返回用户有权限访问的项目的测试用例
            accessible_projects = get_user_accessible_projects(request.user)
            accessible_project_ids = set(accessible_projects.values_list('id', flat=True))
            allowed_project_ids = [pid for pid in project_ids if pid in accessible_project_ids]
            
            if not allowed_project_ids:
                return Response({
                    'error': '没有权限访问所选项目',
                    'detail': '您未加入所选项目'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # 获取指定项目的测试用例
            testcases = TestCase.objects.filter(
                project_id__in=allowed_project_ids,
                status__in=['draft', 'active']  # 包含草稿和激活状态的测试用例
            ).values('id', 'title', 'priority', 'test_type', 'project__name', 'module')
            
            return Response({
                'results': list(testcases)
            })
            
        except ValueError:
            return Response({
                'error': '项目 ID 格式错误',
                'detail': '请提供有效的项目 ID'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': '获取测试用例失败',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_update(self, serializer):
        # 在更新TestPlan时，处理版本信息
        version_id = self.request.data.get('version')
        version = None
        if version_id:
            from apps.versions.models import Version
            try:
                version = Version.objects.get(id=version_id)
            except Version.DoesNotExist:
                pass
        
        with transaction.atomic():
            test_plan = serializer.save(version=version)

            # 只允许用户有权限的项目
            accessible_projects = get_user_accessible_projects(self.request.user)
            accessible_project_ids = set(accessible_projects.values_list('id', flat=True))
            project_ids = [pid for pid in self.request.data.get('projects', []) if int(pid) in accessible_project_ids]
            testcase_ids = self.request.data.get('testcases', [])
            self._sync_test_runs(test_plan, project_ids, testcase_ids)

            assignee_ids = self.request.data.get('assignees', [])
            if assignee_ids:
                test_plan.assignees.set(assignee_ids)
            else:
                test_plan.assignees.clear()


class TestRunViewSet(viewsets.ModelViewSet):
    """
    测试执行视图集
    """
    queryset = TestRun.objects.all().order_by('-created_at')
    serializer_class = TestRunSerializer

    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        return TestRun.objects.filter(
            models.Q(project__in=accessible_projects) |
            models.Q(test_plan__projects__in=accessible_projects)
        ).distinct().order_by('-created_at')

class TestRunCaseViewSet(viewsets.ModelViewSet):
    """
    测试执行用例视图集
    """
    queryset = TestRunCase.objects.all()
    serializer_class = TestRunCaseSerializer

    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        return TestRunCase.objects.filter(
            models.Q(test_run__project__in=accessible_projects) |
            models.Q(test_run__test_plan__projects__in=accessible_projects)
        ).distinct()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TestRunCaseDetailSerializer
        return TestRunCaseSerializer

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """
        更新单个用例的执行状态，并自动创建历史记录
        """
        run_case = self.get_object()
        new_status = request.data.get('status')
        actual_result = request.data.get('actual_result', '')
        comments = request.data.get('comments', '')
        
        if not new_status:
            return Response({'error': 'Status is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 创建历史记录
        TestRunCaseHistory.objects.create(
            run_case=run_case,
            status=new_status,
            actual_result=actual_result,
            comments=comments,
            executed_by=request.user,
            executed_at=timezone.now()
        )
        
        # 更新执行用例状态
        run_case.status = new_status
        run_case.actual_result = actual_result
        run_case.comments = comments
        run_case.executed_by = request.user
        run_case.executed_at = timezone.now()
        run_case.save()
        
        # 更新关联的测试执行状态
        self._update_run_status(run_case.test_run)
        
        return Response(TestRunCaseDetailSerializer(run_case).data)

    @action(detail=False, methods=['post'], url_path='batch_update_status')
    def batch_update_status(self, request):
        """批量更新测试执行用例状态（优化版：bulk_create + update + 聚合统计）"""
        ids = request.data.get('ids', [])
        new_status = request.data.get('status')
        comments = request.data.get('comments', '')
        
        if not ids:
            return Response({'error': '请提供要更新的用例ID列表'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status not in dict(TestRunCase.STATUS_CHOICES):
            return Response({'error': '无效的执行状态'}, status=status.HTTP_400_BAD_REQUEST)
        
        now = timezone.now()
        
        # 先获取 run_case 的 id 和 test_run_id 用于创建历史和后续聚合
        run_cases_qs = TestRunCase.objects.filter(id__in=ids).values('id', 'test_run_id')
        run_cases = list(run_cases_qs)
        if not run_cases:
            return Response({'error': '未找到匹配的执行用例'}, status=status.HTTP_404_NOT_FOUND)
        
        # 1. 批量创建历史记录（1条SQL）
        history_objects = [
            TestRunCaseHistory(
                run_case_id=rc['id'],
                status=new_status,
                actual_result='',
                comments=comments,
                executed_by=request.user,
                executed_at=now
            )
            for rc in run_cases
        ]
        TestRunCaseHistory.objects.bulk_create(history_objects)
        
        # 2. 批量更新状态（1条SQL）
        updated_count = TestRunCase.objects.filter(id__in=ids).update(
            status=new_status,
            comments=comments,
            executed_by=request.user,
            executed_at=now,
            updated_at=now
        )
        
        # 3. 收集受影响的 run_ids 并批量更新 TestRun 状态
        run_ids = list(set(rc['test_run_id'] for rc in run_cases))
        self._batch_update_run_statuses(run_ids)
        
        return Response({
            'message': '批量状态更新完成',
            'updated_count': updated_count,
            'status': new_status
        })
    
    def _batch_update_run_statuses(self, run_ids):
        """批量更新多个 TestRun 的整体状态（聚合查询 + bulk_update）"""
        if not run_ids:
            return
        
        # 一次聚合查询获取所有 TestRun 的统计信息
        stats = TestRunCase.objects.filter(test_run_id__in=run_ids).values('test_run_id').annotate(
            total=Count('id'),
            untested=Count('id', filter=Q(status='untested')),
            tested=Count('id', filter=~Q(status='untested')),
        )
        
        # 一次查询加载所有涉及的 TestRun
        runs_map = TestRun.objects.in_bulk(
            [s['test_run_id'] for s in stats], field_name='id'
        )
        
        now = timezone.now()
        runs_to_update = []
        
        for stat in stats:
            run_id = stat['test_run_id']
            test_run = runs_map.get(run_id)
            if not test_run:
                continue
            
            total = stat['total']
            untested = stat['untested']
            tested = stat['tested']
            
            if total == 0:
                test_run.status = 'untested'
            elif untested == total:
                test_run.status = 'untested'
                test_run.completed_at = None
            elif tested >= total:
                test_run.status = 'completed'
                test_run.completed_at = now
            else:
                test_run.status = 'in_progress'
                test_run.started_at = test_run.started_at or now
                test_run.completed_at = None
            
            test_run.updated_at = now
            runs_to_update.append(test_run)
        
        if runs_to_update:
            TestRun.objects.bulk_update(
                runs_to_update, 
                ['status', 'started_at', 'completed_at', 'updated_at']
            )
    
    def _update_run_status(self, test_run):
        """根据执行用例状态更新 TestRun 的整体状态（单个用）"""
        stats = test_run.progress_stats
        total = stats['total']
        if total == 0:
            test_run.status = 'untested'
            test_run.save()
            return
        
        if stats['untested'] == total:
            test_run.status = 'untested'
        elif stats['tested'] >= total:
            test_run.status = 'completed'
            test_run.completed_at = timezone.now()
        else:
            test_run.status = 'in_progress'
            test_run.started_at = test_run.started_at or timezone.now()
        
        test_run.save()

    @action(detail=True, methods=['patch'])
    def update_testcase(self, request, pk=None):
        """
        更新关联的测试用例数据（标题、前置条件、操作步骤、预期结果、优先级）
        调用方通过 TestRunCase ID 定位并修改关联的 TestCase
        """
        run_case = self.get_object()
        testcase = run_case.testcase
        if not testcase:
            return Response({'error': '关联的测试用例不存在'}, status=status.HTTP_404_NOT_FOUND)

        updatable_fields = ['title', 'preconditions', 'steps', 'expected_result', 'priority', 'description']
        changed = False
        for field in updatable_fields:
            if field in request.data:
                setattr(testcase, field, request.data[field])
                changed = True
        if not changed:
            return Response({'error': '没有可更新的字段'}, status=status.HTTP_400_BAD_REQUEST)
        testcase.save(update_fields=[f for f in updatable_fields if f in request.data] + ['updated_at'])
        return Response({'message': '用例数据更新成功'})

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        获取用例执行历史记录
        """
        run_case = self.get_object()
        history = run_case.history.all().order_by('-executed_at')
        serializer = TestRunCaseHistorySerializer(history, many=True)
        return Response(serializer.data)

class TestRunCaseHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    测试执行历史视图集（只读）
    """
    queryset = TestRunCaseHistory.objects.all().order_by('-executed_at')
    serializer_class = TestRunCaseHistorySerializer

    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        return TestRunCaseHistory.objects.filter(
            models.Q(run_case__test_run__project__in=accessible_projects) |
            models.Q(run_case__test_run__test_plan__projects__in=accessible_projects)
        ).distinct().order_by('-executed_at')
