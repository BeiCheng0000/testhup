<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('testcase.title') }}</h1>
      <div class="header-actions">
        <el-button
          v-if="selectedTestCases.length > 0"
          type="warning"
          @click="openBatchEditDialog">
          <el-icon><Edit /></el-icon>
          {{ $t('testcase.batchEdit') }} ({{ selectedTestCases.length }})
        </el-button>
        <el-button
          v-if="selectedTestCases.length > 0"
          type="danger"
          @click="batchDeleteTestCases"
          :disabled="isDeleting">
          <el-icon><Delete /></el-icon>
          {{ $t('testcase.batchDelete') }} ({{ selectedTestCases.length }})
        </el-button>
        <el-button type="success" @click="exportToExcel">
          <el-icon><Download /></el-icon>
          {{ $t('testcase.exportExcel') }}
        </el-button>
        <el-button @click="downloadImportTemplate">
          <el-icon><Download /></el-icon>
          {{ $t('testcase.downloadImportTemplate') }}
        </el-button>
        <el-button type="warning" @click="openImportDialog">
          <el-icon><Upload /></el-icon>
          {{ $t('testcase.importCases') }}
        </el-button>
        <el-button @click="goToImportRecords">
          {{ $t('testcase.importRecords') }}
        </el-button>
        <el-button type="primary" @click="$router.push('/ai-generation/testcases/create')">
          <el-icon><Plus /></el-icon>
          {{ $t('testcase.newCase') }}
        </el-button>
      </div>
    </div>
    
    <div class="card-container">
      <div class="filter-bar">
        <el-row :gutter="16">
          <el-col :span="4">
            <el-input
              v-model="searchText"
              :placeholder="$t('testcase.searchPlaceholder')"
              clearable
              @input="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-col>
          <el-col :span="4">
            <el-select v-model="projectFilter" :placeholder="$t('testcase.relatedProject')" clearable @change="onProjectFilterChange">
              <el-option
                v-for="project in projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-select v-model="versionFilter" :placeholder="$t('testcase.versionFilter')" clearable @change="handleFilter" :disabled="!projectFilter">
              <el-option
                v-for="version in filterVersions"
                :key="version.id"
                :label="version.name"
                :value="version.id"
              />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-input
              v-model="moduleFilter"
              :placeholder="$t('testcase.moduleFilter')"
              clearable
              @input="handleSearch"
            />
          </el-col>
          <el-col :span="4">
            <el-select v-model="priorityFilter" :placeholder="$t('testcase.priorityFilter')" clearable @change="handleFilter">
              <el-option :label="$t('testcase.low')" value="low" />
              <el-option :label="$t('testcase.medium')" value="medium" />
              <el-option :label="$t('testcase.high')" value="high" />
              <el-option :label="$t('testcase.critical')" value="critical" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-select v-model="typeFilter" :placeholder="$t('testcase.selectTestType')" clearable @change="handleFilter">
              <el-option :label="$t('testcase.functional')" value="functional" />
              <el-option :label="$t('testcase.integration')" value="integration" />
              <el-option :label="$t('testcase.api')" value="api" />
              <el-option :label="$t('testcase.ui')" value="ui" />
              <el-option :label="$t('testcase.performance')" value="performance" />
              <el-option :label="$t('testcase.security')" value="security" />
            </el-select>
          </el-col>
        </el-row>
      </div>
      
      <div class="table-container">
        <el-table 
          :data="testcases" 
          v-loading="loading" 
          style="width: 100%"
          height="100%"
          @selection-change="handleSelectionChange">
          <el-table-column type="selection" width="55" />
          <el-table-column type="index" :label="$t('testcase.serialNumber')" width="80" :index="getSerialNumber" />
          <el-table-column prop="module" :label="$t('testcase.module')" width="120">
            <template #default="{ row }">
              {{ row.module || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="title" :label="$t('testcase.caseTitle')" min-width="180">
            <template #default="{ row }">
              <el-link @click="goToTestCase(row.id)" type="primary">
                {{ row.title }}
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="preconditions" :label="$t('testcase.preconditions')" min-width="260">
            <template #default="{ row }">
              <span v-if="row.preconditions" v-html="formatRichText(row.preconditions)" class="rich-cell"></span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="steps" :label="$t('testcase.steps')" min-width="300">
            <template #default="{ row }">
              <span v-if="row.steps" v-html="formatRichText(row.steps)" class="rich-cell"></span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="expected_result" :label="$t('testcase.expectedResult')" min-width="300">
            <template #default="{ row }">
              <span v-if="row.expected_result" v-html="formatRichText(row.expected_result)" class="rich-cell"></span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="priority" :label="$t('testcase.priority')" width="80">
            <template #default="{ row }">
              <el-tag :class="`priority-tag ${row.priority}`">{{ getPriorityText(row.priority) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" :label="$t('testcase.createdAt')" width="150">
            <template #default="{ row }">
              {{ formatDate(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="project.name" :label="$t('testcase.relatedProject')" width="130" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.project?.name || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="versions" :label="$t('testcase.relatedVersions')" width="140">
            <template #default="{ row }">
              <div v-if="row.versions && row.versions.length > 0" class="version-tags">
                <el-tag 
                  v-for="version in row.versions.slice(0, 2)" 
                  :key="version.id" 
                  size="small" 
                  :type="version.is_baseline ? 'warning' : 'info'"
                  class="version-tag"
                >
                  {{ version.name }}
                </el-tag>
                <el-tooltip v-if="row.versions.length > 2" :content="getVersionsTooltip(row.versions)">
                  <el-tag size="small" type="info" class="version-tag">
                    +{{ row.versions.length - 2 }}
                  </el-tag>
                </el-tooltip>
              </div>
              <span v-else class="no-version">{{ $t('testcase.noVersion') }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('project.actions')" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="editTestCase(row)">{{ $t('common.edit') }}</el-button>
              <el-button size="small" type="danger" @click="deleteTestCase(row)">{{ $t('common.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[15, 25, 35, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <el-dialog
      v-model="importDialogVisible"
      :title="$t('testcase.importDialogTitle')"
      width="560px"
    >
      <el-alert
        :title="$t('testcase.uploadTip')"
        type="info"
        :closable="false"
        show-icon
        class="import-alert"
      />

      <el-form label-width="100px">
        <el-form-item :label="$t('testcase.importProject')">
          <el-select
            v-model="importForm.projectId"
            style="width: 100%"
            :placeholder="$t('testcase.selectImportProject')"
            filterable
            @change="onImportProjectChange"
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('testcase.selectImportVersions')">
          <el-select
            v-model="importForm.versionIds"
            style="width: 100%"
            multiple
            :placeholder="$t('testcase.selectImportVersionsPlaceholder')"
            filterable
          >
            <el-option
              v-for="version in importVersions"
              :key="version.id"
              :label="version.name + (version.is_baseline ? ' (' + $t('testcase.baseline') + ')' : '')"
              :value="version.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('testcase.selectImportFile')">
          <el-upload
            class="import-upload"
            drag
            action="#"
            :auto-upload="false"
            :limit="1"
            accept=".xlsx"
            :show-file-list="false"
            :before-upload="beforeImportUpload"
            :on-change="handleImportFileChange"
          >
            <el-icon class="el-icon--upload"><Upload /></el-icon>
            <div class="el-upload__text">
              {{ $t('testcase.chooseFile') }}
            </div>
            <template #tip>
              <div class="el-upload__tip">
                {{ $t('testcase.selectedFile') }}: {{ selectedImportFile?.name || '-' }}
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="importDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button @click="downloadImportTemplate">
          {{ $t('testcase.downloadImportTemplate') }}
        </el-button>
        <el-button type="primary" :loading="isCreatingImport" @click="submitImport">
          {{ isCreatingImport ? $t('testcase.uploading') : $t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量修改对话框 -->
    <el-dialog
      v-model="batchEditDialogVisible"
      :title="$t('testcase.batchEditTitle')"
      width="560px"
    >
      <el-alert
        :title="$t('testcase.batchEditTip')"
        type="info"
        :closable="false"
        show-icon
        class="import-alert"
      />

      <el-form label-width="100px" class="batch-edit-form">
        <el-form-item :label="$t('testcase.relatedProject')">
          <el-select
            v-model="batchEditForm.projectId"
            style="width: 100%"
            :placeholder="$t('common.selectProject')"
            filterable
            clearable
            @change="onBatchProjectChange"
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('testcase.relatedVersions')">
          <el-select
            v-model="batchEditForm.versionIds"
            style="width: 100%"
            multiple
            :placeholder="$t('testcase.selectVersions')"
            filterable
          >
            <el-option
              v-for="version in batchEditVersions"
              :key="version.id"
              :label="version.name + (version.is_baseline ? ' (' + $t('testcase.baseline') + ')' : '')"
              :value="version.id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="batchEditDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="isBatchUpdating" @click="submitBatchUpdate">
          {{ $t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Download, Delete, Upload, Edit } from '@element-plus/icons-vue'
import api from '@/utils/api'
import dayjs from 'dayjs'
import * as XLSX from 'xlsx'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const testcases = ref([])
const projects = ref([])
const currentPage = ref(1)
const pageSize = ref(15)
const total = ref(0)
const searchText = ref('')
const projectFilter = ref('')
const versionFilter = ref('')
const moduleFilter = ref('')
const priorityFilter = ref('')
const typeFilter = ref('')
const filterVersions = ref([])
const selectedTestCases = ref([])
const isDeleting = ref(false)
const importDialogVisible = ref(false)
const isCreatingImport = ref(false)
const selectedImportFile = ref(null)
const importForm = ref({
  projectId: '',
  versionIds: []
})

const importVersions = ref([])

// 批量修改
const batchEditDialogVisible = ref(false)
const isBatchUpdating = ref(false)
const batchEditVersions = ref([])
const batchEditForm = ref({
  projectId: null,
  versionIds: []
})

const fetchTestCases = async () => {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchText.value,
      project: projectFilter.value,
      version: versionFilter.value,
      module: moduleFilter.value,
      priority: priorityFilter.value,
      test_type: typeFilter.value
    }
    const response = await api.get('/testcases/', { params })
    testcases.value = response.data.results || []
    total.value = response.data.count || 0
  } catch (error) {
    ElMessage.error(t('testcase.fetchListFailed'))
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchTestCases()
}

const handleFilter = () => {
  currentPage.value = 1
  fetchTestCases()
}

const onProjectFilterChange = (projectId) => {
  versionFilter.value = ''
  filterVersions.value = []
  if (projectId) {
    fetchFilterVersions(projectId)
  }
  handleFilter()
}

const fetchFilterVersions = async (projectId) => {
  try {
    const response = await api.get(`/versions/projects/${projectId}/versions/`)
    filterVersions.value = response.data || []
  } catch (error) {
    console.error('Fetch filter versions failed:', error)
    filterVersions.value = []
  }
}

const handlePageChange = () => {
  fetchTestCases()
}

const handleSizeChange = () => {
  currentPage.value = 1
  fetchTestCases()
}

const goToTestCase = (id) => {
  router.push(`/ai-generation/testcases/${id}`)
}

const editTestCase = (testcase) => {
  router.push(`/ai-generation/testcases/${testcase.id}/edit`)
}

const deleteTestCase = async (testcase) => {
  try {
    await ElMessageBox.confirm(t('testcase.deleteConfirm'), t('common.warning'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    })
    
    await api.delete(`/testcases/${testcase.id}/`)
    ElMessage.success(t('testcase.deleteSuccess'))
    fetchTestCases()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('testcase.deleteFailed'))
    }
  }
}

// 处理选择变化
const handleSelectionChange = (selection) => {
  selectedTestCases.value = selection
}

// 获取序号
const getSerialNumber = (index) => {
  return (currentPage.value - 1) * pageSize.value + index + 1
}

// 批量删除
const batchDeleteTestCases = async () => {
  if (selectedTestCases.value.length === 0) {
    ElMessage.warning(t('testcase.selectFirst'))
    return
  }

  try {
    await ElMessageBox.confirm(
      t('testcase.batchDeleteConfirm', { count: selectedTestCases.value.length }),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )

    isDeleting.value = true
    const ids = selectedTestCases.value.map(tc => tc.id)

    const response = await api.post('/testcases/batch-delete/', { ids })
    const { deleted_count, not_found_count } = response.data

    if (not_found_count > 0) {
      ElMessage.warning(t('testcase.batchDeletePartialSuccess', { successCount: deleted_count, failCount: not_found_count }))
    } else {
      ElMessage.success(t('testcase.batchDeleteSuccess', { successCount: deleted_count }))
    }

    // 清空选择并重新加载列表
    selectedTestCases.value = []
    fetchTestCases()

  } catch (error) {
    if (error !== 'cancel') {
      console.error('Batch delete failed:', error)
      ElMessage.error(t('testcase.batchDeleteError') + ': ' + (error.response?.data?.error || t('common.error')))
    }
  } finally {
    isDeleting.value = false
  }
}

const getPriorityText = (priority) => {
  const textMap = {
    low: t('testcase.low'),
    medium: t('testcase.medium'),
    high: t('testcase.high'),
    critical: t('testcase.critical')
  }
  return textMap[priority] || priority
}

const getTypeText = (type) => {
  const textMap = {
    functional: t('testcase.functional'),
    integration: t('testcase.integration'),
    api: t('testcase.api'),
    ui: t('testcase.ui'),
    performance: t('testcase.performance'),
    security: t('testcase.security')
  }
  return textMap[type] || '-'
}

const formatDate = (dateString) => {
  return dayjs(dateString).format('YYYY-MM-DD HH:mm')
}

const getVersionsTooltip = (versions) => {
  return versions.map(v => v.name + (v.is_baseline ? ' (' + t('testcase.baseline') + ')' : '')).join('、')
}

// 格式化富文本内容：换行显示 + 自动识别序号分行
const formatRichText = (text) => {
  if (!text) return ''
  let result = text
  // 1. 将 \n 转换为 <br/>
  result = result.replace(/\r?\n/g, '<br/>')
  // 2. 如果没有 <br/> 标签，尝试自动识别序号分行（如 1.xxx2.xxx -> 1.xxx<br/>2.xxx）
  if (!/<br/i.test(result)) {
    result = result.replace(/([。！？”"）\)\u4e00-\u9fff\w])(\d+)[\.\、](?=\s*\D)/g, '$1<br/>$2.')
  }
  return result
}

// 将HTML的<br>标签转换为换行符（用于Excel导出）
const convertBrToNewline = (text) => {
  if (!text) return ''
  return text.replace(/<br\s*\/?>/gi, '\n')
}

const exportToExcel = async () => {
  try {
    loading.value = true

    // 确定要导出的数据
    let testCasesToExport = []

    if (selectedTestCases.value.length > 0) {
      // 如果有勾选，导出勾选的数据
      testCasesToExport = selectedTestCases.value
    } else {
      // 如果没有勾选，分页获取所有数据
      const pageSize = 100  // 使用后端允许的最大值
      let page = 1
      let hasMore = true
      let allData = []

      while (hasMore) {
        const response = await api.get('/testcases/', {
          params: {
            page: page,
            page_size: pageSize,
            search: searchText.value,
            project: projectFilter.value,
            version: versionFilter.value,
            module: moduleFilter.value,
            priority: priorityFilter.value,
            test_type: typeFilter.value
          }
        })

        const results = response.data.results || []
        allData.push(...results)

        // 检查是否还有更多数据
        // 如果返回的数据少于pageSize，说明已经是最后一页
        if (results.length < pageSize) {
          hasMore = false
        } else {
          page++
        }
      }

      testCasesToExport = allData
    }

    if (testCasesToExport.length === 0) {
      ElMessage.warning(t('testcase.noDataToExport'))
      loading.value = false
      return
    }

    // 创建工作簿
    const workbook = XLSX.utils.book_new()

    // 准备Excel数据
    const worksheetData = [
      [t('testcase.excelNumber'), t('testcase.excelModule'), t('testcase.excelTitle'), t('testcase.excelProject'), t('testcase.excelVersions'), t('testcase.excelPreconditions'), t('testcase.excelSteps'), t('testcase.excelExpectedResult'), t('testcase.excelPriority'), t('testcase.excelTestType'), t('testcase.excelAuthor'), t('testcase.excelCreatedAt')]
    ]

    testCasesToExport.forEach((testcase, index) => {
      const versions = testcase.versions && testcase.versions.length > 0
        ? testcase.versions.map(v => v.name + (v.is_baseline ? '(' + t('testcase.baseline') + ')' : '')).join('、')
        : t('testcase.noVersion')

      worksheetData.push([
        `TC${String(index + 1).padStart(3, '0')}`,
        testcase.module || '',
        testcase.title || '',
        testcase.project?.name || '',
        versions,
        convertBrToNewline(testcase.preconditions || ''),
        convertBrToNewline(testcase.steps || ''),
        convertBrToNewline(testcase.expected_result || ''),
        getPriorityText(testcase.priority),
        getTypeText(testcase.test_type),
        testcase.author?.username || '',
        formatDate(testcase.created_at)
      ])
    })
    
    // 创建工作表
    const worksheet = XLSX.utils.aoa_to_sheet(worksheetData)
    
    // 设置列宽
    const colWidths = [
      { wch: 15 }, // Test case number
      { wch: 20 }, // Module
      { wch: 30 }, // Case title
      { wch: 20 }, // Related project
      { wch: 25 }, // Related versions
      { wch: 30 }, // Preconditions
      { wch: 40 }, // Steps
      { wch: 30 }, // Expected result
      { wch: 10 }, // Priority
      { wch: 15 }, // Test type
      { wch: 15 }, // Author
      { wch: 20 }  // Created at
    ]
    worksheet['!cols'] = colWidths
    
    // 设置表头样式
    for (let col = 0; col < worksheetData[0].length; col++) {
      const cellAddress = XLSX.utils.encode_cell({ r: 0, c: col })
      if (!worksheet[cellAddress]) continue
      worksheet[cellAddress].s = {
        font: { bold: true },
        alignment: { horizontal: 'center', vertical: 'center', wrapText: true }
      }
    }
    
    // 设置其他行的样式
    for (let row = 1; row < worksheetData.length; row++) {
      for (let col = 0; col < worksheetData[row].length; col++) {
        const cellAddress = XLSX.utils.encode_cell({ r: row, c: col })
        if (worksheet[cellAddress]) {
          worksheet[cellAddress].s = {
            alignment: { vertical: 'top', wrapText: true }
          }
        }
      }
    }

    // Add worksheet to workbook
    XLSX.utils.book_append_sheet(workbook, worksheet, t('testcase.excelSheetName'))

    // Generate filename
    const fileName = t('testcase.excelFileName', { date: new Date().toISOString().slice(0, 10) })

    // Export file
    XLSX.writeFile(workbook, fileName)

    ElMessage.success(t('testcase.exportSuccess'))
  } catch (error) {
    console.error('Export test cases failed:', error)
    ElMessage.error(t('testcase.exportFailed') + ': ' + (error.message || t('common.error')))
  } finally {
    loading.value = false
  }
}

const downloadBlob = (blob, fileName) => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

const downloadImportTemplate = async () => {
  try {
    const response = await api.get('/testcases/import/template/', {
      responseType: 'blob'
    })
    downloadBlob(response.data, 'testcase_import_template_v1.xlsx')
    ElMessage.success(t('testcase.downloadTemplateSuccess'))
  } catch (error) {
    console.error('Download import template failed:', error)
    ElMessage.error(t('testcase.downloadTemplateFailed'))
  }
}

const openImportDialog = () => {
  importForm.value.projectId = projectFilter.value || ''
  selectedImportFile.value = null
  importDialogVisible.value = true
}

const beforeImportUpload = (file) => {
  const isXlsx = file.name.toLowerCase().endsWith('.xlsx')
  if (!isXlsx) {
    ElMessage.error(t('testcase.invalidImportFile'))
  }
  return isXlsx
}

const handleImportFileChange = (uploadFile) => {
  if (uploadFile?.raw) {
    selectedImportFile.value = uploadFile.raw
  }
}

const submitImport = async () => {
  if (!importForm.value.projectId) {
    ElMessage.warning(t('testcase.importProjectRequired'))
    return
  }
  if (!importForm.value.versionIds || importForm.value.versionIds.length === 0) {
    ElMessage.warning(t('testcase.importVersionRequired'))
    return
  }
  if (!selectedImportFile.value) {
    ElMessage.warning(t('testcase.importFileRequired'))
    return
  }

  const formData = new FormData()
  formData.append('project_id', importForm.value.projectId)
  formData.append('version_ids', importForm.value.versionIds.join(','))
  formData.append('file', selectedImportFile.value)

  isCreatingImport.value = true
  try {
    await api.post('/testcases/import-records/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    ElMessage.success(t('testcase.importCreated'))
    importDialogVisible.value = false
    goToImportRecords()
  } catch (error) {
    console.error('Create import record failed:', error)
    ElMessage.error(error.response?.data?.error || t('testcase.importCreateFailed'))
  } finally {
    isCreatingImport.value = false
  }
}

const goToImportRecords = () => {
  router.push('/ai-generation/testcases/import-records')
}

const onImportProjectChange = (projectId) => {
  importForm.value.versionIds = []
  if (projectId) {
    fetchImportVersions(projectId)
  } else {
    importVersions.value = []
  }
}

const fetchImportVersions = async (projectId) => {
  try {
    const response = await api.get(`/versions/projects/${projectId}/versions/`)
    importVersions.value = response.data || []
  } catch (error) {
    console.error('Fetch import versions failed:', error)
    importVersions.value = []
  }
}

// 批量修改相关
const openBatchEditDialog = () => {
  if (selectedTestCases.value.length === 0) {
    ElMessage.warning(t('testcase.selectFirst'))
    return
  }

  // 默认显示第一个选中用例的参数
  const first = selectedTestCases.value[0]
  batchEditForm.value.projectId = first.project?.id || null
  batchEditForm.value.versionIds = first.versions ? first.versions.map(v => v.id) : []

  // 加载第一个用例所在项目的版本列表
  if (first.project?.id) {
    fetchVersionsForProject(first.project.id)
  } else {
    batchEditVersions.value = []
  }

  batchEditDialogVisible.value = true
}

const fetchVersionsForProject = async (projectId) => {
  try {
    const response = await api.get(`/versions/projects/${projectId}/versions/`)
    batchEditVersions.value = response.data || []
  } catch (error) {
    console.error('Fetch versions failed:', error)
    batchEditVersions.value = []
  }
}

const onBatchProjectChange = (projectId) => {
  // 切换项目时清空已选版本并重新加载
  batchEditForm.value.versionIds = []
  if (projectId) {
    fetchVersionsForProject(projectId)
  } else {
    batchEditVersions.value = []
  }
}

const submitBatchUpdate = async () => {
  const { projectId, versionIds } = batchEditForm.value

  // 检查是否至少有一个字段被修改
  if (!projectId && (!versionIds || versionIds.length === 0)) {
    ElMessage.warning('至少需要选择关联项目或关联版本中的一项')
    return
  }

  isBatchUpdating.value = true
  try {
    const ids = selectedTestCases.value.map(tc => tc.id)
    const payload = { ids }
    if (projectId) {
      payload.project_id = projectId
    }
    if (versionIds && versionIds.length > 0) {
      payload.version_ids = versionIds
    }

    const response = await api.post('/testcases/batch-update/', payload)
    const { updated_count, not_found_count } = response.data

    if (not_found_count > 0) {
      ElMessage.warning(`成功修改 ${updated_count} 个，${not_found_count} 个无权限或不存在`)
    } else {
      ElMessage.success(t('testcase.batchUpdateSuccess', { updatedCount: updated_count }))
    }

    batchEditDialogVisible.value = false
    selectedTestCases.value = []
    fetchTestCases()
  } catch (error) {
    console.error('Batch update failed:', error)
    ElMessage.error(t('testcase.batchUpdateFailed') + ': ' + (error.response?.data?.error || t('common.error')))
  } finally {
    isBatchUpdating.value = false
  }
}

const fetchProjects = async () => {
  try {
    const response = await api.get('/projects/')
    projects.value = response.data.results || response.data || []
  } catch (error) {
    ElMessage.error(t('testcase.fetchProjectsFailed'))
  }
}

onMounted(() => {
  fetchProjects()
  fetchTestCases()
})
</script>

<style lang="scss" scoped>
.page-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 20px;
  box-sizing: border-box;
  overflow: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.card-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.filter-bar {
  padding: 20px;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}

.table-container {
  flex: 1;
  overflow: hidden;
  padding: 0 20px;
  
  :deep(.el-table) {
    height: 100% !important;
  }
  
  :deep(.el-table__body-wrapper) {
    overflow-y: auto !important;
  }
}

.pagination-container {
  padding: 20px;
  border-top: 1px solid #ebeef5;
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}

.import-alert {
  margin-bottom: 20px;
}

.import-upload {
  width: 100%;

  :deep(.el-upload),
  :deep(.el-upload-dragger) {
    width: 100%;
  }
}

.batch-edit-form {
  margin-top: 16px;
}

.priority-tag {
  &.low { color: #67c23a; }
  &.medium { color: #e6a23c; }
  &.high { color: #f56c6c; }
  &.critical { color: #f56c6c; font-weight: bold; }
}

.version-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  
  .version-tag {
    margin: 0;
  }
}

.no-version {
  color: #909399;
  font-size: 12px;
  font-style: italic;
}

.text-muted {
  color: #c0c4cc;
}

.rich-cell {
  line-height: 1.6;
  word-break: break-word;
  white-space: normal;
  display: block;
}

:deep(.el-table__body-wrapper .cell) {
  word-break: break-word;
}

@media (max-width: 1200px) {
  .page-container {
    height: auto;
    min-height: 100vh;
    overflow-y: auto;
  }
  
  .card-container {
    min-height: 600px;
  }
  
  .table-container {
    min-height: 400px;
  }
}

@media (max-width: 768px) {
  .page-container {
    padding: 10px;
  }
  
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }
  
  .header-actions {
    width: 100%;
  }
  
  .filter-bar {
    padding: 15px;
  }
  
  .pagination-container {
    padding: 15px;
  }
}

.step-content {
  min-height: 200px;
}

.preview-info {
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 4px;

  p {
    margin: 5px 0;
  }
}
</style>
