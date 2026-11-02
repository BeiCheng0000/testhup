"""AI 接口用例：生成 / AI自审 / 采纳 / 执行。

只调用既有能力（AIServiceConfig、AIModelConfig、ApiRequest、TestSuite、执行引擎），
不修改任何既有代码。
"""
import json
import logging
import re
import threading
import time

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

GENERATION_SYSTEM_PROMPT = """你是一名资深接口测试专家，负责编写可直接被自动化执行的接口测试用例。
你必须只输出严格合法的 JSON 数组，不要输出任何解释、Markdown 说明或额外文字。
数组每个元素代表一条接口用例，字段如下：
{
  "name": "用例名称",
  "method": "GET|POST|PUT|PATCH|DELETE",
  "url": "完整URL或路径",
  "headers": {"Content-Type": "application/json"},
  "params": {"key": "value"},
  "body": {"type": "json", "data": {}},
  "assertions": [{"name": "状态码断言", "type": "status_code", "expected": 200}],
  "expected_result": "预期结果描述",
  "description": "用例描述/测试点",
  "priority": "P0|P1|P2|P3",
  "rationale": "为什么这样设计"
}
断言 type 只允许：status_code / response_time / contains / json_path / header。
status_code 的 expected 必须是整数（如 200）。
json_path 断言需额外提供 json_path 字段，如 "$.code"。
body.type 只允许 json / form-data / raw / none。

断言要面向真实响应校准：优先校验"结构 / 类型 / 关键字段存在性 / 状态码"这类稳定特征，
避免写死与具体数据强绑定的固定值（如把某个动态 id、时间戳、本次返回的 token 当成 expected）；
生成后会以真实试跑响应再次校验并校准断言，所以断言应描述"真实合理的响应长什么样"，而非臆测固定值。
"""

REVIEW_SYSTEM_PROMPT = """你是一名接口测试用例评审专家。
对给定的用例逐条评审，只输出严格合法的 JSON 数组，不要任何额外文字。
每个元素：{"index": 用例序号(从0开始), "action": "approve|reject|needs_revision", "comment": "简短评审意见"}

【首要原则：真实响应优先 / 对齐原则】
当用例已真实试跑并附带 actual_response（接口真实返回的响应体），且真实响应在业务上合理、
与用例的测试目标一致（例如成功场景返回了成功的数据、关键字段基本齐全、没有错误码或异常结构）时——
即使某些断言字面没命中真实响应，也应视为"用例的断言 / 预期值需要按真实响应校正"，
而不是判定用例不通过。此时：
  - 若仅断言字面不符、响应本身合理：建议 action=approve，并在 comment 中说明"建议把断言对齐到真实响应即可"；
  - 或 action=needs_revision，但 comment 必须明确"仅微调断言 / 预期值去匹配真实响应，不要改动请求与场景"。
切记：断言是验证接口行为的手段，不是目的。当真实响应合理且符合预期时，应让用例去描述真实响应，
而不是要求真实响应去符合写死的断言。不要把"响应和设想不一致但业务合理"当成缺陷。

【第一层：用例设计合理性】URL/参数/请求是否合理、是否覆盖正向+异常+边界、断言是否充分且可执行、
是否缺少鉴权或必要请求头。注意：若断言只是"写得太死 / 预期值过时 / 字段名与真实响应不一致"导致没命中，
这是用例侧可校正的问题，不应据此 reject 用例本身。

【第二层：实际响应数据合理性】只有当真实响应本身确实错误时才判不通过：
  - 真实返回了错误码（如 $.code 非成功值）、被包装成成功的失败、空数组 / 空对象、缺关键字段、
    数据结构违反接口契约、业务字段前后矛盾、或状态码与业务语义明显不符；
  - 重要：接口本身不是标准答案，actual_response 只是当前"现状"，你要基于接口契约、业务常识和
    用例设计目标判断数据"应不应该长这样"；
  - 但若响应只是"和最初设想的字面不完全一致、但业务上合理且符合测试目标"，那不是响应的问题，
    而是用例断言需要校正——按上面的对齐原则处理，不要 reject。
"""


def _generation_system_prompt():
    """接口用例生成的系统提示词：优先用配置中心的 api_case_generate，否则用内置默认。"""
    try:
        from apps.requirement_analysis.models import PromptConfig
        cfg = PromptConfig.get_active_config('api_case_generate')
        if cfg and cfg.content and cfg.content.strip():
            return cfg.content.strip()
    except Exception:
        pass
    return GENERATION_SYSTEM_PROMPT


def _review_system_prompt():
    """接口用例评审的系统提示词：优先用配置中心的 api_case_review，否则用内置默认。"""
    try:
        from apps.requirement_analysis.models import PromptConfig
        cfg = PromptConfig.get_active_config('api_case_review')
        if cfg and cfg.content and cfg.content.strip():
            return cfg.content.strip()
    except Exception:
        pass
    return REVIEW_SYSTEM_PROMPT


def resolve_ai_config():
    """优先使用接口测试模块的 AIServiceConfig，回退到需求分析的 AIModelConfig(writer)。"""
    # 1) 接口测试模块的 AI 服务配置
    try:
        from apps.api_testing.models import AIServiceConfig
        cfg = AIServiceConfig.objects.filter(is_active=True).exclude(api_key='').first()
    except Exception as exc:
        logger.warning('读取 AIServiceConfig 失败: %s', exc)
        cfg = None

    if cfg:
        return {
            'source': 'api_testing',
            'base_url': cfg.base_url,
            'api_key': cfg.api_key,
            'model_name': cfg.model_name,
            'temperature': cfg.temperature or 0.7,
            'max_tokens': cfg.max_tokens or 4096,
            'label': f"{cfg.name}({cfg.service_type})",
        }

    # 2) 需求分析模块的配置（writer 优先）
    try:
        from apps.requirement_analysis.models import AIModelConfig
        cfg2 = (AIModelConfig.objects.filter(role='writer', is_active=True).exclude(api_key='').first()
                or AIModelConfig.objects.filter(is_active=True).exclude(api_key='').first())
    except Exception as exc:
        logger.warning('读取 AIModelConfig 失败: %s', exc)
        cfg2 = None

    if cfg2:
        return {
            'source': 'requirement_analysis',
            'base_url': cfg2.base_url,
            'api_key': cfg2.api_key,
            'model_name': cfg2.model_name,
            'temperature': cfg2.temperature or 0.7,
            'max_tokens': cfg2.max_tokens or 4096,
            'label': f"{cfg2.name}({cfg2.model_type})",
        }

    return None


def iter_ai_configs():
    """按优先级返回所有可尝试的 AI 配置（按 base_url + model_name 去重）。

    顺序：接口测试的 AIServiceConfig → 需求分析 AIModelConfig（writer 优先）。
    这样某个模型名不存在/无权限时会自动尝试下一个，而不是整条链路失败。
    """
    configs = []
    seen = set()

    def _add(cfg):
        base = (cfg.get('base_url') or '').strip()
        model = (cfg.get('model_name') or '').strip()
        if not base or not model or not cfg.get('api_key'):
            return
        key = (base, model)
        if key in seen:
            return
        seen.add(key)
        configs.append(cfg)

    try:
        from apps.api_testing.models import AIServiceConfig
        for c in AIServiceConfig.objects.filter(is_active=True).exclude(api_key='').order_by('id'):
            _add({
                'source': 'api_testing',
                'base_url': c.base_url,
                'api_key': c.api_key,
                'model_name': c.model_name,
                'temperature': c.temperature or 0.7,
                'max_tokens': c.max_tokens or 4096,
                'label': f'{c.name}({c.service_type})',
            })
    except Exception as exc:
        logger.warning('读取 AIServiceConfig 失败: %s', exc)

    try:
        from apps.requirement_analysis.models import AIModelConfig
        rows = list(AIModelConfig.objects.filter(is_active=True).exclude(api_key='').order_by('id'))
        rows.sort(key=lambda x: 0 if getattr(x, 'role', '') == 'writer' else 1)
        for c in rows:
            _add({
                'source': 'requirement_analysis',
                'base_url': c.base_url,
                'api_key': c.api_key,
                'model_name': c.model_name,
                'temperature': c.temperature or 0.7,
                'max_tokens': c.max_tokens or 4096,
                'label': f'{c.name}({c.model_type})',
            })
    except Exception as exc:
        logger.warning('读取 AIModelConfig 失败: %s', exc)

    return configs


def build_endpoint(base_url):
    """拼出 chat completions 地址，兼容不同厂商的 base_url 形态。

    - .../chat/completions        -> 原样
    - .../v1、.../v3（火山方舟等）  -> + /chat/completions
    - https://api.deepseek.com    -> + /v1/chat/completions
    """
    base = (base_url or '').strip().rstrip('/')
    if not base:
        return ''
    if 'chat/completions' in base:
        return base
    if re.search(r'/v\d+$', base):
        return base + '/chat/completions'
    return base + '/v1/chat/completions'


def call_llm(cfg, system_prompt, user_prompt, timeout=300, max_tokens=None):
    """调用 OpenAI 兼容的 chat completions 接口，返回文本。"""
    endpoint = build_endpoint(cfg.get('base_url'))
    if not endpoint:
        raise ValueError('AI 配置缺少 base_url')
    if not cfg.get('api_key'):
        raise ValueError('AI 配置缺少 api_key')

    payload = {
        'model': cfg.get('model_name'),
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': cfg.get('temperature', 0.7),
        'max_tokens': max_tokens or cfg.get('max_tokens', 4096),
    }
    headers = {
        'Authorization': f"Bearer {cfg.get('api_key')}",
        'Content-Type': 'application/json',
    }

    resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        raise ValueError(f"AI 服务返回 {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    try:
        message = data['choices'][0]['message']
    except (KeyError, IndexError, TypeError):
        raise ValueError(f"AI 返回结构异常: {str(data)[:500]}")

    content = (message.get('content') or '').strip()
    if not content:
        reasoning = (message.get('reasoning_content') or '')[:200]
        raise ValueError(f'AI 未返回正文内容（可能被 max_tokens 截断或为思考型模型）: {reasoning}')
    return content


def call_llm_with_fallback(system_prompt, user_prompt, timeout=300, max_tokens=None):
    """依次尝试所有可用 AI 配置，返回 (text, cfg)；全部失败则抛出汇总错误。"""
    configs = iter_ai_configs()
    if not configs:
        raise ValueError('未找到可用的 AI 配置，请先在「AI服务配置」或需求分析模块配置 '
                         'base_url / api_key / model_name。')

    errors = []
    for cfg in configs:
        try:
            text = call_llm(cfg, system_prompt, user_prompt,
                            timeout=timeout, max_tokens=max_tokens)
            logger.info('AI 调用成功: %s', cfg.get('label'))
            return text, cfg
        except Exception as exc:
            logger.warning('AI 配置 %s 调用失败: %s', cfg.get('label'), exc)
            errors.append(f"{cfg.get('label')}: {str(exc)[:180]}")

    raise ValueError('所有 AI 配置均调用失败 → ' + '；'.join(errors))


def extract_json_array(text):
    """从模型输出中提取 JSON 数组（兼容 ```json 代码块）。"""
    if not text:
        return None
    content = text.strip()

    fence = re.search(r'```(?:json)?\s*(.*?)```', content, re.S)
    if fence:
        content = fence.group(1).strip()

    candidates = []
    start = content.find('[')
    end = content.rfind(']')
    if start != -1 and end != -1 and end > start:
        candidates.append(content[start:end + 1])
    candidates.append(content)

    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except Exception:
            continue
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ('cases', 'test_cases', 'data', 'results'):
                if isinstance(parsed.get(key), list):
                    return parsed[key]
    return None


def _as_dict(val):
    if isinstance(val, dict):
        return val
    if isinstance(val, list):
        out = {}
        for item in val:
            if isinstance(item, dict):
                key = item.get('key') or item.get('name')
                if key and item.get('enabled', True):
                    out[key] = item.get('value', '')
        return out
    return {}


def _form_items(data):
    """把 form-data / urlencoded 的 data 规范为执行引擎要求的 list[{key,value,enabled}]。

    执行引擎是按列表遍历并调用 item.get() 的，若 data 是 dict 会遍历出字符串键，
    从而抛出 'str' object has no attribute 'get'。
    """
    if isinstance(data, dict):
        items = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            items.append({
                'key': str(key),
                'value': '' if value is None else str(value),
                'enabled': True,
            })
        return items

    if isinstance(data, list):
        items = []
        for item in data:
            if isinstance(item, dict):
                value = item.get('value')
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                items.append({
                    'key': str(item.get('key', '')),
                    'value': '' if value is None else str(value),
                    'enabled': item.get('enabled', True),
                })
            elif isinstance(item, str):
                if '=' in item:
                    key, value = item.split('=', 1)
                    items.append({'key': key, 'value': value, 'enabled': True})
                elif item.strip():
                    items.append({'key': item.strip(), 'value': '', 'enabled': True})
        return items

    return []


def _normalize_body(raw_body):
    """统一为 {'type': ..., 'data': ...}，且 data 结构与执行引擎的读取方式一致。

    - json: data 为 dict/list（字符串会尝试解析）
    - form-data / x-www-form-urlencoded: data 必须是 list[{key,value,enabled}]
    - raw: data 为字符串
    """
    if raw_body is None:
        return {}
    if isinstance(raw_body, str):
        try:
            parsed = json.loads(raw_body)
        except Exception:
            return {'type': 'raw', 'data': raw_body}
        return _normalize_body(parsed)
    if isinstance(raw_body, list):
        return {'type': 'json', 'data': raw_body}
    if not isinstance(raw_body, dict):
        return {}

    if 'type' in raw_body or 'data' in raw_body:
        body_type = str(raw_body.get('type') or '').strip().lower()
        data = raw_body.get('data')

        if body_type in ('form-data', 'form_data', 'multipart'):
            return {'type': 'form-data', 'data': _form_items(data)}
        if body_type in ('x-www-form-urlencoded', 'urlencoded', 'url-encoded'):
            return {'type': 'x-www-form-urlencoded', 'data': _form_items(data)}
        if body_type in ('raw', 'text'):
            return {'type': 'raw',
                    'data': data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)}
        if body_type in ('none', ''):
            if not data:
                return {'type': 'none', 'data': None}
            body_type = 'json'

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                return {'type': 'raw', 'data': data}
        return {'type': 'json', 'data': {} if data is None else data}

    return {'type': 'json', 'data': raw_body}


def _normalize_assertions(raw_assertions):
    allowed = {'status_code', 'response_time', 'contains', 'json_path', 'header'}
    default = [{'name': '状态码断言', 'type': 'status_code', 'expected': 200}]

    if not isinstance(raw_assertions, list) or not raw_assertions:
        return default

    result = []
    for item in raw_assertions:
        if not isinstance(item, dict):
            continue
        a_type = item.get('type') or 'status_code'
        if a_type not in allowed:
            a_type = 'status_code'

        expected = item.get('expected') if item.get('expected') is not None else item.get('value')
        # AI 有时会编造 {{not_empty}} 这类模板函数，执行时无法解析，断言会恒失败
        if isinstance(expected, str) and re.fullmatch(r'\{\{\s*[\w.]+\s*\}\}', expected.strip()):
            if a_type == 'json_path' and item.get('json_path'):
                expected = None  # 转为「字段存在且非空」校验
            else:
                continue  # 其它类型的伪期望直接丢弃

        assertion = {
            'name': item.get('name') or '断言',
            'type': a_type,
            'expected': expected,
        }
        if a_type == 'status_code':
            try:
                assertion['expected'] = int(assertion['expected'])
            except (TypeError, ValueError):
                assertion['expected'] = 200
        if item.get('json_path'):
            assertion['json_path'] = item['json_path']
        if item.get('header_name'):
            assertion['header_name'] = item['header_name']
        result.append(assertion)

    return result or default


# URL 开头的域名变量前缀：{{host_test}}、{host_test} 都算
_HOST_VAR_PREFIX_RE = re.compile(r'^\s*\{\{?\s*[A-Za-z_][\w.\-]*\s*\}?\}\s*')


def _host_var_prefix(url):
    """取 URL 开头的域名变量前缀，原样返回（保留单/双花括号写法）。"""
    if not url:
        return ''
    m = _HOST_VAR_PREFIX_RE.match(url)
    return m.group(0) if m else ''


# 整个值就是一个变量占位，如 {{token}} / {token}
_PLACEHOLDER_VALUE_RE = re.compile(r'^\s*\{\{?\s*([A-Za-z_][\w.\-]*)\s*\}?\}\s*$')


def _restore_real_headers(headers, source_request, available_variables):
    """把模型臆造的占位请求头还原成来源接口的真实值。

    模型常把来源接口里真实的 token 值改写成 {{valid_token}}，而环境里并没有这个变量，
    执行时不会被替换、只会原样发出，必然鉴权失败。
    还原条件：来源接口有同名头的真实值，且该占位变量确实未定义。
    """
    if not headers or source_request is None:
        return headers

    src_values = {}
    for item in (getattr(source_request, 'headers', None) or []):
        if not isinstance(item, dict) or not item.get('enabled', True):
            continue
        key = (item.get('key') or item.get('name') or '').strip()
        value = item.get('value') or ''
        # 来源本身就是占位（如 {{token}}）——属于有意的变量引用，不参与还原
        if not key or not value or _PLACEHOLDER_VALUE_RE.match(value):
            continue
        src_values[key.lower()] = value

    if not src_values:
        return headers

    fixed = {}
    for key, value in headers.items():
        text = value if isinstance(value, str) else ''
        m = _PLACEHOLDER_VALUE_RE.match(text)
        if m and m.group(1) not in (available_variables or set()):
            real = src_values.get(str(key).lower())
            if real:
                logger.info('还原被改写的请求头 %s: %s -> 来源接口的真实值', key, value)
                fixed[key] = real
                continue
        fixed[key] = value
    return fixed


def normalize_case(raw, index, source_url=None, source_request=None, available_variables=None):
    """把模型输出的一条用例归一化为草稿字段。

    url 默认保持相对路径（如 /api/v1/users），域名由执行环境变量的 host 自动补全；
    但若来源接口用 {{host_test}} 指定了环境，相对路径要补回这个前缀——
    否则执行时回落到默认 host，用例会打到另一个环境。
    """
    name = (raw.get('name') or raw.get('title') or f'AI用例-{index + 1}').strip()
    method = str(raw.get('method') or 'GET').upper()
    if method not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'):
        method = 'GET'

    url = (raw.get('url') or raw.get('path') or '').strip()

    # 来源接口用 {{host_test}} 指定环境时补回前缀，避免执行时落到默认 host
    prefix = _host_var_prefix(source_url or '')
    if prefix and url and not _host_var_prefix(url) \
            and not url.startswith(('http://', 'https://')):
        url = prefix + '/' + url.lstrip('/')

    priority = str(raw.get('priority') or 'P1').upper()
    if priority not in ('P0', 'P1', 'P2', 'P3'):
        priority = 'P1'

    headers = _as_dict(raw.get('headers'))
    if source_request is not None:
        headers = _restore_real_headers(headers, source_request, available_variables)

    return {
        'name': name[:200],
        'method': method,
        'url': url,
        'headers': headers,
        'params': _as_dict(raw.get('params') or raw.get('query')),
        'body': _normalize_body(raw.get('body')),
        'auth': _as_dict(raw.get('auth')),
        'pre_request_script': raw.get('pre_request_script') or '',
        'post_request_script': raw.get('post_request_script') or '',
        'assertions': _normalize_assertions(raw.get('assertions')),
        'description': raw.get('description') or '',
        'expected_result': raw.get('expected_result') or raw.get('expected') or '',
        'priority': priority,
        'ai_rationale': raw.get('rationale') or raw.get('ai_rationale') or '',
    }


PROBE_LIMIT = 10  # 单次任务最多预跑多少个接口，避免生成等待过久
PROBE_SENSITIVE_KEYS = ('token', 'secret', 'password', 'authorization', 'cookie', 'session')
PROBE_EXACT_SENSITIVE_KEYS = ('key', 'api_key', 'apikey', 'accesskey')


def _truncate_text(text, limit=1200):
    text = str(text or '')
    return text if len(text) <= limit else text[:limit] + '...（已截断）'


def _mask_value(value, key=''):
    """响应里的敏感字段不进入提示词，避免把 token 原样喂给模型。"""
    lowered = str(key).lower()
    if any(word in lowered for word in PROBE_SENSITIVE_KEYS) or lowered in PROBE_EXACT_SENSITIVE_KEYS:
        return '***'
    if isinstance(value, dict):
        return {k: _mask_value(v, k) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [_mask_value(item, key) for item in value[:5]]
    if isinstance(value, str) and len(value) > 300:
        return value[:300] + '...'
    return value


def probe_request(api_request, environment, user):
    """用绑定环境真实调用一次接口，采集响应结构供模型写用例。

    基线没跑通也不中断生成：把失败信息交给模型，让它只写状态码类断言。
    """
    from apps.api_testing.utils import execute_api_request

    item = {
        'request_id': api_request.id,
        'name': api_request.name,
        'method': api_request.method,
        'url': api_request.url,
        'ok': False,
        'status_code': None,
        'content_type': '',
        'response_time': None,
        'json_preview': None,
        'body_preview': '',
        'error': '',
        'assertion_error': '',
    }

    try:
        result = execute_api_request(api_request, environment, user)
    except Exception as exc:
        item['error'] = f'调用异常：{exc}'
        return item

    status_code = result.get('status_code')
    response_data = result.get('response_data') or {}
    headers = response_data.get('headers') or {}

    item['status_code'] = status_code
    item['ok'] = status_code is not None
    if result.get('response_time') is not None:
        item['response_time'] = round(result.get('response_time') or 0, 1)
    item['content_type'] = next(
        (str(v) for k, v in headers.items() if str(k).lower() == 'content-type'), '')
    item['body_preview'] = _truncate_text(response_data.get('body'))
    if response_data.get('json') is not None:
        item['json_preview'] = _mask_value(response_data.get('json'))

    if not item['ok']:
        item['error'] = _truncate_text(result.get('error') or '请求未拿到响应', 300)
    elif result.get('success') is False:
        item['assertion_error'] = _truncate_text(result.get('error'), 300)

    return item


def _probe_prompt_block(probes):
    """把预跑结论提炼成给模型的硬性约束。"""
    if not probes:
        return ''
    ok_count = sum(1 for p in probes if p.get('ok') and 200 <= (p.get('status_code') or 0) < 300)
    lines = [
        '【接口预跑结果】',
        f'生成前已用真实请求调用过这些接口：{ok_count}/{len(probes)} 个返回 2xx。',
        '每个接口的 probe 字段就是本次真实调用的结果：'
        'status_code 实际状态码、json_preview 真实响应体（敏感字段已脱敏）、'
        'body_preview 文本响应、error 表示请求根本没通。',
        '写用例时必须遵守：',
        '1. 正常场景的 status_code 断言直接使用 probe 里实测到的 2xx 状态码；',
        '2. json_path 必须严格按 json_preview 的真实层级书写（如 $.data.access_token），'
        '不确定层级时改用 contains 断言字段名；',
        '3. probe.ok 为 false 或状态码非 2xx 的接口，说明基线没跑通，'
        '只生成以状态码为主的用例，并在 description 里注明"基线未跑通"及原因；',
        '4. 异常场景的期望状态码按接口语义推断（参数缺失 400、鉴权失败 401、无权限 403、不存在 404），'
        '不要照抄正常场景的 200。',
    ]
    return '\n'.join(lines)


def _request_brief(api_request, index, probe=None):
    """把接口管理中的一条接口压缩成给模型看的定义。"""
    brief = {
        'index': index,
        'id': api_request.id,
        'name': api_request.name,
        'description': api_request.description,
        'method': api_request.method,
        'url': api_request.url,
        'headers': api_request.headers,
        'params': api_request.params,
        'body': api_request.body,
        'auth': api_request.auth,
        'assertions': api_request.assertions,
    }
    if probe is not None:
        brief['probe'] = probe
    return brief


def _collect_variables(environment, project=None):
    """任务可用的变量 = 绑定环境 + 全局环境(scope=GLOBAL)。

    全局环境里常放 host_test 这类域名变量，且有的不绑定项目(project=None)，
    不纳入的话模型根本不知道它存在，只能生成相对路径的 URL。
    """
    variables = dict(environment.variables or {}) if environment else {}
    try:
        from apps.api_testing.utils import global_variables_for_project
        for key, value in global_variables_for_project(project).items():
            variables.setdefault(key, value)
    except Exception as exc:  # 取不到全局变量不该阻断生成
        logger.warning('读取全局环境变量失败，提示词仅含绑定环境: %s', exc)
    return variables


def _env_prompt_block(environment, project=None):
    """生成给模型看的环境变量说明（只给变量名与地址，不展开其它敏感值）。"""
    variables = _collect_variables(environment, project)

    lines = [f'【执行环境】{environment.name}' if environment else '【执行环境】未绑定环境']
    keys = sorted(variables.keys())
    if keys:
        lines.append('【可用变量】' + '、'.join('{{%s}}' % k for k in keys))
        def _plain(v):
            # 环境里可能存成编辑器形态 {"currentValue": "...", "initialValue": "..."}
            if isinstance(v, dict):
                return v.get('currentValue') or v.get('initialValue') or ''
            return '' if v is None else v

        hosts = {k: _plain(variables[k])
                 for k in ('host', 'host_test', 'host_zs', 'host_pre',
                           'base_url', 'domain', 'HOST', 'BASE_URL')
                 if _plain(variables.get(k))}
        if hosts:
            lines.append('【环境地址】' + json.dumps(hosts, ensure_ascii=False))
    lines.append(
        'url 书写要求：默认用相对路径（如 /api/v1/users）；'
        '若来源接口 url 以 {{host_test}} 这类变量开头，必须原样保留该变量前缀'
        '（如 {{host_test}}/report/...），既不要改成相对路径也不要写死域名——'
        '它决定用例打到哪个环境。'
    )
    lines.append(
        '请求头要求（重要）：来源接口已有的请求头（token / Authorization / Cookie 等）'
        '必须原样照抄其 value，具体值（如 login_xxx、eyJhbGci...）直接保留，'
        '不要替换成 {{valid_token}} 这类占位——具体值本来就能直接执行，'
        '换成不存在的变量后执行时不会被替换、只会原样发出，必然鉴权失败；'
        '只有来源接口本身就写成 {{token}} 占位时才保留占位。'
    )
    lines.append(
        '变量使用：只能使用上面【可用变量】列出的变量名，'
        '禁止发明不存在的变量（如 valid_token、token_value）——'
        '未定义的变量执行时不会被替换，会原样发给服务端，导致请求必然失败。'
    )
    return '\n'.join(lines)


def build_generation_prompt(task, source_requests=None, probes=None):
    """构建生成 Prompt：优先基于接口管理中勾选的已有接口，否则回退到文本描述。

    probes 为预跑结果（按 request_id 索引），让模型按真实响应结构写断言。
    """
    env_block = _env_prompt_block(
        getattr(task, 'environment', None), getattr(task, 'project', None))
    probes = probes or {}

    if source_requests:
        payload = [_request_brief(r, i, probes.get(r.id)) for i, r in enumerate(source_requests)]
        probe_block = _probe_prompt_block([p for p in probes.values() if p])
        lines = [
            f'下面是接口管理中的 {len(source_requests)} 个已有接口定义（JSON 数组）。',
            '请为**每一个接口**设计可直接自动化执行的接口测试用例，条数由接口的复杂度自行决定：',
            '参数多、分支多、鉴权复杂的接口多设计几条；简单接口至少覆盖 1 条正常和 1 条异常。',
            '不要为了凑数重复用例，也不设条数上限，以覆盖充分为准。',
            '',
            '覆盖方向：正常调用、必填参数缺失、参数类型/边界异常、鉴权缺失或 token 失效、越权/无权限、资源不存在、重复提交。',
            '',
            f'【测试关注点】{task.focus or "正向、参数校验、边界、鉴权、异常场景"}',
            env_block,
        ]
        if probe_block:
            lines.append(probe_block)
        lines.extend([
            '',
            '【接口定义】',
            json.dumps(payload, ensure_ascii=False, indent=2),
            '',
            '输出要求：',
            '1. 输出 JSON 数组，每个元素是一条用例；',
            '2. 每个元素必须包含 "source_index"，值为其来源接口在上面的 index；',
            '3. 用例 url 基于来源接口：默认写成以 / 开头的相对路径，追加查询参数即可，不要带协议和域名；'
            '若来源接口 url 以 {{host_test}} 这类变量开头，必须原样保留该变量前缀'
            '（如 {{host_test}}/report/...），不要改成相对路径也不要写死域名；',
            '4. 断言必须可执行：状态码用 status_code；校验响应字段时优先使用 probe.json_preview 的真实路径，'
            '层级不确定时用 contains 断言字段名；',
            '5. 不要输出 Content-Type 请求头，执行时会按 body 类型自动生成；',
            '6. 请求头（token / Authorization / Cookie 等）照抄来源接口的原 value，'
            '   具体字符串原样保留，不要替换成任何 {{...}} 占位；'
            '   只能使用【可用变量】中列出的变量名，禁止发明；',
            '7. 只输出 JSON 数组。',
        ])
        return '\n'.join(lines)

    lines = [
        '请为以下接口/需求编写可直接自动化执行的接口测试用例，条数由内容复杂度自行决定，不设上限。',
        '',
        f'【输入类型】{task.get_source_type_display()}',
        f'【测试关注点】{task.focus or "正向、异常、边界、鉴权、参数校验"}',
        env_block,
        '',
        '【输入内容】',
        task.source_content,
        '',
        '要求：用例覆盖正常场景、参数异常、边界值、鉴权缺失等；每条用例断言必须可执行；'
        'url 使用相对路径；token、id 等具体值原样保留，不要替换成占位变量；'
        '只能使用上面【可用变量】列出的变量名，禁止发明。',
        '只输出 JSON 数组。',
    ]
    return '\n'.join(lines)


def _set_task_progress(task, **kwargs):
    for key, value in kwargs.items():
        setattr(task, key, value)
    task.save()


def run_generation(task_id, user_id):
    """后台线程：调用 AI 生成草稿。"""
    from django.contrib.auth import get_user_model
    from django.db import connection

    from .models import ApiCaseDraft, ApiCaseDraftReview, ApiCaseGenerationTask

    try:
        connection.close()
    except Exception:
        pass

    User = get_user_model()
    user = User.objects.get(id=user_id)
    task = ApiCaseGenerationTask.objects.get(id=task_id)

    try:
        _set_task_progress(task, status='running', progress=5, error_message=None)

        # 环境：优先任务指定，否则回退到项目下激活的「局部」环境，用于渲染 URL 与鉴权变量
        # 全局变量已独立为 GlobalVariable，旧的 GLOBAL 环境不再作为生成环境
        environment = task.environment
        if environment is not None and environment.scope == 'GLOBAL':
            environment = None
        if environment is None and task.project_id:
            from apps.api_testing.models import Environment
            environment = Environment.objects.filter(
                project_id=task.project_id, scope='LOCAL', is_active=True
            ).order_by('id').first()
            if environment:
                task.environment = environment
                task.save(update_fields=['environment'])

        source_requests = []
        if task.source_type == 'interfaces':
            source_requests = list(task.source_requests.all().order_by('id'))

        # 生成前预跑：用真实请求打通接口，把真实响应交给模型写断言
        probes = {}
        if source_requests and task.probe_enabled:
            probe_targets = source_requests[:PROBE_LIMIT]
            probe_results = []
            _set_task_progress(task, progress=10)
            for idx, api_request in enumerate(probe_targets, start=1):
                probes[api_request.id] = probe_request(api_request, environment, user)
                probe_results.append(probes[api_request.id])
                _set_task_progress(
                    task,
                    progress=10 + int(30 * idx / len(probe_targets)),
                    probe_results=probe_results,
                )

        # 多配置兜底：某个模型名不可用时自动切换下一个可用配置
        text, cfg = call_llm_with_fallback(
            _generation_system_prompt(),
            build_generation_prompt(task, source_requests, probes),
            max_tokens=8192,
        )
        _set_task_progress(task, ai_config_snapshot={
            'label': cfg['label'], 'model': cfg['model_name'], 'source': cfg['source'],
            'environment': environment.name if environment else '',
            'probed': len(probes),
        }, progress=70)

        cases = extract_json_array(text)
        if cases is None:
            _set_task_progress(
                task, status='failed', progress=100, finished_at=timezone.now(),
                error_message=f'AI 输出无法解析为 JSON 用例数组：{str(text)[:300]}')
            return

        # 可用变量表：用于把模型臆造的占位请求头（如 {{valid_token}}）还原成真实值
        available_variables = set(_collect_variables(
            getattr(task, 'environment', None), getattr(task, 'project', None)).keys())

        created = 0
        for index, raw in enumerate(cases):
            if not isinstance(raw, dict):
                continue

            # 关联来源接口（模型输出的 source_index -> 勾选接口的序号）
            source_request = None
            if source_requests:
                raw_index = raw.get('source_index')
                try:
                    raw_index = int(raw_index)
                except (TypeError, ValueError):
                    raw_index = None
                if raw_index is not None and 0 <= raw_index < len(source_requests):
                    source_request = source_requests[raw_index]

            fields = normalize_case(
                raw, index,
                source_request.url if source_request else None,
                source_request=source_request,
                available_variables=available_variables,
            )
            if source_request and not fields['url']:
                fields['url'] = source_request.url

            draft = ApiCaseDraft.objects.create(
                task=task, created_by=user, status='pending_review',
                source_request=source_request, ai_raw=raw, order=index, **fields)
            ApiCaseDraftReview.objects.create(
                draft=draft, reviewer=None, reviewer_name='AI', action='submit',
                comment='AI 生成，等待审核', previous_status='', new_status='pending_review')
            created += 1

        # 生成完成后自动试跑所有用例：记录断言能否跑通并缓存真实响应（不自动修断言）
        if created:
            try:
                run_self_check(task, user, auto_fix=False)
            except Exception as exc:
                logger.warning('生成后自动试跑失败（不影响生成结果）：%s', exc)

        _set_task_progress(
            task,
            status='success' if created else 'partial',
            progress=100,
            total_generated=created,
            finished_at=timezone.now(),
            error_message=None if created else 'AI 未返回任何可用用例',
        )
    except Exception as exc:
        logger.exception('AI 生成接口用例失败')
        _set_task_progress(task, status='failed', progress=100, finished_at=timezone.now(),
                           error_message=str(exc)[:1000])


def run_self_check(task, user, auto_fix=True, fix_values=False, approve_on_pass=False):
    """对整个任务做试跑：逐条试跑、记录断言能否跑通、缓存真实响应。

    不自动修断言（去除「试图跑通」），也不改变用例审核状态，只把结果写到
    self_check_result 与 action='self_check' 的流水（与 AI 审核意见区分开）。
    返回汇总 {total, passed, needs_revision, error}。
    """
    from .models import ApiCaseDraft, ApiCaseDraftReview

    environment = task.environment
    if environment is not None and environment.scope == 'GLOBAL':
        environment = None
    if environment is None and task.project_id:
        from apps.api_testing.models import Environment
        environment = Environment.objects.filter(
            project_id=task.project_id, scope='LOCAL', is_active=True
        ).order_by('id').first()

    drafts = list(ApiCaseDraft.objects.filter(task=task)
                  .exclude(status='adopted').order_by('order', 'id'))
    summary = {'total': len(drafts), 'passed': 0,
               'needs_revision': 0, 'error': 0}
    if not drafts:
        return summary

    for draft in drafts:
        previous_status = draft.status
        checked, _ = self_check_draft(draft, user, environment, auto_fix=False, fix_values=False)
        verdict = checked['verdict']
        status_code = checked.get('status_code')

        if verdict == 'passed':
            summary['passed'] += 1
            comment = f'试跑通过（状态码 {status_code}），断言全部命中真实响应'
        elif verdict == 'error':
            summary['error'] += 1
            comment = f'试跑未拿到响应 —— {checked.get("error") or "请求失败"}'
        else:
            summary['needs_revision'] += 1
            comment = '试跑未通过：' + '；'.join(checked['unresolved'] or ['断言未通过'])

        # 只更新试跑结果，不改用例审核状态（避免误判通过/待修订）
        draft.self_check_result = checked
        draft.save(update_fields=['self_check_result', 'updated_at'])

        ApiCaseDraftReview.objects.create(
            draft=draft, reviewer=None, reviewer_name='系统', action='self_check',
            comment=comment[:2000], previous_status=previous_status, new_status=previous_status,
            extra={'verdict': verdict, 'status_code': status_code})

    task.ai_config_snapshot = dict(task.ai_config_snapshot or {})
    task.ai_config_snapshot['self_check'] = summary
    task.ai_config_snapshot['self_check_at'] = timezone.now().isoformat()
    task.save(update_fields=['ai_config_snapshot', 'updated_at'])
    return summary


def run_ai_review(task_id, user_id, auto_fix=True, fix_values=False, approve_on_pass=False):
    """后台线程：AI 审核。

    不再自动试跑——直接基于「已试跑并缓存」的响应头与响应体评审用例：
    1) 用例设计合理性；2) 实际响应数据合理性。
    """
    from django.contrib.auth import get_user_model
    from django.db import connection

    from .models import ApiCaseDraft, ApiCaseDraftReview, ApiCaseGenerationTask

    try:
        connection.close()
    except Exception:
        pass

    User = get_user_model()
    user = User.objects.get(id=user_id)
    task = ApiCaseGenerationTask.objects.get(id=task_id)

    try:
        updated = 0
        cfg = resolve_ai_config()
        if cfg:
            drafts = list(ApiCaseDraft.objects.filter(task=task).order_by('order', 'id')[:30])
            payload = [{
                'index': idx,
                'name': draft.name,
                'method': draft.method,
                'url': draft.url,
                'assertions': draft.assertions,
                'expected_result': draft.expected_result,
                'response_headers': (draft.self_check_result or {}).get('response_headers'),
                # 真实试跑拿到的响应体（脱敏、截断），用于评审「响应数据合理性」
                'actual_response': (draft.self_check_result or {}).get('response_preview'),
            } for idx, draft in enumerate(drafts)]

            user_prompt = (
                '以下用例已经真实试跑过，response_headers 是接口真实返回的响应头，'
                'actual_response 是接口真实返回的响应体（可能为空）。\n'
                '请基于真实响应评审：\n'
                '1) 用例设计合理性（断言是否遗漏、场景是否覆盖不足、请求是否正确）；\n'
                '2) 实际响应数据合理性（响应头与响应体是否完整、类型/值域是否合理、'
                '有无业务矛盾或异常结构）。\n'
                '注意：接口本身不是标准答案，应基于接口契约、业务常识判断数据是否合理。\n'
                '给出通过/驳回/需修订的结论与简短意见。\n'
                + json.dumps(payload, ensure_ascii=False, indent=2)
            )

            try:
                text = call_llm(cfg, _review_system_prompt(), user_prompt)
                reviews = extract_json_array(text) or []
            except Exception as exc:
                logger.warning('AI 复核意见生成失败：%s', exc)
                reviews = []

            for item in reviews:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item.get('index'))
                except (TypeError, ValueError):
                    continue
                if idx < 0 or idx >= len(drafts):
                    continue
                draft = drafts[idx]
                comment = (item.get('comment') or '').strip()
                if not comment:
                    continue
                ApiCaseDraftReview.objects.create(
                    draft=draft, reviewer=None, reviewer_name='AI', action='ai_review',
                    comment=comment[:2000], previous_status=draft.status,
                    new_status=draft.status,
                    extra={'suggestion': item.get('action')})
                updated += 1

        task.ai_config_snapshot = dict(task.ai_config_snapshot or {})
        task.ai_config_snapshot['last_ai_review_at'] = timezone.now().isoformat()
        task.ai_config_snapshot['last_ai_review_count'] = updated
        task.save(update_fields=['ai_config_snapshot', 'updated_at'])
    except Exception as exc:
        logger.exception('AI 审核接口用例失败')
        task.error_message = f'AI 审核失败：{str(exc)[:500]}'
        task.save(update_fields=['error_message', 'updated_at'])
    finally:
        # 释放并发锁，允许下一次审核；失败也不能影响主流程
        try:
            ApiCaseGenerationTask.objects.filter(pk=task_id).update(ai_review_running=False)
        except Exception:
            logger.exception('释放 AI 审核锁失败')


def _build_revise_prompt(draft, review_comment, response_preview):
    """构造「按审核意见 + 真实响应修订单条用例」的用户提示词。"""
    original = {
        'name': draft.name,
        'method': draft.method,
        'url': draft.url,
        'headers': draft.headers,
        'params': draft.params,
        'body': draft.body,
        'assertions': draft.assertions,
        'expected_result': draft.expected_result,
        'description': draft.description,
        'priority': draft.priority,
        'rationale': getattr(draft, 'ai_rationale', ''),
    }
    lines = [
        '你是一名接口测试专家。下面是一条已有的接口用例，以及该用例真实试跑拿到的接口响应数据，'
        '和 AI 审核对该用例给出的评审意见。',
        '请对该用例做"最小改动"式修订，并输出修订后的单条用例 JSON：',
        '1. 以【真实响应数据】为事实基准：优先只校正用例的"断言"和"预期结果"，'
        '让它们去匹配真实响应（修正 json_path 指向、expected 期望值、字段名、状态码、contains 内容等）；',
        '2. 不要重写请求：保持 url、method、headers、params、body 不变'
        '（除非评审意见明确指出请求本身有误）；',
        '3. 不要改变用例的核心测试目标与场景覆盖；',
        '4. 只有当真实响应本身不合理（缺字段、错误码、结构错误）时，才在 expected_result / description 中说明，'
        '但仍优先让断言去表达对真实合理响应的校验；',
        '5. 只输出一个 JSON 数组，数组仅含一个修订后的用例对象，字段结构与原用例一致'
        '（name/method/url/headers/params/body/assertions/expected_result/description/priority/rationale）。'
        '未改动的部分请原样保留原值，不要另起炉灶重写。',
        '',
        '【原用例】',
        json.dumps(original, ensure_ascii=False, indent=2),
        '',
        '【AI 评审意见】',
        review_comment or '（无）',
        '',
        '【真实响应数据】',
        response_preview or '（无，未拿到真实响应）',
    ]
    return '\n'.join(lines)


def run_ai_revise(task_id, user_id, draft_ids=None):
    """后台线程：根据 AI 审核意见与真实响应，自动改写用例。

    不传 draft_ids 时，默认对「已被 AI 审核过」的用例全部修订；
    传 draft_ids 时只修订指定草稿（如单条手动触发）。
    """
    from django.contrib.auth import get_user_model
    from django.db import connection

    from .models import ApiCaseDraft, ApiCaseDraftReview, ApiCaseGenerationTask

    try:
        connection.close()
    except Exception:
        pass

    User = get_user_model()
    user = User.objects.get(id=user_id)
    task = ApiCaseGenerationTask.objects.get(id=task_id)

    try:
        drafts = ApiCaseDraft.objects.filter(task=task)
        if draft_ids:
            drafts = drafts.filter(id__in=draft_ids)
        else:
            reviewed_ids = ApiCaseDraftReview.objects.filter(
                draft__task=task, action='ai_review').values_list(
                'draft_id', flat=True).distinct()
            drafts = drafts.filter(id__in=reviewed_ids)

        cfg = resolve_ai_config()
        if not cfg:
            task.error_message = '未配置可用 AI 模型，无法 AI 修订'
            task.save(update_fields=['error_message', 'updated_at'])
            return

        available_variables = set(_collect_variables(
            getattr(task, 'environment', None), getattr(task, 'project', None)).keys())

        revised = 0
        for draft in drafts.order_by('order', 'id'):
            ai_review = ApiCaseDraftReview.objects.filter(
                draft=draft, action='ai_review').order_by('-id').first()
            review_comment = (ai_review.comment or '').strip() if ai_review else ''
            response_preview = (draft.self_check_result or {}).get('response_preview')

            if not review_comment and not response_preview:
                continue

            user_prompt = _build_revise_prompt(draft, review_comment, response_preview)
            try:
                text, _ = call_llm_with_fallback(
                    _generation_system_prompt(), user_prompt, max_tokens=8192)
                cases = extract_json_array(text)
                if not cases:
                    # 兜底：模型可能只输出单个对象
                    try:
                        obj = json.loads(text[text.index('{'):text.rindex('}') + 1])
                        cases = [obj]
                    except Exception:
                        cases = []
            except Exception as exc:
                logger.warning('AI 修订调用失败（草稿 %s）：%s', draft.id, exc)
                continue

            if not cases or not isinstance(cases[0], dict):
                continue

            fields = normalize_case(
                cases[0], draft.order,
                source_url=draft.url,
                source_request=draft.source_request,
                available_variables=available_variables,
            )
            previous_status = draft.status
            # 最小改动：只校正「断言 / 预期结果 / 描述」，保留原请求与场景，
            # 避免整条重写把本来合理的用例改坏（这是"太死板"的根因之一）
            new_assertions = fields.get('assertions') or []
            if new_assertions:
                draft.assertions = new_assertions
            if fields.get('expected_result'):
                draft.expected_result = fields['expected_result']
            if fields.get('description'):
                draft.description = fields['description']
            draft.status = 'pending_review'
            draft.ai_raw = cases[0]
            draft.save()

            ApiCaseDraftReview.objects.create(
                draft=draft, reviewer=None, reviewer_name='AI', action='ai_revise',
                comment='AI 根据审核意见与真实响应修订用例：%s' % (
                    (review_comment or '无明确意见，仅按真实响应优化')[:300]),
                previous_status=previous_status, new_status='pending_review',
                extra={'review_comment': review_comment[:2000] if review_comment else None})

            revised += 1

        task.ai_config_snapshot = dict(task.ai_config_snapshot or {})
        task.ai_config_snapshot['last_ai_revise_at'] = timezone.now().isoformat()
        task.ai_config_snapshot['last_ai_revise_count'] = revised
        task.save(update_fields=['ai_config_snapshot', 'updated_at'])
    except Exception as exc:
        logger.exception('AI 修订接口用例失败')
        task.error_message = f'AI 修订失败：{str(exc)[:500]}'
        task.save(update_fields=['error_message', 'updated_at'])
    finally:
        try:
            ApiCaseGenerationTask.objects.filter(pk=task_id).update(ai_review_running=False)
        except Exception:
            logger.exception('释放 AI 修订锁失败')


def get_or_create_target_collection(task):
    """草稿采纳时的落地集合：优先任务指定集合，否则在项目下创建/复用「AI生成用例」。"""
    from apps.api_testing.models import ApiCollection

    if task.collection_id:
        return task.collection

    collection = ApiCollection.objects.filter(project=task.project, name='AI生成用例').first()
    if not collection:
        collection = ApiCollection.objects.create(
            project=task.project, name='AI生成用例',
            description='由 AI 接口用例中心自动创建，用于承载已采纳的用例')
    return collection


def _adopt_description(draft):
    """采纳后的描述：开头带上 AI 来源标记，在接口管理里一眼能看出出处。"""
    origin = draft.source_request.name if draft.source_request_id else 'AI 生成用例'
    tag = f'【AI 用例】源自接口：{origin}'
    base = draft.description or draft.expected_result or ''
    lines = [l for l in base.splitlines() if not l.startswith('【AI 用例】')]
    return '\n'.join([tag] + lines).strip()


def adopt_draft(draft, user, collection=None):
    """把草稿采纳为 ApiRequest（已存在则更新）。返回 ApiRequest。"""
    from apps.api_testing.models import ApiRequest

    collection = collection or get_or_create_target_collection(draft.task)

    values = {
        'collection': collection,
        'name': draft.name,
        'description': _adopt_description(draft),
        'method': draft.method,
        'url': draft.url,
        'headers': draft.headers or {},
        'params': draft.params or {},
        'body': draft.body or {},
        'auth': draft.auth or {},
        'pre_request_script': draft.pre_request_script or '',
        'post_request_script': draft.post_request_script or '',
        'assertions': draft.assertions or [],
        # 关联性标记：入库的接口能追溯到「哪个已有接口」生成的
        'ai_generated': True,
        'ai_source_request': draft.source_request,
    }

    api_request = draft.adopted_request
    if api_request:
        for key, value in values.items():
            setattr(api_request, key, value)
        api_request.save()
    else:
        api_request = ApiRequest.objects.create(created_by=user, **values)
        draft.adopted_request = api_request
        draft.save(update_fields=['adopted_request', 'updated_at'])

    return api_request


def adopt_task(task, user, suite_name=None, draft_ids=None):
    """批量采纳任务中「审核通过」的草稿，并汇总到一个测试套件。返回 (suite, adopted_count)。

    draft_ids 非空时只采纳这些勾选的草稿（仍需是「审核通过」状态）。
    """
    from apps.api_testing.models import TestSuite, TestSuiteRequest

    qs = task.drafts.filter(status='approved')
    if draft_ids:
        qs = qs.filter(id__in=draft_ids)
    drafts = list(qs.order_by('order', 'id'))
    if not drafts:
        # 勾选项都还没审核通过是常见操作顺序问题，不是异常：
        # 返回 (None, 0) 让调用方给出引导提示，避免前端弹红色 400 错误
        return None, 0

    collection = get_or_create_target_collection(task)
    suite_name = suite_name or f'{task.name}-自动化套件'

    suite = TestSuite.objects.filter(project=task.project, name=suite_name).first()
    if not suite:
        suite = TestSuite.objects.create(
            project=task.project, name=suite_name,
            description=f'由 AI 接口用例任务「{task.name}」自动创建',
            environment=task.environment, created_by=user)
    elif suite.environment_id is None and task.environment_id:
        # 套件未绑定环境时，用任务环境补齐，保证执行时能解析 host/变量
        suite.environment = task.environment
        suite.save(update_fields=['environment'])

    adopted = 0
    for order, draft in enumerate(drafts):
        api_request = adopt_draft(draft, user, collection)
        TestSuiteRequest.objects.update_or_create(
            test_suite=suite, request=api_request,
            defaults={'order': order, 'assertions': api_request.assertions, 'enabled': True})
        draft.test_suite = suite
        draft.save(update_fields=['test_suite', 'updated_at'])
        adopted += 1

    return suite, adopted


def start_execution(suite, user):
    """复用既有执行引擎，在后台线程执行套件。返回 TestExecution。"""
    from apps.api_testing.models import TestExecution, TestSuiteRequest

    execution = TestExecution.objects.create(
        test_suite=suite, status='RUNNING', start_time=timezone.now(), executed_by=user)
    execution.total_requests = TestSuiteRequest.objects.filter(
        test_suite=suite, enabled=True).count()
    execution.save(update_fields=['total_requests'])

    from apps.api_testing.views import _run_test_suite_execution
    threading.Thread(
        target=_run_test_suite_execution,
        args=(execution.id, suite.id, user.id),
        daemon=True).start()

    return execution


def run_draft(draft, user, environment=None, persist=True):
    """单条试运行：复用既有执行引擎跑一次。

    persist=True  —— 先落地为 ApiRequest（人工点「试运行」时的行为，便于留痕）
    persist=False —— 只构造临时实例发请求，不写接口管理、不写请求历史（AI 自检用）
    """
    from apps.api_testing.models import ApiRequest
    from apps.api_testing.utils import execute_api_request

    if environment is None:
        environment = getattr(draft.task, 'environment', None)

    if persist:
        api_request = adopt_draft(draft, user)
    else:
        api_request = ApiRequest(
            name=draft.name,
            description=draft.description or draft.expected_result,
            method=draft.method,
            url=draft.url,
            headers=draft.headers or {},
            params=draft.params or {},
            body=draft.body or {},
            auth=draft.auth or {},
            pre_request_script=draft.pre_request_script or '',
            post_request_script=draft.post_request_script or '',
            assertions=draft.assertions or [],
            created_by=user,
        )

    return execute_api_request(api_request, environment, user, save_history=persist)


# ---------------------------------------------------------------------------
# AI 自检：试跑一次 → 对照真实响应校验断言 → 自动纠正
# ---------------------------------------------------------------------------

NEGATIVE_CASE_KEYWORDS = (
    '缺失', '缺少', '非法', '错误', '异常', '越权', '无权限', '不存在',
    '过期', '失效', '为空', '空值', '重复', '超时', '不合法', '无效', '未授权',
)


def _is_negative_case(draft):
    """异常场景的期望状态码本来就是推测值，可按实测修正。"""
    text = f'{draft.name}{draft.description or ""}{draft.expected_result or ""}'
    return any(word in text for word in NEGATIVE_CASE_KEYWORDS)


def _flatten_json_paths(data, prefix='$', depth=0):
    """把响应 JSON 展开成 {jsonpath: 值}，用于按字段名反查真实路径。"""
    flat = {}
    if depth > 6:
        return flat
    if isinstance(data, dict):
        for key, value in data.items():
            path = f'{prefix}.{key}'
            flat[path] = value
            flat.update(_flatten_json_paths(value, path, depth + 1))
    elif isinstance(data, list):
        for idx, item in enumerate(data[:3]):
            path = f'{prefix}[{idx}]'
            flat[path] = item
            flat.update(_flatten_json_paths(item, path, depth + 1))
    return flat


def _self_fix_assertions(draft, run_result, fix_values=False):
    """对照真实响应修正断言。

    只修「写错了」的部分，不掩盖「接口可能有问题」的部分：
      - json_path 路径不存在      → 按字段名反查真实路径；找不到则降级为 contains
      - json_path 路径对但值不同  → 默认降级为存在性断言并提示人工确认；fix_values 时按实测值改
      - 异常场景 status_code 不符 → 按实测状态码修正
      - 正常场景 status_code 不符 → 不自动改，标记待人工确认（避免把接口缺陷改成通过）
    """
    from copy import deepcopy

    assertions = deepcopy(draft.assertions or [])
    results = run_result.get('assertions_results') or []
    response_data = run_result.get('response_data') or {}
    response_json = response_data.get('json')
    response_text = response_data.get('body') or ''
    status_code = run_result.get('status_code')

    flat = _flatten_json_paths(response_json) if response_json is not None else {}
    negative = _is_negative_case(draft)

    new_assertions, fixes, unresolved = [], [], []

    for idx, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            continue

        res = results[idx] if idx < len(results) else {}
        if res.get('passed'):
            new_assertions.append(assertion)
            continue

        atype = assertion.get('type')
        name = assertion.get('name') or atype

        if atype == 'status_code':
            expected = assertion.get('expected')
            if negative and status_code:
                assertion['expected'] = status_code
                new_assertions.append(assertion)
                fixes.append(f'{name}：期望 {expected} → {status_code}（异常场景按实测状态码修正）')
            else:
                new_assertions.append(assertion)
                unresolved.append(
                    f'{name}：期望 {expected}，实际 {status_code}'
                    f'（正常场景未自动修改，请确认是断言写错还是接口缺陷）')
            continue

        if atype == 'json_path':
            path = str(assertion.get('json_path') or '')
            expected = assertion.get('expected')

            if not path:
                new_assertions.append(assertion)
                unresolved.append(f'{name}：断言缺少 json_path')
                continue

            if path in flat:
                actual = flat[path]
                if fix_values:
                    assertion['expected'] = actual
                    new_assertions.append(assertion)
                    fixes.append(f'{name}：期望值 {expected} → {actual}（按真实响应修正）')
                else:
                    assertion['expected'] = None
                    new_assertions.append(assertion)
                    unresolved.append(
                        f'{name}：路径正确但期望 {expected}、实际 {actual}，'
                        f'已降级为存在性断言，请确认该期望值是否合理')
                continue

            leaf = path.split('.')[-1].split('[')[0]
            candidates = [p for p in flat if p.split('.')[-1].split('[')[0] == leaf]
            if len(candidates) == 1:
                actual = flat[candidates[0]]
                assertion['json_path'] = candidates[0]
                if expected is not None and fix_values:
                    assertion['expected'] = actual
                    fixes.append(f'{name}：路径 {path} → {candidates[0]}，期望值同步为 {actual}')
                else:
                    assertion['expected'] = None
                    fixes.append(f'{name}：路径 {path} → {candidates[0]}（按真实响应修正）')
                new_assertions.append(assertion)
                continue

            if leaf and leaf in response_text:
                new_assertions.append({'name': name, 'type': 'contains', 'expected': leaf})
                fixes.append(f'{name}：路径 {path} 不存在，改为 contains("{leaf}")')
                continue

            new_assertions.append(assertion)
            unresolved.append(f'{name}：路径 {path} 在当前响应中不存在，且无法按字段名定位')
            continue

        new_assertions.append(assertion)
        unresolved.append(f'{name}：{res.get("error") or "断言未通过"}')

    return new_assertions, fixes, unresolved


def _mask_headers(headers):
    """脱敏响应头中的敏感字段（Cookie/Set-Cookie/Authorization 等），其余保留。"""
    if not isinstance(headers, dict):
        return {}
    sensitive = ('cookie', 'authorization', 'token', 'set-cookie', 'x-csrf', 'x-xsrf')
    out = {}
    for k, v in headers.items():
        out[k] = '***' if isinstance(k, str) and k.lower() in sensitive else v
    return out


def self_check_draft(draft, user, environment, auto_fix=True, fix_values=False):
    """对单条草稿做「试跑」，返回 (自检结果, 执行结果)。

    只记录断言能否跑通与真实响应，不再自动修改断言去「试图跑通」。
    """
    run_result = run_draft(draft, user, environment, persist=False)
    status_code = run_result.get('status_code')

    checked = {
        'ok': status_code is not None,
        'passed': run_result.get('success') is True,
        'status_code': status_code,
        'response_time': (round(run_result.get('response_time') or 0, 1)
                          if status_code is not None else None),
        'error': '' if status_code is not None else _truncate_text(run_result.get('error'), 500),
        'fixes': [],
        'unresolved': [],
        'verdict': '',
        'checked_at': timezone.now().isoformat(),
    }

    # 真实响应预览：供「AI 审核」与「AI 修订」使用
    raw_resp = run_result.get('json')
    if raw_resp is None:
        raw_resp = run_result.get('body')
    if raw_resp is not None:
        masked = raw_resp if not isinstance(raw_resp, (dict, list)) else _mask_value(raw_resp)
        checked['response_preview'] = _truncate_text(
            masked if isinstance(masked, str) else json.dumps(masked, ensure_ascii=False), 2000)
    else:
        checked['response_preview'] = None

    # 真实响应头：供「AI 审核」评审响应数据合理性使用
    resp_headers = (run_result.get('response_data') or {}).get('headers') or {}
    checked['response_headers'] = _mask_headers(resp_headers)

    if status_code is None:
        checked['verdict'] = 'error'
        checked['unresolved'] = [checked['error'] or '请求未拿到响应']
        return checked, run_result

    if run_result.get('success'):
        checked['verdict'] = 'passed'
    else:
        checked['verdict'] = 'needs_revision'
        checked['unresolved'] = [_truncate_text(run_result.get('error'), 500)]
    return checked, run_result
