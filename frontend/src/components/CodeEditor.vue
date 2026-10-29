<template>
  <div class="code-editor" :class="{ 'code-editor--readonly': readonly }">
    <textarea
      ref="textareaRef"
      class="code-editor__input"
      :value="modelValue"
      :placeholder="placeholder"
      :readonly="readonly"
      :spellcheck="false"
      @input="onInput"
      @scroll="syncScroll"
    ></textarea>
    <pre
      ref="preRef"
      class="code-editor__highlight"
      aria-hidden="true"
    ><code v-html="highlighted"></code></pre>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  modelValue: string
  language?: 'text' | 'json' | 'html' | 'xml' | 'javascript'
  placeholder?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const preRef = ref<HTMLPreElement | null>(null)

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

function syncScroll() {
  const ta = textareaRef.value
  const pre = preRef.value
  if (ta && pre) {
    pre.scrollTop = ta.scrollTop
    pre.scrollLeft = ta.scrollLeft
  }
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function highlightJson(s: string): string {
  // 铁律：高亮只能「给原文套一层标签」，绝不能增删任何字符。
  // 之前的实现会把 :true 改成 `: true`（多插一个空格）、把 `"k" :` 的冒号重复输出，
  // 高亮层与输入层字符数一旦不等，光标就和文字错位，且越往后偏得越明显。
  return escapeHtml(s).replace(
    /("(?:[^"\\]|\\.)*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    (m, str: string | undefined, colon: string | undefined) => {
      if (str) {
        return colon
          ? `<span style="color: #268bd2;">${str}</span>${colon}`
          : `<span style="color: #2aa198;">${str}</span>`
      }
      // 布尔/null 与数字：原样包一层，字符数保持不变
      const isBool = m === 'true' || m === 'false' || m === 'null'
      return `<span style="color: ${isBool ? '#cb4b16' : '#d33682'};">${m}</span>`
    }
  )
}

const highlighted = computed(() => {
  const v = props.modelValue ?? ''
  if (!v) return ''
  if (props.language === 'json') {
    try {
      return highlightJson(v)
    } catch {
      return escapeHtml(v)
    }
  }
  // 非 JSON：仅做 HTML 转义，避免直接使用用户输入破坏页面
  return escapeHtml(v)
})
</script>

<style scoped>
.code-editor {
  position: relative;
  width: 100%;
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 4px;
  background: #fbfbfd;
  overflow: hidden;
}

.code-editor__input,
.code-editor__highlight {
  margin: 0;
  border: 0;
  padding: 10px 12px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  font-size: 13px;
  line-height: 1.6;
  tab-size: 2;
  white-space: pre;
  word-wrap: normal;
  overflow: auto;
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  /* 连字、字距、字距调整都会改变字符实际宽度；
     输入层与高亮层必须逐字符等宽，否则光标和文字会错位且越往后越偏 */
  letter-spacing: 0;
  font-variant-ligatures: none;
  font-feature-settings: normal;
  font-kerning: none;
}

/* <code> 带浏览器默认样式 font-family: monospace，会覆盖继承自 <pre> 的字体栈，
   结果是高亮层字体和输入层不一致、字符宽度不同（中文尤其明显），
   光标位置与文字显示位置因此错开，且随输入长度累积 */
.code-editor__highlight code {
  display: block;
  margin: 0;
  padding: 0;
  font-family: inherit;
  font-size: inherit;
  font-weight: inherit;
  line-height: inherit;
  letter-spacing: inherit;
  tab-size: inherit;
  white-space: inherit;
}

.code-editor__input {
  position: absolute;
  inset: 0;
  resize: none;
  background: transparent;
  color: transparent;
  caret-color: #303133;
  outline: none;
  z-index: 2;
}

.code-editor__input::selection {
  background: rgba(38, 139, 210, 0.25);
}

.code-editor__highlight {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  color: #333;
}

.code-editor--readonly .code-editor__input {
  color: #333;
  caret-color: transparent;
}
</style>
