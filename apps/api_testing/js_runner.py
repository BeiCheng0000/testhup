"""Tests 脚本（请求后脚本）服务端执行封装。

通过 node 子进程运行 tests_runner.js，与前端 InterfaceManagement.vue 中
runPostRequestScript 提供完全一致的 pm / console API，使自动化测试与定时任务
也能执行 Postman 风格的 Tests 脚本。

依赖：服务器需安装 Node.js（与前端构建使用的 node 一致）。若 node 不可用，
会返回含 error 的降级结果，不会中断请求执行流程。
"""
import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

NODE_RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests_runner.js')
NODE_EXE = shutil.which('node')


def run_tests_script(script, response_info, environments):
    """执行 Tests 脚本，返回结构化结果字典。

    :param script: 脚本源码字符串
    :param response_info: {status_code, status_text, response_time, response_data:{headers,body,json}}
    :param environments: [{id, name, scope, current, variables}]
    :return: {testResults, scriptLogs, savedEnvVariables, updatedEnvironments, error}
    """
    default = {
        'testResults': [],
        'scriptLogs': [],
        'savedEnvVariables': [],
        'updatedEnvironments': [],
        'error': None,
    }
    if not script or not script.strip():
        return None

    if not NODE_EXE:
        return {**default, 'error': '未找到 node 运行环境，无法执行 Tests 脚本（请安装 Node.js）'}

    payload = {
        'script': script,
        'response': response_info,
        'environments': environments or [],
    }

    try:
        proc = subprocess.run(
            [NODE_EXE, NODE_RUNNER],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {**default, 'error': 'Tests 脚本执行超时（30秒）'}
    except Exception as e:  # pragma: no cover - 防御性兜底
        logger.exception('Tests 脚本执行引擎异常')
        return {**default, 'error': f'Tests 脚本执行引擎错误: {e}'}

    if proc.returncode != 0:
        return {**default, 'error': 'Tests 脚本执行引擎异常: ' + (proc.stderr or '').strip()[:500]}

    try:
        result = json.loads(proc.stdout.strip())
    except Exception as e:
        return {**default, 'error': f'Tests 脚本结果解析失败: {e}'}

    result.setdefault('testResults', [])
    result.setdefault('scriptLogs', [])
    result.setdefault('savedEnvVariables', [])
    result.setdefault('updatedEnvironments', [])
    return result
