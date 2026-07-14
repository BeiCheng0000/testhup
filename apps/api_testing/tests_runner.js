'use strict';
// Tests 脚本（请求后脚本）服务端执行器
// 镜像前端 InterfaceManagement.vue 中 runPostRequestScript 提供的 pm / console API，
// 通过 node 子进程被 Django 后端调用，使自动化测试与定时任务也能执行 Tests 脚本。
// 从标准输入读取 JSON，向标准输出写入 JSON 结果。

// ---------------- JSONPath 求值器（与前端一致） ----------------
function tokenizeJsonPath(path) {
  const tokens = [];
  let i = 0;
  if (path[i] === '$') { i++; tokens.push({ t: 'root' }); }
  while (i < path.length) {
    const c = path[i];
    if (c === '.') {
      if (path[i + 1] === '.') { tokens.push({ t: 'descend' }); i += 2; continue; }
      const m = /^\.([a-zA-Z_$][\w$]*)/.exec(path.slice(i));
      if (m) { tokens.push({ t: 'child', key: m[1] }); i += m[0].length; continue; }
      i++;
      continue;
    }
    if (c === '[') {
      const end = path.indexOf(']', i);
      if (end === -1) break;
      const inner = path.slice(i + 1, end);
      if (inner === '*') {
        tokens.push({ t: 'wildcard' });
      } else if (/^-?\d+$/.test(inner.trim())) {
        tokens.push({ t: 'index', idx: parseInt(inner, 10) });
      } else if (inner.indexOf(':') !== -1) {
        const parts = inner.split(':');
        const step = parts.length > 2 && parts[2] !== '' ? parseInt(parts[2], 10) : 1;
        tokens.push({
          t: 'slice',
          start: parts[0] === '' ? null : parseInt(parts[0], 10),
          end: parts[1] === undefined || parts[1] === '' ? null : parseInt(parts[1], 10),
          step: step || 1
        });
      } else if (inner.startsWith('?')) {
        const expr = inner.slice(1).replace(/^\(|\)$/g, '').trim();
        tokens.push({ t: 'filter', expr });
      } else {
        tokens.push({ t: 'child', key: inner });
      }
      i = end + 1;
      continue;
    }
    // 裸标识符（紧跟在 $ 或 .. 之后的 key）
    const bm = /^([a-zA-Z_$][\w$]*)/.exec(path.slice(i));
    if (bm) { tokens.push({ t: 'child', key: bm[1] }); i += bm[0].length; continue; }
    i++;
  }
  return tokens;
}

function collectDescendants(x, out) {
  if (x && typeof x === 'object') {
    const vals = Array.isArray(x) ? x : Object.values(x);
    for (const v of vals) { out.push(v); collectDescendants(v, out); }
  }
}

function evalJsonPathFilter(item, expr) {
  try {
    const fn = new Function('_it', 'return (' + expr.replace(/@/g, '_it') + ')');
    return !!fn(item);
  } catch (e) { return false; }
}

function jsonPathQuery(data, path) {
  if (data == null || !path || typeof path !== 'string') return [];
  const tokens = tokenizeJsonPath(path);
  let nodes = [data];
  for (const tok of tokens) {
    const next = [];
    switch (tok.t) {
      case 'root':
        next.push(...nodes);
        break;
      case 'child':
        for (const node of nodes) {
          if (node != null && typeof node === 'object' && tok.key in node) next.push(node[tok.key]);
        }
        break;
      case 'wildcard':
        for (const node of nodes) {
          if (node != null && typeof node === 'object') {
            next.push(...(Array.isArray(node) ? node : Object.values(node)));
          }
        }
        break;
      case 'index':
        for (const node of nodes) {
          if (Array.isArray(node)) {
            const idx = tok.idx < 0 ? node.length + tok.idx : tok.idx;
            if (idx >= 0 && idx < node.length) next.push(node[idx]);
          }
        }
        break;
      case 'slice': {
        for (const node of nodes) {
          if (Array.isArray(node)) {
            const len = node.length;
            const s = tok.start == null ? 0 : (tok.start < 0 ? len + tok.start : tok.start);
            const e = tok.end == null ? len : (tok.end < 0 ? len + tok.end : tok.end);
            for (let k = s; k < e; k += tok.step) next.push(node[k]);
          }
        }
        break;
      }
      case 'filter':
        for (const node of nodes) {
          const arr = node && typeof node === 'object'
            ? (Array.isArray(node) ? node : Object.values(node))
            : [];
          for (const item of arr) if (evalJsonPathFilter(item, tok.expr)) next.push(item);
        }
        break;
      case 'descend':
        for (const node of nodes) collectDescendants(node, next);
        break;
    }
    nodes = next;
  }
  return nodes;
}

// ---------------- 主流程 ----------------
function main() {
  let raw = '';
  try {
    raw = require('fs').readFileSync(0, 'utf8');
  } catch (e) {
    process.stdout.write(JSON.stringify({ testResults: [], scriptLogs: [], savedEnvVariables: [], updatedEnvironments: [], error: '无法读取脚本输入: ' + e.message }));
    return;
  }

  let input;
  try {
    input = JSON.parse(raw);
  } catch (e) {
    process.stdout.write(JSON.stringify({ testResults: [], scriptLogs: [], savedEnvVariables: [], updatedEnvironments: [], error: '脚本输入解析失败: ' + e.message }));
    return;
  }

  const script = input.script || '';
  const responseInfo = input.response || {};
  const environments = Array.isArray(input.environments) ? input.environments : [];

  const testResults = [];
  const scriptLogs = [];
  const savedEnvVariables = [];
  const dirty = new Set();

  // 构建环境读写代理
  function buildEnvApi(env) {
    if (!env) return null;
    const vars = env.variables && typeof env.variables === 'object' ? env.variables : {};
    const readValue = (name) => {
      const v = vars[name];
      if (v && typeof v === 'object') return v.currentValue != null ? v.currentValue : (v.initialValue != null ? v.initialValue : '');
      return v != null ? v : '';
    };
    return {
      _id: env.id,
      get name() { return env.name; },
      get variables() {
        const obj = {};
        for (const k of Object.keys(vars)) obj[k] = readValue(k);
        return obj;
      },
      get: readValue,
      set: (name, value) => {
        const v = String(value);
        vars[name] = { initialValue: v, currentValue: v };
        savedEnvVariables.push({ env: env.name, name, value: v });
        dirty.add(env.id);
      },
      has: (name) => Object.prototype.hasOwnProperty.call(vars, name),
      unset: (name) => {
        if (Object.prototype.hasOwnProperty.call(vars, name)) {
          delete vars[name];
          dirty.add(env.id);
        }
      },
      toObject: () => {
        const obj = {};
        for (const k of Object.keys(vars)) obj[k] = readValue(k);
        return obj;
      }
    };
  }

  // 当前环境（current:true）与全局环境（scope:GLOBAL）
  let currentEnv = null;
  let globalEnv = null;
  for (const env of environments) {
    if (env.current) currentEnv = buildEnvApi(env);
    if (env.scope === 'GLOBAL') globalEnv = buildEnvApi(env);
  }

  const fallbackEnv = {
    get name() { return ''; },
    get variables() { return {}; },
    get: () => '',
    set: (name, value) => {
      scriptLogs.push('[warn] 未选择环境，pm.environment.set 未生效: ' + name);
    },
    has: () => false,
    unset: () => {},
    toObject: () => ({})
  };

  const respData = responseInfo.response_data || {};
  const pm = {
    response: {
      code: responseInfo.status_code,
      status: responseInfo.status_text || '',
      responseTime: responseInfo.response_time,
      headers: respData.headers || {},
      text() {
        return typeof respData.body === 'string'
          ? respData.body
          : (respData.body != null ? JSON.stringify(respData.body) : '');
      },
      json() {
        if (respData.json != null) return respData.json;
        try { return JSON.parse(respData.body || 'null'); } catch (e) { return null; }
      },
      jsonPath(expression) {
        return jsonPathQuery(this.json(), expression);
      }
    },
    environment: currentEnv || fallbackEnv,
    globals: globalEnv || currentEnv || fallbackEnv,
    test(name, fn) {
      try {
        if (fn) fn();
        testResults.push({ name, passed: true, error: '' });
      } catch (e) {
        testResults.push({ name, passed: false, error: e && e.message ? e.message : String(e) });
      }
    },
    expect(actual) {
      return {
        toEqual(expected) { if (actual !== expected) throw new Error('期望 ' + JSON.stringify(expected) + '，实际 ' + JSON.stringify(actual)); },
        toBe(expected) { if (actual !== expected) throw new Error('期望 ' + JSON.stringify(expected) + '，实际 ' + JSON.stringify(actual)); },
        toContain(sub) { if (!String(actual).includes(String(sub))) throw new Error('期望包含 ' + sub); }
      };
    },
    jsonPath(obj, expression) {
      return jsonPathQuery(obj, expression);
    }
  };

  const scriptConsole = {
    log: (...args) => scriptLogs.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')),
    warn: (...args) => scriptLogs.push('[warn] ' + args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')),
    error: (...args) => scriptLogs.push('[error] ' + args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '))
  };

  let error = null;
  try {
    const fn = new Function('pm', 'console', script);
    fn(pm, scriptConsole);
  } catch (e) {
    error = e && e.message ? e.message : String(e);
  }

  // 收集被修改过的环境变量，回写给后端
  const updatedEnvironments = [];
  for (const env of environments) {
    if (dirty.has(env.id)) {
      updatedEnvironments.push({ id: env.id, variables: env.variables });
    }
  }

  process.stdout.write(JSON.stringify({
    testResults,
    scriptLogs,
    savedEnvVariables,
    updatedEnvironments,
    error
  }));
}

main();
