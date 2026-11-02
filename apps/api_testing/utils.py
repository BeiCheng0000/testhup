

import base64
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
                    if not matches:
                        # 路径写错时给出可定位的原因，而不是笼统的「缺少期望/实际信息」
                        if isinstance(response_json, dict):
                            top_keys = ', '.join(list(response_json)[:8])
                        else:
                            top_keys = type(response_json).__name__
                        result['error'] = f'路径 {json_path} 未匹配到，响应顶层字段：{top_keys}'
                    if expected_val is None:
                        # 没有期望值时，只校验该路径存在且非空（用于「字段存在」类断言）
                        passed = bool(matches) and actual not in (None, '', [], {})
                    else:
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
    global_vars = global_variables_for_project(project)
    if global_vars:
        environments.append({
            'id': 'global-variables',
            'name': '全局变量',
            'scope': 'GLOBAL',
            'current': False,
            'is_global_variables': True,
            'variables': {
                k: {'initialValue': v, 'currentValue': v}
                for k, v in global_vars.items()
            },
        })

    result = run_tests_script(script, response_info, environments)
    if not result:
        return None

    # 持久化环境变量变更，并同步更新内存中的 environment 对象以支持请求间变量串联
    for upd in result.get('updatedEnvironments', []) or []:
        try:
            if upd.get('is_global_variables') or upd.get('id') == 'global-variables':
                _persist_global_variables(project, upd.get('variables') or {}, api_request)
                continue
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
                # 变量来自环境（含全局环境兜底）。缺失不再中断：按原数据继续请求，
                # 由上游决定成败，缺失只记日志
                parts, missing = prepare_request_parts(api_request, environment, resolver)
                if missing:
                    logger.warning(
                        '接口[id=%s] 引用了未定义变量 %s，按原数据继续请求',
                        api_request.id, '、'.join(missing))

                variables = parts['variables']
                url = parts['url']
                headers = parts['headers']
                params = parts['params']

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
                        for item in iter_form_items(api_request.body.get('data', [])):
                            if item.get('enabled', True):
                                key = item.get('key', '')
                                value = item.get('value', '')
                                value = _replace_variables(str(value), variables)
                                value = resolver.resolve(value)
                                body_data[key] = value
                    elif body_type == 'x-www-form-urlencoded':
                        body_data = {}
                        for item in iter_form_items(api_request.body.get('data', [])):
                            if item.get('enabled', True):
                                key = item.get('key', '')
                                value = item.get('value', '')
                                value = _replace_variables(str(value), variables)
                                value = resolver.resolve(value)
                                body_data[key] = value
                    elif body_type == 'raw':
                        raw_data = api_request.body.get('data', '')
                        if isinstance(raw_data, str):
                            body_data = _replace_variables(raw_data, variables)
                            body_data = resolver.resolve(body_data)
                        else:
                            # 原始文本被存成结构化对象时，同样递归解析其中的字符串
                            body_data = _resolve_variables_in_dict(
                                _replace_variables_in_dict(raw_data, variables), resolver)
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


def execute_api_request(api_request, environment, executed_by, save_history=True):
    """执行单个API请求并返回结果

    save_history=False 时请求照常发出，但不写请求历史，也不要求
    api_request 已落库（供「AI 自检试跑」这类内部调用使用）。
    """
    import requests
    import time

    try:
        # 创建变量解析器
        resolver = VariableResolver()

        # 变量来自环境（含全局环境兜底）。缺失不再中断：按原数据继续请求，
        # 成败交给上游；缺失只记日志，既不阻断执行也便于事后排查
        parts, missing = prepare_request_parts(api_request, environment, resolver)
        if missing:
            logger.warning(
                '接口[id=%s] 引用了未定义变量 %s，按原数据继续请求',
                getattr(api_request, 'id', None), '、'.join(missing))

        variables = parts['variables']
        url = parts['url']
        headers = parts['headers']
        params = parts['params']

        # 准备请求体
        body_data = None
        files = None
        body_type = 'none'  # GET 等方法不进入下面的分支，此处必须先初始化，否则会 UnboundLocalError
        if api_request.body and api_request.method in ['POST', 'PUT', 'PATCH']:
            body_type = api_request.body.get('type', 'json')

            if body_type == 'json':
                body_data = api_request.body.get('data', {})
                body_data = _replace_variables_in_dict(body_data, variables)
                body_data = _resolve_variables_in_dict(body_data, resolver)
            elif body_type == 'form-data':
                body_data = {}
                for item in iter_form_items(api_request.body.get('data', [])):
                    if item.get('enabled', True):
                        key = item.get('key', '')
                        value = item.get('value', '')
                        value = _replace_variables(str(value), variables)
                        value = resolver.resolve(value)
                        body_data[key] = value
            elif body_type == 'x-www-form-urlencoded':
                body_data = {}
                for item in iter_form_items(api_request.body.get('data', [])):
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
                for item in iter_form_items(api_request.body.get('data', [])):
                    if item.get('enabled', True):
                        key = item.get('key', '')
                        value = item.get('value', '')
                        value = _replace_variables(str(value), variables)
                        value = resolver.resolve(value)
                        body_data[key] = value
            elif body_type == 'x-www-form-urlencoded':
                body_data = {}
                for item in iter_form_items(api_request.body.get('data', [])):
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

        # 实际发出的请求（变量已解析），供前端展示「实际请求」
        request_payload = {
            'url': url,
            'method': api_request.method,
            'headers': headers,
            'params': params,
            'body': body_data,
        }

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

        # 保存请求历史（试跑场景可跳过，且未落库的接口实例无法挂历史）
        history = None
        if save_history and getattr(api_request, 'pk', None):
            history = RequestHistory.objects.create(
                request=api_request,
                environment=environment,
                request_data=request_payload,
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
                'history_id': history.id if history else None,
                'status_code': response.status_code,
                'response_time': response_time,
                'request_data': request_payload,
                'response_data': {
                    'headers': dict(response.headers),
                    'body': response.text,
                    'json': response.json() if response.headers.get('content-type', '').startswith(
                        'application/json') else None
                }
            }

        return {
            'success': True,
            'history_id': history.id if history else None,
            'status_code': response.status_code,
            'response_time': response_time,
            'assertions_results': assertions_results,
            'tests_result': tests_result,
            'request_data': request_payload,
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


def variable_aliases(key):
    """变量名的等价写法：下划线与连字符互通。

    环境里配的是 host_test，接口 URL 里却常写成 {host-test}，
    两者应视为同一个变量；否则 {host-test} 会原样保留，URL 缺协议，请求必然失败。
    """
    key = str(key)
    forms = [key, key.replace('_', '-'), key.replace('-', '_')]
    return list(dict.fromkeys(forms))  # 去重且保持顺序


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
        # 兼容单花括号 {key} 写法（如 URL 路径参数 /path/{assistantCode}）：
        # 必须先替换双花括号 {{key}}，再替换单花括号 {key}，
        # 否则 {{key}} 内部的 {key} 会被单括号规则先命中，导致外层花括号残留。
        # 同时按别名替换，让 {host-test} 也能命中环境里的 host_test。
        for name in variable_aliases(key):
            result = result.replace(f'{{{{{name}}}}}', replacement)
            result = result.replace(f'{{{name}}}', replacement)
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

def iter_form_items(data):
    """把 form-data / x-www-form-urlencoded 的 data 规范为 list[{key,value,enabled}]。

    兼容 dict（AI 生成或历史数据）与 list。若直接遍历 dict 会拿到字符串 key，
    随后的 item.get() 会抛 'str' object has no attribute 'get'。
    """
    if isinstance(data, dict):
        return [{'key': str(k), 'value': '' if v is None else str(v), 'enabled': True}
                for k, v in data.items()]
    if isinstance(data, list):
        items = []
        for item in data:
            if isinstance(item, dict):
                items.append(item)
            elif isinstance(item, str) and '=' in item:
                key, value = item.split('=', 1)
                items.append({'key': key, 'value': value, 'enabled': True})
        return items
    return []


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


# ---------------------------------------------------------------------------
# 环境变量统一解析：所有变量只允许来自环境，缺失即报错，避免把 {{xxx}} 原样发出去
# ---------------------------------------------------------------------------

# 只识别双花括号，避免把 REST 风格路径 /path/{id} 误判为变量
VAR_REF_PATTERN = re.compile(r'\{\{\s*([A-Za-z_][\w.\-]*)\s*\}\}')


def normalize_env_variables(environment):
    """把环境变量统一成 {name: str}，并展开变量之间的相互引用。

    库里的环境变量有两种形态：
      - 扁平：{"host": "https://x.com"}
      - 编辑器形态：{"host": {"currentValue": "...", "initialValue": "..."}}
    变量值本身也可以引用其它变量，例如 token = "{{token_head}} {{token_body}}"，
    这里会迭代展开，保证用例里写 {{token}} 能拿到完整值。
    """
    raw = getattr(environment, 'variables', None) or {}
    flat = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            flat[key] = value.get('currentValue') or value.get('initialValue') or ''
        elif value is None:
            flat[key] = ''
        else:
            flat[key] = str(value)

    for _ in range(5):  # 最多展开 5 轮，兼容循环引用
        changed = False
        for key, value in list(flat.items()):
            if not isinstance(value, str):
                continue
            new_value = _replace_variables(value, flat)
            if new_value != value:
                flat[key] = new_value
                changed = True
        if not changed:
            break
    return flat


def find_undefined_variables(*texts, variables=None):
    """返回文本里引用了、但环境里没定义的变量名（按出现顺序去重）。"""
    variables = variables or {}
    missing = []
    for text in texts:
        if not isinstance(text, str):
            continue
        for name in VAR_REF_PATTERN.findall(text):
            if name not in variables and name not in missing:
                missing.append(name)
    return missing


def build_auth_headers(auth, variables, resolver=None):
    """把接口的 auth 配置转成请求头，值同样从环境变量取值。

    支持：bearer / basic / apikey
      {"type": "bearer", "token": "{{token}}"}
      {"type": "basic", "username": "{{user}}", "password": "{{pass}}"}
      {"type": "apikey", "key": "X-API-Key", "value": "{{api_key}}", "in": "header"}
    """
    if not isinstance(auth, dict):
        return {}

    auth_type = str(auth.get('type') or 'none').strip().lower()
    if auth_type in ('', 'none', 'noauth', 'inherit'):
        return {}

    def _value(raw):
        text = _replace_variables(str(raw or ''), variables)
        return resolver.resolve(text) if resolver else text

    if auth_type == 'bearer':
        token = _value(auth.get('token'))
        if not token:
            return {}
        if token.lower().startswith('bearer '):
            return {'Authorization': token}
        return {'Authorization': f'Bearer {token}'}

    if auth_type == 'basic':
        username = _value(auth.get('username'))
        password = _value(auth.get('password'))
        encoded = base64.b64encode(f'{username}:{password}'.encode()).decode()
        return {'Authorization': f'Basic {encoded}'}

    if auth_type in ('apikey', 'api_key', 'api-key'):
        if str(auth.get('in') or 'header').strip().lower() != 'header':
            return {}
        key = str(auth.get('key') or 'X-API-Key').strip()
        value = _value(auth.get('value') or auth.get('api_key'))
        return {key: value} if value else {}

    return {}


def _build_headers(raw_headers, variables, resolver=None):
    headers = {}
    if isinstance(raw_headers, list):
        for item in raw_headers:
            if isinstance(item, dict) and item.get('enabled', True) and item.get('key'):
                text = _replace_variables(str(item.get('value', '')), variables)
                headers[item['key']] = resolver.resolve(text) if resolver else text
        return headers

    for key, value in (raw_headers or {}).items():
        text = _replace_variables(str(value), variables)
        headers[key] = resolver.resolve(text) if resolver else text
    return headers


def _build_params(raw_params, variables, resolver=None):
    params = {}
    if isinstance(raw_params, list):
        for item in raw_params:
            if isinstance(item, dict) and item.get('enabled', True) and item.get('key'):
                text = _replace_variables(str(item.get('value', '')), variables)
                params[item['key']] = resolver.resolve(text) if resolver else text
        return params

    for key, value in (raw_params or {}).items():
        text = _replace_variables(str(value), variables)
        params[key] = resolver.resolve(text) if resolver else text
    return params


def _build_body(api_request, variables, resolver=None):
    """返回 (body_type, body_data, files)。"""
    body_type = 'none'
    body_data = None
    files = None

    if not api_request.body or api_request.method not in ('POST', 'PUT', 'PATCH'):
        return body_type, body_data, files

    body_type = api_request.body.get('type', 'json')

    if body_type == 'json':
        body_data = _replace_variables_in_dict(api_request.body.get('data', {}), variables)
        if resolver:
            body_data = _resolve_variables_in_dict(body_data, resolver)
    elif body_type in ('form-data', 'x-www-form-urlencoded'):
        body_data = {}
        for item in iter_form_items(api_request.body.get('data', [])):
            if item.get('enabled', True):
                text = _replace_variables(str(item.get('value', '')), variables)
                body_data[item.get('key', '')] = resolver.resolve(text) if resolver else text
    elif body_type == 'raw':
        body_data = _replace_variables(api_request.body.get('data', ''), variables)
        if resolver:
            body_data = resolver.resolve(body_data)
    elif body_type == 'binary':
        file_data = api_request.body.get('file_data')
        if file_data:
            files = []
            for file_item in file_data:
                if file_item.get('enabled', True) and file_item.get('path'):
                    files.append((file_item.get('key', ''), open(file_item['path'], 'rb')))

    return body_type, body_data, files


def _global_variable_value(gv):
    """取全局变量的有效值：变量值优先，其次初始值。"""
    if gv.value not in (None, ''):
        return gv.value
    return gv.initial_value or ''


def global_variables_for_project(project):
    """取某项目可用的全局变量（GlobalVariable 表），项目级优先、跨项目兜底。

    host_test 这类域名变量通常配在「适用项目为空」的全局变量里，
    只按当前项目查会查不到，导致执行时 {{host_test}} 原样发出去、请求直接失败。
    """
    from django.db.models import F, Q
    from .models import GlobalVariable

    if project:
        # 同时纳入「属于本项目」和「不绑定项目」的全局变量
        qs = GlobalVariable.objects.filter(Q(project=project) | Q(project__isnull=True))
    else:
        # 无项目上下文时只取跨项目全局变量，避免误用某个项目的专属变量
        qs = GlobalVariable.objects.filter(project__isnull=True)
    # 属于当前项目的排在前面，同名变量以它为准
    qs = qs.order_by(F('project').desc(nulls_last=True), 'id')

    variables = {}
    for gv in qs:
        variables.setdefault(gv.key, _global_variable_value(gv))

    # 展开变量互引（如 host_dongtai = {{host_zs}}），与原环境变量解析行为一致
    for _ in range(5):
        changed = False
        for key, value in list(variables.items()):
            if not isinstance(value, str):
                continue
            new_value = _replace_variables(value, variables)
            if new_value != value:
                variables[key] = new_value
                changed = True
        if not changed:
            break
    return variables


def _persist_global_variables(project, variables, api_request=None):
    """把 Tests 脚本里 pm.globals.set 写入的变量持久化到 GlobalVariable 表。"""
    from .models import GlobalVariable

    user = getattr(api_request, 'created_by', None)
    for key, value in (variables or {}).items():
        if not key:
            continue
        val = value.get('currentValue') if isinstance(value, dict) else value
        if val is None:
            val = ''
        val = str(val)
        obj = GlobalVariable.objects.filter(key=key, project=project).first()
        if obj:
            obj.value = val
            obj.save(update_fields=['value', 'updated_at'])
        elif user:
            GlobalVariable.objects.create(
                key=key, project=project, value=val, initial_value=val,
                created_by=user,
            )


def collect_global_variables(api_request):
    """按接口所属项目取全局环境变量（执行期用）。"""
    project = None
    collection = getattr(api_request, 'collection', None)
    if collection:
        project = getattr(collection, 'project', None)
    return global_variables_for_project(project)


def prepare_request_parts(api_request, environment, resolver=None):
    """按环境变量准备一次请求的 url / headers / params / body。

    返回值 (parts, missing)：
      parts   —— {'url','headers','params','body_type','body_data','files','variables'}
      missing —— 环境中缺失的变量名列表，非空时调用方应中断执行并提示用户
    """
    resolver = resolver or VariableResolver()
    # 旧 GLOBAL 环境不再作为局部变量合并（全局变量走 GlobalVariable）
    if environment is not None and getattr(environment, 'scope', '') == 'GLOBAL':
        environment = None
    variables = normalize_env_variables(environment)

    # 环境里没配的变量回落到全局环境，否则未指定环境执行套件时
    # host_test 这类全局变量会被判为「未定义」而整条失败
    for key, value in collect_global_variables(api_request).items():
        variables.setdefault(key, value)

    missing = find_undefined_variables(
        api_request.url,
        json.dumps(api_request.headers, ensure_ascii=False, default=str),
        json.dumps(api_request.params, ensure_ascii=False, default=str),
        json.dumps(api_request.body, ensure_ascii=False, default=str),
        json.dumps(api_request.auth, ensure_ascii=False, default=str),
        variables=variables,
    )

    parts = {
        'url': resolve_url_with_host(api_request.url, variables, resolver),
        'headers': _build_headers(api_request.headers, variables, resolver),
        'params': _build_params(api_request.params, variables, resolver),
        'variables': variables,
    }

    body_type, body_data, files = _build_body(api_request, variables, resolver)
    parts['body_type'] = body_type
    parts['body_data'] = body_data
    parts['files'] = files

    # 认证信息统一从环境变量取值（用例里不写死 token）
    for key, value in build_auth_headers(api_request.auth, variables, resolver).items():
        parts['headers'].setdefault(key, value)

    # 表单类请求不能沿用用例里手写的 Content-Type：
    # 例如写死 multipart/form-data 却没有 boundary，服务端解析不到表单会返回 401/400。
    # 交给 requests 依据实际 data/files 自动生成正确的头。
    if parts['body_type'] in ('form-data', 'x-www-form-urlencoded', 'binary'):
        for key in [k for k in parts['headers'] if str(k).lower() == 'content-type']:
            parts['headers'].pop(key)

    return parts, missing
