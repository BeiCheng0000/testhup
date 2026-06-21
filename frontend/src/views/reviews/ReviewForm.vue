<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ isEdit ? $t('reviewForm.editTitle') : $t('reviewForm.createTitle') }}</h1>
      <div>
        <el-button @click="$router.back()">{{ $t('reviewForm.back') }}</el-button>
        <el-button type="primary" @click="saveReview" :loading="saving">{{ $t('reviewForm.save') }}</el-button>
      </div>
    </div>

    <div class="form-container">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="$t('reviewForm.reviewTitle')" prop="title">
              <el-input v-model="form.title" :placeholder="$t('reviewForm.reviewTitlePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('reviewForm.associatedProject')" prop="projects">
              <el-select
                v-model="form.projects"
                multiple
                :placeholder="$t('reviewForm.selectProject')"
                @change="onProjectChange"
              >
                <el-option
                  v-for="project in projects"
                  :key="project.id"
                  :label="project.name"
                  :value="project.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="$t('reviewForm.priority')" prop="priority">
              <el-select v-model="form.priority" :placeholder="$t('reviewForm.selectPriority')">
                <el-option :label="$t('reviewForm.priorityLow')" value="low" />
                <el-option :label="$t('reviewForm.priorityMedium')" value="medium" />
                <el-option :label="$t('reviewForm.priorityHigh')" value="high" />
                <el-option :label="$t('reviewForm.priorityUrgent')" value="urgent" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('reviewForm.deadline')">
              <el-date-picker
                v-model="form.deadline"
                type="datetime"
                :placeholder="$t('reviewForm.deadlinePlaceholder')"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="$t('reviewForm.description')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            :placeholder="$t('reviewForm.descriptionPlaceholder')"
          />
        </el-form-item>

        <el-form-item :label="$t('reviewForm.selectTestcases')">
          <div class="testcase-selector">
            <el-row :gutter="12" class="module-select-row">
              <el-col :span="12">
                <el-select
                  v-model="selectedVersion"
                  :placeholder="$t('reviewForm.selectVersionPlaceholder')"
                  :disabled="!form.projects || form.projects.length === 0"
                  clearable
                  @change="onVersionChange"
                  style="width: 100%"
                >
                  <el-option
                    v-for="version in availableVersions"
                    :key="version.id"
                    :label="version.name"
                    :value="version.id"
                  />
                </el-select>
              </el-col>
              <el-col :span="12">
                <el-select
                  v-model="selectedModules"
                  multiple
                  :placeholder="$t('reviewForm.selectModulesPlaceholder')"
                  :disabled="!form.projects || form.projects.length === 0"
                  collapse-tags
                  collapse-tags-tooltip
                  :max-collapse-tags="10"
                  @change="onModuleChange"
                  style="width: 100%"
                  popper-class="module-select-popper"
                >
                  <el-option
                    v-for="mod in availableModules"
                    :key="mod"
                    :label="mod"
                    :value="mod"
                  >
                    <span>{{ mod }}</span>
                    <span class="module-option-count">({{ getModuleStatCount(mod) }})</span>
                  </el-option>
                </el-select>
              </el-col>
            </el-row>

            <div v-if="selectedModules.length > 0" class="module-summary">
              <div class="module-tags-wrap">
                <el-tag
                  v-for="mod in selectedModules"
                  :key="mod"
                  type="info"
                  class="module-tag"
                  closable
                  @close="removeModule(mod)"
                >
                  <span class="tag-text">{{ mod }}</span>
                  <span class="tag-count">({{ getSelectedModuleCount(mod) }} {{ $t('reviewForm.cases') }})</span>
                </el-tag>
              </div>
              <div class="total-cases">
                {{ $t('reviewForm.totalCases') }}: <strong>{{ totalSelectedCases }}</strong>
              </div>
            </div>

            <div v-if="selectedModules.length === 0 && form.projects.length > 0" class="empty-tip">
              {{ $t('reviewForm.emptyTestcasesTip') }}
            </div>
          </div>
        </el-form-item>

        <el-form-item :label="$t('reviewForm.reviewers')" prop="reviewers">
          <el-select
            v-model="form.reviewers"
            multiple
            :placeholder="$t('reviewForm.selectReviewers')"
            @change="onReviewersChange"
          >
            <el-option
              v-for="user in projectUsers"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('reviewForm.reviewTemplate')">
          <el-select v-model="form.template" :placeholder="$t('reviewForm.selectTemplate')" @change="applyTemplate">
            <el-option
              v-for="template in templates"
              :key="template.id"
              :label="template.name"
              :value="template.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import api from '@/utils/api'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const isEdit = computed(() => !!route.params.id)

const formRef = ref()
const saving = ref(false)

const projects = ref([])
const projectUsers = ref([])
const templates = ref([])
const testcases = ref([])

// 版本和模块选择
const availableVersions = ref([])
const selectedVersion = ref('')
const availableModules = ref([])
const selectedModules = ref([])

const form = reactive({
  title: '',
  description: '',
  projects: [],
  priority: 'medium',
  deadline: '',
  testcases: [],
  reviewers: [],
  template: ''
})

const rules = computed(() => ({
  title: [{ required: true, message: t('reviewForm.titleRequired'), trigger: 'blur' }],
  projects: [{ required: true, message: t('reviewForm.projectRequired'), trigger: 'change' }],
  reviewers: [{ required: true, message: t('reviewForm.reviewersRequired'), trigger: 'change' }]
}))

// 从已加载的用例中提取去重的模块列表
const extractModules = (cases) => {
  const modules = new Set()
  cases.forEach(c => {
    if (c.module) modules.add(c.module)
  })
  return Array.from(modules).sort()
}

const fetchProjects = async () => {
  try {
    const response = await api.get('/projects/')
    projects.value = response.data.results || response.data
  } catch (error) {
    ElMessage.error(t('reviewForm.fetchProjectsFailed'))
  }
}

const fetchProjectUsers = async () => {
  try {
    const response = await api.get('/auth/users/')
    projectUsers.value = response.data.results || response.data || []
    console.log('All users:', projectUsers.value)
  } catch (error) {
    console.error('Fetch users failed:', error)
    ElMessage.error(t('reviewForm.fetchUsersFailed'))
    projectUsers.value = []
  }
}

const fetchTestcases = async (projectIds, versionId = '') => {
  try {
    if (!projectIds || projectIds.length === 0) {
      testcases.value = []
      availableModules.value = []
      return
    }

    const params = { page_size: 10000 }
    if (versionId) {
      params.version = versionId
    }

    const promises = projectIds.map(projectId =>
      api.get('/testcases/', { params: { project: projectId, ...params } })
    )

    const responses = await Promise.all(promises)
    const allTestcases = []

    responses.forEach(response => {
      const cases = response.data.results || response.data || []
      allTestcases.push(...cases)
    })

    // 去重
    const uniqueTestcases = allTestcases.filter((testcase, index, self) =>
      index === self.findIndex(t => t.id === testcase.id)
    )

    testcases.value = uniqueTestcases
    // 不再在此处设置 availableModules，由 fetchModuleStats 统一管理模块列表
  } catch (error) {
    console.error('Fetch testcases failed:', error)
  }
}

const fetchTemplates = async (projectIds) => {
  try {
    // 如果没有选择项目，清空模板列表
    if (!projectIds || projectIds.length === 0) {
      templates.value = []
      return
    }

    // 获取所有选中项目的模板
    const promises = projectIds.map(projectId =>
      api.get('/reviews/review-templates/', { params: { project: projectId } })
    )

    const responses = await Promise.all(promises)
    const allTemplates = []

    responses.forEach(response => {
      const temps = response.data.results || response.data || []
      allTemplates.push(...temps)
    })

    // 去重（基于模板ID）
    const uniqueTemplates = allTemplates.filter((template, index, self) =>
      index === self.findIndex(t => t.id === template.id)
    )

    templates.value = uniqueTemplates
  } catch (error) {
    console.error('Fetch templates failed:', error)
  }
}

const fetchVersions = async (projectIds) => {
  if (!projectIds || projectIds.length === 0) {
    availableVersions.value = []
    return
  }

  try {
    const promises = projectIds.map(projectId =>
      api.get(`/versions/projects/${projectId}/versions/`)
    )
    const responses = await Promise.all(promises)
    const allVersions = []
    responses.forEach(response => {
      const vers = response.data.results || response.data || []
      allVersions.push(...vers)
    })
    // 去重
    availableVersions.value = allVersions.filter((v, i, self) =>
      i === self.findIndex(t => t.id === v.id)
    )
  } catch (error) {
    console.error('Fetch versions failed:', error)
    availableVersions.value = []
  }
}

const onProjectChange = (projectIds) => {
  // 清空版本、模块和用例相关选择
  selectedVersion.value = ''
  selectedModules.value = []
  availableVersions.value = []
  availableModules.value = []
  moduleCaseCountMap.value = {}
  form.reviewers = []

  if (projectIds && projectIds.length > 0) {
    fetchVersions(projectIds)
    fetchTestcases(projectIds)
    fetchModuleStats(projectIds)
    fetchTemplates(projectIds)
  } else {
    testcases.value = []
    templates.value = []
  }
}

const onVersionChange = () => {
  selectedModules.value = []
  moduleCaseCountMap.value = {}
  if (form.projects && form.projects.length > 0) {
    fetchTestcases(form.projects, selectedVersion.value)
    fetchModuleStats(form.projects)
  }
}

// 下拉框中显示的模块可用用例数（来自所有已加载用例）
const getModuleCaseCount = (moduleName) => {
  return testcases.value.filter(tc => tc.module === moduleName).length
}

// 标签中显示的已选中模块的用例数（来自API统计）
const getSelectedModuleCount = (moduleName) => {
  // 优先使用 API 统计的模块用例数
  if (moduleCaseCountMap.value[moduleName] !== undefined) {
    return moduleCaseCountMap.value[moduleName]
  }
  return 0
}

// 总计已选中用例数（来自API统计，不限于已加载的用例）
const totalSelectedCases = computed(() => {
  return selectedModules.value.reduce((sum, mod) => {
    return sum + (moduleCaseCountMap.value[mod] || 0)
  }, 0)
})

// 模块统计载入状态
const moduleStatsLoading = ref(false)

// 通过API获取模块统计数据（按项目+版本）
const fetchModuleStats = async (projectIds) => {
  if (!projectIds || projectIds.length === 0) {
    availableModules.value = []
    return
  }
  moduleStatsLoading.value = true
  try {
    const params = {}
    if (selectedVersion.value) {
      params.version = selectedVersion.value
    }
    const promises = projectIds.map(projectId =>
      api.get('/testcases/module-stats/', { params: { project: projectId, ...params } })
    )
    const responses = await Promise.all(promises)

    // 合并多个项目的模块统计
    const moduleCountMap = {}
    responses.forEach(response => {
      const data = response.data
      if (data.modules) {
        data.modules.forEach(m => {
          if (moduleCountMap[m.module]) {
            moduleCountMap[m.module] += m.count
          } else {
            moduleCountMap[m.module] = m.count
          }
        })
      }
    })

    // 按模块名排序
    const sortedModules = Object.keys(moduleCountMap).sort()
    availableModules.value = sortedModules
    // 缓存模块用例数映射
    moduleCaseCountMap.value = moduleCountMap
  } catch (error) {
    console.error('Fetch module stats failed:', error)
    // 降级：从已加载用例中提取模块（仅当测试用例已加载时有意义）
    if (testcases.value.length > 0) {
      availableModules.value = extractModules(testcases.value)
    }
  } finally {
    moduleStatsLoading.value = false
  }
}

// 缓存模块->用例数映射
const moduleCaseCountMap = ref({})

// 获取模块用例数（优先从统计API获取）
const getModuleStatCount = (moduleName) => {
  if (moduleCaseCountMap.value[moduleName] !== undefined) {
    return moduleCaseCountMap.value[moduleName]
  }
  // 降级
  return testcases.value.filter(tc => tc.module === moduleName).length
}

const onModuleChange = () => {
  // 不再将用例ID填入 form.testcases，保存时只发送模块名
  // 用例总数和统计由 moduleCaseCountMap（API统计）提供
}

const removeModule = (moduleName) => {
  selectedModules.value = selectedModules.value.filter(m => m !== moduleName)
  onModuleChange()
}

const onReviewersChange = () => {
  // 可以在这里添加评审人员变更的逻辑
}

const applyTemplate = async (templateId) => {
  if (!templateId) return

  try {
    const template = templates.value.find(t => t.id === templateId)
    if (template) {
      // 应用模板的默认评审人员
      form.reviewers = template.default_reviewers.map(u => u.id)
    }
  } catch (error) {
    console.error('Apply template failed:', error)
  }
}

const saveReview = async () => {
  if (!formRef.value) return

  // 模块校验
  if (selectedModules.value.length === 0) {
    ElMessage.warning(t('reviewForm.testcasesRequired'))
    return
  }

  try {
    await formRef.value.validate()
    saving.value = true

    const data = {
      title: form.title,
      description: form.description,
      projects: form.projects,
      priority: form.priority,
      deadline: form.deadline,
      modules: selectedModules.value,
      reviewers: form.reviewers,
      template: form.template || null
    }

    if (isEdit.value) {
      await api.put(`/reviews/reviews/${route.params.id}/`, data)
      ElMessage.success(t('reviewForm.updateSuccess'))
    } else {
      await api.post('/reviews/reviews/', data)
      ElMessage.success(t('reviewForm.createSuccess'))
    }

    router.push('/ai-generation/reviews')

  } catch (error) {
    if (error.response?.data) {
      const errors = Object.values(error.response.data).flat()
      ElMessage.error(errors[0] || t('reviewForm.saveFailed'))
    } else {
      ElMessage.error(t('reviewForm.saveFailed'))
    }
  } finally {
    saving.value = false
  }
}

const findMatchingTemplate = (review, templateList) => {
  if (!templateList || templateList.length === 0) return null

  // 获取评审的项目ID列表和评审人ID列表
  const reviewProjectIds = review.projects.map(p => p.id).sort()
  const reviewReviewerIds = review.assignments.map(a => a.reviewer.id).sort()

  let bestMatch = null
  let bestScore = 0

  for (const template of templateList) {
    let score = 0

    // 检查项目匹配度
    const templateProjectIds = (template.project || []).map(p => p.id).sort()
    const projectIntersection = reviewProjectIds.filter(id => templateProjectIds.includes(id))
    if (projectIntersection.length > 0) {
      score += projectIntersection.length * 2 // 项目匹配权重更高
    }

    // 检查默认评审人匹配度
    const templateReviewerIds = (template.default_reviewers || []).map(r => r.id).sort()
    const reviewerIntersection = reviewReviewerIds.filter(id => templateReviewerIds.includes(id))
    if (reviewerIntersection.length > 0) {
      score += reviewerIntersection.length // 评审人匹配
    }

    // 如果有更高的匹配分数，更新最佳匹配
    if (score > bestScore) {
      bestScore = score
      bestMatch = template
    }
  }

  // 只有当匹配分数大于0时才返回匹配的模板
  return bestScore > 0 ? bestMatch : null
}

const fetchReviewData = async (reviewId) => {
  try {
    const response = await api.get(`/reviews/reviews/${reviewId}/`)
    const review = response.data

    // 填充表单数据
    form.title = review.title
    form.description = review.description
    form.projects = review.projects.map(p => p.id)
    form.priority = review.priority
    form.deadline = review.deadline
    form.reviewers = review.assignments.map(a => a.reviewer.id)

    // 处理测试用例 - 从 review.modules 读取已选模块
    if (review.modules && review.modules.length > 0) {
      selectedModules.value = [...review.modules]
    } else {
      // 兼容旧数据：从已有用例提取模块
      selectedModules.value = extractModules(review.testcases)
    }

    // 加载项目相关数据
    if (form.projects.length > 0) {
      await fetchVersions(form.projects)
      await fetchTestcases(form.projects)
      await fetchModuleStats(form.projects)
      await fetchTemplates(form.projects)

      // 在模板加载完成后，尝试找到匹配的模板
      const matchingTemplate = findMatchingTemplate(review, templates.value)
      if (matchingTemplate) {
        form.template = matchingTemplate.id
      }
    }

  } catch (error) {
    console.error('Fetch review data failed:', error)
    ElMessage.error(t('reviewForm.fetchReviewFailed'))
    router.push('/ai-generation/reviews')
  }
}

onMounted(async () => {
  await fetchProjects()
  fetchProjectUsers() // 页面加载时就获取所有用户

  if (isEdit.value) {
    // 如果是编辑模式，加载现有数据
    fetchReviewData(route.params.id)
  } else {
    // 创建模式，检查是否有模板参数
    const templateId = route.query.template
    if (templateId) {
      try {
        // 获取模板详情
        const response = await api.get(`/reviews/review-templates/${templateId}/`)
        const template = response.data

        // 设置模板ID到表单
        form.template = parseInt(templateId)

        // 自动填充项目
        if (template.project && template.project.length > 0) {
          form.projects = template.project.map(p => p.id)

          // 触发项目变更，加载对应的用例和模板
          await onProjectChange(form.projects)

          // 应用模板的默认评审人
          if (template.default_reviewers && template.default_reviewers.length > 0) {
            form.reviewers = template.default_reviewers.map(u => u.id)
          }
        }
      } catch (error) {
        console.error('加载模板失败:', error)
      }
    }
  }
})
</script>

<style lang="scss" scoped>
.testcase-selector {
  .module-select-row {
    margin-bottom: 12px;
  }

  .module-summary {
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    padding: 8px;
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 8px;
    max-height: 300px;
    overflow-y: auto;

    .module-tags-wrap {
      flex: 1;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-content: flex-start;
    }

    .module-tag {
      margin: 0;
      max-width: 100%;
      display: inline-flex;
      align-items: center;

      .tag-text {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .tag-count {
        flex-shrink: 0;
        margin-left: 2px;
      }
    }

    .total-cases {
      flex-shrink: 0;
      font-size: 13px;
      color: #606266;
      padding: 4px 12px;
      background: #f5f7fa;
      border-radius: 4px;
      margin-top: 2px;

      strong {
        color: #409eff;
        font-size: 16px;
      }
    }
  }

  .empty-tip {
    color: #909399;
    text-align: center;
    padding: 24px;
    border: 1px dashed #dcdfe6;
    border-radius: 4px;
  }
}
</style>

<style lang="scss">
.module-select-popper {
  .el-select-dropdown__list {
    max-height: 400px;
  }

  .el-select-dropdown__item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: auto;
    line-height: 1.5;
    padding: 8px 20px;
  }

  .module-option-count {
    flex-shrink: 0;
    margin-left: 8px;
    font-size: 12px;
    color: #909399;
  }
}
</style>
