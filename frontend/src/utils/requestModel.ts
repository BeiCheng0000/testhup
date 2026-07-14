export interface RequestModel {
  method: string
  baseURL: string
  path: string
  query: QueryParam[]
  headers: Header[]
  body: Body
  auth?: Auth
  timeout?: number
}

export interface QueryParam {
  key: string
  value: string
  enabled: boolean
}

export interface Header {
  key: string
  value: string
  enabled: boolean
}

export interface Body {
  mode: 'none' | 'raw' | 'json' | 'formdata' | 'urlencoded' | 'binary'
  raw?: string
  json?: string
  formdata?: FormField[]
  urlencoded?: FormField[]
  binary?: File
}

export interface FormField {
  key: string
  value: string
  type: 'text' | 'file'
  enabled: boolean
}

export interface Auth {
  type: 'none' | 'basic' | 'bearer' | 'api_key'
  username?: string
  password?: string
  token?: string
  key?: string
  value?: string
  addTo?: 'header' | 'query'
}

// 判断字符串是否为合法 JSON（用于区分 json 报文与加密/普通文本）
function isValidJson(s: string): boolean {
  if (!s.trim()) return false
  try {
    JSON.parse(s)
    return true
  } catch {
    return false
  }
}

// 预处理：去除 Windows cmd 行继续符（^+换行）与 bash 多行续行（\+空白）
function normalizeCurl(cmd: string): string {
  let s = cmd.replace(/\^\s*\n\s*/g, ' ') // Windows cmd: ^ 后接换行 -> 空格
  s = s.replace(/\\\s+/g, ' ')            // bash: \ 后接空白 -> 空格
  return s.trim()
}

// 类 shell 分词器：正确处理单/双引号，以及双引号内的 \" 与 \^X（cmd 转义，X 为任意特殊字符）
function tokenizeCurl(cmd: string): string[] {
  const tokens: string[] = []
  let current = ''
  let quote: '"' | "'" | null = null
  let i = 0
  while (i < cmd.length) {
    const c = cmd[i]
    if (quote === "'") {
      if (c === "'") { quote = null; i++; continue }
      current += c; i++; continue
    }
    if (quote === '"') {
      if (c === '\\' && cmd[i + 1] === '^' && cmd[i + 2] === '"') { current += '"'; i += 3; continue } // \^" -> "
      if (c === '\\' && cmd[i + 1] === '^') { current += cmd[i + 2] ?? ''; i += 3; continue } // \^X -> X
      if (c === '^' && cmd[i + 1] === '\\' && cmd[i + 2] === '^') { current += cmd[i + 3] ?? ''; i += 4; continue } // ^\^X -> X（chat 渲染出的双重转义）
      if (c === '\\' && cmd[i + 1] === '"') { current += '"'; i += 2; continue }               // \"
      if (c === '\\') { current += cmd[i + 1] ?? ''; i += 2; continue }                        // \X
      if (c === '^' && cmd[i + 1] !== '\n') { current += cmd[i + 1] ?? ''; i += 2; continue }  // ^X cmd 转义（含 ^"）
      if (c === '^') { i++; continue }                                                        // 理论已被 normalize 处理
      if (c === '"') { quote = null; i++; continue }
      current += c; i++; continue
    }
    if (c === "'") { quote = "'"; i++; continue }
    if (c === '"') { quote = '"'; i++; continue }
    if (c === '\\') { current += cmd[i + 1] ?? ''; i += 2; continue }
    if (c === '^') { current += cmd[i + 1] ?? ''; i += 2; continue } // cmd 转义（引号外）
    if (/\s/.test(c)) { if (current) { tokens.push(current); current = '' } i++; continue }
    current += c; i++
  }
  if (current) tokens.push(current)
  return tokens
}

// 将 key=value 形式的 urlencoded 字符串解析为数组
function parseUrlencoded(data: string): FormField[] {
  if (!data) return []
  return data.split('&').map((pair) => {
    const idx = pair.indexOf('=')
    const key = idx === -1 ? pair : pair.slice(0, idx)
    const value = idx === -1 ? '' : pair.slice(idx + 1)
    return {
      key: safeDecode(key),
      value: safeDecode(value),
      type: 'text',
      enabled: true
    }
  })
}

function safeDecode(s: string): string {
  try {
    return decodeURIComponent(s)
  } catch {
    return s
  }
}

export class RequestModelParser {
  static async parseCurl(curlCommand: string): Promise<RequestModel> {
    try {
      // 处理多行 curl 的续行符（Windows cmd 的 ^ 与 bash 的 \）
      const normalized = normalizeCurl(curlCommand)
      const tokens = tokenizeCurl(normalized)
      let i = 0
      // 跳过开头的 curl
      if (tokens[i] === 'curl') i++

      let method = ''
      let url = ''
      const headers: Header[] = []
      let bodyText = ''
      let formdata: FormField[] = []
      let contentType = ''
      let basicAuth: { username: string; password: string } | null = null

      for (; i < tokens.length; i++) {
        const t = tokens[i]

        // 长参数 --key=value
        if (t.startsWith('--') && t.includes('=')) {
          const name = t.slice(2, t.indexOf('='))
          const val = t.slice(t.indexOf('=') + 1)
          if (name === 'request') method = val.toUpperCase()
          else if (name === 'header') pushHeader(headers, val, (v) => (contentType = v))
          else           if (name === 'data' || name === 'data-raw' || name === 'data-binary' || name === 'data-urlencode') {
            if (!method) method = 'POST'
            bodyText = val
          } else if (name === 'form') {
            if (!method) method = 'POST'
            pushForm(formdata, val)
            if (!contentType) contentType = 'multipart/form-data'
          } else if (name === 'url') {
            if (!url) url = val
          } else if (name === 'user') {
            const [u, p] = val.split(':')
            basicAuth = { username: u || '', password: p || '' }
          }
          continue
        }

        if (t === '-X' || t === '--request') {
          method = (tokens[++i] || 'GET').toUpperCase()
        } else if (t === '-H' || t === '--header') {
          pushHeader(headers, tokens[++i] || '', (v) => (contentType = v))
        } else if (t === '-d' || t === '--data' || t === '--data-raw' || t === '--data-binary' || t === '--data-urlencode') {
          const data = tokens[++i] || ''
          if (!method) method = 'POST'
          bodyText = data
        } else if (t === '-F' || t === '--form') {
          const data = tokens[++i] || ''
          if (!method) method = 'POST'
          pushForm(formdata, data)
          if (!contentType) contentType = 'multipart/form-data'
        } else if (t === '--url') {
          if (!url) url = tokens[++i] || ''
        } else if (t === '-u' || t === '--user') {
          const val = tokens[++i] || ''
          const [u, p] = val.split(':')
          basicAuth = { username: u || '', password: p || '' }
        } else if (t.startsWith('-X') && t.length > 2) {
          // -XPOST 形式
          method = t.slice(2).toUpperCase()
        } else if (t.startsWith('-') && t.length > 1 && !t.startsWith('--')) {
          // 其它短参数（如 -s -L -k -i -v -I 等），可能附带值则跳过下一个 token
          const attached = t.slice(1)
          // 仅在明显是 -X 风格附带值时处理，其余忽略
          if (/^[A-Za-z]$/.test(attached)) {
            // 单字母短参数，无值
          }
          // 若下一个 token 不是以 - 开头，可能是该参数的值（如 -x proxy），跳过
          if (i + 1 < tokens.length && !tokens[i + 1].startsWith('-') && !/^[A-Za-z]$/.test(attached)) {
            i++
          }
        } else if (!t.startsWith('-')) {
          // 位置参数：URL
          if (!url) url = t
        }
      }

      // 处理 basic auth
      if (basicAuth) {
        const encoded = btoa(`${basicAuth.username}:${basicAuth.password}`)
        headers.push({ key: 'Authorization', value: `Basic ${encoded}`, enabled: true })
      }

      // 拆分 URL 为 baseURL / path / query
      let baseURL = ''
      let path = ''
      const query: QueryParam[] = []
      if (url) {
        let parsed: URL
        try {
          parsed = new URL(url)
          baseURL = `${parsed.protocol}//${parsed.host}`
          path = parsed.pathname
          parsed.searchParams.forEach((value, key) => {
            query.push({ key, value, enabled: true })
          })
        } catch {
          // 相对路径（如 /api/login?a=1）
          baseURL = ''
          path = url
        }
      }

      // body 模式在解析完成后统一判定，避免 -d 早于 -H(content-type) 时误判
      const body: Body = { mode: 'none' }
      if (formdata.length > 0) {
        body.mode = 'formdata'
        body.formdata = formdata
      } else if (bodyText) {
        if (contentType.includes('application/json') && isValidJson(bodyText)) {
          body.mode = 'json'
          body.json = bodyText
        } else if (contentType.includes('application/x-www-form-urlencoded')) {
          body.mode = 'urlencoded'
          body.urlencoded = parseUrlencoded(bodyText)
        } else {
          // content-type 为 application/json 但 body 不是合法 JSON（如加密报文），
          // 或没有可识别的 content-type，均按 raw 文本发送，避免被 JSON.stringify 加引号
          body.mode = 'raw'
          body.raw = bodyText
        }
      }

      return {
        method: method || 'GET',
        baseURL,
        path,
        query,
        headers,
        body,
        auth: RequestModelParser.parseAuth(headers),
        timeout: 30000
      }
    } catch (error: any) {
      console.error('Failed to parse cURL command:', error)
      console.error('cURL command:', curlCommand)
      const errorMessage = error?.message || error?.toString() || 'Unknown error'
      throw new Error(`cURL命令解析失败: ${errorMessage}，请检查命令格式`)
    }
  }

  static parseAuth(headers: Header[]): Auth | undefined {
    const authHeader = headers.find(h => h.key.toLowerCase() === 'authorization')
    if (authHeader) {
      const value = authHeader.value

      if (value.startsWith('Bearer ')) {
        return {
          type: 'bearer',
          token: value.substring(7)
        }
      }

      if (value.startsWith('Basic ')) {
        try {
          const decoded = atob(value.substring(6))
          const [username, password] = decoded.split(':')
          return {
            type: 'basic',
            username,
            password
          }
        } catch {
          return undefined
        }
      }
    }

    return undefined
  }

  static toCurl(model: RequestModel): string {
    let curl = `curl -X ${model.method}`

    let fullUrl: string
    try {
      fullUrl = new URL((model.baseURL || '') + (model.path || '')).toString()
    } catch {
      // 相对路径（如 /api/auth/login）无法构造绝对 URL，直接使用拼接结果
      fullUrl = (model.baseURL || '') + (model.path || '')
    }

    const queryParts: string[] = []
    model.query.forEach((param) => {
      if (param.enabled && param.key) {
        queryParts.push(`${encodeURIComponent(param.key)}=${encodeURIComponent(param.value)}`)
      }
    })
    if (queryParts.length > 0) {
      fullUrl += (fullUrl.includes('?') ? '&' : '?') + queryParts.join('&')
    }

    curl += ` '${fullUrl}'`

    model.headers.forEach((header) => {
      if (header.enabled && header.key) {
        curl += ` -H '${header.key}: ${header.value}'`
      }
    })

    if (model.body.mode === 'raw' && model.body.raw) {
      curl += ` -d '${model.body.raw}'`
    } else if (model.body.mode === 'json' && model.body.json != null) {
      const jsonStr = typeof model.body.json === 'string'
        ? model.body.json
        : JSON.stringify(model.body.json, null, 2)
      curl += ` -d '${jsonStr}'`
    } else if (model.body.mode === 'urlencoded' && model.body.urlencoded) {
      const ud = model.body.urlencoded
        .filter((f) => f.enabled && f.key)
        .map((f) => `${encodeURIComponent(f.key)}=${encodeURIComponent(f.value)}`)
        .join('&')
      if (ud) curl += ` -d '${ud}'`
    } else if (model.body.mode === 'formdata' && model.body.formdata) {
      model.body.formdata
        .filter((f) => f.enabled && f.key)
        .forEach((f) => {
          curl += ` -F '${f.key}=${f.type === 'file' ? '@' : ''}${f.value}'`
        })
    }

    if (model.timeout) {
      curl += ` --max-time ${model.timeout / 1000}`
    }

    return curl
  }

  static toFormData(model: RequestModel): FormData {
    const formData = new FormData()

    if (model.body.mode === 'formdata' && model.body.formdata) {
      model.body.formdata.forEach((field) => {
        if (field.enabled && field.key) {
          if (field.type === 'file' && field.value) {
            formData.append(field.key, field.value as any)
          } else {
            formData.append(field.key, field.value)
          }
        }
      })
    }

    return formData
  }

  static toURLSearchParams(model: RequestModel): URLSearchParams {
    const params = new URLSearchParams()

    if (model.body.mode === 'urlencoded' && model.body.urlencoded) {
      model.body.urlencoded.forEach((field) => {
        if (field.enabled && field.key) {
          params.append(field.key, field.value)
        }
      })
    }

    return params
  }
}

// 解析单个 header 字符串 "Key: Value"
function pushHeader(headers: Header[], raw: string, onContentType?: (v: string) => void) {
  const idx = raw.indexOf(':')
  if (idx === -1) return
  const key = raw.slice(0, idx).trim()
  const value = raw.slice(idx + 1).trim()
  if (!key) return
  headers.push({ key, value, enabled: true })
  if (key.toLowerCase() === 'content-type') onContentType?.(value)
}

// 解析 -F 表单字段 "key=value" 或 "key=@/path"
function pushForm(formdata: FormField[], raw: string) {
  const idx = raw.indexOf('=')
  if (idx === -1) return
  const key = raw.slice(0, idx).trim()
  let value = raw.slice(idx + 1)
  const isFile = value.startsWith('@')
  if (isFile) value = value.slice(1)
  formdata.push({ key, value, type: isFile ? 'file' : 'text', enabled: true })
}
