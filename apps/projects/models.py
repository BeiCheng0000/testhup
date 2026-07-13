from django.db import models
from django.utils import timezone
from apps.users.models import User


class SoftDeleteQuerySet(models.QuerySet):
    """支持软删除的 QuerySet"""
    def delete(self):
        """默认调用软删除（标记 is_deleted=True）"""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """物理删除（不可恢复）"""
        return super().delete()

    def restore(self):
        """批量恢复"""
        return self.update(is_deleted=False, deleted_at=None)


class SoftDeleteManager(models.Manager):
    """默认过滤已删除记录的 Manager"""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def with_deleted(self):
        """获取包含已删除记录的 QuerySet（回收站用）"""
        return SoftDeleteQuerySet(self.model, using=self._db)

    def only_deleted(self):
        """仅获取已删除记录"""
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=True)


class SoftDeleteModel(models.Model):
    """
    软删除抽象基类
    - is_deleted: 删除标记
    - deleted_at: 删除时间
    - objects: 默认只返回未删除记录
    - all_objects: 返回所有记录（包括已删除，供 Django 内部使用）
    """
    is_deleted = models.BooleanField(default=False, verbose_name='是否删除')
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='删除时间')

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        # 默认 manager 名设为 all_objects，避免 Django 内部查询被 objects 过滤
        default_manager_name = 'objects'

    def soft_delete(self):
        """软删除"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def restore(self):
        """恢复已删除记录"""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def hard_delete(self, *args, **kwargs):
        """物理删除（不可恢复）"""
        super().delete(*args, **kwargs)

class Project(SoftDeleteModel):
    """项目模型"""
    STATUS_CHOICES = [
        ('active', '进行中'),
        ('paused', '暂停'),
        ('completed', '已完成'),
        ('archived', '已归档'),
    ]
    
    name = models.CharField(max_length=200, verbose_name='项目名称')
    description = models.TextField(blank=True, verbose_name='项目描述')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name='状态')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects', verbose_name='负责人')
    members = models.ManyToManyField(User, through='ProjectMember', related_name='joined_projects', verbose_name='成员')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'projects'
        verbose_name = '项目'
        verbose_name_plural = '项目'
        ordering = ['-created_at']

class ProjectMember(models.Model):
    """项目成员"""
    ROLE_CHOICES = [
        ('owner', '负责人'),
        ('admin', '管理员'),
        ('developer', '开发者'),
        ('tester', '测试者'),
        ('viewer', '观察者'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tester', verbose_name='角色')
    joined_at = models.DateTimeField(default=timezone.now, verbose_name='加入时间')
    
    class Meta:
        db_table = 'project_members'
        unique_together = ['project', 'user']
        verbose_name = '项目成员'
        verbose_name_plural = '项目成员'

class ProjectEnvironment(models.Model):
    """项目环境"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='environments')
    name = models.CharField(max_length=100, verbose_name='环境名称')
    base_url = models.URLField(verbose_name='基础URL')
    description = models.TextField(blank=True, verbose_name='环境描述')
    variables = models.JSONField(default=dict, verbose_name='环境变量')
    is_default = models.BooleanField(default=False, verbose_name='是否默认')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    
    class Meta:
        db_table = 'project_environments'
        verbose_name = '项目环境'
        verbose_name_plural = '项目环境'