"""
自定义分页类 - 支持前端通过 page_size 参数控制每页条数
"""
from rest_framework.pagination import PageNumberPagination


class CustomPageNumberPagination(PageNumberPagination):
    """允许客户端通过 ?page_size=N 自定义每页条数"""
    page_size_query_param = 'page_size'  # 前端传 ?page_size=10 即可生效
    max_page_size = 100  # 最大限制，防止过载
