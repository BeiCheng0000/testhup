from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import User, UserProfile


class MinimalPasswordChangeForm(AdminPasswordChangeForm):
    """管理员修改用户密码 —— 仅校验长度>=6位且两次输入一致，解除所有其他限制"""

    def clean_password1(self):
        """跳过父类的 password_validation.validate_password，只做简单校验"""
        password1 = self.cleaned_data.get('password1')
        password2 = self.data.get('password2')  # 此时 password2 可能还没进入 cleaned_data
        if password1:
            if len(password1) < 6:
                raise ValidationError(_('密码长度至少6位'))
            if password2 and password1 != password2:
                raise ValidationError(_('两次输入的密码不一致'))
        return password1

    def _post_clean(self):
        """跳过父类的密码验证器校验，避免重复报错"""
        super(forms.Form, self)._post_clean()  # 仅调用顶层 Form._post_clean，不触发父类 AdminPasswordChangeForm._post_clean
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', ValidationError(_('两次输入的密码不一致')))


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'department', 'position', 'is_active', 'date_joined']
    list_filter = ['is_active', 'department', 'position']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    change_password_form = MinimalPasswordChangeForm


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'theme', 'language', 'timezone']
