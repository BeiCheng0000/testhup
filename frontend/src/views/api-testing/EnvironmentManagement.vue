<template>
  <div class="environment-management">
    <div class="header">
      <h3>{{ $t('apiTesting.environment.title') }}</h3>
      <el-button v-if="activeTab === 'LOCAL'" type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        {{ $t('apiTesting.environment.createEnvironment') }}
      </el-button>
      <el-button v-else type="primary" @click="openGlobalVariableDialog()">
        <el-icon><Plus /></el-icon>
        {{ $t('apiTesting.environment.addGlobalVariable') }}
      </el-button>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane :label="$t('apiTesting.environment.scopeTypes.global')" name="GLOBAL">
        <!-- 统计卡片 -->
        <div class="gv-stats">
          <div class="stat-card stat-total">
            <div class="stat-icon"><el-icon><Key /></el-icon></div>
            <div class="stat-info">
              <div class="stat-value">{{ gvStats.total }}</div>
              <div class="stat-label">{{ $t('apiTesting.environment.statTotal') }}</div>
            </div>
          </div>
          <div class="stat-card stat-cross">
            <div class="stat-icon"><el-icon><Connection /></el-icon></div>
            <div class="stat-info">
              <div class="stat-value">{{ gvStats.cross }}</div>
              <div class="stat-label">{{ $t('apiTesting.environment.statCrossProject') }}</div>
            </div>
          </div>
          <div class="stat-card stat-scoped">
            <div class="stat-icon"><el-icon><OfficeBuilding /></el-icon></div>
            <div class="stat-info">
              <div class="stat-value">{{ gvStats.scoped }}</div>
              <div class="stat-label">{{ $t('apiTesting.environment.statProjectScoped') }}</div>
            </div>
          </div>
        </div>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="global-var-help"
        >
          {{ $t('apiTesting.environment.globalVariableHelp') }}
        </el-alert>

        <div class="gv-filter-bar">
          <el-select v-model="gvFilters.field" class="gv-field" style="width: 150px">
            <el-option :label="$t('apiTesting.environment.filterFieldAll')" value="all" />
            <el-option :label="$t('apiTesting.environment.filterFieldName')" value="key" />
            <el-option :label="$t('apiTesting.environment.filterFieldValue')" value="value" />
          </el-select>
          <el-input
            v-model="gvFilters.keyword"
            :prefix-icon="Search"
            :placeholder="$t('apiTesting.environment.filterKeyword')"
            clearable
            class="gv-search"
            style="width: 260px"
          />
          <el-select
            v-model="gvFilters.project"
            :prefix-icon="OfficeBuilding"
            :placeholder="$t('apiTesting.environment.filterByProject')"
            clearable
            filterable
            class="gv-project"
            style="width: 220px"
          >
            <el-option :label="$t('apiTesting.environment.allProjects')" :value="null" />
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-button @click="resetGvFilters" :icon="Refresh">
            {{ $t('apiTesting.environment.resetFilter') }}
          </el-button>
        </div>

        <div class="gv-table-card">
          <el-table
            :data="filteredGlobalVariables"
            v-loading="loading"
            class="gv-table"
            style="width: 100%"
          >
            <el-table-column prop="key" :label="$t('apiTesting.environment.variableName')" min-width="150">
              <template #default="{ row }">
                <span class="gv-key">{{ row.key }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="value" :label="$t('apiTesting.environment.variableValue')" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <code class="gv-value" v-if="row.value">{{ row.value }}</code>
                <span v-else class="gv-empty-value">—</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('apiTesting.environment.relatedProject')" width="170">
              <template #default="{ row }">
                <el-tag v-if="!row.project" size="small" type="success" effect="light">
                  {{ $t('apiTesting.environment.allProjects') }}
                </el-tag>
                <el-tag v-else size="small" type="info" effect="plain">{{ row.project_name }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" :label="$t('apiTesting.environment.description')" min-width="150" show-overflow-tooltip />
            <el-table-column :label="$t('apiTesting.common.operation')" width="160" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" :icon="Edit" @click="openGlobalVariableDialog(row)">
                  {{ $t('apiTesting.common.edit') }}
                </el-button>
                <el-button type="danger" link size="small" :icon="Delete" @click="deleteGlobalVariable(row)">
                  {{ $t('apiTesting.common.delete') }}
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <div class="gv-empty">
                <el-icon class="gv-empty-icon"><FolderOpened /></el-icon>
                <span>{{ $t('apiTesting.environment.noGlobalVariables') }}</span>
              </div>
            </template>
          </el-table>
        </div>
      </el-tab-pane>
      <el-tab-pane :label="$t('apiTesting.environment.scopeTypes.local')" name="LOCAL">
        <div class="local-env-header">
          <el-select
            v-model="selectedProject"
            :placeholder="$t('apiTesting.common.selectProject')"
            @change="loadLocalEnvironments"
            style="width: 200px;"
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </div>
        <EnvironmentTable
          :data="localEnvironments"
          :loading="loading"
          scope="LOCAL"
          @edit="editEnvironment"
          @delete="deleteEnvironment"
          @activate="activateEnvironment"
          @deactivate="deactivateEnvironment"
          @duplicate="duplicateEnvironment"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 创建/编辑环境对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingEnvironment ? $t('apiTesting.environment.editEnvironment') : $t('apiTesting.environment.createEnvironment')"
      width="800px"
      :close-on-click-modal="false"
      @close="resetForm"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
      >
        <el-form-item :label="$t('apiTesting.environment.environmentName')" prop="name">
          <el-input v-model="form.name" :placeholder="$t('apiTesting.environment.inputEnvironmentName')" />
        </el-form-item>

        <el-form-item
          v-if="form.scope === 'LOCAL'"
          :label="$t('apiTesting.environment.relatedProject')"
          prop="project"
        >
          <el-select v-model="form.project" :placeholder="$t('apiTesting.environment.selectRelatedProject')">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('apiTesting.environment.environmentVariables')" prop="variables">
          <div class="variables-editor">
            <div class="variables-header">
              <div class="column">{{ $t('apiTesting.environment.variableName') }}</div>
              <div class="column">{{ $t('apiTesting.environment.initialValue') }}</div>
              <div class="column">{{ $t('apiTesting.environment.currentValue') }}</div>
              <div class="column">{{ $t('apiTesting.common.operation') }}</div>
            </div>

            <div class="variables-body">
              <div
                v-for="(variable, index) in form.variables"
                :key="index"
                class="variable-row"
              >
                <div class="column">
                  <el-input
                    v-model="variable.key"
                    :placeholder="$t('apiTesting.environment.variableName')"
                    size="small"
                  />
                </div>
                <div class="column">
                  <el-input
                    v-model="variable.initialValue"
                    :placeholder="$t('apiTesting.environment.initialValue')"
                    size="small"
                  />
                </div>
                <div class="column">
                  <el-input
                    v-model="variable.currentValue"
                    :placeholder="$t('apiTesting.environment.currentValue')"
                    size="small"
                  />
                </div>
                <div class="column">
                  <el-button
                    size="small"
                    type="danger"
                    :icon="Delete"
                    @click="removeVariable(index)"
                    :disabled="form.variables.length <= 1"
                  />
                </div>
              </div>
            </div>

            <div class="variables-footer">
              <el-button size="small" @click="addVariable">
                <el-icon><Plus /></el-icon>
                {{ $t('apiTesting.environment.addVariable') }}
              </el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">{{ $t('apiTesting.common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">
          {{ editingEnvironment ? $t('apiTesting.common.update') : $t('apiTesting.common.create') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 全局变量：新增/编辑 -->
    <el-dialog
      v-model="showGlobalVariableDialog"
      :title="editingGlobalVariable ? $t('apiTesting.environment.editGlobalVariable') : $t('apiTesting.environment.addGlobalVariable')"
      width="520px"
      :close-on-click-modal="false"
      @close="resetGlobalVariableForm"
    >
      <el-form ref="globalVarFormRef" :model="globalVarForm" :rules="globalVarRules" label-width="100px">
        <el-form-item :label="$t('apiTesting.environment.variableName')" prop="key">
          <el-input v-model="globalVarForm.key" placeholder="host_test" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.environment.variableValue')" prop="value">
          <el-input v-model="globalVarForm.value" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.environment.relatedProject')">
          <el-select
            v-model="globalVarForm.project"
            clearable
            :placeholder="$t('apiTesting.environment.allProjects')"
            style="width: 100%"
          >
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-text size="small" type="info">
            {{ $t('apiTesting.environment.projectScopeHelp') }}
          </el-text>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.environment.description')">
          <el-input v-model="globalVarForm.description" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showGlobalVariableDialog = false">{{ $t('apiTesting.common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submitGlobalVariable">
          {{ editingGlobalVariable ? $t('apiTesting.common.update') : $t('apiTesting.common.create') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 查看变量对话框 -->
    <el-dialog
      v-model="showViewDialog"
      :title="$t('apiTesting.environment.environmentVariableDetail')"
      width="600px"
    >
      <div v-if="viewingEnvironment" class="view-variables">
        <el-table :data="viewVariables" style="width: 100%">
          <el-table-column prop="key" :label="$t('apiTesting.environment.variableName')" width="150" />
          <el-table-column prop="initialValue" :label="$t('apiTesting.environment.initialValue')" />
          <el-table-column prop="currentValue" :label="$t('apiTesting.environment.currentValue')" />
        </el-table>
      </div>

      <template #footer>
        <el-button @click="showViewDialog = false">{{ $t('apiTesting.common.close') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { Plus, Delete, Edit, Search, Refresh, Connection, OfficeBuilding, Key, FolderOpened } from '@element-plus/icons-vue'
import api from '@/utils/api'
import EnvironmentTable from './components/EnvironmentTable.vue'

const { t } = useI18n()
const activeTab = ref('GLOBAL')
const globalVariables = ref([])
const gvFilters = reactive({ field: 'all', keyword: '', project: null })
const filteredGlobalVariables = computed(() => {
  const kw = (gvFilters.keyword || '').trim().toLowerCase()
  const field = gvFilters.field || 'all'
  const proj = gvFilters.project
  return (globalVariables.value || []).filter(item => {
    const matchField = (() => {
      if (!kw) return true
      if (field === 'key') return (item.key || '').toLowerCase().includes(kw)
      if (field === 'value') return (item.value || '').toLowerCase().includes(kw)
      return (item.key || '').toLowerCase().includes(kw) ||
        (item.value || '').toLowerCase().includes(kw)
    })()
    const matchProject = proj == null ? true : item.project === proj
    return matchField && matchProject
  })
})
const resetGvFilters = () => {
  gvFilters.field = 'all'
  gvFilters.keyword = ''
  gvFilters.project = null
}
const gvStats = computed(() => {
  const list = globalVariables.value || []
  return {
    total: list.length,
    cross: list.filter(v => !v.project).length,
    scoped: list.filter(v => v.project).length
  }
})
const localEnvironments = ref([])
const projects = ref([])
const selectedProject = ref(null)
const loading = ref(false)
const showCreateDialog = ref(false)
const showViewDialog = ref(false)
const showGlobalVariableDialog = ref(false)
const editingEnvironment = ref(null)
const editingGlobalVariable = ref(null)
const viewingEnvironment = ref(null)
const submitting = ref(false)
const formRef = ref()
const globalVarFormRef = ref()

const globalVarForm = reactive({
  key: '',
  value: '',
  project: null,
  description: ''
})

const globalVarRules = computed(() => ({
  key: [
    { required: true, message: t('apiTesting.environment.variableNameRequired'), trigger: 'blur' }
  ]
}))

const form = reactive({
  name: '',
  scope: 'LOCAL',
  project: null,
  variables: [
    {
      key: 'host',
      initialValue: '',
      currentValue: ''
    }
  ]
})

const rules = computed(() => ({
  name: [
    { required: true, message: t('apiTesting.environment.inputEnvironmentName'), trigger: 'blur' }
  ],
  project: [
    {
      validator: (rule, value, callback) => {
        if (form.scope === 'LOCAL' && !value) {
          callback(new Error(t('apiTesting.environment.selectRelatedProject')))
        } else {
          callback()
        }
      },
      trigger: 'change'
    }
  ]
}))

const viewVariables = computed(() => {
  if (!viewingEnvironment.value?.variables) return []
  
  const vars = viewingEnvironment.value.variables
  return Object.keys(vars).map(key => ({
    key,
    initialValue: vars[key]?.initialValue || vars[key] || '',
    currentValue: vars[key]?.currentValue || vars[key] || ''
  }))
})

const loadProjects = async () => {
  try {
    const response = await api.get('/api-testing/projects/')
    projects.value = response.data.results || response.data
    if (projects.value.length > 0 && !selectedProject.value) {
      selectedProject.value = projects.value[0].id
    }
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.projectListLoadFailed'))
  }
}

const loadGlobalVariables = async () => {
  loading.value = true
  try {
    const response = await api.get('/api-testing/global-variables/')
    globalVariables.value = response.data.results || response.data
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.globalEnvLoadFailed'))
  } finally {
    loading.value = false
  }
}

const openGlobalVariableDialog = (row = null) => {
  editingGlobalVariable.value = row
  if (row) {
    Object.assign(globalVarForm, {
      key: row.key,
      value: row.value || '',
      project: row.project || null,
      description: row.description || ''
    })
  } else {
    Object.assign(globalVarForm, { key: '', value: '', project: null, description: '' })
  }
  showGlobalVariableDialog.value = true
}

const resetGlobalVariableForm = () => {
  editingGlobalVariable.value = null
  Object.assign(globalVarForm, { key: '', value: '', project: null, description: '' })
  globalVarFormRef.value?.resetFields()
}

const submitGlobalVariable = async () => {
  if (!globalVarFormRef.value) return
  const valid = await globalVarFormRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const data = {
      key: globalVarForm.key,
      value: globalVarForm.value || '',
      project: globalVarForm.project || null,
      description: globalVarForm.description || ''
    }
    if (editingGlobalVariable.value) {
      await api.put(`/api-testing/global-variables/${editingGlobalVariable.value.id}/`, data)
      ElMessage.success(t('apiTesting.messages.success.environmentUpdated'))
    } else {
      await api.post('/api-testing/global-variables/', data)
      ElMessage.success(t('apiTesting.messages.success.environmentCreated'))
    }
    showGlobalVariableDialog.value = false
    await loadGlobalVariables()
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.updateFailed'))
  } finally {
    submitting.value = false
  }
}

const deleteGlobalVariable = async (row) => {
  try {
    await ElMessageBox.confirm(
      t('apiTesting.environment.confirmDeleteGlobalVar', { name: row.key }),
      t('apiTesting.messages.confirm.deleteTitle'),
      {
        confirmButtonText: t('apiTesting.common.confirm'),
        cancelButtonText: t('apiTesting.common.cancel'),
        type: 'warning'
      }
    )
    await api.delete(`/api-testing/global-variables/${row.id}/`)
    ElMessage.success(t('apiTesting.messages.success.delete'))
    await loadGlobalVariables()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('apiTesting.messages.error.deleteFailed'))
    }
  }
}

const loadLocalEnvironments = async () => {
  if (!selectedProject.value) return

  loading.value = true
  try {
    const response = await api.get('/api-testing/environments/', {
      params: {
        scope: 'LOCAL',
        project: selectedProject.value
      }
    })
    localEnvironments.value = response.data.results || response.data
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.localEnvLoadFailed'))
  } finally {
    loading.value = false
  }
}

const onTabChange = (tab) => {
  if (tab === 'GLOBAL') {
    loadGlobalVariables()
  } else {
    loadLocalEnvironments()
  }
}

const addVariable = () => {
  form.variables.push({
    key: '',
    initialValue: '',
    currentValue: ''
  })
}

const removeVariable = (index) => {
  // 不允许删除 host 变量
  if (form.variables[index]?.key === 'host') {
    ElMessage.warning(t('apiTesting.environment.hostVariableRequired'))
    return
  }
  if (form.variables.length > 1) {
    form.variables.splice(index, 1)
  }
}

const editEnvironment = (environment) => {
  editingEnvironment.value = environment
  form.name = environment.name
  form.scope = environment.scope
  form.project = environment.project
  
  // 转换变量格式
  const variables = environment.variables || {}
  form.variables = Object.keys(variables).map(key => {
    const value = variables[key]
    if (typeof value === 'object') {
      return {
        key,
        initialValue: value.initialValue || '',
        currentValue: value.currentValue || ''
      }
    } else {
      return {
        key,
        initialValue: value || '',
        currentValue: value || ''
      }
    }
  })
  
  if (form.variables.length === 0) {
    form.variables.push({
      key: '',
      initialValue: '',
      currentValue: ''
    })
  }
  
  showCreateDialog.value = true
}

const deleteEnvironment = async (environment) => {
  try {
    await ElMessageBox.confirm(
      t('apiTesting.environment.confirmDeleteEnv', { name: environment.name }),
      t('apiTesting.messages.confirm.deleteTitle'),
      {
        confirmButtonText: t('apiTesting.common.confirm'),
        cancelButtonText: t('apiTesting.common.cancel'),
        type: 'warning'
      }
    )

    await api.delete(`/api-testing/environments/${environment.id}/`)
    ElMessage.success(t('apiTesting.messages.success.delete'))

    if (activeTab.value === 'GLOBAL') {
      await loadGlobalVariables()
    } else {
      await loadLocalEnvironments()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('apiTesting.messages.error.deleteFailed'))
    }
  }
}

const activateEnvironment = async (environment) => {
  try {
    await api.post(`/api-testing/environments/${environment.id}/activate/`)
    ElMessage.success(t('apiTesting.messages.success.environmentActivated'))

    if (activeTab.value === 'GLOBAL') {
      await loadGlobalVariables()
    } else {
      await loadLocalEnvironments()
    }
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.activateFailed'))
  }
}

const deactivateEnvironment = async (environment) => {
  try {
    await api.post(`/api-testing/environments/${environment.id}/deactivate/`)
    ElMessage.success(t('apiTesting.messages.success.environmentDeactivated'))

    if (activeTab.value === 'GLOBAL') {
      await loadGlobalVariables()
    } else {
      await loadLocalEnvironments()
    }
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.deactivateFailed'))
  }
}

const duplicateEnvironment = async (environment) => {
  const newEnv = {
    name: `${environment.name} - Copy`,
    scope: environment.scope,
    project: environment.scope === 'LOCAL' ?
      (typeof environment.project === 'object' ? environment.project.id : environment.project) :
      null,
    variables: environment.variables || {}
  }

  try {
    await api.post('/api-testing/environments/', newEnv)
    ElMessage.success(t('apiTesting.messages.success.copy'))

    if (activeTab.value === 'GLOBAL') {
      await loadGlobalVariables()
    } else {
      await loadLocalEnvironments()
    }
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.copyFailed'))
  }
}

const submitForm = async () => {
  if (!formRef.value) return
  
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  
  submitting.value = true
  try {
    // 转换变量格式
    const variables = {}
    form.variables.forEach(variable => {
      if (variable.key) {
        variables[variable.key] = {
          initialValue: variable.initialValue || '',
          currentValue: variable.currentValue || variable.initialValue || ''
        }
      }
    })
    
    const data = {
      name: form.name,
      scope: form.scope,
      project: form.scope === 'LOCAL' ? form.project : null,
      variables
    }
    
    if (editingEnvironment.value) {
      await api.put(`/api-testing/environments/${editingEnvironment.value.id}/`, data)
      ElMessage.success(t('apiTesting.messages.success.environmentUpdated'))
    } else {
      await api.post('/api-testing/environments/', data)
      ElMessage.success(t('apiTesting.messages.success.environmentCreated'))
    }

    showCreateDialog.value = false

    if (activeTab.value === 'GLOBAL') {
      await loadGlobalVariables()
    } else {
      await loadLocalEnvironments()
    }
  } catch (error) {
    ElMessage.error(editingEnvironment.value ? t('apiTesting.messages.error.updateFailed') : t('apiTesting.messages.error.createFailed'))
  } finally {
    submitting.value = false
  }
}

const resetForm = () => {
  editingEnvironment.value = null
  Object.assign(form, {
    name: '',
    scope: 'GLOBAL',
    project: null,
    variables: [
      {
        key: 'host',
        initialValue: '',
        currentValue: ''
      }
    ]
  })
  formRef.value?.resetFields()
}

onMounted(async () => {
  await loadProjects()
  await loadGlobalVariables()
  if (selectedProject.value) {
    await loadLocalEnvironments()
  }
})
</script>

<style scoped>
.environment-management {
  padding: 24px 28px;
  min-height: calc(100vh - 60px);
  background: linear-gradient(180deg, #f5f8ff 0%, #f0f4f9 100%);
}

/* header */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 22px;
}
.header h3 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  background: linear-gradient(90deg, #2b6cff, #6a5cff);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* tabs */
.environment-management :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: #e6ebf5;
}
.environment-management :deep(.el-tabs__item) {
  font-weight: 600;
  font-size: 14px;
}

/* 统计卡片 */
.gv-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 18px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 6px 18px rgba(31, 45, 80, 0.06);
  border: 1px solid #eef1f8;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 26px rgba(31, 45, 80, 0.12);
}
.stat-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: #fff;
}
.stat-total .stat-icon { background: linear-gradient(135deg, #4e8bff, #2b6cff); }
.stat-cross .stat-icon { background: linear-gradient(135deg, #9a7bff, #6a5cff); }
.stat-scoped .stat-icon { background: linear-gradient(135deg, #2bd9a8, #11b386); }
.stat-info { display: flex; flex-direction: column; }
.stat-value { font-size: 26px; font-weight: 700; line-height: 1.1; color: #1f2d50; }
.stat-label { font-size: 13px; color: #8a93a6; margin-top: 2px; }

/* alert */
.global-var-help {
  border-radius: 12px;
  border: none;
  background: linear-gradient(90deg, #eef4ff, #f3eefe);
  margin-bottom: 16px;
}

/* 筛选栏 */
.gv-filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 4px 14px rgba(31, 45, 80, 0.05);
  border: 1px solid #eef1f8;
}
.gv-filter-bar :deep(.el-button) { margin-left: auto; }

/* 表格卡片 */
.gv-table-card {
  background: #fff;
  border-radius: 14px;
  padding: 8px;
  box-shadow: 0 6px 18px rgba(31, 45, 80, 0.06);
  border: 1px solid #eef1f8;
}

/* 表格定制 */
.gv-table {
  border-radius: 10px;
  overflow: hidden;
}
.gv-table :deep(.el-table__header-wrapper th) {
  background: linear-gradient(90deg, #f3f7ff, #f7f3ff);
  color: #2b3552;
  font-weight: 600;
}
.gv-table :deep(.el-table__row) {
  transition: background 0.15s ease;
}
.gv-table :deep(.el-table__row:hover > td) {
  background: #f5f9ff !important;
}
.gv-key {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-weight: 600;
  color: #2b6cff;
}
.gv-value {
  font-family: 'SFMono-Regular', Consolas, monospace;
  background: #f3f5f9;
  color: #344056;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12.5px;
  max-width: 100%;
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.gv-empty-value { color: #c0c4cc; }
.gv-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 36px 0;
  color: #a8b0c0;
}
.gv-empty-icon { font-size: 40px; }

/* 局部环境 header */
.local-env-header {
  margin-bottom: 16px;
  padding: 14px 18px;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 4px 14px rgba(31, 45, 80, 0.05);
  border: 1px solid #eef1f8;
}

/* 对话框 */
.environment-management :deep(.el-dialog) {
  border-radius: 16px;
  overflow: hidden;
}
.environment-management :deep(.el-dialog__header) {
  margin: 0;
  padding: 18px 22px;
  background: linear-gradient(90deg, #2b6cff, #6a5cff);
}
.environment-management :deep(.el-dialog__title) {
  color: #fff;
  font-weight: 600;
}
.environment-management :deep(.el-dialog__headerbtn .el-dialog__close) {
  color: #fff;
}
.environment-management :deep(.el-dialog__body) {
  padding: 22px 24px;
}

/* 变量编辑器 */
.variables-editor {
  border: 1px solid #e6ebf5;
  border-radius: 12px;
  overflow: hidden;
}
.variables-header {
  display: flex;
  background: linear-gradient(90deg, #f3f7ff, #f7f3ff);
  border-bottom: 1px solid #e6ebf5;
  padding: 10px 12px;
  font-weight: 600;
  font-size: 12.5px;
  color: #2b3552;
}
.variables-body { max-height: 320px; overflow-y: auto; }
.variable-row {
  display: flex;
  border-bottom: 1px solid #f2f4f8;
  padding: 10px 12px;
  min-height: 44px;
  align-items: center;
  transition: background 0.15s ease;
}
.variable-row:hover { background: #f8faff; }
.column { flex: 1; display: flex; align-items: center; gap: 8px; padding: 0 4px; }
.column:last-child { flex: 0 0 60px; justify-content: center; }
.variables-footer {
  padding: 10px 12px;
  border-top: 1px solid #f2f4f8;
  background: #fafbff;
}

/* 查看变量 */
.view-variables {
  max-height: 400px;
  overflow-y: auto;
  border-radius: 10px;
}
</style>