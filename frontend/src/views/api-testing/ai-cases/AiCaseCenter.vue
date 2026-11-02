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
      <el-table-column :label="$t('apiTesting.aiCases.operation')" width="260" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openDrafts(row)">
            {{ $t('apiTesting.aiCases.viewDrafts') }}
          </el-button>
          <el-button
            type="warning"
            link
            size="small"
            :disabled="row.ai_review_running"
            @click="regenerate(row)"
          >
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
      size="80%"
      class="draft-drawer"
      :destroy-on-close="true"
    >
      <!-- 统计概览 -->
      <div class="draft-stats">
        <div class="stat-card">
          <span class="stat-num">{{ draftPagination.total }}</span>
          <span class="stat-label">{{ $t('apiTesting.aiCases.statTotal') }}</span>
        </div>
        <div class="stat-card stat-card--ok">
          <span class="stat-num">{{ currentTask?.approved_count ?? 0 }}</span>
          <span class="stat-label">{{ $t('apiTesting.aiCases.statApproved') }}</span>
        </div>
        <div class="stat-card stat-card--done">
          <span class="stat-num">{{ currentTask?.adopted_count ?? 0 }}</span>
          <span class="stat-label">{{ $t('apiTesting.aiCases.statAdopted') }}</span>
        </div>
        <div class="stat-card stat-card--sel" :class="{ 'is-active': hasDraftSelection }">
          <span class="stat-num">{{ selectedDraftIds.size }}</span>
          <span class="stat-label">{{ $t('apiTesting.aiCases.statSelected') }}</span>
        </div>
      </div>

      <!-- 筛选栏 -->
      <div class="draft-filter-bar">
        <el-select
          v-model="draftSourceFilter"
          size="small"
          clearable
          class="filter-sel"
          :placeholder="$t('apiTesting.aiCases.filterByInterface')"
          @change="onDraftFilterChange"
        >
          <el-option :label="$t('apiTesting.aiCases.allInterfaces')" value="" />
          <el-option
            v-for="opt in draftSourceOptions"
            :key="opt.id"
            :label="opt.label"
            :value="opt.id"
          />
        </el-select>

        <el-radio-group
          v-model="draftStatusFilter"
          size="small"
          class="status-tabs"
          @change="onDraftFilterChange"
        >
          <el-radio-button value="">{{ $t('apiTesting.aiCases.statusAll') }}</el-radio-button>
          <el-radio-button
            v-for="s in draftStatusOptions"
            :key="s.value"
            :value="s.value"
          >
            {{ s.label }}
          </el-radio-button>
        </el-radio-group>

        <div class="flex-spacer" />

        <el-button type="success" size="small" plain @click="openCreateDraft">
          <el-icon><Plus /></el-icon>
          {{ $t('apiTesting.aiCases.addCase') }}
        </el-button>
        <el-button size="small" @click="loadDrafts">
          <el-icon><Refresh /></el-icon>
        </el-button>
        <el-button
          type="warning"
          size="small"
          :disabled="currentTask?.ai_review_running"
          @click="selfCheck(currentTask)"
        >
          {{ currentTask?.ai_review_running ? $t('apiTesting.aiCases.running') : $t('apiTesting.aiCases.selfCheck') }}
        </el-button>
        <el-button
          type="success"
          size="small"
          :disabled="currentTask?.ai_review_running"
          @click="aiReview(currentTask)"
        >
          {{ currentTask?.ai_review_running ? $t('apiTesting.aiCases.aiReviewing') : $t('apiTesting.aiCases.aiReview') }}
        </el-button>
      </div>

      <!-- 批量操作条：勾选后才可用 -->
      <div class="draft-action-bar" :class="{ 'is-active': hasDraftSelection }">
        <span class="sel-info">
          {{ $t('apiTesting.aiCases.selectedCount') }}
          <b>{{ selectedDraftIds.size }}</b>
          {{ $t('apiTesting.aiCases.selectedUnit') }}
        </span>
        <el-button
          v-if="hasDraftSelection"
          link
          size="small"
          type="info"
          @click="clearDraftSelection"
        >
          {{ $t('apiTesting.aiCases.clearSelection') }}
        </el-button>

        <div class="flex-spacer" />

        <el-button type="success" size="small" :disabled="!hasDraftSelection" @click="bulkApprove">
          {{ $t('apiTesting.aiCases.bulkApprove') }}
        </el-button>
        <el-button type="primary" size="small" :disabled="!hasDraftSelection" @click="adoptAll">
          {{ $t('apiTesting.aiCases.adoptAll') }}
        </el-button>
        <el-button type="warning" size="small" :disabled="!hasDraftSelection" @click="executeSuite">
          {{ $t('apiTesting.aiCases.execute') }}
        </el-button>
      </div>

      <div class="draft-table-wrap">
        <el-table
          ref="draftTableRef"
          v-loading="draftLoading"
          :data="drafts"
          row-key="id"
          size="small"
          height="100%"
          stripe
          @selection-change="onDraftSelectionChange"
        >
        <el-table-column type="selection" width="46" reserve-selection />
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
                v-if="row.self_check_result && row.self_check_result.unresolved && row.self_check_result.unresolved.length"
                class="fix-list"
              >
                <div class="fix-list-title">{{ $t('apiTesting.aiCases.pendingConfirm') }}</div>
                <div v-for="(f, i) in row.self_check_result.unresolved" :key="i" class="fix-item">- {{ f }}</div>
              </div>

              <div v-if="row.latest_ai_review" class="ai-review-block">
                <div class="ai-review-title">
                  <strong>{{ $t('apiTesting.aiCases.aiReviewOpinion') }}：</strong>
                  <el-tag size="small" :type="reviewSuggestionType(row.latest_ai_review.suggestion)">
                    {{ reviewSuggestionLabel(row.latest_ai_review.suggestion) }}
                  </el-tag>
                </div>
                <div class="ai-review-comment">{{ row.latest_ai_review.comment }}</div>
                <el-button
                  v-if="row.latest_ai_review.suggestion && row.latest_ai_review.suggestion !== 'approve'"
                  type="warning"
                  size="small"
                  :disabled="currentTask?.ai_review_running"
                  @click="aiReviseDraft(row)"
                >{{ $t('apiTesting.aiCases.aiRevise') }}</el-button>
              </div>

              <p><strong>{{ $t('apiTesting.aiCases.comment') }}：</strong>{{ row.review_comment || '-' }}</p>
              <pre class="draft-json">{{ prettyJson(row) }}</pre>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.caseName')" min-width="190">
          <template #default="{ row }">
            <div class="draft-name">
              <span class="draft-name-text" :title="row.name">{{ row.name }}</span>
              <el-tooltip
                v-if="row.adopted_request_id"
                :content="`${$t('apiTesting.aiCases.adoptedTag')} #${row.adopted_request_id}`"
                placement="top"
              >
                <span class="draft-adopted-tag">
                  <el-icon><Link /></el-icon>
                  {{ $t('apiTesting.aiCases.adoptedTag') }}
                </span>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="method" :label="$t('apiTesting.aiCases.method')" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="methodType(row.method)">{{ row.method }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.sourceInterfaces')" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.source_request_name">
              <el-tag size="small" type="info" class="source-req-tag">{{ row.source_request_method }}</el-tag>
              {{ row.source_request_name }}
            </span>
            <span v-else class="col-empty">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="url" :label="$t('apiTesting.aiCases.url')" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="draft-url">{{ row.url }}</span>
          </template>
        </el-table-column>
        <!-- 优先级按 P0/P1 配色，便于先挑重点用例 -->
        <el-table-column prop="priority" :label="$t('apiTesting.aiCases.priority')" width="78" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="priorityType(row.priority)">
              {{ row.priority || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- 断言条数：一眼看出这条用例校验得够不够 -->
        <el-table-column :label="$t('apiTesting.aiCases.colAssertions')" width="72" align="center">
          <template #default="{ row }">
            <span v-if="row.assertions && row.assertions.length">{{ row.assertions.length }}</span>
            <span v-else class="col-empty">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.status')" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="draftStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.selfCheck')" width="120">
          <template #default="{ row }">
            <template v-if="row.self_check_result && row.self_check_result.verdict">
              <el-tag size="small" :type="selfCheckType(row.self_check_result.verdict)">
                {{ selfCheckLabel(row.self_check_result.verdict) }}
              </el-tag>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.aiCases.operation')" width="268" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEdit(row)">
              {{ $t('apiTesting.aiCases.edit') }}
            </el-button>
            <el-button type="success" link size="small" @click="reviewDraft(row, 'approve')">
              {{ $t('apiTesting.aiCases.approve') }}
            </el-button>
            <el-tooltip
              :content="$t('apiTesting.aiCases.adoptOnlyApproved')"
              placement="top"
              :disabled="row.status === 'approved'"
            >
              <span>
                <el-button
                  link
                  size="small"
                  :disabled="row.status !== 'approved'"
                  @click="adoptDraft(row)"
                >
                  {{ $t('apiTesting.aiCases.adopt') }}
                </el-button>
              </span>
            </el-tooltip>
            <el-button type="primary" link size="small" @click="runCase(row)">
              {{ $t('apiTesting.aiCases.runCase') }}
            </el-button>
            <el-dropdown trigger="click" @command="(cmd) => onDraftCommand(cmd, row)">
              <el-button link size="small">
                {{ $t('apiTesting.aiCases.more') }}
                <el-icon><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="duplicate">
                    {{ $t('apiTesting.aiCases.duplicate') }}
                  </el-dropdown-item>
                  <el-dropdown-item command="request_revision">
                    {{ $t('apiTesting.aiCases.requestRevision') }}
                  </el-dropdown-item>
                  <el-dropdown-item command="reject">
                    {{ $t('apiTesting.aiCases.reject') }}
                  </el-dropdown-item>
                  <el-dropdown-item command="reviews">
                    {{ $t('apiTesting.aiCases.reviews') }}
                  </el-dropdown-item>

                  <el-dropdown-item command="delete" divided>
                    <span class="danger-text">{{ $t('apiTesting.aiCases.deleteCase') }}</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="$t('apiTesting.aiCases.noDrafts')" />
        </template>
        </el-table>
      </div>

      <div class="draft-pagination">
        <el-pagination
          v-model:current-page="draftPagination.page"
          v-model:page-size="draftPagination.pageSize"
          :page-sizes="[10, 20, 50]"
          :total="draftPagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="onDraftPageSizeChange"
          @current-change="loadDrafts"
        />
      </div>
    </el-drawer>

    <!-- 新建任务 -->
    <el-dialog
      v-model="createVisible"
      width="760px"
      class="create-task-dialog"
      :show-close="false"
      align-center
      destroy-on-close
    >
      <template #header>
        <div class="dlg-head">
          <div class="dlg-head-icon">
            <el-icon><MagicStick /></el-icon>
          </div>
          <div class="dlg-head-text">
            <h3>{{ $t('apiTesting.aiCases.newTask') }}</h3>
            <p>{{ $t('apiTesting.aiCases.createSubtitle') }}</p>
          </div>
          <el-icon class="dlg-head-close" @click="createVisible = false"><Close /></el-icon>
        </div>
      </template>

      <el-form :model="createForm" label-position="top" class="create-form">
        <section class="form-section">
          <div class="section-title">
            <i class="section-dot" />
            {{ $t('apiTesting.aiCases.basicInfo') }}
          </div>
          <div class="grid-2">
            <el-form-item :label="$t('apiTesting.aiCases.taskName')" required>
              <el-input v-model="createForm.name" :placeholder="$t('apiTesting.aiCases.namePlaceholder')" />
            </el-form-item>
            <el-form-item :label="$t('apiTesting.aiCases.project')" required>
              <el-select v-model="createForm.project" filterable style="width: 100%">
                <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
          </div>
        </section>

        <section class="form-section">
          <div class="section-title">
            <i class="section-dot" />
            {{ $t('apiTesting.aiCases.sourceAndEnv') }}
          </div>
          <el-form-item :label="$t('apiTesting.aiCases.sourceType')">
            <el-radio-group v-model="createForm.source_type" class="type-group">
              <el-radio-button label="interfaces">{{ $t('apiTesting.aiCases.fromInterfaces') }}</el-radio-button>
              <el-radio-button label="text">文本描述</el-radio-button>
              <el-radio-button label="api_doc">API文档</el-radio-button>
              <el-radio-button label="requirement">需求描述</el-radio-button>
            </el-radio-group>
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
        </section>

        <section v-if="createForm.source_type === 'interfaces'" class="form-section">
          <div class="section-title">
            <i class="section-dot" />
            {{ $t('apiTesting.aiCases.caseScope') }}
          </div>

          <div class="switch-card">
            <div class="switch-card-text">
              <div class="switch-card-title">{{ $t('apiTesting.aiCases.probeEnabled') }}</div>
              <div class="switch-card-desc">{{ $t('apiTesting.aiCases.probeEnabledTip') }}</div>
            </div>
            <el-switch v-model="createForm.probe_enabled" />
          </div>

          <el-form-item :label="$t('apiTesting.aiCases.selectInterfaces')" required>
            <el-select
              v-model="createForm.source_requests"
              multiple
              filterable
              remote
              reserve-keyword
              fit-input-width
              collapse-tags
              collapse-tags-tooltip
              :max-collapse-tags="2"
              :remote-method="searchInterfaces"
              :loading="interfaceLoading"
              :placeholder="$t('apiTesting.aiCases.selectInterfacesPlaceholder')"
              no-data-text="暂无接口"
              popper-class="if-select-popper"
              style="width: 100%"
            >
              <el-option
                v-for="item in interfaceOptions"
                :key="item.id"
                :value="item.id"
                :label="`[${item.method}] ${item.name}`"
              >
                <div class="if-option">
                  <el-tag size="small" :type="methodType(item.method)" effect="plain" class="if-method">
                    {{ item.method }}
                  </el-tag>
                  <span class="if-name" :title="item.name">{{ item.name }}</span>
                  <span class="if-url" :title="cleanUrl(item.url)">{{ cleanUrl(item.url) }}</span>
                </div>
              </el-option>
            </el-select>
            <div class="form-tip">
              {{ $t('apiTesting.aiCases.interfacesSelected', { n: createForm.source_requests.length }) }}
            </div>
          </el-form-item>

          <el-form-item :label="$t('apiTesting.aiCases.focus')">
            <el-input v-model="createForm.focus" :placeholder="$t('apiTesting.aiCases.focusPlaceholder')" />
          </el-form-item>
        </section>

        <section v-else class="form-section">
          <div class="section-title">
            <i class="section-dot" />
            {{ $t('apiTesting.aiCases.caseScope') }}
          </div>
          <el-form-item :label="$t('apiTesting.aiCases.sourceContent')" required>
            <el-input
              v-model="createForm.source_content"
              type="textarea"
              :rows="8"
              :placeholder="$t('apiTesting.aiCases.sourceContentPlaceholder')"
            />
          </el-form-item>
        </section>
      </el-form>

      <template #footer>
        <div class="dlg-footer">
          <span class="dlg-footer-hint">{{ $t('apiTesting.aiCases.footerHint') }}</span>
          <div class="dlg-footer-actions">
            <el-button @click="createVisible = false">{{ $t('apiTesting.common.cancel') }}</el-button>
            <el-button type="primary" :loading="creating" @click="submitCreate">
              <el-icon><MagicStick /></el-icon>
              {{ $t('apiTesting.aiCases.createAndGenerate') }}
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 编辑草稿（人工修改） -->
    <el-dialog
      v-model="editVisible"
      width="900px"
      class="edit-draft-dialog"
      :show-close="false"
      align-center
      destroy-on-close
    >
      <template #header>
        <div class="dlg-head">
          <div
            class="dlg-head-icon"
            :class="isCreateMode ? 'dlg-head-icon--green' : ''"
          >
            <el-icon><Plus v-if="isCreateMode" /><EditPen v-else /></el-icon>
          </div>
          <div class="dlg-head-text">
            <h3>{{ isCreateMode
              ? $t('apiTesting.aiCases.manualAdd')
              : $t('apiTesting.aiCases.edit') }}</h3>
            <p>{{ isCreateMode
              ? $t('apiTesting.aiCases.manualAddSubtitle')
              : $t('apiTesting.aiCases.editSubtitle') }}</p>
          </div>
          <el-icon class="dlg-head-close" @click="editVisible = false"><Close /></el-icon>
        </div>
      </template>

      <div v-if="editForm" class="edit-draft">
        <el-form :model="editForm" label-position="top" class="edit-basic">
          <div class="grid-2">
            <el-form-item :label="$t('apiTesting.aiCases.caseName')" required>
              <el-input v-model="editForm.name" :placeholder="$t('apiTesting.aiCases.caseNamePlaceholder')" />
            </el-form-item>
            <el-form-item :label="$t('apiTesting.aiCases.methodAndPriority')">
              <div class="method-priority">
                <el-select v-model="editForm.method" class="method-sel">
                  <el-option v-for="m in methods" :key="m" :label="m" :value="m" />
                </el-select>
                <el-select v-model="editForm.priority" class="priority-sel">
                  <el-option v-for="p in priorities" :key="p" :label="p" :value="p" />
                </el-select>
              </div>
            </el-form-item>
          </div>
          <div class="grid-2">
            <el-form-item :label="$t('apiTesting.aiCases.url')">
              <el-input v-model="editForm.url" placeholder="/api/v1/users">
                <template #prepend>{{ editForm.method }}</template>
              </el-input>
              <div class="form-tip">{{ $t('apiTesting.aiCases.urlTip') }}</div>
            </el-form-item>
            <el-form-item :label="$t('apiTesting.aiCases.sourceInterface')">
              <el-select
                v-model="editForm.source_request"
                clearable
                class="source-sel"
                :placeholder="$t('apiTesting.aiCases.noSourceInterfaceOption')"
              >
                <el-option
                  v-for="opt in draftSourceOptions"
                  :key="opt.id"
                  :label="opt.label"
                  :value="opt.id"
                />
              </el-select>
              <div class="form-tip">{{ $t('apiTesting.aiCases.sourceInterfaceTip') }}</div>
            </el-form-item>
          </div>
        </el-form>

        <el-tabs v-model="editTab" class="edit-tabs">
          <el-tab-pane name="params">
            <template #label>
              <span class="tab-label">
                {{ $t('apiTesting.aiCases.tabParams') }}
                <span v-if="kvCount(editForm.params)" class="tab-badge">{{ kvCount(editForm.params) }}</span>
              </span>
            </template>
            <p class="tab-tip">{{ $t('apiTesting.aiCases.tipParams') }}</p>
            <div class="kv-editor">
              <div class="kv-head">
                <span></span>
                <span>{{ $t('apiTesting.aiCases.kvKey') }}</span>
                <span>{{ $t('apiTesting.aiCases.kvValue') }}</span>
                <span></span>
              </div>
              <div v-for="(row, i) in editForm.params" :key="'p' + i" class="kv-row">
                <el-checkbox v-model="row.enabled" />
                <el-input v-model="row.key" size="small" :placeholder="$t('apiTesting.aiCases.kvKeyPlaceholder')" />
                <el-input v-model="row.value" size="small" :placeholder="$t('apiTesting.aiCases.kvValuePlaceholder')" />
                <el-button text type="danger" size="small" @click="editForm.params.splice(i, 1)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <el-button text type="primary" size="small" class="kv-add" @click="addKv(editForm.params)">
                <el-icon><Plus /></el-icon>
                {{ $t('apiTesting.aiCases.addRow') }}
              </el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane name="headers">
            <template #label>
              <span class="tab-label">
                {{ $t('apiTesting.aiCases.tabHeaders') }}
                <span v-if="kvCount(editForm.headers)" class="tab-badge">{{ kvCount(editForm.headers) }}</span>
              </span>
            </template>
            <p class="tab-tip">{{ $t('apiTesting.aiCases.tipHeaders') }}</p>
            <div class="kv-editor">
              <div class="kv-head">
                <span></span>
                <span>{{ $t('apiTesting.aiCases.kvHeaderName') }}</span>
                <span>{{ $t('apiTesting.aiCases.kvValue') }}</span>
                <span></span>
              </div>
              <div v-for="(row, i) in editForm.headers" :key="'h' + i" class="kv-row">
                <el-checkbox v-model="row.enabled" />
                <el-input v-model="row.key" size="small" placeholder="Authorization" />
                <el-input v-model="row.value" size="small" placeholder="Bearer {{token}}" />
                <el-button text type="danger" size="small" @click="editForm.headers.splice(i, 1)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <el-button text type="primary" size="small" class="kv-add" @click="addKv(editForm.headers)">
                <el-icon><Plus /></el-icon>
                {{ $t('apiTesting.aiCases.addRow') }}
              </el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane name="body">
            <template #label>
              <span class="tab-label">
                {{ $t('apiTesting.aiCases.tabBody') }}
                <span v-if="editForm.bodyType !== 'none'" class="tab-dot"></span>
              </span>
            </template>
            <p class="tab-tip">{{ $t('apiTesting.aiCases.tipBody') }}</p>
            <el-radio-group v-model="editForm.bodyType" class="body-type-group">
              <el-radio-button label="none">{{ $t('apiTesting.aiCases.bodyNone') }}</el-radio-button>
              <el-radio-button label="json">{{ $t('apiTesting.aiCases.bodyJson') }}</el-radio-button>
              <el-radio-button label="form-data">{{ $t('apiTesting.aiCases.bodyFormData') }}</el-radio-button>
              <el-radio-button label="x-www-form-urlencoded">{{ $t('apiTesting.aiCases.bodyUrlencoded') }}</el-radio-button>
              <el-radio-button label="raw">{{ $t('apiTesting.aiCases.bodyRaw') }}</el-radio-button>
            </el-radio-group>

            <div v-if="editForm.bodyType === 'none'" class="body-empty">
              {{ $t('apiTesting.aiCases.noBodyTip') }}
            </div>

            <div v-else-if="editForm.bodyType === 'json'" class="body-editor">
              <CodeEditor
                v-model="editForm.bodyText"
                language="json"
                placeholder="{&#10;  &quot;key&quot;: &quot;value&quot;&#10;}"
                class="body-code"
              />
              <p class="tab-tip">{{ $t('apiTesting.aiCases.jsonBodyTip') }}</p>
            </div>

            <div v-else-if="editForm.bodyType === 'raw'" class="body-editor">
              <CodeEditor v-model="editForm.bodyText" language="text" class="body-code" />
              <p class="tab-tip">{{ $t('apiTesting.aiCases.rawBodyTip') }}</p>
            </div>

            <div v-else class="kv-editor">
              <div class="kv-head">
                <span></span>
                <span>{{ $t('apiTesting.aiCases.kvKey') }}</span>
                <span>{{ $t('apiTesting.aiCases.kvValue') }}</span>
                <span></span>
              </div>
              <div v-for="(row, i) in editForm.bodyRows" :key="'b' + i" class="kv-row">
                <el-checkbox v-model="row.enabled" />
                <el-input v-model="row.key" size="small" :placeholder="$t('apiTesting.aiCases.kvKeyPlaceholder')" />
                <el-input v-model="row.value" size="small" :placeholder="$t('apiTesting.aiCases.kvValuePlaceholder')" />
                <el-button text type="danger" size="small" @click="editForm.bodyRows.splice(i, 1)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <el-button text type="primary" size="small" class="kv-add" @click="addKv(editForm.bodyRows)">
                <el-icon><Plus /></el-icon>
                {{ $t('apiTesting.aiCases.addRow') }}
              </el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane name="assertions">
            <template #label>
              <span class="tab-label">
                {{ $t('apiTesting.aiCases.tabAssertions') }}
                <span v-if="editForm.assertions.length" class="tab-badge">{{ editForm.assertions.length }}</span>
              </span>
            </template>
            <p class="tab-tip">{{ $t('apiTesting.aiCases.tipAssertions') }}</p>

            <div v-if="!editForm.assertions.length" class="assertion-empty">
              <p>{{ $t('apiTesting.aiCases.noAssertionsTip') }}</p>
              <el-button size="small" type="primary" @click="addEditAssertion">
                <el-icon><Plus /></el-icon>
                {{ $t('apiTesting.interface.addAssertion') }}
              </el-button>
            </div>

            <div v-else class="assertion-table">
              <div class="at-head">
                <span class="at-idx">#</span>
                <span>{{ $t('apiTesting.interface.assertionName') }}</span>
                <span>{{ $t('apiTesting.interface.selectAssertionType') }}</span>
                <span>{{ $t('apiTesting.aiCases.assertionParam') }}</span>
                <span></span>
              </div>
              <div v-for="(a, i) in editForm.assertions" :key="'a' + i" class="at-row">
                <span class="at-idx">{{ i + 1 }}</span>
                <el-input v-model="a.name" size="small" :placeholder="$t('apiTesting.interface.assertionName')" />
                <el-select v-model="a.type" size="small" @change="onEditAssertionTypeChange(a)">
                  <el-option :label="$t('apiTesting.interface.assertionTypes.statusCode')" value="status_code" />
                  <el-option :label="$t('apiTesting.interface.assertionTypes.responseTime')" value="response_time" />
                  <el-option :label="$t('apiTesting.interface.assertionTypes.contains')" value="contains" />
                  <el-option :label="$t('apiTesting.interface.assertionTypes.jsonPath')" value="json_path" />
                  <el-option :label="$t('apiTesting.interface.assertionTypes.header')" value="header" />
                  <el-option :label="$t('apiTesting.interface.assertionTypes.equals')" value="equals" />
                </el-select>
                <div class="at-params">
                  <el-input-number
                    v-if="a.type === 'status_code'"
                    v-model="a.expected"
                    :min="100"
                    :max="599"
                    size="small"
                    controls-position="right"
                    class="at-num"
                  />
                  <el-input-number
                    v-else-if="a.type === 'response_time'"
                    v-model="a.expected"
                    :min="1"
                    size="small"
                    controls-position="right"
                    class="at-num"
                  />
                  <template v-else-if="a.type === 'json_path'">
                    <el-input v-model="a.json_path" size="small" :placeholder="$t('apiTesting.aiCases.jsonPathLabel')" />
                    <el-input v-model="a.expected" size="small" :placeholder="$t('apiTesting.aiCases.expectedOptional')" />
                  </template>
                  <template v-else-if="a.type === 'header'">
                    <el-input v-model="a.header_name" size="small" :placeholder="$t('apiTesting.interface.headerNameLabel')" />
                    <el-input v-model="a.expected_value" size="small" :placeholder="$t('apiTesting.interface.expectedValue')" />
                  </template>
                  <el-input
                    v-else
                    v-model="a.expected"
                    size="small"
                    :placeholder="$t('apiTesting.interface.expectedValue')"
                  />
                </div>
                <el-button text type="danger" size="small" @click="editForm.assertions.splice(i, 1)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <el-button text type="primary" size="small" class="kv-add" @click="addEditAssertion">
                <el-icon><Plus /></el-icon>
                {{ $t('apiTesting.interface.addAssertion') }}
              </el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane name="doc">
            <template #label>
              <span class="tab-label">{{ $t('apiTesting.aiCases.tabDoc') }}</span>
            </template>
            <el-form :model="editForm" label-position="top" class="doc-form">
              <el-form-item :label="$t('apiTesting.aiCases.expectedResult')">
                <el-input
                  v-model="editForm.expected_result"
                  type="textarea"
                  :rows="4"
                  :placeholder="$t('apiTesting.aiCases.expectedResultPlaceholder')"
                />
                <div class="form-tip">{{ $t('apiTesting.aiCases.tipDoc') }}</div>
              </el-form-item>
              <el-form-item :label="$t('apiTesting.common.description')">
                <el-input v-model="editForm.description" type="textarea" :rows="4" />
              </el-form-item>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </div>

      <template #footer>
        <div class="dlg-footer">
          <span class="dlg-footer-hint">{{ $t('apiTesting.aiCases.editFooterHint') }}</span>
          <div class="dlg-footer-actions">
            <el-button @click="editVisible = false">{{ $t('apiTesting.common.cancel') }}</el-button>
            <el-button type="primary" :loading="saving" @click="submitEdit">
              {{ $t('apiTesting.common.save') }}
            </el-button>
          </div>
        </div>
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
    <el-dialog
      v-model="runResultVisible"
      width="880px"
      class="im-dialog"
      :show-close="false"
      align-center
    >
      <template #header>
        <div class="dlg-head">
          <div
            class="dlg-head-icon"
            :class="runResult?.success ? 'dlg-head-icon--green' : 'dlg-head-icon--red'"
          >
            <el-icon><Document /></el-icon>
          </div>
          <div class="dlg-head-text">
            <h3>{{ $t('apiTesting.aiCases.runResult') }}</h3>
            <p>{{ $t('apiTesting.aiCases.runResultSubtitle') }}</p>
          </div>
          <el-icon class="dlg-head-close" @click="runResultVisible = false"><Close /></el-icon>
        </div>
      </template>

      <div v-if="runResult" class="run-result">
        <div class="run-result-head">
          <el-tag :type="runResult.success ? 'success' : 'danger'" effect="dark">
            {{ runResult.success ? $t('apiTesting.aiCases.runSuccess') : $t('apiTesting.aiCases.runFailed') }}
          </el-tag>
          <span class="run-result-name">{{ runResult.draftName }}</span>
        </div>
        <p class="run-hint">{{ $t('apiTesting.aiCases.runNoAdoptTip') }}</p>

        <div class="run-result-metrics">
          <div class="run-metric">
            <span class="run-metric-label">{{ $t('apiTesting.aiCases.statusCode') }}</span>
            <span class="run-metric-value" :class="{ 'is-fail': !runResult.success }">
              {{ runResult.status_code ?? '-' }}
            </span>
          </div>
          <div class="run-metric">
            <span class="run-metric-label">{{ $t('apiTesting.aiCases.responseTime') }}</span>
            <span class="run-metric-value">
              {{ runResult.response_time != null ? Math.round(runResult.response_time) : '-' }}
            </span>
          </div>
          <div class="run-metric">
            <span class="run-metric-label">{{ $t('apiTesting.aiCases.assertionResults') }}</span>
            <span class="run-metric-value">
              {{ passedAssertionCount }} / {{ (runResult.assertions_results || []).length }}
            </span>
          </div>
        </div>

        <div v-if="runResult.error" class="run-error">{{ runResult.error }}</div>

        <div class="run-section-title">{{ $t('apiTesting.aiCases.assertionResults') }}</div>
        <el-table :data="runResult.assertions_results || []" size="small" max-height="240">
          <el-table-column prop="name" :label="$t('apiTesting.aiCases.assertionResults')" min-width="150" show-overflow-tooltip />
          <el-table-column prop="type" :label="$t('apiTesting.aiCases.assertionType')" width="130" />
          <el-table-column :label="$t('apiTesting.aiCases.expectedValue')" width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ row.expected }}</template>
          </el-table-column>
          <el-table-column :label="$t('apiTesting.aiCases.actualValue')" width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.actual }}</template>
          </el-table-column>
          <el-table-column :label="$t('apiTesting.aiCases.result')" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.passed ? 'success' : 'danger'">
                {{ row.passed ? 'PASS' : 'FAIL' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <!-- 默认折叠：点标题才展开实际请求 / 响应 -->
        <el-collapse v-model="runDetailPanels" class="run-collapse">
          <el-collapse-item name="request">
            <template #title>
              <span class="run-collapse-title">
                <el-icon><Upload /></el-icon>
                {{ $t('apiTesting.aiCases.actualRequest') }}
                <span class="run-collapse-summary">
                  {{ runResult.request_data?.method }} {{ runResult.request_data?.url }}
                </span>
              </span>
            </template>

            <div class="run-detail">
              <div class="run-detail-row">
                <span class="run-detail-label">URL</span>
                <span class="run-detail-value">
                  <el-tag size="small" :type="methodType(runResult.request_data?.method)">
                    {{ runResult.request_data?.method }}
                  </el-tag>
                  {{ runResult.request_data?.url || '-' }}
                </span>
              </div>

              <div class="run-detail-block">
                <div class="run-detail-title">
                  {{ $t('apiTesting.aiCases.requestHeaders') }}
                  <span class="run-detail-count">{{ asEntries(runResult.request_data?.headers).length }}</span>
                </div>
                <div class="kv-mini">
                  <div
                    v-for="(item, i) in asEntries(runResult.request_data?.headers)"
                    :key="i"
                    class="kv-mini-row"
                  >
                    <span class="kv-mini-k">{{ item[0] }}</span>
                    <span class="kv-mini-v">{{ item[1] }}</span>
                  </div>
                  <div v-if="!asEntries(runResult.request_data?.headers).length" class="kv-mini-empty">
                    {{ $t('apiTesting.aiCases.noContent') }}
                  </div>
                </div>
              </div>

              <div class="run-detail-block">
                <div class="run-detail-title">
                  {{ $t('apiTesting.aiCases.queryParams') }}
                  <span class="run-detail-count">{{ asEntries(runResult.request_data?.params).length }}</span>
                </div>
                <div class="kv-mini">
                  <div
                    v-for="(item, i) in asEntries(runResult.request_data?.params)"
                    :key="i"
                    class="kv-mini-row"
                  >
                    <span class="kv-mini-k">{{ item[0] }}</span>
                    <span class="kv-mini-v">{{ item[1] }}</span>
                  </div>
                  <div v-if="!asEntries(runResult.request_data?.params).length" class="kv-mini-empty">
                    {{ $t('apiTesting.aiCases.noContent') }}
                  </div>
                </div>
              </div>

              <div class="run-detail-block">
                <div class="run-detail-title">{{ $t('apiTesting.aiCases.requestBody') }}</div>
                <CodeEditor
                  :model-value="requestBodyText"
                  language="json"
                  class="run-code"
                />
              </div>
            </div>
          </el-collapse-item>

          <el-collapse-item name="response">
            <template #title>
              <span class="run-collapse-title">
                <el-icon><Download /></el-icon>
                {{ $t('apiTesting.aiCases.actualResponse') }}
                <span class="run-collapse-summary">
                  {{ runResult.status_code ?? '-' }} ｜
                  {{ runResult.response_time != null ? Math.round(runResult.response_time) : '-' }} ms
                </span>
              </span>
            </template>

            <div class="run-detail">
              <div class="run-detail-block">
                <div class="run-detail-title">
                  {{ $t('apiTesting.aiCases.responseHeaders') }}
                  <span class="run-detail-count">{{ asEntries(runResult.response_data?.headers).length }}</span>
                </div>
                <div class="kv-mini">
                  <div
                    v-for="(item, i) in asEntries(runResult.response_data?.headers)"
                    :key="i"
                    class="kv-mini-row"
                  >
                    <span class="kv-mini-k">{{ item[0] }}</span>
                    <span class="kv-mini-v">{{ item[1] }}</span>
                  </div>
                  <div v-if="!asEntries(runResult.response_data?.headers).length" class="kv-mini-empty">
                    {{ $t('apiTesting.aiCases.noContent') }}
                  </div>
                </div>
              </div>

              <div class="run-detail-block">
                <div class="run-detail-title">{{ $t('apiTesting.aiCases.responseBody') }}</div>
                <CodeEditor
                  :model-value="responseBodyText"
                  language="json"
                  class="run-code"
                />
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
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
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import {
  ArrowDown, Close, Document, Download, EditPen, Link, MagicStick, Plus, Refresh, Upload
} from '@element-plus/icons-vue'
import CodeEditor from '@/components/CodeEditor.vue'

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
// 实际请求 / 响应默认折叠，点标题才展开
const runDetailPanels = ref([])

const asEntries = (obj) => Object.entries(obj || {})
const prettyBody = (value) => (
  typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)
)

const requestBodyText = computed(() => prettyBody(runResult.value?.request_data?.body))
const responseBodyText = computed(() => {
  const data = runResult.value?.response_data
  if (!data) return ''
  if (data.json != null) return JSON.stringify(data.json, null, 2)
  return data.body || ''
})
const passedAssertionCount = computed(
  () => (runResult.value?.assertions_results || []).filter((a) => a.passed).length
)
const probeVisible = ref(false)
const probeList = ref([])

const createVisible = ref(false)
const editVisible = ref(false)
const reviewVisible = ref(false)
const draftDrawer = ref(false)

const currentTask = ref(null)
const editForm = ref(null)

const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
const priorities = ['P0', 'P1', 'P2', 'P3']

const filters = reactive({ project: null, status: '', search: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const defaultFocus = () => t('apiTesting.aiCases.focusDefault')

const createForm = reactive({
  name: '',
  project: null,
  source_type: 'interfaces',
  source_requests: [],
  environment: null,
  probe_enabled: true,
  source_content: '',
  focus: defaultFocus()
})

let pollTimer = null

const formatDate = (val) => {
  if (!val) return '-'
  return new Date(val).toLocaleString('zh-CN')
}

// 选项里只展示 path，去掉 query 参数（接口原生 url 本身很短）
const cleanUrl = (url) => String(url || '').split('?')[0]

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

// 把后端校验错误翻译成人话：
// {'url': ['该字段不能为空。']} -> 'url: 该字段不能为空。'
// 之前报错只显示「保存失败」这类写死文案，后端给的原因全被吞掉
const formatApiError = (e, fallback = '操作失败') => {
  const data = e?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.error) return data.error
  if (data.detail) return data.detail
  const parts = Object.entries(data).map(([field, val]) => {
    const text = Array.isArray(val) ? val.join('，') : String(val)
    return `${field}: ${text}`
  })
  return parts.length ? parts.join('；') : fallback
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
    // 列表整体换掉后抽屉里持有的还是旧对象，统计卡会一直显示采纳前的数字
    if (currentTask.value) {
      const fresh = tasks.value.find((t) => t.id === currentTask.value.id)
      if (fresh) currentTask.value = fresh
    }
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
    source_content: '', focus: defaultFocus()
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
    const running = tasks.value.some(
      (x) => x.status === 'pending' || x.status === 'running' || x.ai_review_running
    )
    if (!running) stopPolling()
  }, 3000)
}
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ---------- 草稿列表：筛选 / 分页 / 跨页多选 ----------

const DRAFT_PAGE_SIZE = 10

const draftTableRef = ref(null)
const draftSourceFilter = ref('')
const draftStatusFilter = ref('')
const draftPagination = reactive({ page: 1, pageSize: DRAFT_PAGE_SIZE, total: 0 })
// 跨页保留的选中 id：翻页、筛选后仍记得勾了哪些
const selectedDraftIds = ref(new Set())

const hasDraftSelection = computed(() => selectedDraftIds.value.size > 0)

const draftStatusOptions = [
  { value: 'draft', label: t('apiTesting.aiCases.statusDraft') },
  { value: 'pending_review', label: t('apiTesting.aiCases.statusPendingReview') },
  { value: 'approved', label: t('apiTesting.aiCases.statusApproved') },
  { value: 'rejected', label: t('apiTesting.aiCases.statusRejected') },
  { value: 'needs_revision', label: t('apiTesting.aiCases.statusNeedsRevision') }
]

// 优先级按紧急程度配色，扫一眼就知道该先盯哪几条
const priorityType = (p) => ({ P0: 'danger', P1: 'warning', P2: 'primary', P3: 'info' }[p] || 'info')

// 任务用到的来源接口，用于「按接口筛选」；任务没记录时回退到当前草稿里出现过的接口
const draftSourceOptions = computed(() => {
  const detail = currentTask.value?.source_requests_detail || []
  if (detail.length) {
    return detail.map((r) => ({
      id: r.id,
      label: `${r.method || ''} ${cleanUrl(r.url)} · ${r.name}`.trim()
    }))
  }
  const seen = new Map()
  drafts.value.forEach((d) => {
    if (d.source_request && !seen.has(d.source_request)) {
      seen.set(d.source_request, {
        id: d.source_request,
        label: `${d.source_request_method || ''} ${cleanUrl(d.url)} · ${d.source_request_name || ''}`.trim()
      })
    }
  })
  return [...seen.values()]
})

const openDrafts = async (task) => {
  currentTask.value = task
  draftDrawer.value = true
  draftSourceFilter.value = ''
  draftStatusFilter.value = ''
  draftPagination.page = 1
  draftPagination.pageSize = DRAFT_PAGE_SIZE
  selectedDraftIds.value = new Set()
  await loadDrafts()
}

const loadDrafts = async () => {
  if (!currentTask.value) return
  draftLoading.value = true
  try {
    const { data } = await axios.get(`${BASE}ai-case-tasks/${currentTask.value.id}/drafts/`, {
      params: {
        page: draftPagination.page,
        page_size: draftPagination.pageSize,
        status: draftStatusFilter.value || undefined,
        source_request: draftSourceFilter.value || undefined
      }
    })
    drafts.value = data.results || data || []
    draftPagination.total = data.count ?? drafts.value.length
    syncDraftSelection()
  } catch (e) {
    ElMessage.error('加载草稿失败')
  } finally {
    draftLoading.value = false
  }
}

const onDraftFilterChange = () => {
  draftPagination.page = 1
  // 筛选条件一变，之前勾选的用例可能已经不在结果里了，必须清空，
  // 否则「批量通过 / 采纳 / 执行」会误伤到当前看不见的用例
  clearDraftSelection()
  loadDrafts()
}

const onDraftPageSizeChange = () => {
  draftPagination.page = 1
  loadDrafts()
}

// 勾选变化：只同步当前页的选中状态，其他页的保留不动
const onDraftSelectionChange = (rows) => {
  const selectedOnPage = new Set(rows.map((r) => r.id))
  const next = new Set(selectedDraftIds.value)
  drafts.value.forEach((row) => {
    if (selectedOnPage.has(row.id)) next.add(row.id)
    else next.delete(row.id)
  })
  selectedDraftIds.value = next
}

// 回到某页时，把「跨页记住的选中」回填到表格
const syncDraftSelection = () => {
  nextTick(() => {
    drafts.value.forEach((row) => {
      draftTableRef.value?.toggleRowSelection(row, selectedDraftIds.value.has(row.id))
    })
  })
}

const clearDraftSelection = () => {
  selectedDraftIds.value = new Set()
  draftTableRef.value?.clearSelection()
}

const selectedIdList = () => [...selectedDraftIds.value]

const aiReview = async (task) => {
  if (task.ai_review_running) {
    ElMessage.warning(t('apiTesting.aiCases.aiReviewRunning'))
    return
  }
  task.ai_review_running = true // 乐观置位，等轮询回来再用服务端状态校正
  try {
    await axios.post(`${BASE}ai-case-tasks/${task.id}/ai-review/`, {})
    ElMessage.success(t('apiTesting.aiCases.aiReviewStarted'))
    startPolling()
  } catch (e) {
    if (e?.response?.status === 409) {
      ElMessage.warning(t('apiTesting.aiCases.aiReviewRunning'))
    } else {
      ElMessage.error('启动 AI 审核失败')
    }
  } finally {
    await loadTasks() // 用服务端真实状态校正按钮
  }
}

const selfCheck = async (task) => {
  if (!task || task.ai_review_running) {
    ElMessage.warning(t('apiTesting.aiCases.aiReviewRunning'))
    return
  }
  task.ai_review_running = true
  try {
    await axios.post(`${BASE}ai-case-tasks/${task.id}/self-check/`, {})
    ElMessage.success(t('apiTesting.aiCases.selfCheckStarted'))
    startPolling()
  } catch (e) {
    if (e?.response?.status === 409) {
      ElMessage.warning(t('apiTesting.aiCases.aiReviewRunning'))
    } else {
      ElMessage.error('启动一键试跑失败')
    }
  } finally {
    await loadTasks()
  }
}

const aiReviseDraft = async (row) => {
  if (!currentTask.value) return
  try {
    await axios.post(`${BASE}ai-case-tasks/${currentTask.value.id}/ai-revise/`, {
      draft_ids: [row.id],
    })
    ElMessage.success(t('apiTesting.aiCases.aiReviseStarted'))
    startPolling()
  } catch (e) {
    if (e?.response?.status === 409) {
      ElMessage.warning(t('apiTesting.aiCases.aiReviewRunning'))
    } else {
      ElMessage.error('启动 AI 修订失败')
    }
  } finally {
    await loadDrafts()
    await loadTasks()
  }
}

const reviewSuggestionLabel = (s) => ({
  approve: t('apiTesting.aiCases.reasonOK'),
  reject: t('apiTesting.aiCases.reject'),
  needs_revision: t('apiTesting.aiCases.needsRevision'),
}[s] || s || '-')

const reviewSuggestionType = (s) => ({
  approve: 'success', reject: 'danger', needs_revision: 'warning',
}[s] || 'info')

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
  const ids = selectedIdList()
  if (!currentTask.value) return
  if (!ids.length) {
    ElMessage.warning(t('apiTesting.aiCases.pleaseSelectDrafts'))
    return
  }
  try {
    const { data } = await axios.post(`${BASE}ai-case-tasks/${currentTask.value.id}/bulk-review/`, {
      action: 'approve',
      ids
    })
    ElMessage.success(data.message || t('apiTesting.aiCases.reviewSuccess'))
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error(`批量审核失败：${formatApiError(e)}`)
  }
}

const adoptAll = async () => {
  const ids = selectedIdList()
  if (!currentTask.value) return
  if (!ids.length) {
    ElMessage.warning(t('apiTesting.aiCases.pleaseSelectDrafts'))
    return
  }
  try {
    const { data } = await axios.post(`${BASE}ai-case-tasks/${currentTask.value.id}/adopt-all/`, {
      ids
    })
    // 一条都没采纳（勾选的都还没审核通过）时只提示引导，不弹红色错误
    const msg = data.message || t('apiTesting.aiCases.adoptSuccess')
    if (data.adopted_count) ElMessage.success(msg)
    else ElMessage.warning(msg)
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error(formatApiError(e, '批量采纳失败'))
  }
}

// 执行套件：先把勾选的用例采纳进套件，再启动套件执行
const executeSuite = async () => {
  const ids = selectedIdList()
  if (!currentTask.value) return
  if (!ids.length) {
    ElMessage.warning(t('apiTesting.aiCases.pleaseSelectDrafts'))
    return
  }
  try {
    const { data } = await axios.post(`${BASE}ai-case-tasks/${currentTask.value.id}/adopt-all/`, {
      ids
    })
    // 没采纳成功就说明还没审核通过，不要继续执行（否则会撞上「尚未采纳任何用例」的 400）
    if (!data.adopted_count) {
      ElMessage.warning(data.message || t('apiTesting.aiCases.adoptOnlyApproved'))
      return
    }
    const { data: exec } = await axios.post(
      `${BASE}ai-case-tasks/${currentTask.value.id}/execute/`,
      { suite_id: data.suite_id }
    )
    const base = t('apiTesting.aiCases.adoptedThenExecute', { n: data.adopted_count ?? ids.length })
    ElMessage.success(
      exec?.execution_id ? `${base}｜${t('apiTesting.aiCases.executionId')} #${exec.execution_id}` : base
    )
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error(formatApiError(e, t('apiTesting.aiCases.executeTip')))
  }
}

// ---------- 编辑弹窗：结构化数据转换 ----------

const editTab = ref('params')

// 后端可能存对象或数组，统一转成可编辑的键值行
const toKvRows = (data) => {
  if (Array.isArray(data)) {
    return data.map((item) => ({
      key: item?.key || '',
      value: item?.value == null ? '' : String(item.value),
      enabled: item?.enabled !== false
    }))
  }
  return Object.entries(data || {}).map(([key, value]) => ({
    key,
    value: value == null ? '' : (typeof value === 'object' ? JSON.stringify(value) : String(value)),
    enabled: true
  }))
}

const kvRowsToObject = (rows) => {
  const result = {}
  ;(rows || []).forEach((row) => {
    if (row && row.key && row.enabled !== false) result[row.key] = row.value
  })
  return result
}

const kvRowsToArray = (rows) => (rows || [])
  .filter((row) => row && row.key)
  .map((row) => ({ key: row.key, value: row.value, enabled: row.enabled !== false }))

const kvCount = (rows) => (rows || []).filter((row) => row && row.key).length

const addKv = (rows) => {
  rows.push({ key: '', value: '', enabled: true })
}

const normalizeAssertions = (assertions) => (Array.isArray(assertions) ? assertions : [])
  .filter((item) => item && typeof item === 'object')
  .map((item) => ({ ...item }))

// 没有 id 就是「手动添加」模式
const isCreateMode = computed(() => !editForm.value?.id)

const openEdit = (row) => {
  const body = row.body || {}
  const bodyType = body.type || 'none'
  const rawData = body.data

  let bodyText = ''
  let bodyRows = []
  if (bodyType === 'json') {
    bodyText = JSON.stringify(rawData == null ? {} : rawData, null, 2)
  } else if (bodyType === 'raw') {
    bodyText = typeof rawData === 'string' ? rawData : JSON.stringify(rawData ?? '', null, 2)
  } else if (bodyType === 'form-data' || bodyType === 'x-www-form-urlencoded') {
    bodyRows = toKvRows(rawData)
  }

  editForm.value = {
    id: row.id,
    name: row.name,
    method: row.method,
    url: row.url,
    priority: row.priority || 'P1',
    headers: toKvRows(row.headers),
    params: toKvRows(row.params),
    bodyType,
    bodyText,
    bodyRows,
    assertions: normalizeAssertions(row.assertions),
    expected_result: row.expected_result || '',
    description: row.description || '',
    source_request: row.source_request || null
  }
  editTab.value = 'params'
  editVisible.value = true
}

// 手动添加：在当前任务下补一条草稿，默认带一条状态码断言
const openCreateDraft = () => {
  if (!currentTask.value) return
  editForm.value = {
    id: null,
    name: '',
    method: 'GET',
    url: '',
    priority: 'P1',
    headers: [],
    params: [],
    bodyType: 'none',
    bodyText: '',
    bodyRows: [],
    assertions: [{ name: `${t('apiTesting.interface.assertion')}1`, type: 'status_code', expected: 200 }],
    expected_result: '',
    description: '',
    // 列表正按某个接口筛选时，默认就归到这个接口
    source_request: draftSourceFilter.value || null
  }
  editTab.value = 'params'
  editVisible.value = true
}

const onDraftCommand = (cmd, row) => {
  if (cmd === 'duplicate') duplicateDraft(row)
  else if (cmd === 'delete') removeDraft(row)
  else if (cmd === 'reviews') showReviews(row)
  else if (cmd === 'ai_revise') aiReviseDraft(row)

  else reviewDraft(row, cmd)
}

const duplicateDraft = async (row) => {
  try {
    await axios.post(`${BASE}ai-case-drafts/${row.id}/duplicate/`)
    ElMessage.success(t('apiTesting.aiCases.duplicateSuccess'))
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error(formatApiError(e, t('apiTesting.aiCases.duplicate')))
  }
}

const removeDraft = async (row) => {
  try {
    await ElMessageBox.confirm(t('apiTesting.aiCases.confirmDeleteCase'), '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await axios.delete(`${BASE}ai-case-drafts/${row.id}/`)
    const next = new Set(selectedDraftIds.value)
    next.delete(row.id)
    selectedDraftIds.value = next
    ElMessage.success(t('apiTesting.aiCases.deleteCaseSuccess'))
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error(formatApiError(e, t('apiTesting.aiCases.deleteCase')))
  }
}

const onEditAssertionTypeChange = (assertion) => {
  if (assertion.type === 'status_code') {
    assertion.expected = 200
  } else if (assertion.type === 'response_time') {
    assertion.expected = 500
  } else if (assertion.type === 'contains' || assertion.type === 'equals') {
    assertion.expected = ''
  } else if (assertion.type === 'json_path') {
    assertion.json_path = ''
    assertion.expected = null
  } else if (assertion.type === 'header') {
    assertion.header_name = ''
    assertion.expected_value = ''
  }
}

const addEditAssertion = () => {
  editForm.value.assertions.push({
    name: `${t('apiTesting.interface.assertion')}${editForm.value.assertions.length + 1}`,
    type: 'status_code',
    expected: 200
  })
}

const buildEditBody = () => {
  const type = editForm.value.bodyType
  if (type === 'none') return { type: 'none', data: null }
  if (type === 'json') return { type: 'json', data: JSON.parse(editForm.value.bodyText || '{}') }
  if (type === 'raw') return { type: 'raw', data: editForm.value.bodyText }
  return { type, data: kvRowsToArray(editForm.value.bodyRows) }
}

const submitEdit = async () => {
  const form = editForm.value
  if (!form.name?.trim()) {
    ElMessage.warning(t('apiTesting.aiCases.caseNameRequired'))
    return
  }
  if (!form.url?.trim()) {
    ElMessage.warning(t('apiTesting.aiCases.urlRequired'))
    return
  }
  if (form.bodyType === 'json') {
    try {
      JSON.parse(form.bodyText || '{}')
    } catch {
      editTab.value = 'body'
      ElMessage.warning(t('apiTesting.aiCases.jsonInvalid'))
      return
    }
  }

  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      method: form.method,
      url: form.url.trim(),
      priority: form.priority,
      headers: kvRowsToObject(form.headers),
      params: kvRowsToObject(form.params),
      body: buildEditBody(),
      // json_path 的期望值留空要存成 null，执行引擎才会按「存在且非空」校验
      assertions: form.assertions.map((item) => {
        const next = { ...item }
        if (next.type === 'json_path' && (next.expected === '' || next.expected === undefined)) {
          next.expected = null
        }
        return next
      }),
      expected_result: form.expected_result,
      description: form.description
    }

    if (form.id) {
      await axios.patch(`${BASE}ai-case-drafts/${form.id}/`, payload)
      ElMessage.success(t('apiTesting.aiCases.saveSuccess'))
    } else {
      // 手动添加：落在当前任务下，状态为「草稿」，需审核通过才能采纳
      await axios.post(`${BASE}ai-case-tasks/${currentTask.value.id}/add-draft/`, {
        ...payload,
        source_request: form.source_request || null
      })
      ElMessage.success(t('apiTesting.aiCases.saveDraftSuccess'))
    }
    editVisible.value = false
    await loadDrafts()
    await loadTasks()
  } catch (e) {
    ElMessage.error(formatApiError(e, t('apiTesting.aiCases.saveFailed')))
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
    runDetailPanels.value = []
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

/* ---------- 新建任务弹窗 ---------- */
.dlg-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dlg-head-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #fff;
  background: linear-gradient(135deg, #6d5efc, #4a8cff);
  box-shadow: 0 6px 16px rgba(99, 88, 246, 0.3);
}

.dlg-head-text h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: #1f2440;
}

.dlg-head-text p {
  margin: 3px 0 0;
  font-size: 12px;
  color: #8a90a8;
}

.dlg-head-close {
  margin-left: auto;
  font-size: 18px;
  color: #98a0b8;
  cursor: pointer;
  transition: color 0.2s;
}

.dlg-head-close:hover {
  color: #4a4f6a;
}

.create-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.create-form :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 600;
  color: #454a63;
  line-height: 1.4;
  padding-bottom: 6px;
}

.form-section + .form-section {
  margin-top: 6px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 2px 0 12px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #7b819c;
}

.section-dot {
  display: inline-block;
  width: 4px;
  height: 14px;
  border-radius: 2px;
  background: linear-gradient(180deg, #6d5efc, #4a8cff);
}

.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 18px;
}

.type-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.type-group :deep(.el-radio-button__inner) {
  border: 1px solid #e3e6f3;
  border-radius: 10px;
  padding: 8px 16px;
  font-size: 13px;
  color: #565c78;
  box-shadow: none;
}

.type-group :deep(.el-radio-button.is-active .el-radio-button__inner) {
  background: #f0efff;
  border-color: #b9b3ff;
  color: #5a4ff0;
  box-shadow: none;
}

.switch-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  margin-bottom: 16px;
  border: 1px solid #eceefb;
  border-radius: 12px;
  background: #f8f9ff;
}

.switch-card-text {
  flex: 1;
}

.switch-card-title {
  font-size: 13px;
  font-weight: 600;
  color: #3a3f5c;
}

.switch-card-desc {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: #8a90a8;
}

.if-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.if-method {
  flex-shrink: 0;
}

.if-name {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 46%;
  font-size: 13px;
  color: #2f3450;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.if-url {
  flex: 1 1 0;
  min-width: 0;
  font-size: 12px;
  color: #9aa0b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dlg-footer {
  display: flex;
  align-items: center;
  gap: 16px;
}

.dlg-footer-hint {
  margin-right: auto;
  font-size: 12px;
  color: #9aa0b8;
}

.dlg-footer-actions {
  display: flex;
  gap: 10px;
}

/* 编辑弹窗 */
.edit-basic :deep(.el-form-item) {
  margin-bottom: 12px;
}

.edit-basic :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 600;
  color: #454a63;
  line-height: 1.4;
  padding-bottom: 6px;
}

.method-priority {
  display: flex;
  gap: 10px;
}

.method-sel {
  width: 140px;
}

.priority-sel {
  width: 110px;
}

.edit-tabs :deep(.el-tabs__header) {
  margin-bottom: 14px;
}

.edit-tabs :deep(.el-tabs__item) {
  font-size: 13px;
  font-weight: 600;
}

.edit-tabs :deep(.el-tabs__content) {
  min-height: 296px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tab-badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #ecebff;
  color: #5a4ff0;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.tab-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
}

.tab-tip {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #8a90a8;
}

/* 键值编辑器 */
.kv-editor {
  border: 1px solid #eceef5;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}

.kv-head,
.kv-row {
  display: grid;
  grid-template-columns: 28px 220px 1fr 36px;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
}

.kv-head {
  background: #fafbff;
  border-bottom: 1px solid #eff1f8;
  font-size: 12px;
  font-weight: 600;
  color: #8a90a8;
}

.kv-row + .kv-row {
  border-top: 1px solid #f5f6fa;
}

.kv-add {
  margin: 4px 0 4px 8px;
}

/* 请求体 */
.body-type-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.body-type-group :deep(.el-radio-button__inner) {
  border: 1px solid #e3e6f3;
  border-radius: 10px;
  padding: 7px 14px;
  font-size: 12px;
  color: #565c78;
  box-shadow: none;
}

.body-type-group :deep(.el-radio-button.is-active .el-radio-button__inner) {
  background: #f0efff;
  border-color: #b9b3ff;
  color: #5a4ff0;
  box-shadow: none;
}

.body-code {
  height: 260px;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  overflow: hidden;
}

.body-empty {
  padding: 40px 16px;
  text-align: center;
  font-size: 13px;
  color: #9aa0b8;
  border: 1px dashed #dfe3ec;
  border-radius: 10px;
  background: #fbfcff;
}

/* 断言表格 */
.assertion-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.at-head,
.at-row {
  display: grid;
  grid-template-columns: 30px minmax(110px, 1fr) 138px minmax(260px, 1.9fr) 36px;
  gap: 8px;
  align-items: center;
}

.at-head {
  padding: 0 6px 4px;
  font-size: 12px;
  font-weight: 600;
  color: #8a90a8;
}

.at-row {
  padding: 8px 6px;
  border: 1px solid #eceef5;
  border-radius: 10px;
  background: #fff;
}

.at-row:hover {
  border-color: #c9c4f5;
}

.at-idx {
  font-size: 12px;
  color: #a8adb9;
  text-align: center;
}

.at-params {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.at-params > * {
  flex: 1;
  min-width: 0;
}

.at-num {
  flex: 0 0 130px;
}

.assertion-empty {
  padding: 40px 16px;
  text-align: center;
  border: 1px dashed #dfe3ec;
  border-radius: 10px;
  background: #fbfcff;
}

.assertion-empty p {
  margin: 0 0 12px;
  font-size: 13px;
  color: #9aa0b8;
}

.doc-form :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 600;
  color: #454a63;
  padding-bottom: 6px;
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

.dlg-head-icon--green {
  background: linear-gradient(135deg, #34d399, #22b573);
  box-shadow: 0 6px 16px rgba(34, 181, 115, 0.3);
}

.dlg-head-icon--red {
  background: linear-gradient(135deg, #ff7a7a, #e5443f);
  box-shadow: 0 6px 16px rgba(229, 68, 63, 0.3);
}

/* ---------- 用例抽屉 ---------- */
.flex-spacer {
  flex: 1;
}

/* 统计概览 */
.draft-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f7f8ff 0%, #fdfdff 100%);
  border: 1px solid #eceef8;
  border-left: 3px solid #b9b4f7;
  border-radius: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.stat-card--ok {
  border-left-color: #3ec98a;
  background: linear-gradient(135deg, #f2fbf7 0%, #fdfffe 100%);
}

.stat-card--done {
  border-left-color: #4a8cff;
  background: linear-gradient(135deg, #f2f7ff 0%, #fdfeff 100%);
}

.stat-card--sel {
  border-left-color: #d8dcea;
}

.stat-card--sel.is-active {
  border-left-color: #f0a13c;
  box-shadow: 0 4px 14px rgba(240, 161, 60, 0.16);
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
  color: #2f3450;
}

.stat-label {
  font-size: 12px;
  color: #8a90a8;
}

/* 筛选栏 */
.draft-filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.filter-sel {
  width: 320px;
}

.status-tabs :deep(.el-radio-button__inner) {
  font-size: 12px;
}

/* 批量操作条：有勾选时高亮 */
.draft-action-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  margin-bottom: 12px;
  background: #f7f8fc;
  border: 1px solid #edeff8;
  border-radius: 10px;
  transition: background 0.2s, border-color 0.2s;
}

.draft-action-bar.is-active {
  background: linear-gradient(90deg, #f3f1ff 0%, #f7f9ff 100%);
  border-color: #cfc9fb;
}

.sel-info {
  font-size: 13px;
  color: #6b7280;
}

.sel-info b {
  margin: 0 3px;
  font-size: 15px;
  color: #5046e5;
}

/* 表格占满剩余高度并内部滚动，分页固定在底部 */
.draft-table-wrap {
  flex: 1;
  min-height: 260px;
  border: 1px solid #edeff8;
  border-radius: 12px;
  overflow: hidden;
}

.draft-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

/* 试运行结果：折叠详情 */
.run-collapse {
  margin-top: 16px;
  border: 1px solid #eceef5;
  border-radius: 10px;
  overflow: hidden;
}

.run-collapse :deep(.el-collapse-item__header) {
  height: 46px;
  padding: 0 14px;
  background: #fafbff;
  font-size: 13px;
}

.run-collapse :deep(.el-collapse-item__content) {
  padding: 14px;
}

.run-collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #3a3f58;
}

.run-collapse-summary {
  max-width: 460px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 400;
  font-size: 12px;
  color: #8a90a8;
}

.run-detail-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.run-detail-label {
  flex-shrink: 0;
  font-size: 12px;
  color: #8a90a8;
}

.run-detail-value {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #303133;
  word-break: break-all;
}

.run-detail-block + .run-detail-block {
  margin-top: 12px;
}

.run-detail-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
}

.run-detail-count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #ecebff;
  color: #5a4ff0;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.kv-mini {
  border: 1px solid #eceef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.kv-mini-row {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 10px;
  padding: 6px 10px;
  font-size: 12px;
  border-bottom: 1px solid #f5f6fa;
}

.kv-mini-row:last-child {
  border-bottom: none;
}

.kv-mini-k {
  color: #6b7280;
  font-weight: 600;
  word-break: break-all;
}

.kv-mini-v {
  color: #303133;
  word-break: break-all;
}

.kv-mini-empty {
  padding: 10px;
  font-size: 12px;
  color: #a8adb9;
}

.run-code {
  height: 220px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}

.run-metric-value.is-fail {
  color: #e5443f;
}

.run-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #909399;
}

/* 用例名称 + 已入库标记 */
.draft-name {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.draft-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: #303133;
}

.draft-adopted-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  padding: 0 6px;
  height: 18px;
  border-radius: 9px;
  background: #eaf7f0;
  color: #23935f;
  font-size: 11px;
  line-height: 18px;
}

.danger-text {
  color: #e5443f;
}

/* 空值占位，和有内容的单元格区分开 */
.col-empty {
  color: #c0c4cc;
}

/* URL 用等宽字体，路径与变量一眼能分辨 */
.draft-url {
  font-family: 'SFMono-Regular', Consolas, 'Courier New', monospace;
  font-size: 12px;
  color: #606266;
}

.source-sel {
  width: 100%;
}
</style>

<style>
/* 弹窗挂载在 body 上，外壳样式需要非 scoped 才能命中 */
.create-task-dialog {
  padding: 0;
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(24, 30, 66, 0.18);
}

.create-task-dialog .el-dialog__header {
  margin: 0;
  padding: 20px 24px 16px;
  background: linear-gradient(135deg, #f6f4ff 0%, #eef5ff 100%);
  border-bottom: 1px solid #edeff8;
}

.create-task-dialog .el-dialog__body {
  padding: 18px 24px 4px;
  max-height: 60vh;
  overflow-y: auto;
}

.create-task-dialog .el-dialog__footer {
  padding: 14px 24px 18px;
  background: #fbfbfe;
  border-top: 1px solid #edeff8;
}

.edit-draft-dialog {
  padding: 0;
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(24, 30, 66, 0.18);
}

.edit-draft-dialog .el-dialog__header {
  margin: 0;
  padding: 20px 24px 16px;
  background: linear-gradient(135deg, #f6f4ff 0%, #eef5ff 100%);
  border-bottom: 1px solid #edeff8;
}

.edit-draft-dialog .el-dialog__body {
  padding: 16px 24px 2px;
  max-height: 64vh;
  overflow-y: auto;
}

.edit-draft-dialog .el-dialog__footer {
  padding: 14px 24px 18px;
  background: #fbfbfe;
  border-top: 1px solid #edeff8;
}

.im-dialog {
  padding: 0;
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(24, 30, 66, 0.18);
}

.im-dialog .el-dialog__header {
  margin: 0;
  padding: 20px 24px 16px;
  background: linear-gradient(135deg, #f6f4ff 0%, #eef5ff 100%);
  border-bottom: 1px solid #edeff8;
}

.im-dialog .el-dialog__body {
  padding: 18px 24px 4px;
  max-height: 64vh;
  overflow-y: auto;
}

/* 用例抽屉：纵向布局 —— 统计/筛选固定，表格内部滚动，分页常驻底部 */
.draft-drawer .el-drawer__header {
  margin-bottom: 0;
  padding: 16px 20px;
  border-bottom: 1px solid #edeff8;
  color: #1f2440;
  font-weight: 600;
}

.draft-drawer .el-drawer__body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 16px 20px;
  overflow: hidden;
}

.if-select-popper .el-select-dropdown__item {
  height: auto;
  padding: 8px 12px;
  overflow: hidden;
  line-height: 1.5;
}

.if-select-popper .el-select-dropdown__item.is-selected {
  background: #f3f2ff;
}

/* 下拉宽度跟随输入框，长文本在选项内部截断，不再撑宽面板 */
.if-select-popper .el-select-dropdown {
  max-width: 100%;
  overflow-x: hidden;
}

.create-task-dialog .el-select__tags .el-tag {
  max-width: 220px;
  overflow: hidden;
  white-space: nowrap;
}

.create-task-dialog .el-select__tags .el-tag .el-tag__content {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
