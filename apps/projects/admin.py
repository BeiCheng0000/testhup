from django.contrib import admin
from .models import Project, ProjectMember, ProjectEnvironment


class ProjectMemberInline(admin.TabularInline):
    """项目成员内联管理"""
    model = ProjectMember
    extra = 1
    fields = ['user', 'role', 'joined_at']
    readonly_fields = ['joined_at']
    raw_id_fields = ['user']
    ordering = ['role', 'joined_at']

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True


class ProjectEnvironmentInline(admin.TabularInline):
    """项目环境内联管理"""
    model = ProjectEnvironment
    extra = 1
    fields = ['name', 'base_url', 'description', 'is_default', 'created_at']
    readonly_fields = ['created_at']
    ordering = ['-is_default', 'name']


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """项目管理"""
    list_display = ['name', 'owner', 'status', 'member_count', 'created_at', 'updated_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'description', 'owner__username', 'owner__email']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['owner']
    ordering = ['-created_at']

    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'description', 'status')
        }),
        ('负责人', {
            'fields': ('owner',),
            'description': '更改项目负责人'
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [ProjectMemberInline, ProjectEnvironmentInline]

    def member_count(self, obj):
        """显示成员数量"""
        count = obj.projectmember_set.count()
        return f"{count + 1} 人（含负责人）"
    member_count.short_description = '成员数'

    def save_formset(self, request, form, formset, change):
        """保存内联表单集时，处理成员变更"""
        if formset.model == ProjectMember:
            instances = formset.save(commit=False)
            for instance in instances:
                # 确保 project 正确关联
                if not instance.project_id:
                    instance.project = form.instance
                instance.save()
            # 处理删除的成员
            for obj in formset.deleted_objects:
                obj.delete()
        else:
            super().save_formset(request, form, formset, change)


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    """项目成员管理"""
    list_display = ['project', 'user', 'role', 'joined_at']
    list_filter = ['role', 'joined_at']
    search_fields = ['project__name', 'user__username', 'user__email']
    raw_id_fields = ['project', 'user']
    ordering = ['project', 'role', 'joined_at']


@admin.register(ProjectEnvironment)
class ProjectEnvironmentAdmin(admin.ModelAdmin):
    """项目环境管理"""
    list_display = ['name', 'project', 'base_url', 'is_default', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['name', 'base_url', 'project__name']
    raw_id_fields = ['project']
    ordering = ['project', '-is_default', 'name']
