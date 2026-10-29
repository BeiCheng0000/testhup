<template>
  <div class="ai-case-center">
    <!-- 头部 -->
    <div class="page-header">
      <h2>{{ $t('apiTesting.aiCases.title') }}</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><MagicStick /></el-icon>
        {{ $t('apiTesting.aiCases.newTask') }}
      </el-button>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <el-select
        v-model="filters.project"
        :placeholder="$t('apiTesting.aiCases.project')"
        clearable
        filterable
        style="width: 200px"
        @change="loadTasks"
      >
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>

      <el-select
        v-model="filters.status"
        :placeholder="$t('apiTesting.aiCases.status')"
        clearable
        style="width: 160px"
        @change="loadTasks"
      >
        <el-option label="待生成" value="pending" />
        <el-option label="生成中" value="running" />
        <el-option label="生成完成" value="success" />
        <el-option label="部分完成" value="partial" />
        <el-option label="生成失败" value="failed" />
      </el-select>

      <el-input
        v-model="filters.search"
        :placeholder="$t('apiTesting.aiCases.searchPlaceholder')"
        clearable
        style="width: 240px"
        @clear="loadTasks"
        @keyup.enter="loadTasks"
      />

      <el-button @click="loadTasks">
        <el-icon><Refresh /></el-icon>
        {{ $t('apiTesting.common.refresh') }}
      </el-button>
    </div>

    <!-- 任务列表 -->
    <el-table v-loading="loading" :data="tasks" style="width: 100%">
      <el-table-column prop="name" :label="$t('apiTesting.aiCases.taskName')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="project_name" :label="$t('apiTesting.aiCases.project')" min-width="140" show-overflow-tooltip />
      <el-table-column :label="$t('apiTesting.aiCases.status')" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small" effect="dark">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('apiTesting.aiCases.progress')" width="160">
        <template #default="{ row }">
          <el-progress :percentage="row.progress || 0" :stroke-width="10" />
        </template>
      </el-table-column>
      <el-table-column :label="$t('apiTesting.aiCases.sourceInterfaces')" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.source_type === 'interfaces'" size="small" type="info">
            {{ row.source_request_count || 0 }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('apiTesting.aiCases.environment')" width="130" show-overflow-tooltip>
        <template #default="{ row }">{{ row.environment_name || '-' }}</template>
      </el-table-column>
      <el-table-column :label="$t('apiTesting.aiCases.probe')" width="100">
        <template #default="{ row }">
          <el-button
            v-if="row.probe_results && row.probe_results.length"
            link
            type="primary"
            size="small"
            @click="showProbes(row)"
          >
            {{ row.probe_summary.ok }}/{{ row.probe_summary.total }}
          </el-button>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="total_generated" :label="$t('apiTesting.aiCases.generated')" width="90" />
      <el-table-column prop="approved_count" :label="$t('apiTesting.aiCases.approved')" width="90" />
      <el-table-column prop="adopted_count" :label="$t('apiTesting.aiCases.adopted')" width="90" />
      <el-table-column prop="created_by_name" :label="$t('apiTesting.aiCases.creator')" width="110" />
      <el-table-column :label="$t('apiTesting.aiCases.createdAt')" min-width="170">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column :label="$t('apiTesting.aiCases.operation')" width="300" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openDrafts(row)">
            {{ $t('apiTesting.aiCases.viewDrafts') }}
          </el-button>
          <el-button type="success" link size="small" @click="aiReview(row)">
            {{ $t('apiTesting.aiCases.aiReview') }}
          </el-button>
          <el-button type="warning" link size="small" @click="regenerate(row)">
            {{ $t('apiTesting.aiCases.regenerate') }}
          </el-button>
          <el-button type="danger" link size="small" @click="removeTask(row)">
            {{ $t('apiTesting.aiCases.delete') }}
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty :description="$t('apiTesting.aiCases.noDrafts')" />
      </template>
    </el-table>

    <div class="pagination-container">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :page-sizes="[10, 20, 50]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadTasks"
        @current-change="loadTasks"
      />
    </div>

    <!-- 草稿抽屉 -->
    <el-drawer
      v-model="draftDrawer"
      :title="`${$t('apiTesting.aiCases.draftList')} - ${currentTask?.name || ''}`"
      size="78%"
      :destroy-on-close="true"
    >
      <div class="draft-toolbar">
        <el-button type="success" size="small" @click="bulkApprove">
          {{ $t('apiTesting.aiCases.bulkApprove') }}
        </el-button>
        <el-input
          v-model="suiteName"
          :placeholder="$t('apiTesting.aiCases.suiteName')"
          size="small"
          clearable
          style="width: 240px"
        />
        <el-button type="primary" size="small" @click="adoptAll">
          {{ $t('apiTesting.aiCases.adoptAll') }}
        </el-button>
        <el-button type="warning" size="small" @click="executeSuite">
          {{ $t('apiTesting.aiCases.execute') }}
        </el-button>
        <el-button size="small" @click="loadDrafts">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>

      <el-table v-loading="draftLoading" :data="drafts" style="width: 100%" size="small">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="draft-detail">
              <p><strong>{{ $t('apiTesting.aiCases.rationale') }}：</strong>{{ row.ai_rationale || '-' }}</p>
              <p><strong>{{ $t('apiTesting.aiCases.expectedResult') }}：</strong>{{ row.expected_result || '-' }}</p>
              <p v-if="row.self_check_result && row.self_check_result.verdict">
                <strong>{{ $t('apiTesting.aiCases.selfCheck') }}：</strong>
                {{ selfCheckLabel(row.self_check_result.verdict) }}
                <span v-if="row.self_check_result.status_code != null">
                  ｜{{ $t('apiTesting.aiCases.statusCode') }} {{ row.self_check_result.status_code }}
                </span>
                <span v-if="row.self_check_result.response_time != null">
                  ｜{{ row.self_check_result.response_time }} ms
                </span>
                <span v-if="row.self_check_result.error" class="probe-error">
                  ｜{{ row.self_check_result.error }}
                </span>
              </p>
              <div
                v-if="row.self_check_result && row.self_check_result.fixes && row.self_check_result.fixes.length"
                class="fix-list"
              >
                <div class="fix-list-title">{{ $t('apiTesting.aiCases.autoFixes') }}</div>
                <div v-for="(f, i) in row.self_check_result.fixes" :key="i" class="fix-item">- {{ f }}</div>
              </div>
              <div
                v-if="row.self_check_result && row.self_check_result.unresolved && row.self_check_result.unresolved.length"
                class="fix-list"
              >
                <div class="fix-list-title">{{ $t('apiTesting.aiCases.pendingConfirm') }}</div>
                <div v-for="(f, i) in row.self_check_result.unresolved" :key="i" class="fix-item">- {{ f }}</div>
              </div>
              <p><strong>{{ $t('apiTesting.aiCases.comment') }}：</strong>{{ row.review_comment || '-' }}</p>
              <pre class="draft-json">{{ prettyJson(row) }}</pre>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" :label="$t('apiTesting.aiCases.taskName')" min-width="180" show-overflow-tooltip />
        <el-table-column prop="method" :label="$t('apiTesting.aiCases.method')" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="methodType(row.method)">{{ row.method }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.sourceInterfaces')" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.source_request_name">
              <el-tag size="small" type="info" class="source-req-tag">{{ row.source_request_method }}</el-tag>
              {{ row.source_request_name }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="url" :label="$t('apiTesting.aiCases.url')" min-width="220" show-overflow-tooltip />
        <el-table-column prop="priority" :label="$t('apiTesting.aiCases.priority')" width="80" />
        <el-table-column :label="$t('apiTesting.aiCases.status')" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="draftStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.selfCheck')" width="150">
          <template #default="{ row }">
            <template v-if="row.self_check_result && row.self_check_result.verdict">
              <el-tag size="small" :type="selfCheckType(row.self_check_result.verdict)">
                {{ selfCheckLabel(row.self_check_result.verdict) }}
              </el-tag>
              <span
                v-if="row.self_check_result.fixes && row.self_check_result.fixes.length"
                class="fix-count"
              >{{ row.self_check_result.fixes.length }}{{ $t('apiTesting.aiCases.fixCount') }}</span>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.operation')" width="320" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEdit(row)">
              {{ $t('apiTesting.aiCases.edit') }}
            </el-button>
            <el-button type="success" link size="small" @click="reviewDraft(row, 'approve')">
              {{ $t('apiTesting.aiCases.approve') }}
            </el-button>
            <el-button type="warning" link size="small" @click="reviewDraft(row, 'request_revision')">
              {{ $t('apiTesting.aiCases.requestRevision') }}
            </el-button>
            <el-button type="danger" link size="small" @click="reviewDraft(row, 'reject')">
              {{ $t('apiTesting.aiCases.reject') }}
            </el-button>
            <el-button link size="small" :disabled="row.status !== 'approved'" @click="adoptDraft(row)">
              {{ $t('apiTesting.aiCases.adopt') }}
            </el-button>
            <el-button type="primary" link size="small" @click="runCase(row)">
              {{ $t('apiTesting.aiCases.runCase') }}
            </el-button>
            <el-button link size="small" @click="showReviews(row)">
              {{ $t('apiTesting.aiCases.reviews') }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="$t('apiTesting.aiCases.noDrafts')" />
        </template>
      </el-table>
    </el-drawer>

    <!-- 新建任务 -->
    <el-dialog v-model="createVisible" :title="$t('apiTesting.aiCases.newTask')" width="640px">
      <el-form :model="createForm" label-width="120px">
        <el-form-item :label="$t('apiTesting.aiCases.taskName')" required>
          <el-input v-model="createForm.name" :placeholder="$t('apiTesting.aiCases.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.aiCases.project')" required>
          <el-select v-model="createForm.project" filterable style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.aiCases.sourceType')">
          <el-select v-model="createForm.source_type" style="width: 100%">
            <el-option :label="$t('apiTesting.aiCases.fromInterfaces')" value="interfaces" />
            <el-option label="文本描述" value="text" />
            <el-option label="API文档" value="api_doc" />
            <el-option label="需求描述" value="requirement" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.aiCases.environment')">
          <el-select
            v-model="createForm.environment"
            clearable
            :placeholder="$t('apiTesting.aiCases.selectEnvironment')"
            :no-data-text="$t('apiTesting.aiCases.noEnvironment')"
            style="width: 100%"
          >
            <el-option
              v-for="item in environments"
              :key="item.id"
              :label="`${item.name}${item.is_active ? ' （默认）' : ''}`"
              :value="item.id"
            />
          </el-select>
          <div class="form-tip">用例中的 host、token 等将从该环境变量取值，URL 保持相对路径</div>
        </el-form-item>
        <el-form-item v-if="createForm.source_type === 'interfaces'" :label="$t('apiTesting.aiCases.probeEnabled')">
          <el-switch v-model="createForm.probe_enabled" />
          <div class="form-tip">{{ $t('apiTesting.aiCases.probeEnabledTip') }}</div>
        </el-form-item>
        <el-form-item
          v-if="createForm.source_type === 'interfaces'"
          :label="$t('apiTesting.aiCases.selectInterfaces')"
          required
        >
          <el-select
            v-model="createForm.source_requests"
            multiple
            filterable
            remote
            :remote-method="searchInterfaces"
            :loading="interfaceLoading"
            :placeholder="$t('apiTesting.aiCases.selectInterfacesPlaceholder')"
            no-data-text="暂无接口"
            style="width: 100%"
          >
            <el-option
              v-for="item in interfaceOptions"
              :key="item.id"
              :label="`[${item.method}] ${item.name} — ${item.url}`"
              :value="item.id"
            />
          </el-select>
          <div class="form-tip">{{ $t('apiTesting.aiCases.interfacesSelected', { n: createForm.source_requests.length }) }}</div>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.aiCases.focus')">
          <el-input v-model="createForm.focus" :placeholder="$t('apiTesting.aiCases.focusPlaceholder')" />
        </el-form-item>
        <el-form-item v-if="createForm.source_type !== 'interfaces'" :label="$t('apiTesting.aiCases.sourceContent')" required>
          <el-input
            v-model="createForm.source_content"
            type="textarea"
            :rows="8"
            :placeholder="$t('apiTesting.aiCases.sourceContentPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">{{ $t('apiTesting.common.cancel') }}</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">
          {{ $t('apiTesting.common.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑草稿（人工修改） -->
    <el-dialog v-model="editVisible" :title="$t('apiTesting.aiCases.edit')" width="720px">
      <el-form v-if="editForm" :model="editForm" label-width="110px">
        <el-form-item :label="$t('apiTesting.aiCases.taskName')" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.aiCases.method')">
          <el-select v-model="editForm.method" style="width: 160px">
            <el-option v-for="m in methods" :key="m" :label="m" :value="m" />
          </el-select>
          <el-select v-model="editForm.priority" style="width: 120px; margin-left: 12px">
            <el-option v-for="p in priorities" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.aiCases.url')">
          <el-input v-model="editForm.url" />
        </el-form-item>
        <el-form-item label="Headers (JSON)">
          <el-input v-model="editForm.headersText" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="Params (JSON)">
          <el-input v-model="editForm.paramsText" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="Body (JSON)">
          <el-input v-model="editForm.bodyText" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="Assertions (JSON)">
          <el-input v-model="editForm.assertionsText" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.aiCases.expectedResult')">
          <el-input v-model="editForm.expected_result" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.common.description')">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">{{ $t('apiTesting.common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">
          {{ $t('apiTesting.common.save') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 审核记录 -->
    <el-dialog v-model="reviewVisible" :title="$t('apiTesting.aiCases.reviews')" width="560px">
      <el-timeline v-if="reviewList.length">
        <el-timeline-item
          v-for="item in reviewList"
          :key="item.id"
          :timestamp="formatDate(item.created_at)"
          :type="reviewItemType(item.action)"
        >
          <div class="review-item">
            <strong>{{ item.reviewer_name || '-' }}</strong>
            <el-tag size="small" class="review-action">{{ item.action_display }}</el-tag>
          </div>
          <div class="review-comment">{{ item.comment || '-' }}</div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else :description="$t('apiTesting.aiCases.noDrafts')" />
    </el-dialog>

    <!-- 试运行结果 -->
    <el-dialog v-model="runResultVisible" :title="$t('apiTesting.aiCases.runResult')" width="660px">
      <div v-if="runResult" class="run-result">
        <div class="run-result-head">
          <el-tag :type="runResult.success ? 'success' : 'danger'" effect="dark">
            {{ runResult.success ? $t('apiTesting.aiCases.runSuccess') : $t('apiTesting.aiCases.runFailed') }}
          </el-tag>
          <span class="run-result-name">{{ runResult.draftName }}</span>
        </div>

        <div class="run-result-metrics">
          <div class="run-metric">
            <span class="run-metric-label">{{ $t('apiTesting.aiCases.statusCode') }}</span>
            <span class="run-metric-value">{{ runResult.status_code ?? '-' }}</span>
          </div>
          <div class="run-metric">
            <span class="run-metric-label">{{ $t('apiTesting.aiCases.responseTime') }}</span>
            <span class="run-metric-value">
              {{ runResult.response_time != null ? Math.round(runResult.response_time) : '-' }}
            </span>
          </div>
        </div>

        <div v-if="runResult.error" class="run-error">{{ runResult.error }}</div>

        <div class="run-section-title">{{ $t('apiTesting.aiCases.assertionResults') }}</div>
        <el-table :data="runResult.assertions_results || []" size="small" max-height="260">
          <el-table-column prop="name" :label="$t('apiTesting.aiCases.assertionResults')" min-width="150" show-overflow-tooltip />
          <el-table-column prop="type" label="Type" width="130" />
          <el-table-column label="Expected" width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ row.expected }}</template>
          </el-table-column>
          <el-table-column label="Actual" width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.actual }}</template>
          </el-table-column>
          <el-table-column label="Result" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.passed ? 'success' : 'danger'">
                {{ row.passed ? 'PASS' : 'FAIL' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <!-- 接口预跑结果 -->
    <el-dialog v-model="probeVisible" :title="$t('apiTesting.aiCases.probeResult')" width="900px">
      <el-table :data="probeList" size="small" max-height="440">
        <el-table-column prop="name" :label="$t('apiTesting.aiCases.taskName')" min-width="170" show-overflow-tooltip />
        <el-table-column prop="method" label="Method" width="85" />
        <el-table-column label="Status" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.ok && row.status_code >= 200 && row.status_code < 300 ? 'success' : 'danger'"
            >
              {{ row.status_code ?? '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Time(ms)" width="95">
          <template #default="{ row }">{{ row.response_time ?? '-' }}</template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.probeResponse')" min-width="360">
          <template #default="{ row }">
            <span v-if="row.error" class="probe-error">{{ row.error }}</span>
            <code v-else class="probe-preview">
              {{ row.json_preview ? JSON.stringify(row.json_preview) : (row.body_preview || '-') }}
            </code>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { MagicStick, Refresh } from '@element-plus/icons-vue'

const { t } = useI18n()

const BASE = '/api/api-testing/'

const loading = ref(false)
const creating = ref(false)
const saving = ref(false)
const draftLoading = ref(false)
const tasks = ref([])
const drafts = ref([])
const projects = ref([])
const reviewList = ref([])
const interfaceOptions = ref([])
const interfaceLoading = ref(false)
const environments = ref([])
const runResult = ref(null)
const runResultVisible = ref(false)
const probeVisible = ref(false)
const probeList = ref([])

const createVisible = ref(false)
const editVisible = ref(false)
const reviewVisible = ref(false)
const draftDrawer = ref(false)

const currentTask = ref(null)
const editForm = ref(null)
const suiteName = ref('')

const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
const priorities = ['P0', 'P1', 'P2', 'P3']

const filters = reactive({ project: null, status: '', search: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const createForm = reactive({
  name: '',
  project: null,
  source_type: 'interfaces',
  source_requests: [],
  environment: null,
  probe_enabled: true,
  source_content: '',
  focus: ''
})

let pollTimer = null

const formatDate = (val) => {
  if (!val) return '-'
  return new Date(val).toLocaleString('zh-CN')
}

const statusLabel = (s) => (
  { pending: '待生成', running: '生成中', success: '生成完成', partial: '部分完成', failed: '生成失败' }[s] || s
)
const statusType = (s) => (
  { pending: 'info', running: 'warning', success: 'success', partial: 'warning', failed: 'danger' }[s] || 'info'
)
const draftStatusType = (s) => (
  { draft: 'info', pending_review: 'warning', approved: 'success', rejected: 'danger', needs_revision: 'warning' }[s] || 'info'
)
const methodType = (m) => (
  { GET: 'success', POST: 'primary', PUT: 'warning', PATCH: 'warning', DELETE: 'danger' }[m] || 'info'
)
const selfCheckLabel = (v) => ({
  passed: t('apiTesting.aiCases.selfCheckPassed'),
  fixed: t('apiTesting.aiCases.selfCheckFixed'),
  fixed_partial: t('apiTesting.aiCases.selfCheckPartial'),
  needs_revision: t('apiTesting.aiCases.selfCheckNeedsRevision'),
  error: t('apiTesting.aiCases.selfCheckError')
}[v] || v)
const selfCheckType = (v) => ({
  passed: 'success', fixed: 'warning', fixed_partial: 'warning',
  needs_revision: 'danger', error: 'danger'
}[v] || 'info')
const reviewItemType = (a) => (
  { approve: 'success', reject: 'danger', request_revision: 'warning', ai_review: 'primary' }[a] || 'info'
)

const prettyJson = (row) => JSON.stringify(
  { headers: row.headers, params: row.params, body: row.body, assertions: row.assertions }, null, 2
)

const loadProjects = async () => {
  try {
    const { data } = await axios.get(`${BASE}projects/`, { params: { page_size: 200 } })
    projects.value = data.results || data || []
  } catch (e) {
    console.error('加载项目失败', e)
  }
}

// 加载「接口管理」中当前项目下可选接口
const loadInterfaces = async (search = '') => {
  if (!createForm.project) {
    interfaceOptions.value = []
    return
  }
  interfaceLoading.value = true
  try {
    const { data } = await axios.get(`${BASE}ai-case-tasks/available-requests/`, {
      params: { project: createForm.project, search: search || undefined }
    })
    interfaceOptions.value = data || []
  } catch (e) {
    ElMessage.error(t('apiTesting.aiCases.loadInterfacesFailed'))
  } finally {
    interfaceLoading.value = false
  }
}

const searchInterfaces = (keyword) => loadInterfaces(keyword)

// 加载当前项目的环境（用例中的 host/token 等由环境变量提供）
const loadEnvironments = async () => {
  if (!createForm.project) {
    environments.value = []
    return
  }
  try {
    const { data } = await axios.get(`${BASE}environments/`, {
      params: { project: createForm.project, page_size: 200 }
    })
    const list = data.results || data || []
    environments.value = list.filter((e) => !e.project || e.project === createForm.project)
    if (!createForm.environment) {
      const active = environments.value.find((e) => e.is_active)
      if (active) createForm.environment = active.id
    }
  } catch (e) {
    console.error('加载环境失败', e)
  }
}

const loadTasks = async () => {
  loading.value = true
  try {
    const params = { page: pagination.page, page_size: pagination.pageSize }
    if (filters.project) params.project = filters.project
    if (filters.status) params.status = filters.status
    if (filters.search) params.search = filters.search
    const { data } = await axios.get(`${BASE}ai-case-tasks/`, { params })
    tasks.value = data.results || []
    pagination.total = data.count || 0
  } catch (e) {
    ElMessage.error('加载生成任务失败')
    console.error(e)
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  Object.assign(createForm, {
    name: '', project: filters.project || null, source_type: 'interfaces',
    source_requests: [], environment: null, probe_enabled: true,
    source_content: '', focus: ''
  })
  createVisible.value = true
  loadEnvironments()
  loadInterfaces()
}

const showProbes = (row) => {
  probeList.value = row.probe_results || []
  probeVisible.value = true
}

const submitCreate = async () => {
  const interfaceMode = createForm.source_type === 'interfaces'
  if (!createForm.name || !createForm.project) {
    ElMessage.warning('请填写任务名称与所属项目')
    return
  }
  if (interfaceMode && !createForm.source_requests.length) {
    ElMessage.warning('请从接口管理中勾选至少一个接口')
    return
  }
  if (!interfaceMode && !createForm.source_content) {
    ElMessage.warning('请填写接口/需求内容')
    return
  }

  const payload = { ...createForm }
  if (!interfaceMode) payload.source_requests = []

  creating.value = true
  try {
    await axios.post(`${BASE}ai-case-tasks/`, payload)
    ElMessage.success(t('apiTesting.aiCases.createSuccess'))
    createVisible.value = false
    await loadTasks()
    startPolling()
  } catch (e) {
    ElMessage.error(e?.response?.data ? JSON.stringify(e.response.data) : '创建失败')
  } finally {
    creating.value = false
  }
}

// 切换项目时刷新可选接口与环境
watch(() => createForm.project, () => {
  createForm.source_requests = []
  createForm.environment = null
  if (createVisible.value) {
    loadInterfaces()
    loadEnvironments()
  }
})

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(async () => {
    await loadTasks()
    const running = tasks.value.some((x) => x.status === 'pending' || x.status === 'running')
    if (!running) stopPolling()
  }, 3000)
}
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const openDrafts = async (task) => {
  currentTask.value = task
  draftDrawer.value = true
  suiteName.value = ''
  await loadDrafts()
}

const loadDrafts = async () => {
  if (!currentTask.value) return
  draftLoading.value = true
  try {
    const { data } = await axios.get(`${BASE}ai-case-tasks/${currentTask.value.id}/drafts/`, {
      params: { page_size: 200 }
    })
    drafts.value = data.results || data || []
  } catch (e) {
    ElMessage.error('加载草稿失败')
  } finally {
    draftLoading.value = false
  }
}

const aiReview = async (task) => {
  try {
    await axios.post(`${BASE}ai-case-tasks/${task.id}/ai-review/`, {
      auto_fix: true,
      fix_values: false,
      approve_on_pass: false
    })
    ElMessage.success(t('apiTesting.aiCases.aiReviewStarted'))
    startPolling()
  } catch (e) {
    ElMessage.error('启动 AI 审核失败')
  }
}

const regenerate = async (task) => {
  try {
    await ElMessageBox.confirm('将清空该任务下已有草稿并重新生成，确认继续？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await axios.post(`${BASE}ai-case-tasks/${task.id}/regenerate/`)
    ElMessage.success('重新生成已启动')
    startPolling()
  } catch (e) {
    ElMessage.error('重新生成失败')
  }
}

const removeTask = async (task) => {
  try {
    await ElMessageBox.confirm(t('apiTesting.aiCases.confirmDelete'), '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await axios.delete(`${BASE}ai-case-tasks/${task.id}/`)
    ElMessage.success('删除成功')
    await loadTasks()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

const bulkApprove = async () => {
  if (!currentTask.value) return
  try {
    const { data } = await axios.post(`${BASE}ai-case-tasks/${currentTask.value.id}/bulk-review/`, {
      action: 'approve'
    })
    ElMessage.success(data.message || t('apiTesting.aiCases.reviewSuccess'))
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error('批量审核失败')
  }
}

const adoptAll = async () => {
  if (!currentTask.value) return
  try {
    const { data } = await axios.post(`${BASE}ai-case-tasks/${currentTask.value.id}/adopt-all/`, {
      suite_name: suiteName.value || undefined
    })
    ElMessage.success(data.message || t('apiTesting.aiCases.adoptSuccess'))
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '批量采纳失败')
  }
}

const executeSuite = async () => {
  if (!currentTask.value) return
  try {
    const { data } = await axios.post(`${BASE}ai-case-tasks/${currentTask.value.id}/execute/`)
    ElMessage.success(t('apiTesting.aiCases.executeStarted'))
    console.log('execution:', data)
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || t('apiTesting.aiCases.executeTip'))
  }
}

const openEdit = (row) => {
  editForm.value = {
    id: row.id,
    name: row.name,
    method: row.method,
    url: row.url,
    priority: row.priority,
    headersText: JSON.stringify(row.headers || {}, null, 2),
    paramsText: JSON.stringify(row.params || {}, null, 2),
    bodyText: JSON.stringify(row.body || {}, null, 2),
    assertionsText: JSON.stringify(row.assertions || [], null, 2),
    expected_result: row.expected_result || '',
    description: row.description || ''
  }
  editVisible.value = true
}

const parseJson = (text, fallback) => {
  try {
    return JSON.parse(text)
  } catch {
    return fallback
  }
}

const submitEdit = async () => {
  saving.value = true
  try {
    await axios.patch(`${BASE}ai-case-drafts/${editForm.value.id}/`, {
      name: editForm.value.name,
      method: editForm.value.method,
      url: editForm.value.url,
      priority: editForm.value.priority,
      headers: parseJson(editForm.value.headersText, {}),
      params: parseJson(editForm.value.paramsText, {}),
      body: parseJson(editForm.value.bodyText, {}),
      assertions: parseJson(editForm.value.assertionsText, []),
      expected_result: editForm.value.expected_result,
      description: editForm.value.description
    })
    ElMessage.success('保存成功')
    editVisible.value = false
    await loadDrafts()
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const reviewDraft = async (row, action) => {
  try {
    const { promptValue } = await ElMessageBox.prompt(
      t('apiTesting.aiCases.commentPlaceholder'),
      t('apiTesting.aiCases.reviews'),
      { inputPlaceholder: t('apiTesting.aiCases.commentPlaceholder'), inputValue: '' }
    ).catch(() => ({ promptValue: null }))
    if (promptValue === null) return
    await axios.post(`${BASE}ai-case-drafts/${row.id}/review/`, {
      action, comment: promptValue || ''
    })
    ElMessage.success(t('apiTesting.aiCases.reviewSuccess'))
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    if (e?.response) ElMessage.error('审核失败')
  }
}

const adoptDraft = async (row) => {
  try {
    const { data } = await axios.post(`${BASE}ai-case-drafts/${row.id}/adopt/`)
    ElMessage.success(data.message || t('apiTesting.aiCases.adoptSuccess'))
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || t('apiTesting.aiCases.adoptTip'))
  }
}

const runCase = async (row) => {
  try {
    const { data } = await axios.post(`${BASE}ai-case-drafts/${row.id}/run/`, {})
    runResult.value = { ...data, draftName: row.name }
    runResultVisible.value = true
    if (data.success) {
      ElMessage.success(t('apiTesting.aiCases.runSuccess'))
    } else {
      ElMessage.warning(t('apiTesting.aiCases.runFailed'))
    }
    await loadDrafts()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || t('apiTesting.aiCases.runFailed'))
  }
}

const showReviews = async (row) => {
  try {
    const { data } = await axios.get(`${BASE}ai-case-drafts/${row.id}/reviews/`)
    reviewList.value = data || []
    reviewVisible.value = true
  } catch (e) {
    ElMessage.error('加载审核记录失败')
  }
}

onMounted(async () => {
  await loadProjects()
  await loadTasks()
})

onUnmounted(() => stopPolling())
</script>

<style scoped>
.ai-case-center {
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.pagination-container {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.draft-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.draft-detail {
  padding: 8px 16px;
  font-size: 13px;
  color: #4b5563;
}

.draft-detail p {
  margin: 4px 0;
}

.draft-json {
  background: #f7f8fa;
  border: 1px solid #eef0f3;
  border-radius: 8px;
  padding: 12px;
  margin: 8px 0 0;
  max-height: 240px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
}

.review-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.review-comment {
  margin-top: 4px;
  color: #606266;
  font-size: 13px;
  white-space: pre-wrap;
}

.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.source-req-tag {
  margin-right: 6px;
}

.run-result-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.run-result-name {
  font-weight: 600;
  color: #303133;
}

.run-result-metrics {
  display: flex;
  gap: 28px;
  background: #f7f8fa;
  border: 1px solid #eef0f3;
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 12px;
}

.run-metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.run-metric-label {
  font-size: 12px;
  color: #909399;
}

.run-metric-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.run-error {
  background: #fff6f6;
  border: 1px solid #fbc4c4;
  border-radius: 10px;
  padding: 10px 14px;
  color: #c0392b;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  margin-bottom: 12px;
}

.run-section-title {
  font-size: 14px;
  font-weight: 700;
  color: #303133;
  margin: 8px 0 10px;
  padding-left: 10px;
  border-left: 3px solid #5046e5;
}

.probe-preview {
  display: block;
  font-size: 12px;
  color: #606266;
  word-break: break-all;
  max-height: 60px;
  overflow: auto;
}

.probe-error {
  color: #c0392b;
  font-size: 12px;
  word-break: break-all;
}

.fix-count {
  margin-left: 6px;
  font-size: 12px;
  color: #e6a23c;
}

.fix-list {
  margin: 6px 0 10px;
  padding: 8px 12px;
  background: #fdf9f1;
  border: 1px solid #f3e2c2;
  border-radius: 8px;
}

.fix-list-title {
  font-size: 12px;
  font-weight: 700;
  color: #b88230;
  margin-bottom: 4px;
}

.fix-item {
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
  word-break: break-all;
}
</style>
