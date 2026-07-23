<template>
  <el-config-provider :locale="elementLocale">
    <div id="app">
      <router-view />
    </div>
  </el-config-provider>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { ElConfigProvider } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'

const userStore = useUserStore()
const appStore = useAppStore()

const elementLocale = computed(() => {
  return appStore.language === 'zh-cn' ? zhCn : en
})

// 预取高频/重型路由分块：慢速隧道下，懒加载分块需先下载+解析才会执行组件并发起后端请求，
// 导致点击菜单后"几秒没反应"。在应用启动（隧道已热）后空闲时预取，点击即可秒开并立即请求。
// 必须用字面量动态导入（Vite 才能静态分析并复用与路由相同的分块文件）。
const prefetchChunks = [
  () => import('@/views/api-testing/InterfaceManagement.vue'),
  () => import('@/views/api-testing/AutomationTesting.vue'),
  () => import('@/views/api-testing/ReportView.vue'),
  () => import('@/views/api-testing/RequestHistory.vue')
]

const prefetchHeavyChunks = () => {
  const run = () => {
    prefetchChunks.forEach((load) => {
      load().catch(() => {})
    })
  }
  if (typeof window.requestIdleCallback === 'function') {
    window.requestIdleCallback(run, { timeout: 3000 })
  } else {
    setTimeout(run, 1500)
  }
}

onMounted(() => {
  userStore.initAuth()
  prefetchHeavyChunks()
})
</script>

<style>
#app {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  height: 100vh;
  width: 100vw;
}
</style>
