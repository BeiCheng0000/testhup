<template>
  <div class="notification-logs-container">
    <!-- 页面操作栏 -->
    <div class="page-actions">
      <el-row :gutter="20" class="filter-row">
        <el-col :span="6">
          <el-input
              v-model="searchForm.taskName"
              :placeholder="$t('notification.logs.searchTaskName')"
              clearable
              @clear="handleSearch"
              @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon>
                <Search/>
              </el-icon>
            </template>
          </el-input>
        </el-col>
        <el-col :span="6">
          <el-date-picker
              v-model="searchForm.dateRange"
              type="daterange"
              :range-separator="$t('notification.logs.rangeSeparator')"
              :start-placeholder="$t('notification.logs.startDate')"
              :end-placeholder="$t('notification.logs.endDate')"
              value-format="YYYY-MM-DD"
              @change="handleSearch"
          />
        </el-col>
        <el-col :span="6">
          <el-select
              v-model="searchForm.status"
              :placeholder="$t('notification.logs.notificationStatus')"
              clearable
              @change="handleSearch"
          >
            <el-option :label="$t('notification.logs.statusOptions.all')" value=""/>
            <el-option :label="$t('notification.logs.statusOptions.success')" value="SUCCESS"/>
            <el-option :label="$t('notification.logs.statusOptions.failed')" value="FAILED"/>
            <el-option :label="$t('notification.logs.statusOptions.retrying')" value="RETRYING"/>
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-button type="primary" @click="handleSearch">
            <el-icon>
              <Search/>
            </el-icon>
            {{ $t('notification.logs.search') }}
          </el-button>
          <el-button @click="handleReset">
            {{ $t('notification.logs.reset') }}
          </el-button>
        </el-col>
      </el-row>
    </div>

    <!-- 通知列表 -->
    <div class="logs-table-container">
      <el-table
          :data="logsData"
          v-loading="loading"
          :element-loading-text="$t('notification.logs.loading')"
          stripe
          style="width: 100%"
          @sort-change="handleSortChange"
      >
        <el-table-column
            prop="task_name"
            :label="$t('notification.logs.columns.taskName')"
            min-width="150"
            sortable="custom"
        />
        <el-table-column
            prop="task_type_display"
            :label="$t('notification.logs.columns.taskType')"
            min-width="100"
        >
          <template #default="{ row }">
            <el-tag
                type="info"
                size="small"
            >
              {{ row.task_type_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
            prop="notification_type_display"
            :label="$t('notification.logs.columns.notificationType')"
            min-width="120"
        >
          <template #default="{ row }">
            <el-tag
                :type="getNotificationTypeTagType(row.notification_type_display)"
                size="small"
            >
              {{ row.notification_type_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
            prop="notification_target_display"
            :label="$t('notification.logs.columns.notificationTarget')"
            min-width="150"
        >
          <template #default="{ row }">
            <span>{{ row.notification_target_display || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column
            prop="created_at"
            :label="$t('notification.logs.columns.notificationTime')"
            min-width="180"
            sortable="custom"
        >
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column
            prop="status_display"
            :label="$t('notification.logs.columns.status')"
            min-width="100"
            sortable="custom"
        >
          <template #default="{ row }">
            <el-tag
                :type="getStatusTagType(row.status_display)"
                size="small"
            >
              {{ row.status_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
            :label="$t('notification.logs.columns.operation')"
            fixed="right"
            width="120"
        >
          <template #default="{ row }">
            <el-button
                type="primary"
                link
                size="small"
                @click="viewDetail(row)"
            >
              {{ $t('notification.logs.viewDetail') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
            v-model:current-page="pagination.currentPage"
            v-model:page-size="pagination.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="pagination.total"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="handleSizeChange"
            @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog
        v-model="detailDialogVisible"
        :title="$t('notification.logs.detailDialog.title')"
        width="660px"
        top="6vh"
        :before-close="handleDetailDialogClose"
        :close-on-click-modal="false"
        :close-on-press-escape="false"
        :modal="true"
        :destroy-on-close="true"
    >
      <div v-if="selectedLog" class="ntf-detail">
        <!-- 状态头卡 -->
        <div class="ntf-status-card" :class="statusClass(selectedLog)">
          <div class="ntf-status-icon">
            <el-icon :size="26"><component :is="statusIcon(selectedLog)"/></el-icon>
          </div>
          <div class="ntf-status-main">
            <div class="ntf-status-badges">
              <el-tag :type="getStatusTagType(selectedLog.status_display)" effect="dark" size="small">
                {{ selectedLog.status_display }}
              </el-tag>
              <el-tag :type="getNotificationTypeTagType(selectedLog.notification_type_display)" size="small">
                {{ selectedLog.notification_type_display }}
              </el-tag>
            </div>
            <div class="ntf-status-sub">{{ selectedLog.task_name }} · {{ selectedLog.task_type_display }}</div>
          </div>
          <div class="ntf-status-time">
            <div class="ntf-time-label">{{ $t('notification.logs.detailDialog.notificationTime') }}</div>
            <div class="ntf-time-value">{{ formatDate(selectedLog.created_at) }}</div>
          </div>
        </div>

        <!-- 基本信息 -->
        <div class="ntf-section">
          <div class="ntf-section-title">{{ $t('notification.logs.detailDialog.basicInfo') }}</div>
          <div class="ntf-grid">
            <div class="ntf-cell">
              <span class="ntf-cell-label">{{ $t('notification.logs.detailDialog.taskName') }}</span>
              <span class="ntf-cell-value">{{ selectedLog.task_name }}</span>
            </div>
            <div class="ntf-cell">
              <span class="ntf-cell-label">{{ $t('notification.logs.detailDialog.taskType') }}</span>
              <span class="ntf-cell-value">{{ selectedLog.task_type_display }}</span>
            </div>
            <div class="ntf-cell">
              <span class="ntf-cell-label">{{ $t('notification.logs.detailDialog.status') }}</span>
              <span class="ntf-cell-value">
                <el-tag :type="getStatusTagType(selectedLog.status_display)" size="small">{{ selectedLog.status_display }}</el-tag>
              </span>
            </div>
            <div class="ntf-cell">
              <span class="ntf-cell-label">{{ $t('notification.logs.detailDialog.sentTime') }}</span>
              <span class="ntf-cell-value">{{ selectedLog.sent_at ? formatDate(selectedLog.sent_at) : '-' }}</span>
            </div>
            <div class="ntf-cell">
              <span class="ntf-cell-label">{{ $t('notification.logs.detailDialog.retryCount') }}</span>
              <span class="ntf-cell-value">{{ selectedLog.retry_count != null ? selectedLog.retry_count : '-' }}</span>
            </div>
          </div>
        </div>

        <!-- 通知对象 -->
        <div class="ntf-section" v-if="selectedLog.notification_target_display && selectedLog.notification_target_display.length">
          <div class="ntf-section-title">{{ $t('notification.logs.detailDialog.notificationTarget') }}</div>
          <div class="notification-targets">
            <el-tag
                v-for="(target, index) in selectedLog.notification_target_display"
                :key="index"
                class="target-tag"
                size="small"
                :type="getTargetTagType(target.type)"
            >
              {{ target.display }}（{{ target.name }}）
            </el-tag>
          </div>
        </div>

        <!-- 消息内容 -->
        <div class="ntf-section">
          <div class="ntf-section-title ntf-section-title--row">
            <span>{{ $t('notification.logs.detailDialog.notificationContent') }}</span>
            <el-button text size="small" type="primary" @click="showRaw = !showRaw">
              {{ showRaw ? $t('notification.logs.detailDialog.notificationContent') : $t('notification.logs.detailDialog.viewRaw') }}
            </el-button>
          </div>

          <div v-if="showRaw" class="ntf-raw">
            <pre>{{ selectedLog.notification_content || '-' }}</pre>
          </div>
          <div v-else class="ntf-msg-card">
            <template v-if="messageLines.length">
              <div
                  v-for="(line, i) in messageLines"
                  :key="i"
                  :class="line.type === 'kv' ? 'ntf-msg-kv' : 'ntf-msg-p'"
              >
                <template v-if="line.type === 'kv'">
                  <span class="ntf-msg-k" v-html="renderInline(line.key)"></span>
                  <span class="ntf-msg-v" v-html="renderInline(line.value)"></span>
                </template>
                <span v-else v-html="renderInline(line.text)"></span>
              </div>
            </template>
            <div v-else class="ntf-msg-empty">{{ selectedLog.notification_content || '-' }}</div>
          </div>
        </div>

        <!-- 错误信息 -->
        <div class="ntf-section ntf-error-section" v-if="selectedLog.error_message">
          <div class="ntf-section-title ntf-error-title">
            <el-icon><WarningFilled/></el-icon>
            {{ $t('notification.logs.detailDialog.errorMessage') }}
          </div>
          <div class="ntf-error">{{ selectedLog.error_message }}</div>
        </div>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="detailDialogVisible = false">{{ $t('notification.logs.detailDialog.close') }}</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import {
  Search, CircleCheckFilled, CircleCloseFilled, WarningFilled, InfoFilled
} from '@element-plus/icons-vue'
import {ref, reactive, onMounted, computed} from 'vue'
import {useI18n} from 'vue-i18n'
import {ElMessage} from 'element-plus'
import axios from 'axios'

export default {
  name: 'NotificationLogs',
  components: {
    Search,
    CircleCheckFilled,
    CircleCloseFilled,
    WarningFilled,
    InfoFilled
  },
  setup() {
    const {t, locale} = useI18n()

    // 数据状态
    const loading = ref(false)
    const logsData = ref([])
    const detailDialogVisible = ref(false)
    const selectedLog = ref(null)
    const showRaw = ref(false)

    // 搜索表单
    const searchForm = reactive({
      taskName: '',
      dateRange: [],
      status: ''
    })

    // 分页配置
    const pagination = reactive({
      currentPage: 1,
      pageSize: 10,
      total: 0
    })

    // 排序参数
    const sortParams = reactive({
      prop: 'created_at',
      order: 'descending'
    })

    // 获取通知日志数据
    const fetchLogsData = async () => {
      loading.value = true
      try {
        const params = {
          page: pagination.currentPage,
          page_size: pagination.pageSize,
          ordering: sortParams.order === 'ascending' ? sortParams.prop : `-${sortParams.prop}`
        }

        // 添加搜索条件
        if (searchForm.taskName) {
          params.search = searchForm.taskName
        }
        if (searchForm.dateRange && searchForm.dateRange.length === 2) {
          params.start_date = searchForm.dateRange[0]
          params.end_date = searchForm.dateRange[1]
        }
        if (searchForm.status) {
          params.status = searchForm.status
        }

        const response = await axios.get('/api/api-testing/notification-logs/', {params})
        logsData.value = response.data.results || []
        pagination.total = response.data.count || 0
      } catch (error) {
        console.error('Fetch notification logs failed:', error)
        ElMessage.error(t('notification.logs.messages.fetchFailed'))
      } finally {
        loading.value = false
      }
    }

    // 处理搜索
    const handleSearch = () => {
      pagination.currentPage = 1
      fetchLogsData()
    }

    // 重置搜索
    const handleReset = () => {
      searchForm.taskName = ''
      searchForm.dateRange = []
      searchForm.status = ''
      pagination.currentPage = 1
      fetchLogsData()
    }

    // 处理分页变化
    const handleSizeChange = (val) => {
      pagination.pageSize = val
      pagination.currentPage = 1
      fetchLogsData()
    }

    const handleCurrentChange = (val) => {
      pagination.currentPage = val
      fetchLogsData()
    }

    // 处理排序
    const handleSortChange = ({prop, order}) => {
      sortParams.prop = prop
      sortParams.order = order || 'descending'
      fetchLogsData()
    }

    // 查看详情
    const viewDetail = async (row) => {
      try {
        const response = await axios.get(`/api/api-testing/notification-logs/${row.id}/detail/`)
        selectedLog.value = response.data
        detailDialogVisible.value = true
      } catch (error) {
        console.error('Fetch notification detail failed:', error)
        ElMessage.error(t('notification.logs.messages.fetchDetailFailed'))
      }
    }

    // 关闭详情弹窗
    const handleDetailDialogClose = (done) => {
      selectedLog.value = null
      done()
    }

    // 格式化日期
    const formatDate = (dateString) => {
      if (!dateString) return '-'
      const date = new Date(dateString)
      return date.toLocaleString(locale.value === 'zh-cn' ? 'zh-CN' : 'en-US')
    }

    // 获取状态标签类型
    const getStatusTagType = (status) => {
      const typeMap = {
        '发送成功': 'success',
        'success': 'success',
        '发送失败': 'danger',
        'failed': 'danger',
        '待发送': 'info',
        'pending': 'info',
        '发送中': 'warning',
        'sending': 'warning',
        '已取消': 'info',
        'cancelled': 'info'
      }
      return typeMap[status] || 'info'
    }

    // 获取通知类型标签类型
    const getNotificationTypeTagType = (typeDisplay) => {
      const typeMap = {
        '邮箱通知': '',
        'Webhook机器人': 'primary',
        '两种都发送': 'warning'
      }
      return typeMap[typeDisplay] || 'info'
    }

    // 获取通知对象标签类型
    const getTargetTagType = (targetType) => {
      const typeMap = {
        'wechat': 'success',
        'feishu': 'primary',
        'dingtalk': 'warning',
        'email': 'info'
      }
      return typeMap[targetType] || 'info'
    }

    // 格式化收件人显示
    const formatRecipients = (recipients) => {
      if (!recipients) return '-'

      if (typeof recipients === 'string') {
        return recipients.length > 20 ? recipients.substring(0, 20) + '...' : recipients
      }

      if (Array.isArray(recipients)) {
        if (recipients.length === 0) return '-'
        if (recipients.length === 1) return recipients[0]
        return `${recipients[0]} +${recipients.length - 1}`
      }

      return '-'
    }

    // 格式化收件人信息
    const formatRecipientInfo = (recipientInfo) => {
      if (!recipientInfo) return []
      if (Array.isArray(recipientInfo)) {
        return recipientInfo.map(item =>
            item.email ? `${item.name} <${item.email}>` : item.name
        )
      }
      return [recipientInfo]
    }

    // 格式化Webhook信息
    const formatWebhookInfo = (webhookInfo) => {
      if (!webhookInfo) return []
      if (Array.isArray(webhookInfo)) {
        return webhookInfo.map(item => item.name || item.type)
      }
      return [webhookInfo.name || webhookInfo.type]
    }

    // 从通知内容中解析出可读文本（兼容企微/飞书 markdown、飞书卡片、纯文本）
    const extractContentText = (raw) => {
      if (!raw) return ''
      try {
        const json = JSON.parse(raw)
        if (json.msgtype === 'markdown' && json.markdown) {
          return json.markdown.text || json.markdown.content || ''
        }
        if (json.msg_type === 'interactive' && json.card) {
          const el = (json.card.elements || [])[0]
          if (el && el.text) return el.text.content || ''
          if (json.card.header && json.card.header.title) return json.card.header.title.content || ''
        }
        if (json.text) return typeof json.text === 'string' ? json.text : JSON.stringify(json.text)
        if (json.content) return json.content
      } catch (e) {
        // 非 JSON，按纯文本处理
      }
      return raw
    }

    // 把通知内容渲染为「键:值 / 段落」结构，保留 **粗体**
    const messageLines = computed(() => {
      if (!selectedLog.value || !selectedLog.value.notification_content) return []
      const text = extractContentText(selectedLog.value.notification_content)
      if (!text) return []

      const lines = text.split('\n').map(l => l.replace(/\r$/, '')).filter(l => l.trim() !== '')
      const result = []
      let lastWasParagraph = false

      lines.forEach(line => {
        // 跳过纯分隔符
        if (/^[-*_]{3,}$/.test(line.trim())) return
        const kvMatch = line.match(/^([^:：]{1,30})[：:]\s*(.*)$/)
        if (kvMatch && !/: /.test(kvMatch[1])) {
          result.push({type: 'kv', key: kvMatch[1].trim(), value: kvMatch[2].trim()})
          lastWasParagraph = false
        } else {
          result.push({type: 'text', text: line.trim()})
          lastWasParagraph = true
        }
      })

      return result
    })

    // 内联渲染：转义 HTML 后把 **x** 渲染为 <strong>x</strong>
    const renderInline = (text) => {
      if (text == null) return ''
      let s = String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
      s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      return s
    }

    // 状态样式类
    const statusClass = (log) => {
      const s = (log.status || '').toUpperCase()
      if (s === 'SUCCESS' || (log.status_display || '').includes('成功')) return 'is-success'
      if (s === 'FAILED' || (log.status_display || '').includes('失败')) return 'is-failed'
      if (s === 'RETRYING' || s === 'SENDING' || (log.status_display || '').includes('重试') || (log.status_display || '').includes('发送中')) return 'is-warning'
      return 'is-info'
    }

    // 状态图标
    const statusIcon = (log) => {
      const cls = statusClass(log)
      if (cls === 'is-success') return 'CircleCheckFilled'
      if (cls === 'is-failed') return 'CircleCloseFilled'
      if (cls === 'is-warning') return 'WarningFilled'
      return 'InfoFilled'
    }

    // 组件挂载时获取数据
    onMounted(() => {
      fetchLogsData()
    })

    return {
      loading,
      logsData,
      detailDialogVisible,
      selectedLog,
      searchForm,
      pagination,
      sortParams,
      showRaw,
      messageLines,
      statusClass,
      statusIcon,
      renderInline,
      handleSearch,
      handleReset,
      handleSizeChange,
      handleCurrentChange,
      handleSortChange,
      viewDetail,
      handleDetailDialogClose,
      formatDate,
      getStatusTagType,
      getNotificationTypeTagType,
      getTargetTagType,
      formatRecipients,
      formatRecipientInfo,
      formatWebhookInfo
    }
  }
}
</script>

<style scoped>
.notification-logs-container {
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.page-actions {
  margin-bottom: 20px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 6px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 15px;
}

.logs-table-container {
  margin-top: 20px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.notification-targets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.target-tag {
  margin: 0;
}

/* ===== 通知详情弹窗新样式 ===== */
.ntf-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 状态头卡 */
.ntf-status-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  border-radius: 12px;
  color: #fff;
  background: linear-gradient(135deg, #909399, #b0b3b8);
}

.ntf-status-card.is-success {
  background: linear-gradient(135deg, #13ce66, #67c23a);
}

.ntf-status-card.is-failed {
  background: linear-gradient(135deg, #f56c6c, #ff7875);
}

.ntf-status-card.is-warning {
  background: linear-gradient(135deg, #e6a23c, #f0b860);
}

.ntf-status-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  flex-shrink: 0;
}

.ntf-status-main {
  flex: 1;
  min-width: 0;
}

.ntf-status-badges {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.ntf-status-sub {
  font-size: 14px;
  opacity: 0.95;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ntf-status-time {
  text-align: right;
  flex-shrink: 0;
}

.ntf-time-label {
  font-size: 12px;
  opacity: 0.85;
  margin-bottom: 4px;
}

.ntf-time-value {
  font-size: 14px;
  font-weight: 600;
}

/* 区块卡片 */
.ntf-section {
  background: #fff;
  border: 1px solid #eef0f3;
  border-radius: 12px;
  padding: 16px 18px;
}

.ntf-section-title {
  font-size: 14px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 14px;
  padding-left: 10px;
  border-left: 3px solid #5046e5;
  line-height: 1.2;
}

.ntf-section-title--row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* 基本信息网格 */
.ntf-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 24px;
}

.ntf-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.ntf-cell-label {
  font-size: 12px;
  color: #909399;
}

.ntf-cell-value {
  font-size: 14px;
  color: #303133;
  word-break: break-word;
}

/* 消息内容卡片 */
.ntf-msg-card {
  background: #f7f8fa;
  border: 1px solid #eef0f3;
  border-radius: 10px;
  padding: 14px 16px;
  max-height: 360px;
  overflow-y: auto;
}

.ntf-msg-kv {
  display: flex;
  gap: 12px;
  padding: 7px 0;
  border-bottom: 1px dashed #e6e8eb;
  font-size: 14px;
  line-height: 1.7;
}

.ntf-msg-kv:last-child {
  border-bottom: none;
}

.ntf-msg-k {
  flex: 0 0 120px;
  color: #606266;
  font-weight: 600;
  word-break: break-all;
}

.ntf-msg-v {
  flex: 1;
  color: #1f2329;
  word-break: break-word;
}

.ntf-msg-p {
  margin: 6px 0;
  font-size: 14px;
  line-height: 1.7;
  color: #1f2329;
  white-space: pre-wrap;
  word-break: break-word;
}

.ntf-msg-empty {
  font-size: 13px;
  color: #909399;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 原始内容（深色代码块） */
.ntf-raw pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  padding: 14px 16px;
  background: #2d2d2d;
  color: #d4d4d4;
  border-radius: 10px;
  font-size: 12.5px;
  line-height: 1.6;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  max-height: 360px;
  overflow-y: auto;
}

/* 错误区 */
.ntf-error-section {
  border-color: #fbc4c4;
  background: #fff6f6;
}

.ntf-error-title {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #f56c6c;
  border-left-color: #f56c6c;
}

.ntf-error {
  font-size: 13px;
  color: #c0392b;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
