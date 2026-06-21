<template>
  <div class="review-execution">
    <!-- 页面头部 -->
    <div class="page-header-card">
      <div class="header-content">
        <div class="title-section">
          <h1 class="page-title">{{ review.title }}</h1>
          <el-tag :type="getReviewStatusType(review.status)" size="large" class="status-tag">
            {{ getReviewStatusText(review.status) }}
          </el-tag>
        </div>
        
        <!-- 项目信息 -->
        <div class="project-info">
          <el-icon class="info-icon"><FolderOpened /></el-icon>
          <span v-if="review.projects && review.projects.length > 0">
            {{ review.projects.map(p => p.name).join(', ') }}
          </span>
          <span v-else class="no-data">{{ $t('reviewExecution.noProject') }}</span>
        </div>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-cards">
      <div class="stat-card total">
        <el-icon class="stat-icon"><Document /></el-icon>
        <div class="stat-content">
          <div class="stat-value">{{ progressStats.total }}</div>
          <div class="stat-label">{{ $t('reviewExecution.total') }}</div>
        </div>
      </div>
      <div class="stat-card passed">
        <el-icon class="stat-icon"><CircleCheck /></el-icon>
        <div class="stat-content">
          <div class="stat-value">{{ progressStats.passed }}</div>
          <div class="stat-label">{{ $t('reviewExecution.passed') }}</div>
        </div>
      </div>
      <div class="stat-card failed">
        <el-icon class="stat-icon"><CircleClose /></el-icon>
        <div class="stat-content">
          <div class="stat-value">{{ progressStats.failed }}</div>
          <div class="stat-label">{{ $t('reviewExecution.failedStatus') }}</div>
        </div>
      </div>
      <div class="stat-card unreviewed">
        <el-icon class="stat-icon"><QuestionFilled /></el-icon>
        <div class="stat-content">
          <div class="stat-value">{{ progressStats.unreviewed }}</div>
          <div class="stat-label">{{ $t('reviewExecution.unreviewed') }}</div>
        </div>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-section">
      <el-progress 
        :percentage="progressStats.progress" 
        :stroke-width="12"
        :color="getProgressColor(progressStats.progress)"
        :show-text="true">
        <template #default="{ percentage }">
          <span class="progress-text">{{ percentage }}%</span>
        </template>
      </el-progress>
    </div>

    <!-- 批量操作 -->
    <div v-if="selectedCases.length > 0" class="batch-actions">
      <span class="batch-count">{{ $t('reviewExecution.batchSelected') }}: <strong>{{ selectedCases.length }}</strong></span>
      <el-dropdown
        trigger="click"
        @command="handleBatchStatusCommand"
        :disabled="isBatchUpdating">
        <el-button type="primary" :loading="isBatchUpdating">
          {{ $t('reviewExecution.batchUpdateStatus') }}
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="passed" :icon="CircleCheck">
              {{ $t('reviewExecution.batchSetPassed') }}
            </el-dropdown-item>
            <el-dropdown-item command="failed" :icon="CircleClose">
              {{ $t('reviewExecution.batchSetFailed') }}
            </el-dropdown-item>
            <el-dropdown-item command="unreviewed" :icon="QuestionFilled">
              {{ $t('reviewExecution.batchSetUnreviewed') }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button
        type="danger"
        :icon="Delete"
        @click="batchDeleteCases"
        :disabled="isDeleting">
        {{ $t('reviewExecution.batchDelete') }}
      </el-button>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <el-select
        v-model="selectedModule"
        :placeholder="$t('reviewExecution.filterByModule')"
        clearable
        size="default"
        style="width: 180px"
        @change="handleModuleFilterChange">
        <el-option
          :label="$t('reviewExecution.allModules')"
          value="" />
        <el-option
          v-for="mod in availableModules"
          :key="mod"
          :label="mod"
          :value="mod" />
      </el-select>
      <span v-if="selectedModule" class="filter-result">
        {{ $t('reviewExecution.filterByModule') }}: <strong>{{ selectedModule }}</strong>
        ({{ filteredCases.length }} {{ $t('reviewExecution.total') }})
      </span>
    </div>

    <!-- 用例评审表格 -->
    <el-table
      ref="tableRef"
      :data="paginatedCases"
      style="width: 100%"
      class="review-table"
      @selection-change="handleSelectionChange"
      :row-key="(row) => row.id">
      <el-table-column type="selection" width="55" :reserve-selection="true" />
      <el-table-column
        type="index"
        :label="$t('reviewExecution.serialNumber')"
        width="80"
        :index="getSerialNumber" />
      <el-table-column prop="module" :label="$t('testcase.module')" width="120">
        <template #default="{ row }">
          {{ row.module || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="priority" :label="$t('testcase.priority')" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="getPriorityTagType(row.priority)" size="small">
            {{ getPriorityText(row.priority) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" :label="$t('reviewExecution.caseTitle')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="preconditions" :label="$t('testcase.preconditions')" min-width="200">
        <template #default="{ row }">
          <span v-if="row.preconditions" v-html="formatRichText(row.preconditions)" class="rich-cell"></span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="steps" :label="$t('testcase.steps')" min-width="240">
        <template #default="{ row }">
          <span v-if="row.steps" v-html="formatRichText(row.steps)" class="rich-cell"></span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="expected_result" :label="$t('testcase.expectedResult')" min-width="260">
        <template #default="{ row }">
          <span v-if="row.expected_result" v-html="formatRichText(row.expected_result)" class="rich-cell"></span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="reviewed_by_name" :label="$t('reviewExecution.reviewedBy')" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.reviewed_by_name">{{ row.reviewed_by_name }}</span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('reviewExecution.actions')" width="180" fixed="right">
        <template #default="scope">
          <div class="actions-cell">
            <div class="actions-row">
              <el-dropdown
                trigger="click"
                @command="(cmd) => handleStatusCommand(scope.row, cmd)">
                <el-button
                  size="small"
                  :type="getStatusButtonType(scope.row.status)"
                  :icon="getStatusButtonIcon(scope.row.status)">
                  {{ getStatusText(scope.row.status) }}
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="passed" :icon="CircleCheck">
                      {{ $t('reviewExecution.passed') }}
                    </el-dropdown-item>
                    <el-dropdown-item command="failed" :icon="CircleClose">
                      {{ $t('reviewExecution.failedStatus') }}
                    </el-dropdown-item>
                    <el-dropdown-item command="unreviewed" :icon="QuestionFilled">
                      {{ $t('reviewExecution.unreviewed') }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-tooltip :content="$t('reviewExecution.viewHistory')" placement="top">
                <el-button
                  size="small"
                  circle
                  type="primary"
                  @click="viewCaseHistory(scope.row)">
                  <el-icon><Clock /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
            <div class="actions-row">
              <el-tooltip :content="$t('reviewExecution.editCase')" placement="top">
                <el-button
                  size="small"
                  circle
                  type="success"
                  @click="openEditDialog(scope.row)">
                  <el-icon><EditPen /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip :content="$t('reviewExecution.addComment')" placement="top">
                <el-button
                  size="small"
                  circle
                  type="warning"
                  @click="openCommentDialog(scope.row)">
                  <el-icon><Edit /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div v-if="reviewCases.length > 0" class="pagination-container">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="filteredCases.length"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="handlePageChange"
        @size-change="handleSizeChange">
      </el-pagination>
    </div>

    <!-- 历史记录对话框 -->
    <el-dialog
      :title="$t('reviewExecution.reviewHistory')"
      v-model="historyDialogVisible"
      width="80%">
      <el-table :data="currentCaseHistory" style="width: 100%">
        <el-table-column prop="status" :label="$t('reviewExecution.status')" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="comments" :label="$t('reviewExecution.comments')" show-overflow-tooltip />
        <el-table-column prop="reviewed_by.username" :label="$t('reviewExecution.reviewedBy')" width="120" />
        <el-table-column prop="reviewed_at" :label="$t('reviewExecution.reviewedAt')" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.reviewed_at) }}
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 备注对话框 -->
    <el-dialog
      :title="$t('reviewExecution.comments')"
      v-model="commentDialogVisible"
      width="500px">
      <el-input
        v-model="editingComment"
        :placeholder="$t('reviewExecution.commentsPlaceholder')"
        type="textarea"
        :rows="4"
        @keyup.enter.ctrl="saveComment" />
      <template #footer>
        <el-button @click="commentDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveComment">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 修改用例对话框 -->
    <el-dialog
      :title="$t('reviewExecution.editCaseTitle')"
      v-model="editDialogVisible"
      width="650px">
      <el-form :model="editForm" label-width="90px" label-position="right">
        <el-form-item :label="$t('reviewExecution.caseTitle')">
          <el-input v-model="editForm.title" placeholder="请输入用例标题" />
        </el-form-item>
        <el-form-item :label="$t('testcase.preconditions')">
          <el-input
            v-model="editForm.preconditions"
            type="textarea"
            :rows="3"
            placeholder="请输入前置条件" />
        </el-form-item>
        <el-form-item :label="$t('testcase.steps')">
          <el-input
            v-model="editForm.steps"
            type="textarea"
            :rows="3"
            placeholder="请输入操作步骤" />
        </el-form-item>
        <el-form-item :label="$t('testcase.expectedResult')">
          <el-input
            v-model="editForm.expected_result"
            type="textarea"
            :rows="3"
            placeholder="请输入预期结果" />
        </el-form-item>
        <el-form-item :label="$t('testcase.priority')">
          <el-select v-model="editForm.priority" style="width:100%">
            <el-option :label="$t('testcase.low')" value="low" />
            <el-option :label="$t('testcase.medium')" value="medium" />
            <el-option :label="$t('testcase.high')" value="high" />
            <el-option :label="$t('testcase.critical')" value="critical" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveEditCase" :loading="editSaving">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Delete, Clock, Document, CircleCheck, CircleClose, Edit, EditPen,
  WarningFilled, QuestionFilled, FolderOpened, ArrowDown, Back
} from '@element-plus/icons-vue'
import api from '@/utils/api'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const review = ref({})
const reviewCases = ref([])
const historyDialogVisible = ref(false)
const currentCaseHistory = ref([])
const selectedCases = ref([])
const currentPage = ref(1)
const pageSize = ref(10)
const isDeleting = ref(false)
const isBatchUpdating = ref(false)
const tableRef = ref(null)
const commentDialogVisible = ref(false)
const editingComment = ref('')
const currentCommentRow = ref(null)
const editDialogVisible = ref(false)
const editForm = ref({ title: '', preconditions: '', steps: '', expected_result: '', priority: 'medium' })
const editCurrentRow = ref(null)
const editSaving = ref(false)
const selectedModule = ref('')

const formatRichText = (text) => {
  if (!text) return ''
  let result = text.replace(/\r?\n/g, '<br/>')
  if (!/<br/i.test(result)) {
    result = result.replace(/([。！？”\"）\\)\u4e00-\u9fff\w])(\d+)[\.\、](?=\s*\D)/g, '$1<br/>$2.')
  }
  return result
}

// 进度统计
const progressStats = computed(() => {
  const total = reviewCases.value.length
  if (total === 0) return { total: 0, unreviewed: 0, passed: 0, failed: 0, progress: 0 }
  
  const unreviewed = reviewCases.value.filter(c => c.status === 'unreviewed').length
  const passed = reviewCases.value.filter(c => c.status === 'passed').length
  const failed = reviewCases.value.filter(c => c.status === 'failed').length
  const reviewed = passed + failed
  
  return {
    total,
    unreviewed,
    passed,
    failed,
    progress: Math.round((reviewed / total) * 100 * 10) / 10
  }
})

// 模块筛选
const availableModules = computed(() => {
  const modules = new Set()
  reviewCases.value.forEach(c => { if (c.module) modules.add(c.module) })
  return Array.from(modules).sort()
})

const filteredCases = computed(() => {
  if (!selectedModule.value) return reviewCases.value
  return reviewCases.value.filter(c => c.module === selectedModule.value)
})

const handleModuleFilterChange = () => {
  currentPage.value = 1
  selectedCases.value = []
  if (tableRef.value) tableRef.value.clearSelection()
}

// 分页
const paginatedCases = computed(() => {
  const cases = filteredCases.value
  const start = (currentPage.value - 1) * pageSize.value
  return cases.slice(start, start + pageSize.value)
})

const getSerialNumber = (index) => {
  return (currentPage.value - 1) * pageSize.value + index + 1
}

const handlePageChange = () => {
  selectedCases.value = []
  if (tableRef.value) tableRef.value.clearSelection()
}

const handleSizeChange = () => {
  currentPage.value = 1
  selectedCases.value = []
  if (tableRef.value) tableRef.value.clearSelection()
}

// 获取评审和用例数据
const fetchReview = async () => {
  try {
    const reviewId = route.params.id
    const response = await api.get(`/reviews/reviews/${reviewId}/`)
    review.value = response.data
    
    // 同步评审用例：确保模块下所有用例都已创建 ReviewCase 记录
    if (review.value.modules && review.value.modules.length > 0) {
      await api.post(`/reviews/reviews/${reviewId}/sync_review_cases/`)
    }
    
    // 单独获取 review_cases 列表
    await fetchReviewCases(reviewId)
  } catch (error) {
    ElMessage.error(t('reviewExecution.fetchFailed'))
  }
}

const fetchReviewCases = async (reviewId) => {
  try {
    const response = await api.get('/reviews/review-cases/', { 
      params: { review: reviewId, page_size: 10000 } 
    })
    reviewCases.value = response.data.results || response.data || []
  } catch (error) {
    ElMessage.error(t('reviewExecution.fetchCasesFailed'))
  }
}

// 状态操作
const handleStatusCommand = async (row, newStatus) => {
  if (row.status === newStatus) return
  row.status = newStatus
  await updateCaseStatus(row)
}

const updateCaseStatus = async (reviewCase) => {
  try {
    await api.patch(`/reviews/review-cases/${reviewCase.id}/update_status/`, {
      status: reviewCase.status,
      comments: reviewCase.comments || ''
    })
    ElMessage.success(t('reviewExecution.statusUpdateSuccess'))
  } catch (error) {
    ElMessage.error(t('reviewExecution.statusUpdateFailed'))
  }
}

// 备注
const openCommentDialog = (row) => {
  currentCommentRow.value = row
  editingComment.value = row.comments || ''
  commentDialogVisible.value = true
}

const saveComment = async () => {
  if (!currentCommentRow.value) return
  try {
    currentCommentRow.value.comments = editingComment.value
    await api.patch(`/reviews/review-cases/${currentCommentRow.value.id}/update_status/`, {
      status: currentCommentRow.value.status,
      comments: editingComment.value
    })
    commentDialogVisible.value = false
    currentCommentRow.value = null
    ElMessage.success(t('reviewExecution.commentsUpdateSuccess'))
  } catch (error) {
    ElMessage.error(t('reviewExecution.commentsUpdateFailed'))
  }
}

// 修改用例
const openEditDialog = (row) => {
  editCurrentRow.value = row
  editForm.value = {
    title: row.title || '',
    preconditions: row.preconditions || '',
    steps: row.steps || '',
    expected_result: row.expected_result || '',
    priority: row.priority || 'medium'
  }
  editDialogVisible.value = true
}

const saveEditCase = async () => {
  if (!editCurrentRow.value) return
  editSaving.value = true
  try {
    await api.patch(`/reviews/review-cases/${editCurrentRow.value.id}/update_testcase/`, {
      title: editForm.value.title,
      preconditions: editForm.value.preconditions,
      steps: editForm.value.steps,
      expected_result: editForm.value.expected_result,
      priority: editForm.value.priority
    })
    const row = editCurrentRow.value
    row.title = editForm.value.title
    row.preconditions = editForm.value.preconditions
    row.steps = editForm.value.steps
    row.expected_result = editForm.value.expected_result
    row.priority = editForm.value.priority
    editDialogVisible.value = false
    editCurrentRow.value = null
    ElMessage.success(t('reviewExecution.caseUpdateSuccess'))
  } catch (error) {
    ElMessage.error(t('reviewExecution.caseUpdateFailed'))
  } finally {
    editSaving.value = false
  }
}

// 历史
const viewCaseHistory = async (reviewCase) => {
  try {
    const response = await api.get(`/reviews/review-cases/${reviewCase.id}/history/`)
    currentCaseHistory.value = response.data
    historyDialogVisible.value = true
  } catch (error) {
    ElMessage.error(t('reviewExecution.fetchHistoryFailed'))
  }
}

// 批量状态更新
const handleBatchStatusCommand = async (targetStatus) => {
  if (selectedCases.value.length === 0) {
    ElMessage.warning(t('reviewExecution.selectCasesFirst'))
    return
  }
  
  const statusTextMap = {
    passed: t('reviewExecution.passed'),
    failed: t('reviewExecution.failedStatus'),
    unreviewed: t('reviewExecution.unreviewed')
  }
  
  try {
    await ElMessageBox.confirm(
      t('reviewExecution.batchStatusConfirm', {
        count: selectedCases.value.length,
        status: statusTextMap[targetStatus]
      }),
      t('common.warning'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
  } catch {
    return
  }
  
  isBatchUpdating.value = true
  try {
    const ids = selectedCases.value.map(c => c.id)
    await api.post('/reviews/review-cases/batch_update_status/', {
      ids: ids,
      status: targetStatus
    })
    
    // 更新本地数据
    selectedCases.value.forEach(c => {
      c.status = targetStatus
    })
    
    ElMessage.success(t('reviewExecution.batchStatusSuccess', {
      count: ids.length,
      status: statusTextMap[targetStatus]
    }))
    
    selectedCases.value = []
    if (tableRef.value) tableRef.value.clearSelection()
  } catch (error) {
    ElMessage.error(t('reviewExecution.batchStatusFailed'))
  } finally {
    isBatchUpdating.value = false
  }
}

// 批量选择/删除
const handleSelectionChange = (selection) => {
  selectedCases.value = selection
}

const batchDeleteCases = async () => {
  if (selectedCases.value.length === 0) {
    ElMessage.warning(t('reviewExecution.selectCasesFirst'))
    return
  }

  try {
    await ElMessageBox.confirm(
      t('reviewExecution.batchDeleteConfirm', { count: selectedCases.value.length }),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )

    isDeleting.value = true
    let successCount = 0
    let failCount = 0

    for (const reviewCase of selectedCases.value) {
      try {
        await api.delete(`/reviews/review-cases/${reviewCase.id}/`)
        successCount++
      } catch (error) {
        failCount++
      }
    }

    if (successCount > 0) {
      ElMessage.success(t('reviewExecution.batchDeleteSuccess', { successCount, failCount }))
    } else {
      ElMessage.error(t('reviewExecution.batchDeleteFailed'))
    }

    selectedCases.value = []
    await fetchReview()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('reviewExecution.batchDeleteFailed'))
    }
  } finally {
    isDeleting.value = false
  }
}

// 辅助函数
const formatDate = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

const getProgressColor = (percentage) => {
  if (percentage < 30) return '#f56c6c'
  if (percentage < 70) return '#e6a23c'
  return '#67c23a'
}

const getReviewStatusType = (status) => {
  const map = { pending: 'info', in_progress: 'warning', approved: 'success', rejected: 'danger', cancelled: 'info' }
  return map[status] || 'info'
}

const getReviewStatusText = (status) => {
  const map = {
    pending: t('reviewList.statusPending'),
    in_progress: t('reviewList.statusInProgress'),
    approved: t('reviewList.statusApproved'),
    rejected: t('reviewList.statusRejected'),
    cancelled: t('reviewList.statusCancelled')
  }
  return map[status] || status
}

const getStatusType = (status) => {
  const typeMap = { unreviewed: 'info', passed: 'success', failed: 'danger' }
  return typeMap[status] || 'info'
}

const getStatusText = (status) => {
  const textMap = {
    unreviewed: t('reviewExecution.unreviewed'),
    passed: t('reviewExecution.passed'),
    failed: t('reviewExecution.failedStatus')
  }
  return textMap[status] || status
}

const getStatusButtonType = (status) => {
  const map = { unreviewed: 'info', passed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

const getStatusButtonIcon = (status) => {
  const map = { unreviewed: QuestionFilled, passed: CircleCheck, failed: CircleClose }
  return map[status] || QuestionFilled
}

const getPriorityText = (priority) => {
  const map = { low: t('testcase.low'), medium: t('testcase.medium'), high: t('testcase.high'), critical: t('testcase.critical') }
  return map[priority] || priority || '-'
}

const getPriorityTagType = (priority) => {
  const map = { low: 'info', medium: '', high: 'warning', critical: 'danger' }
  return map[priority] || 'info'
}

onMounted(() => {
  fetchReview()
})
</script>

<style scoped>
.review-execution {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100vh;
}

/* 页面头部 */
.page-header-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  padding: 32px;
  margin-bottom: 24px;
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.25);
  color: white;
}

.header-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.title-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  color: white;
}

.status-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  backdrop-filter: blur(10px);
}

.project-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.9);
}

.info-icon { font-size: 18px; }
.no-data { color: rgba(255, 255, 255, 0.6); font-style: italic; }

/* 统计卡片 */
.stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: 12px;
  transition: all 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.stat-card.total { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
.stat-card.passed { background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%); color: #155724; }
.stat-card.failed { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); color: #721c24; }
.stat-card.unreviewed { background: linear-gradient(135deg, #e0e7ff 0%, #cfd9ff 100%); color: #383d41; }

.stat-icon { font-size: 32px; opacity: 0.9; }
.stat-content { display: flex; flex-direction: column; }
.stat-value { font-size: 24px; font-weight: 700; line-height: 1; }
.stat-label { font-size: 12px; margin-top: 4px; opacity: 0.9; }

/* 进度条 */
.progress-section {
  margin-bottom: 24px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
}
.progress-text { font-weight: 600; font-size: 14px; }

/* 批量操作 */
.batch-actions {
  margin-bottom: 16px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
}
.batch-count {
  font-size: 13px;
  color: #606266;
  margin-right: auto;
}
.batch-count strong {
  color: #409eff;
  font-size: 15px;
}

/* 筛选 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.filter-result { font-size: 13px; color: #606266; }
.filter-result strong { color: #409eff; }

/* 表格 */
.review-table { border-radius: 8px; overflow: hidden; }

.actions-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}

.actions-row {
  display: flex;
  gap: 4px;
  align-items: center;
}

.actions-cell .el-button { margin: 0; }
.actions-cell .el-button.is-circle { padding: 5px; }

.rich-cell {
  line-height: 1.6;
  word-break: break-word;
  white-space: normal;
  display: block;
}

.text-muted { color: #c0c4cc; }

:deep(.el-table__body-wrapper .cell) {
  word-break: break-word;
}

/* 分页 */
.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}
</style>
