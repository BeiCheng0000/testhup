from django.urls import path
from . import views, project_list_views

urlpatterns = [
    path('', views.ProjectListCreateView.as_view(), name='project-list'),
    path('all/', views.get_all_projects, name='all-projects'),
    path('<int:pk>/', views.ProjectDetailView.as_view(), name='project-detail'),
    path('<int:project_id>/members/', views.get_project_members, name='get-project-members'),
    path('<int:project_id>/members/add/', views.add_project_member, name='add-member'),
    path('<int:project_id>/members/<int:member_id>/', views.project_member_detail, name='member-detail'),
    path('<int:project_id>/transfer-owner/', views.change_project_owner, name='transfer-owner'),
    path('<int:project_id>/environments/', views.ProjectEnvironmentListCreateView.as_view(), name='environment-list'),
    path('list/', project_list_views.user_projects_list, name='user-projects-list'),
]