from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from .models import Project, ProjectMember, ProjectEnvironment
from .serializers import ProjectSerializer, ProjectCreateSerializer, ProjectMemberSerializer, ProjectEnvironmentSerializer

class ProjectListCreateView(generics.ListCreateAPIView):
    queryset = Project.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProjectCreateSerializer
        return ProjectSerializer
    
    def get_queryset(self):
        # 默认只显示用户参与的项目或自己创建的项目
        user = self.request.user
        return Project.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_all_projects(request):
    """获取所有项目列表，用于下拉选择等场景"""
    projects = Project.objects.all().values('id', 'name', 'description', 'status')
    return Response(list(projects))

class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_project_member(request, project_id):
    try:
        project = Project.objects.get(id=project_id)
        if project.owner != request.user:
            return Response({'error': '无权限添加成员'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = ProjectMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(project=project)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Project.DoesNotExist:
        return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_project_members(request, project_id):
    """获取项目成员列表"""
    try:
        project = Project.objects.get(id=project_id)
        
        # 检查用户是否有权限查看项目成员
        if not (project.owner == request.user or 
                ProjectMember.objects.filter(project=project, user=request.user).exists()):
            return Response({'error': '无权限查看项目成员'}, status=status.HTTP_403_FORBIDDEN)
        
        # 获取项目成员，包括项目所有者
        members = []
        
        # 添加项目所有者
        members.append({
            'id': project.owner.id,
            'username': project.owner.username,
            'email': project.owner.email,
            'first_name': project.owner.first_name,
            'last_name': project.owner.last_name,
            'role': 'owner'
        })
        
        # 添加项目成员
        project_members = ProjectMember.objects.filter(project=project).select_related('user')
        for member in project_members:
            members.append({
                'id': member.id,  # ProjectMember ID，用于删除操作
                'user_id': member.user.id,  # User ID
                'username': member.user.username,
                'email': member.user.email,
                'first_name': member.user.first_name,
                'last_name': member.user.last_name,
                'role': member.role
            })
        
        return Response(members)
    except Project.DoesNotExist:
        return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def project_member_detail(request, project_id, member_id):
    """项目成员详情：更新角色(PATCH) / 删除成员(DELETE)"""
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)
    
    # 只有项目负责人才能管理成员
    if project.owner != request.user:
        return Response({'error': '无权限管理成员'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        member = ProjectMember.objects.get(id=member_id, project=project)
    except ProjectMember.DoesNotExist:
        return Response({'error': '成员不存在'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'DELETE':
        member.delete()
        return Response({'message': '成员删除成功'})
    
    elif request.method == 'PATCH':
        # 更新成员角色
        new_role = request.data.get('role', '').strip()
        valid_roles = [choice[0] for choice in ProjectMember.ROLE_CHOICES if choice[0] != 'owner']
        if new_role not in valid_roles:
            return Response(
                {'error': f'无效的角色，可选值: {", ".join(valid_roles)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        member.role = new_role
        member.save()
        return Response({
            'id': member.id,
            'user_id': member.user.id,
            'username': member.user.username,
            'email': member.user.email,
            'role': member.role,
            'joined_at': member.joined_at
        })

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_project_owner(request, project_id):
    """更改项目负责人"""
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)
    
    # 只有当前负责人才能移交权限
    if project.owner != request.user:
        return Response({'error': '只有项目负责人才能更改负责人'}, status=status.HTTP_403_FORBIDDEN)
    
    new_owner_id = request.data.get('user_id')
    if not new_owner_id:
        return Response({'error': '请提供新负责人的 user_id'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        from apps.users.models import User
        new_owner = User.objects.get(id=new_owner_id)
    except Exception:
        return Response({'error': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
    
    if new_owner == project.owner:
        return Response({'error': '新负责人不能是当前负责人'}, status=status.HTTP_400_BAD_REQUEST)
    
    old_owner = project.owner
    
    # 检查新负责人是否已经是项目成员
    if not ProjectMember.objects.filter(project=project, user=new_owner).exists():
        # 如果还不是成员，先添加为成员
        ProjectMember.objects.create(project=project, user=new_owner, role='admin')
    
    # 更改项目负责人
    project.owner = new_owner
    project.save()
    
    # 将旧负责人添加为成员（如果还不是），角色设为 admin
    ProjectMember.objects.get_or_create(
        project=project, 
        user=old_owner, 
        defaults={'role': 'admin'}
    )
    
    return Response({
        'message': '负责人更改成功',
        'owner': {
            'id': new_owner.id,
            'username': new_owner.username,
            'email': new_owner.email,
        }
    })

class ProjectEnvironmentListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectEnvironmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        project_id = self.kwargs['project_id']
        return ProjectEnvironment.objects.filter(project_id=project_id)
    
    def perform_create(self, serializer):
        project_id = self.kwargs['project_id']
        serializer.save(project_id=project_id)