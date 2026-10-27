<template>
  <div class="api-testing-layout">
    <!-- 顶部导航 -->
    <div class="top-nav">
      <h2>{{ $t('apiTesting.nav.title') }}</h2>
      <el-menu
        :default-active="currentRoute"
        mode="horizontal"
        @select="handleMenuSelect"
        class="nav-menu"
      >
        <el-menu-item index="projects">
          <el-icon><Folder /></el-icon>
          <span>{{ $t('apiTesting.nav.projects') }}</span>
        </el-menu-item>
        <el-menu-item index="interfaces">
          <el-icon><Link /></el-icon>
          <span>{{ $t('apiTesting.nav.interfaces') }}</span>
        </el-menu-item>
        <el-menu-item index="automation">
          <el-icon><VideoPlay /></el-icon>
          <span>{{ $t('apiTesting.nav.automation') }}</span>
        </el-menu-item>
        <el-menu-item index="history">
          <el-icon><Timer /></el-icon>
          <span>{{ $t('apiTesting.nav.history') }}</span>
        </el-menu-item>
        <el-menu-item index="environments">
          <el-icon><Location /></el-icon>
          <span>{{ $t('apiTesting.nav.environments') }}</span>
        </el-menu-item>
        <el-menu-item index="scheduled-tasks">
          <el-icon><AlarmClock /></el-icon>
          <span>{{ $t('apiTesting.nav.scheduledTasks') }}</span>
        </el-menu-item>
        <el-menu-item index="reports">
          <el-icon><DataAnalysis /></el-icon>
          <span>{{ $t('apiTesting.nav.reports') }}</span>
        </el-menu-item>
        <el-menu-item index="notification-logs">
          <el-icon><Bell /></el-icon>
          <span>{{ $t('apiTesting.nav.notificationLogs') }}</span>
        </el-menu-item>
        <el-menu-item index="notification-configs">
          <el-icon><Setting /></el-icon>
          <span>{{ $t('apiTesting.nav.notificationConfigs') }}</span>
        </el-menu-item>
      </el-menu>
    </div>

    <!-- 内容区域 -->
    <div class="content">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Folder, Link, VideoPlay, Timer, Location, AlarmClock, DataAnalysis, Bell, Setting } from '@element-plus/icons-vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const currentRoute = computed(() => {
  const path = route.path
  if (path.includes('/projects')) return 'projects'
  if (path.includes('/interfaces')) return 'interfaces' 
  if (path.includes('/automation')) return 'automation'
  if (path.includes('/history')) return 'history'
  if (path.includes('/environments')) return 'environments'
  if (path.includes('/scheduled-tasks')) return 'scheduled-tasks'
  if (path.includes('/reports')) return 'reports'
  if (path.includes('/notification-logs')) return 'notification-logs'
  if (path.includes('/notification-configs')) return 'notification-configs'
  return 'projects'
})

const handleMenuSelect = (index) => {
  router.push(`/api-testing/${index}`)
}
</script>

<style scoped>
.api-testing-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.top-nav {
  border-bottom: 1px solid #e4e7ed;
  background: white;
  padding: 0 20px;
  display: flex;
  align-items: center;
  gap: 30px;
}

.top-nav h2 {
  margin: 0;
  color: #303133;
  white-space: nowrap;
}

.nav-menu {
  flex: 1;
  border: none;
}

.content {
  flex: 1;
  overflow: hidden;
}
</style>