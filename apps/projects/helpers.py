"""项目相关的公共工具函数"""
from django.db import models
from .models import Project


def get_user_accessible_projects(user):
    """获取用户有权限访问的项目（owner 或 member）"""
    return Project.objects.filter(
        models.Q(owner=user) | models.Q(members=user)
    ).distinct()


def get_user_owned_projects(user):
    """获取用户作为负责人的项目（仅 owner）"""
    return Project.objects.filter(owner=user).distinct()
