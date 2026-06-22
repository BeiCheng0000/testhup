from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/app-automation/executions/(?P<execution_id>\d+)/$', consumers.AppExecutionConsumer.as_asgi()),
    re_path(r'^ws/app-automation/agent/(?P<host_id>[\w-]*)/$', consumers.AgentConsumer.as_asgi()),
]
