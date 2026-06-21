from django.http import FileResponse
from rest_framework import generics, permissions, status, pagination
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView

from .models import TestCase, TestCaseStep, TestCaseAttachment, TestCaseComment, TestCaseImportRecord
from .serializers import (
    TestCaseSerializer, TestCaseListSerializer, TestCaseCreateSerializer, TestCaseUpdateSerializer,
    TestCaseImportRecordListSerializer, TestCaseImportRecordDetailSerializer,
    BatchDeleteSerializer, BatchUpdateSerializer
)
from apps.projects.models import Project
from apps.projects.helpers import get_user_accessible_projects
from apps.versions.models import Version
from .services import TestCaseImportTemplateService, TestCaseExcelImportService
from .tasks import import_testcases_from_excel

class TestCasePagination(pagination.PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class TestCaseImportRecordPagination(pagination.PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class TestCaseListCreateView(generics.ListCreateAPIView):
    queryset = TestCase.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = TestCasePagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['priority', 'test_type', 'project']
    search_fields = ['title', 'description', 'module', 'preconditions', 'steps', 'expected_result']
    ordering_fields = ['created_at', 'updated_at', 'priority']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TestCaseCreateSerializer
        return TestCaseListSerializer
    
    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        queryset = TestCase.objects.filter(
            project__in=accessible_projects
        ).select_related(
            'author', 'assignee', 'project'
        ).prefetch_related(
            'versions'
        ).distinct()
        
        # 按关联版本筛选
        version = self.request.query_params.get('version', None)
        if version:
            queryset = queryset.filter(versions__id=version)
        
        # 按模块名称筛选（模糊匹配）
        module = self.request.query_params.get('module', None)
        if module:
            queryset = queryset.filter(module__icontains=module)
        
        return queryset
    
    def get_user_accessible_projects(self, user):
        """获取用户有权限访问的项目"""
        return get_user_accessible_projects(user)
    
    def perform_create(self, serializer):
        user = self.request.user
        project_id = self.request.data.get('project_id')
        
        # 获取用户有权限的项目
        accessible_projects = self.get_user_accessible_projects(user)
        
        if project_id:
            # 检查指定的项目是否存在且用户有权限
            try:
                project = accessible_projects.get(id=project_id)
            except Project.DoesNotExist:
                # 如果指定项目不存在或无权限，使用第一个可访问的项目
                project = accessible_projects.first()
                if not project:
                    # 如果用户没有任何项目，创建默认项目
                    project = Project.objects.create(
                        name="默认项目",
                        owner=user,
                        description='系统自动创建的默认项目'
                    )
        else:
            # 没有指定项目，使用第一个可访问的项目
            project = accessible_projects.first()
            if not project:
                # 如果用户没有任何项目，创建默认项目
                project = Project.objects.create(
                    name="默认项目",
                    owner=user,
                    description='系统自动创建的默认项目'
                )
        
        serializer.save(author=user, project=project)

class TestCaseDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = TestCase.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return TestCaseUpdateSerializer
        return TestCaseSerializer
    
    def get_queryset(self):
        user = self.request.user
        accessible_projects = get_user_accessible_projects(user)
        return TestCase.objects.filter(
            project__in=accessible_projects
        ).select_related(
            'author', 'assignee', 'project'
        ).prefetch_related(
            'versions', 'step_details', 'attachments', 'comments'
        )
    
    def get_user_accessible_projects(self, user):
        """获取用户有权限访问的项目"""
        return get_user_accessible_projects(user)
    
    def perform_update(self, serializer):
        user = self.request.user
        project_id = self.request.data.get('project_id')
        
        if project_id:
            # 检查指定的项目是否存在且用户有权限
            accessible_projects = self.get_user_accessible_projects(user)
            try:
                project = accessible_projects.get(id=project_id)
                serializer.save(project=project)
            except Project.DoesNotExist:
                # 如果指定项目不存在或无权限，保持原项目不变
                serializer.save()
        else:
            # 没有指定项目，保持原项目不变
            serializer.save()


class TestCaseImportTemplateDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        template_stream = TestCaseImportTemplateService.build_template()
        return FileResponse(
            template_stream,
            as_attachment=True,
            filename='testcase_import_template_v1.xlsx',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )


class TestCaseImportRecordListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = TestCaseImportRecordPagination
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        return TestCaseImportRecordListSerializer

    def get_queryset(self):
        return TestCaseImportRecord.objects.filter(
            project__in=get_user_accessible_projects(self.request.user)
        ).select_related('project', 'created_by')

    def create(self, request, *args, **kwargs):
        project_id = request.data.get('project_id')
        import_file = request.FILES.get('file')
        version_ids_str = request.data.get('version_ids', '')

        if not project_id:
            return Response({'error': '请选择导入项目'}, status=status.HTTP_400_BAD_REQUEST)
        if not import_file:
            return Response({'error': '请上传 Excel 文件'}, status=status.HTTP_400_BAD_REQUEST)
        if not import_file.name.lower().endswith('.xlsx'):
            return Response({'error': '仅支持 .xlsx 格式文件'}, status=status.HTTP_400_BAD_REQUEST)

        # 解析版本ID列表
        try:
            version_ids = [int(v.strip()) for v in str(version_ids_str).split(',') if v.strip()]
        except (ValueError, TypeError):
            return Response({'error': '版本ID格式错误'}, status=status.HTTP_400_BAD_REQUEST)

        accessible_projects = get_user_accessible_projects(request.user)
        try:
            project = accessible_projects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': '项目不存在或无权限访问'}, status=status.HTTP_403_FORBIDDEN)

        # 校验所选版本是否属于该项目
        if version_ids:
            valid_version_ids = set(
                Version.objects.filter(id__in=version_ids, projects=project)
                .values_list('id', flat=True)
            )
            if len(valid_version_ids) != len(version_ids):
                return Response({'error': '部分版本不属于所选项目'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            valid_version_ids = []

        record = TestCaseImportRecord.objects.create(
            import_no=TestCaseExcelImportService.generate_import_no(),
            project=project,
            import_file=import_file,
            created_by=request.user,
            template_version='v1'
        )

        celery_task = import_testcases_from_excel.delay(record.id, list(valid_version_ids))
        record.celery_task_id = celery_task.id
        record.save(update_fields=['celery_task_id', 'updated_at'])

        serializer = self.get_serializer(record)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TestCaseImportRecordDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TestCaseImportRecordDetailSerializer
    queryset = TestCaseImportRecord.objects.select_related('project', 'created_by')

    def get_queryset(self):
        return super().get_queryset().filter(
            project__in=get_user_accessible_projects(self.request.user)
        )


class TestCaseImportFailureReportDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        record = TestCaseImportRecord.objects.filter(
            pk=pk,
            project__in=get_user_accessible_projects(request.user)
        ).first()

        if not record:
            return Response({'error': '导入记录不存在'}, status=status.HTTP_404_NOT_FOUND)
        if not record.failure_report_file:
            return Response({'error': '当前记录没有失败明细文件'}, status=status.HTTP_404_NOT_FOUND)

        return FileResponse(
            record.failure_report_file.open('rb'),
            as_attachment=True,
            filename=record.failure_report_file.name.split('/')[-1],
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )


class TestCaseModuleStatsView(APIView):
    """获取模块统计信息（按项目+版本）"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project')
        version_id = request.query_params.get('version')

        if not project_id:
            return Response({'error': 'project 参数必填'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        accessible_projects = get_user_accessible_projects(user)

        try:
            accessible_projects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': '项目不存在或无权限'}, status=status.HTTP_403_FORBIDDEN)

        queryset = TestCase.objects.filter(project_id=project_id)
        if version_id:
            queryset = queryset.filter(versions__id=version_id)

        modules = (
            queryset
            .values('module')
            .annotate(count=models.Count('id'))
            .order_by('module')
        )

        # 过滤空模块名并格式化返回
        result = [
            {'module': m['module'] or '默认模块', 'count': m['count']}
            for m in modules
        ]

        return Response({
            'project_id': int(project_id),
            'version_id': int(version_id) if version_id else None,
            'total_modules': len(result),
            'total_cases': sum(m['count'] for m in result),
            'modules': result
        })


class TestCaseBatchDeleteView(APIView):
    """批量删除测试用例"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = BatchDeleteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ids = serializer.validated_data['ids']
        accessible_projects = get_user_accessible_projects(request.user)

        # 只删除用户有权限访问的项目下的用例
        testcases = TestCase.objects.filter(
            id__in=ids,
            project__in=accessible_projects
        )

        deleted_count = testcases.count()
        testcases.delete()

        not_found_count = len(ids) - deleted_count
        return Response({
            'deleted_count': deleted_count,
            'not_found_count': not_found_count,
            'message': f'成功删除 {deleted_count} 个用例' + (f'，{not_found_count} 个用例无权限或不存在' if not_found_count > 0 else '')
        })


class TestCaseBatchUpdateView(APIView):
    """批量修改测试用例（关联项目和版本）"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = BatchUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ids = serializer.validated_data['ids']
        project_id = serializer.validated_data.get('project_id')
        version_ids = serializer.validated_data.get('version_ids')

        accessible_projects = get_user_accessible_projects(request.user)

        # 验证项目权限
        if project_id:
            try:
                target_project = accessible_projects.get(id=project_id)
            except Project.DoesNotExist:
                return Response({'error': '目标项目不存在或无权限访问'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            target_project = None

        # 验证版本
        if version_ids is not None:
            valid_version_ids = set(
                Version.objects.filter(id__in=version_ids).values_list('id', flat=True)
            )
            if len(valid_version_ids) != len(version_ids):
                return Response({'error': '部分版本ID不存在'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            valid_version_ids = None

        # 只修改用户有权限访问的项目下的用例
        testcases = TestCase.objects.filter(
            id__in=ids,
            project__in=accessible_projects
        )

        updated_count = 0
        for tc in testcases:
            if target_project:
                tc.project = target_project
            if valid_version_ids is not None:
                tc.versions.set(valid_version_ids)
            tc.save()
            updated_count += 1

        not_found_count = len(ids) - updated_count
        return Response({
            'updated_count': updated_count,
            'not_found_count': not_found_count,
            'message': f'成功修改 {updated_count} 个用例' + (f'，{not_found_count} 个用例无权限或不存在' if not_found_count > 0 else '')
        })
