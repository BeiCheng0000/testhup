

import json
import logging
import re
import time
from django.utils import timezone
from .models import RequestHistory
from .variable_resolver import VariableResolver

logger = logging.getLogger(__name__)


def execute_assertions(response, assertions):
    """执行断言验证"""
    results = []

    for assertion in assertions:
        result = {
            'name': assertion.get('name', '未命名断言'),
            'type': assertion.get('type'),
            # 携带断言依据（如 json_path 的 $.code 表达式、响应头名称），供报警邮件/报告展示
            'json_path': assertion.get('json_path', ''),
            'header_name': assertion.get('header_name', ''),
            'passed': False,
            'expected': None,
            'actual': None,
            'error': None
        }

        try:
            assertion_type = assertion.get('type')
            actual = None
            passed = False
            # 优先从 assertion 自身取 expected（兼容多种字段命名）
            # 注意：不能用 `or` 链，因为 0 也是合法的期望值（如 $.code==0）
            expected_val = assertion.get('expected')
            if expected_val is None:
                expected_val = assertion.get('expected_value')
            if expected_val is None:
                expected_val = assertion.get('value')
            result['expected'] = expected_val

            if assertion_type == 'status_code':
                actual = response.status_code
                passed = actual == expected_val

            elif assertion_type == 'response_time':
                # 响应时间断言在调用方处理
                actual = assertion.get('actual_time')
                passed = actual <= expected_val if actual is not None and expected_val is not None else False

            elif assertion_type == 'contains':
                text = response.text or ''
                pattern = str(expected_val) if expected_val is not None else ''
                actual = text[:200] + '...' if len(text) > 200 else text
                passed = pattern in str(text)

            elif assertion_type == 'json_path':
                json_path = assertion.get('json_path', '')
                result['expected'] = expected_val  # json_path 可能从不同字段读取 expected

                try:
                    # 检查响应是否为JSON格式
                    content_type = response.headers.get('content-type', '').lower()
                    if 'application/json' not in content_type:
                        raise ValueError(f"响应不是JSON格式，Content-Type: {content_type}")

                    response_json = json.loads(response.text)

                    # 检查JSONPath表达式是否为空
                    if not json_path:
                        raise ValueError("JSON路径表达式不能为空")

                    from jsonpath_ng import parse
                    matches = parse(json_path).find(response_json)
                    actual = matches[0].value if matches else None
                    passed = str(actual) == str(expected_val)

                except json.JSONDecodeError as e:
                    actual = None
                    passed = False
                    result['error'] = f"JSON解析失败: {str(e)}"
                except ImportError as e:
                    actual = None
                    passed = False
                    result['error'] = f"缺少依赖库: {str(e)}，请安装jsonpath-ng"
                except Exception as e:
                    actual = None
                    passed = False
                    result['error'] = f"执行错误: {str(e)}"

            elif assertion_type == 'header':
                header_name = assertion.get('header_name', '')
                actual = response.headers.get(header_name)
                # header 类型使用 expected_value 而不是 expected
                header_expected = assertion.get('expected_value')
                if header_expected is None:
                    header_expected = assertion.get('expected')
                if header_expected is None:
                    header_expected = assertion.get('value')
                result['expected'] = header_expected
                passed = str(actual) == str(result['expected']) if actual is not None and result['expected'] is not None else actual == result['expected']

            elif assertion_type == 'equals':
                actual = response.text.strip()
                passed = actual == str(expected_val).strip() if expected_val is not None else actual == ''

            # 确保在所有情况下都设置actual值
            result['actual'] = actual
            result['passed'] = passed

        except Exception as e:
            result['error'] = str(e)
            result['passed'] = False

        results.append(result)

    return results


def run_post_request_script(api_request, response, response_time, environment):
    """执行请求后脚本（Tests），返回结构化结果并持久化环境变量变更。

    通过 node 子进程运行 tests_runner.js，与前端 runPostRequestScript 提供完全一致的
    pm / console API。适用于自动化测试（测试套件）与定时任务的服务端执行。

    :return: tests_result 字典（含 testResults/scriptLogs/savedEnvVariables/error），
             脚本为空时返回 None
    """
    script = getattr(api_request, 'post_request_script', '') or ''
    if not script.strip():
        return None

    from .js_runner import run_tests_script
    from .models import Environment

    content_type = response.headers.get('content-type', '') or ''
    response_info = {
        'status_code': response.status_code,
        'status_text': getattr(response, 'reason', '') or '',
        'response_time': response_time,
        'response_data': {
            'headers': dict(response.headers),
            'body': response.text,
            'json': response.json() if 'application/json' in content_type else None,
        },
    }

    # 构建环境列表：当前环境（current:true）+ 项目级全局环境变量
    environments = []
    if environment and getattr(environment, 'variables', None):
        environments.append({
            'id': environment.id,
            'name': environment.name,
            'scope': environment.scope,
            'current': True,
            'variables': environment.variables,
        })

    project = getattr(environment, 'project', None) if environment else None
    if not project and getattr(api_request, 'collection', None):
        project = getattr(api_request.collection, 'project', None)
    global_env = None
    if project:
        global_env = Environment.objects.filter(project=project, scope='GLOBAL').first()
    if global_env and (not environment or global_env.id != environment.id):
        environments.append({
            'id': global_env.id,
            'name': global_env.name,
            'scope': global_env.scope,
            'current': False,
            'variables': global_env.variables,
        })

    result = run_tests_script(script, response_info, environments)
    if not result:
        return None

    # 持久化环境变量变更，并同步更新内存中的 environment 对象以支持请求间变量串联
    for upd in result.get('updatedEnvironments', []) or []:
        try:
            env_obj = Environment.objects.get(id=upd.get('id'))
            env_obj.variables = upd.get('variables')
            env_obj.save(update_fields=['variables'])
            if environment is not None and env_obj.id == environment.id:
                environment.variables = upd.get('variables')
        except Exception:
            logger.exception('持久化 Tests 脚本写入的环境变量失败')

    return result


def execute_test_suite(test_suite, environment, executed_by):
    """执行测试套件并返回结果"""
    from .models import TestExecution, RequestHistory
    import requests
    import time

    try:
        # 创建变量解析器
        resolver = VariableResolver()

        # 如果未传入环境，回退到测试套件自身的环境
        if not environment:
            environment = test_suite.environment

        # 创建执行记录
        execution = TestExecution.objects.create(
            test_suite=test_suite,
            status='RUNNING',
            start_time=timezone.now(),
            executed_by=executed_by
        )

        # 获取套件中的请求
        suite_requests = test_suite.testsuiterequest_set.filter(enabled=True).order_by('order')

        execution.total_requests = suite_requests.count()
        execution.save()

        results = []
        passed_count = 0
        failed_count = 0

        # 执行每个请求
        for suite_request in suite_requests:
            api_request = suite_request.request

            try:
                # 解析环境变量
                variables = {}
                if environment:
                    variables.update(environment.variables)

                # 替换URL中的变量并自动拼接host域名
                url = resolve_url_with_host(api_request.url, variables, resolver)

                # 准备请求头
                headers = {}
                if isinstance(api_request.headers, list):
                    for header_item in api_request.headers:
                        if header_item.get('enabled', True) and header_item.get('key'):
                            key = header_item['key']
                            value = _replace_variables(str(header_item.get('value', '')), variables)
                            value = resolver.resolve(value)
                            headers[key] = value
                else:
                    headers = api_request.headers.copy()
                    for key, value in headers.items():
                        headers[key] = _replace_variables(str(value), variables)
                        headers[key] = resolver.resolve(headers[key])

                # 准备请求参数
                params = api_request.params.copy() if api_request.params else {}
                for key, value in params.items():
                    params[key] = _replace_variables(str(value), variables)
                    params[key] = resolver.resolve(params[key])

                # 准备请求体
                body_data = None
                files = None
                body_type = None
                if api_request.body and api_request.method in ['POST', 'PUT', 'PATCH']:
                    body_type = api_request.body.get('type', 'json')

                    if body_type == 'json':
                        body_data = api_request.body.get('data', {})
                        body_data = _replace_variables_in_dict(body_data, variables)
                        body_data = _resolve_variables_in_dict(body_data, resolver)
                    elif body_type == 'form-data':
                        body_data = {}
                        for item in api_request.body.get('data', []):
                            if item.get('enabled', True):
                                key = item.get('key', '')
                                value = item.get('value', '')
                                value = _replace_variables(str(value), variables)
                                value = resolver.resolve(value)
                                body_data[key] = value
                    elif body_type == 'x-www-form-urlencoded':
                        body_data = {}
                        for item in api_request.body.get('data', []):
                            if item.get('enabled', True):
                                key = item.get('key', '')
                                value = item.get('value', '')
                                value = _replace_variables(str(value), variables)
                                value = resolver.resolve(value)
                                body_data[key] = value
                    elif body_type == 'raw':
                        body_data = _replace_variables(api_request.body.get('data', ''), variables)
                        body_data = resolver.resolve(body_data)
                    elif body_type == 'binary':
                        file_data = api_request.body.get('file_data')
                        if file_data:
                            files = []
                            for file_item in file_data:
                                if file_item.get('enabled', True):
                                    file_key = file_item.get('key', '')
                                    file_path = file_item.get('path', '')
                                    if file_path:
                                        files.append((file_key, open(file_path, 'rb')))

                # 执行请求
                start_time = time.time()
                response = requests.request(
                    method=api_request.method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=body_data if body_type == 'json' else None,
                    data=body_data if body_type != 'json' else None,
                    files=files,
                    timeout=30
                )

                # 关闭文件
                if files:
                    for _, file_obj in files:
                        file_obj.close()
                end_time = time.time()
                response_time = (end_time - start_time) * 1000

                # 执行断言验证
                assertions = api_request.assertions or []
                for assertion in assertions:
                    if assertion.get('type') == 'response_time':
                        assertion['actual_time'] = response_time

                assertions_results = execute_assertions(response, assertions)

                # 检查所有断言是否通过
                passed = True
                error_message = ''

                # 检查套件请求的断言（使用 execute_assertions 兼容所有断言类型）
                suite_assertions = suite_request.assertions or []
                if suite_assertions:
                    # 为 response_time 类型断言设置实际响应时间
                    for sa in suite_assertions:
                        if sa.get('type') == 'response_time':
                            sa['actual_time'] = response_time
                    suite_assertions_results = execute_assertions(response, suite_assertions)
                    # 将套件断言结果合并到总断言结果中
                    assertions_results = assertions_results + suite_assertions_results

                # 检查接口自身的断言（累积所有失败断言，避免只显示第一条；并去重套件/请求级合并导致的重复）
                if passed and assertions_results:
                    failed_assert_msgs = []
                    seen_msgs = set()
                    for assertion_result in assertions_results:
                        if not assertion_result.get('passed', True):
                            passed = False
                            name = assertion_result.get('name', '未命名断言')
                            atype = assertion_result.get('type', '')
                            expected = assertion_result.get('expected')
                            actual = assertion_result.get('actual')
                            err = assertion_result.get('error')
                            if err:
                                msg = f"断言失败: {name} - {err}"
                            elif expected is not None and actual is not None:
                                msg = f"断言失败: {name} - 期望={expected}, 实际={actual}"
                            elif expected is not None:
                                msg = f"断言失败: {name} - 期望={expected}, 实际值未获取"
                            elif actual is not None:
                                msg = f"断言失败: {name} - 实际值={actual}, 期望值未配置"
                            else:
                                msg = f"断言失败: {name} - 类型={atype}, 缺少期望/实际信息"
                            if msg not in seen_msgs:
                                seen_msgs.add(msg)
                                failed_assert_msgs.append(msg)
                    if failed_assert_msgs:
                        error_message = '\n'.join(failed_assert_msgs)

                if passed:
                    passed_count += 1
                else:
                    failed_count += 1

                # 执行请求后脚本（Tests）：提取响应数据并写回环境变量
                tests_result = run_post_request_script(api_request, response, response_time, environment)

                results.append({
                    'name': api_request.name,
                    'method': api_request.method,
                    'url': url,
                    'status_code': response.status_code,
                    'response_time': response_time,
                    'passed': passed,
                    'error': error_message,
                    'assertions_results': assertions_results,
                    'tests_result': tests_result,
                    # 仅为失败（断言失败）的请求携带响应实体，供报警邮件展示问题响应
                    'response_body': response.text if not passed else None,
                })

                # 保存请求历史
                RequestHistory.objects.create(
                    request=api_request,
                    environment=environment,
                    request_data={
                        'url': url,
                        'method': api_request.method,
                        'headers': headers,
                        'params': params,
                        'body': body_data
                    },
                    response_data={
                        'headers': dict(response.headers),
                        'body': response.text,
                        'json': response.json() if response.headers.get('content-type', '').startswith('application/json') else None,
                        'tests_result': tests_result,
                    },
                    status_code=response.status_code,
                    response_time=response_time,
                    error_message=error_message,
                    assertions_results=assertions_results,
                    executed_by=executed_by
                )

            except Exception as e:
                failed_count += 1
                error_detail = f"{type(e).__name__}: {str(e)}"
                results.append({
                    'name': api_request.name,
                    'method': api_request.method,
                    'url': api_request.url,
                    'status_code': None,
                    'response_time': None,
                    'passed': False,
                    'error': error_detail,
                    'assertions_results': []
                })

        # 更新执行结果
        execution.end_time = timezone.now()
        execution.passed_requests = passed_count
        execution.failed_requests = failed_count
        execution.status = 'COMPLETED' if failed_count == 0 else 'FAILED'
        execution.results = results
        execution.save()

        # 汇总所有失败请求的错误信息
        failed_errors = [
            f"[{r.get('name')}][{r.get('method')}] {r.get('url')}: {r.get('error')}"
            for r in results if not r.get('passed', False) and r.get('error')
        ]

        return {
            'success': True,
            'execution_id': execution.id,
            'passed_count': passed_count,
            'failed_count': failed_count,
            'total_count': execution.total_requests,
            'results': results,
            'error_summary': '\n'.join(failed_errors) if failed_errors else ''
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def execute_api_request(api_request, environment, executed_by):
    """执行单个API请求并返回结果"""
    import requests
    import time

    try:
        # 创建变量解析器
        resolver = VariableResolver()

        # 解析环境变量
        variables = {}
        if environment:
            variables.update(environment.variables)

        # 替换URL中的变量并自动拼接host域名
        url = resolve_url_with_host(api_request.url, variables, resolver)

        # 准备请求头
        headers = {}
        if isinstance(api_request.headers, list):
            for header_item in api_request.headers:
                if header_item.get('enabled', True) and header_item.get('key'):
                    key = header_item['key']
                    value = _replace_variables(str(header_item.get('value', '')), variables)
                    value = resolver.resolve(value)
                    headers[key] = value
        else:
            headers = api_request.headers.copy()
            for key, value in headers.items():
                headers[key] = _replace_variables(str(value), variables)
                headers[key] = resolver.resolve(headers[key])

        # 准备请求参数
        params = api_request.params.copy() if api_request.params else {}
        for key, value in params.items():
            params[key] = _replace_variables(str(value), variables)
            params[key] = resolver.resolve(params[key])

        # 准备请求体
        body_data = None
        files = None
        if api_request.body and api_request.method in ['POST', 'PUT', 'PATCH']:
            body_type = api_request.body.get('type', 'json')

            if body_type == 'json':
                body_data = api_request.body.get('data', {})
                body_data = _replace_variables_in_dict(body_data, variables)
                body_data = _resolve_variables_in_dict(body_data, resolver)
            elif body_type == 'form-data':
                body_data = {}
                for item in api_request.body.get('data', []):
                    if item.get('enabled', True):
                        key = item.get('key', '')
                        value = item.get('value', '')
                        value = _replace_variables(str(value), variables)
                        value = resolver.resolve(value)
                        body_data[key] = value
            elif body_type == 'x-www-form-urlencoded':
                body_data = {}
                for item in api_request.body.get('data', []):
                    if item.get('enabled', True):
                        key = item.get('key', '')
                        value = item.get('value', '')
                        value = _replace_variables(str(value), variables)
                        value = resolver.resolve(value)
                        body_data[key] = value
            elif body_type == 'raw':
                body_data = _replace_variables(api_request.body.get('data', ''), variables)
                body_data = resolver.resolve(body_data)
            elif body_type == 'binary':
                file_data = api_request.body.get('file_data')
                if file_data:
                    # 处理文件上传
                    files = []
                    for file_item in file_data:
                        if file_item.get('enabled', True):
                            file_key = file_item.get('key', '')
                            file_path = file_item.get('path', '')
                            if file_path:
                                files.append((file_key, open(file_path, 'rb')))

            elif body_type == 'form-data':
                body_data = {}
                for item in api_request.body.get('data', []):
                    if item.get('enabled', True):
                        key = item.get('key', '')
                        value = item.get('value', '')
                        value = _replace_variables(str(value), variables)
                        value = resolver.resolve(value)
                        body_data[key] = value
            elif body_type == 'x-www-form-urlencoded':
                body_data = {}
                for item in api_request.body.get('data', []):
                    if item.get('enabled', True):
                        key = item.get('key', '')
                        value = item.get('value', '')
                        value = _replace_variables(str(value), variables)
                        value = resolver.resolve(value)
                        body_data[key] = value
            elif body_type == 'raw':
                body_data = _replace_variables(api_request.body.get('data', ''), variables)
                body_data = resolver.resolve(body_data)
            elif body_type == 'binary':
                file_data = api_request.body.get('file_data')
                if file_data:
                    # 处理文件上传
                    files = []
                    for file_item in file_data:
                        if file_item.get('enabled', True):
                            file_key = file_item.get('key', '')
                            file_path = file_item.get('path', '')
                            if file_path:
                                files.append((file_key, open(file_path, 'rb')))

        # 执行请求
        start_time = time.time()
        response = requests.request(
            method=api_request.method,
            url=url,
            headers=headers,
            params=params,
            json=body_data if body_type == 'json' else None,
            data=body_data if body_type != 'json' else None,
            files=files,
            timeout=30
        )

        # 关闭文件
        if files:
            for _, file_obj in files:
                file_obj.close()

        end_time = time.time()
        response_time = (end_time - start_time) * 1000

        # 执行断言验证
        assertions = api_request.assertions or []
        for assertion in assertions:
            if assertion.get('type') == 'response_time':
                assertion['actual_time'] = response_time

        assertions_results = execute_assertions(response, assertions)

        # 检查所有断言是否通过
        passed = True
        error_message = ''
        failed_assert_msgs = []
        seen_msgs = set()
        for assertion_result in assertions_results:
            if not assertion_result.get('passed', True):
                passed = False
                name = assertion_result.get('name', '未命名断言')
                atype = assertion_result.get('type', '')
                expected = assertion_result.get('expected')
                actual = assertion_result.get('actual')
                err = assertion_result.get('error')
                if err:
                    msg = f"断言失败: {name} - {err}"
                elif expected is not None and actual is not None:
                    msg = f"断言失败: {name} - 期望={expected}, 实际={actual}"
                elif expected is not None:
                    msg = f"断言失败: {name} - 期望={expected}, 实际值未获取"
                elif actual is not None:
                    msg = f"断言失败: {name} - 实际值={actual}, 期望值未配置"
                else:
                    msg = f"断言失败: {name} - 类型={atype}, 缺少期望/实际信息"
                if msg not in seen_msgs:
                    seen_msgs.add(msg)
                    failed_assert_msgs.append(msg)
        if failed_assert_msgs:
            error_message = '\n'.join(failed_assert_msgs)

        # 执行请求后脚本（Tests）：提取响应数据并写回环境变量
        tests_result = run_post_request_script(api_request, response, response_time, environment)

        # 保存请求历史
        history = RequestHistory.objects.create(
            request=api_request,
            environment=environment,
            request_data={
                'url': url,
                'method': api_request.method,
                'headers': headers,
                'params': params,
                'body': body_data
            },
            response_data={
                'headers': dict(response.headers),
                'body': response.text,
                'json': response.json() if response.headers.get('content-type', '').startswith(
                    'application/json') else None,
                'tests_result': tests_result,
            },
            status_code=response.status_code,
            response_time=response_time,
            assertions_results=assertions_results,
            executed_by=executed_by
        )

        # 根据断言结果返回成功或失败
        if not passed:
            return {
                'success': False,
                'error': error_message,
                'assertions_results': assertions_results,
                'history_id': history.id,
                'status_code': response.status_code,
                'response_time': response_time,
                'response_data': {
                    'headers': dict(response.headers),
                    'body': response.text,
                    'json': response.json() if response.headers.get('content-type', '').startswith(
                        'application/json') else None
                }
            }

        return {
            'success': True,
            'history_id': history.id,
            'status_code': response.status_code,
            'response_time': response_time,
            'assertions_results': assertions_results,
            'tests_result': tests_result,
            'response_data': {
                'headers': dict(response.headers),
                'body': response.text,
                'json': response.json() if response.headers.get('content-type', '').startswith(
                    'application/json') else None
            }
        }


    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def _replace_variables(text, variables):
    """替换文本中的变量"""
    if not isinstance(text, str):
        return text

    result = text
    for key, value in (variables or {}).items():
        if isinstance(value, dict):
            replacement = str(value.get('currentValue', '') or value.get('initialValue', ''))
        else:
            replacement = str(value) if value is not None else ''
        result = result.replace(f'{{{{{key}}}}}', replacement)
    return result


def _get_env_variable_value(variables, key):
    """从环境变量字典中获取指定key的变量值"""
    value = (variables or {}).get(key)
    if isinstance(value, dict):
        return value.get('currentValue') or value.get('initialValue') or ''
    return value or ''


def resolve_url_with_host(url, variables, resolver=None):
    """解析URL：先替换变量占位符和动态函数，再自动拼接host域名
    
    当URL不以http://或https://开头时，自动从环境变量中获取host值并拼接到前面。
    支持单次执行、测试套件执行、定时任务等所有场景。
    """
    # 第一步：替换 {{变量}} 占位符
    url = _replace_variables(url, variables)
    # 第二步：解析 ${动态函数}
    if resolver:
        url = resolver.resolve(url)
    
    # 第三步：如果URL没有协议前缀，自动拼接host域名
    if url and isinstance(url, str) and not url.startswith(('http://', 'https://')):
        host = _get_env_variable_value(variables, 'host')
        if host:
            host = host.rstrip('/')
            url = host + '/' + url.lstrip('/')
        else:
            logger.warning(
                f"URL缺少协议前缀且环境变量中未配置host，请求可能失败: {url}"
            )
    
    # 第四步：规范化URL，修复变量替换可能产生的双斜杠
    if url and isinstance(url, str):
        # 找到://后面的部分，把其中连续的//替换为/
        url = re.sub(r'(?<!:)/{2,}', '/', url)
    
    return url

def _replace_variables_in_dict(data, variables):
    """递归替换字典中的变量"""
    if isinstance(data, dict):
        return {k: _replace_variables_in_dict(v, variables) for k, v in data.items()}
    elif isinstance(data, list):
        return [_replace_variables_in_dict(item, variables) for item in data]
    elif isinstance(data, str):
        return _replace_variables(data, variables)
    else:
        return data

def _resolve_variables_in_dict(data, resolver):
    """递归解析字典中的动态函数占位符"""
    if isinstance(data, dict):
        return {k: _resolve_variables_in_dict(v, resolver) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_variables_in_dict(item, resolver) for item in data]
    elif isinstance(data, str):
        return resolver.resolve(data)
    else:
        return data
