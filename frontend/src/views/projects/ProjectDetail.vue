<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('project.projectDetail') }}</h1>
      <el-button type="primary" @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon>
        {{ $t('common.back') }}
      </el-button>
    </div>

    <div class="card-container">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane :label="$t('project.projectInfo')" name="info">
          <div v-if="project">
            <el-descriptions :column="2" border>
              <el-descriptions-item :label="$t('project.projectName')">{{ project.name }}</el-descriptions-item>
              <el-descriptions-item :label="$t('project.status')">
                <el-tag :type="getStatusType(project.status)">{{ getStatusText(project.status) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('project.owner')">{{ project.owner?.username }}</el-descriptions-item>
              <el-descriptions-item :label="$t('project.createdAt')">{{ formatDate(project.created_at) }}</el-descriptions-item>
              <el-descriptions-item :label="$t('project.projectDescription')" :span="2">{{ project.description || $t('project.noDescription') }}</el-descriptions-item>
            </el-descriptions>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="$t('project.projectMembers')" name="members">
          <div class="members-section">
            <el-button type="primary" @click="openAddMemberDialog">
              <el-icon><Plus /></el-icon>
              {{ $t('project.addMember') }}
            </el-button>
            <el-table :data="members" style="width: 100%; margin-top: 20px;" v-loading="loadingMembers">
              <el-table-column prop="username" label="用户名" />
              <el-table-column prop="email" label="邮箱" />
              <el-table-column prop="role" label="角色">
                <template #default="{ row }">
                  <el-tag :type="getRoleTagType(row.role)">{{ getRoleText(row.role) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button 
                    v-if="row.role !== 'owner'" 
                    size="small" 
                    type="danger" 
                    @click="removeMember(row)"
                  >
                    移除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="$t('project.environments')" name="environments">
          <div class="environments-section">
            <el-button type="primary" @click="showAddEnvDialog = true">{{ $t('project.addEnvironment') }}</el-button>
            <el-table :data="project?.environments || []" style="width: 100%; margin-top: 20px;">
              <el-table-column prop="name" :label="$t('project.environmentName')" />
              <el-table-column prop="base_url" :label="$t('project.baseUrl')" />
              <el-table-column prop="description" :label="$t('project.description')" />
              <el-table-column prop="is_default" :label="$t('project.defaultEnvironment')">
                <template #default="{ row }">
                  <el-tag v-if="row.is_default" type="success">{{ $t('project.yes') }}</el-tag>
                  <span v-else>{{ $t('project.no') }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 添加成员对话框 -->
    <el-dialog v-model="showAddMemberDialog" title="添加项目成员" width="500px">
      <el-form :model="addMemberForm" label-width="80px">
        <el-form-item label="选择用户">
          <el-select 
            v-model="addMemberForm.user_id" 
            filterable 
            remote
            reserve-keyword
            placeholder="搜索用户名或邮箱"
            :remote-method="searchUsers"
            :loading="searchingUsers"
            style="width: 100%"
          >
            <el-option 
              v-for="user in userOptions" 
              :key="user.id" 
              :label="`${user.username} (${user.email || '无邮箱'})`" 
              :value="user.id"
              :disabled="existingMemberIds.includes(user.id)"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="addMemberForm.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="开发者" value="developer" />
            <el-option label="测试者" value="tester" />
            <el-option label="观察者" value="viewer" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddMemberDialog = false">取消</el-button>
        <el-button type="primary" :loading="addingMember" @click="addMember">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '@/utils/api'
import dayjs from 'dayjs'

const route = useRoute()
const { t } = useI18n()
const project = ref(null)
const members = ref([])
const loadingMembers = ref(false)
const activeTab = ref('info')
const showAddMemberDialog = ref(false)
const showAddEnvDialog = ref(false)

// 添加成员相关
const addMemberForm = ref({ user_id: null, role: 'tester' })
const userOptions = ref([])
const searchingUsers = ref(false)
const addingMember = ref(false)

const existingMemberIds = computed(() => members.value.map(m => m.user_id !== undefined ? m.user_id : m.id))

const fetchProject = async () => {
  try {
    const response = await api.get(`/projects/${route.params.id}/`)
    project.value = response.data
  } catch (error) {
    ElMessage.error(t('project.fetchDetailFailed'))
  }
}

const fetchMembers = async () => {
  loadingMembers.value = true
  try {
    const response = await api.get(`/projects/${route.params.id}/members/`)
    members.value = response.data || []
  } catch (error) {
    ElMessage.error('获取成员列表失败')
  } finally {
    loadingMembers.value = false
  }
}

const handleTabChange = (tabName) => {
  if (tabName === 'members') {
    fetchMembers()
  }
}

const searchUsers = async (query) => {
  if (!query || query.length < 1) {
    userOptions.value = []
    return
  }
  searchingUsers.value = true
  try {
    const response = await api.get('/users/users/', { params: { search: query } })
    userOptions.value = response.data?.results || response.data || []
  } catch (error) {
    ElMessage.error('搜索用户失败')
  } finally {
    searchingUsers.value = false
  }
}

const openAddMemberDialog = () => {
  addMemberForm.value = { user_id: null, role: 'tester' }
  userOptions.value = []
  showAddMemberDialog.value = true
}

const addMember = async () => {
  if (!addMemberForm.value.user_id) {
    ElMessage.warning('请选择用户')
    return
  }
  addingMember.value = true
  try {
    await api.post(`/projects/${route.params.id}/members/add/`, {
      user_id: addMemberForm.value.user_id,
      role: addMemberForm.value.role
    })
    ElMessage.success('成员添加成功')
    showAddMemberDialog.value = false
    fetchMembers()
  } catch (error) {
    const errMsg = error.response?.data?.error || '添加成员失败'
    ElMessage.error(errMsg)
  } finally {
    addingMember.value = false
  }
}

const removeMember = async (member) => {
  try {
    await api.delete(`/projects/${route.params.id}/members/${member.id}/`)
    ElMessage.success('成员已移除')
    fetchMembers()
  } catch (error) {
    ElMessage.error('移除成员失败')
  }
}

const getStatusType = (status) => {
  const typeMap = {
    active: 'success',
    paused: 'warning',
    completed: 'info',
    archived: 'info'
  }
  return typeMap[status] || 'info'
}

const getStatusText = (status) => {
  const textMap = {
    active: t('project.active'),
    paused: t('project.paused'),
    completed: t('project.completed'),
    archived: t('project.archived')
  }
  return textMap[status] || status
}

const getRoleTagType = (role) => {
  const typeMap = { owner: 'danger', admin: 'warning', developer: 'success', tester: '', viewer: 'info' }
  return typeMap[role] || 'info'
}

const getRoleText = (role) => {
  const textMap = { owner: '负责人', admin: '管理员', developer: '开发者', tester: '测试者', viewer: '观察者' }
  return textMap[role] || role
}

const formatDate = (dateString) => {
  return dayjs(dateString).format('YYYY-MM-DD HH:mm')
}

onMounted(() => {
  fetchProject()
})
</script>

<style lang="scss" scoped>
.members-section, .environments-section {
  padding: 20px 0;
}
</style>