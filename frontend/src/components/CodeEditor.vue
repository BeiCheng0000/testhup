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
  language?: 'text' | 'json' | 'html' | 'xml'
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
  return escapeHtml(s)
    .replace(/"([^"\\]*(\\.[^"\\]*)*)"(\s*:)?/g, (m, _g1, _g2, colon) => {
      if (colon) {
        // key：去掉首尾引号后只包一层
        return `<span style="color: #268bd2;">"${m.replace(/^"|":?\s*$/g, '')}"</span>${colon}`
      }
      // string value：m 已含引号，直接使用
      return `<span style="color: #2aa198;">${m}</span>`
    })
    .replace(/:\s*(true|false|null)(?=[,\s}])/g, ': <span style="color: #cb4b16;">$1</span>')
    .replace(/:\s*(-?\d+(\.\d+)?([eE][+-]?\d+)?)(?=[,\s}])/g, ': <span style="color: #d33682;">$1</span>')
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
