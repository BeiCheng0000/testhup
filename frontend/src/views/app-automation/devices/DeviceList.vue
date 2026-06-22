<template>
  <div class="device-management">
    <!-- 页面标题和操作按钮 -->
    <div class="device-header">
      <h3>设备管理</h3>
      <div class="device-actions">
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="refreshing"
          @click="refreshDevices"
        >
          刷新设备
        </el-button>
        <el-button
          type="success"
          :icon="Plus"
          @click="showAddRemoteDialog"
        >
          添加远程设备
        </el-button>
        <el-button
          type="default"
          :icon="Monitor"
          @click="showAgentDialog = true"
        >
          远程设备代理
          <el-badge
            v-if="agentHosts.length > 0"
            :value="agentHosts.length"
            type="success"
            style="margin-left: 6px"
          />
        </el-button>
      </div>
    </div>

    <!-- Agent 远程设备代理 - 弹窗 -->
    <el-dialog
      v-model="showAgentDialog"
      title="远程设备代理 (Agent)"
      width="680px"
      :close-on-click-modal="false"
    >
      <!-- Agent 在线状态 -->
      <div v-if="agentHosts.length > 0" style="margin-bottom: 20px">
        <el-alert type="success" :closable="false" show-icon>
          <template #title>
            已连接 <strong>{{ agentHosts.length }}</strong> 台 Agent 主机，
            共 <strong>{{ agentDeviceCount }}</strong> 台设备
          </template>
        </el-alert>
        <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px">
          <el-tag
            v-for="host in agentHosts"
            :key="host.host_id"
            type="success"
            size="default"
            effect="plain"
          >
            <el-icon style="margin-right: 4px"><Monitor /></el-icon>
            {{ host.host_id }}
            <span style="opacity: 0.7">({{ host.device_count_display || 0 }}台)</span>
          </el-tag>
        </div>
      </div>

      <div v-else style="margin-bottom: 20px">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            暂无 Agent 主机连接，请按照下方指南在远程主机上部署 Agent
          </template>
        </el-alert>
      </div>

      <!-- 安装引导 -->
      <el-divider content-position="left">
        <strong>远程主机安装指南</strong>
      </el-divider>

      <div class="agent-setup-steps">
        <!-- Step 1: 下载 Agent -->
        <div class="setup-step">
          <el-tag type="primary" size="small" round>1</el-tag>
          <span style="font-weight: 500; margin-left: 8px">下载 Agent 脚本</span>
          <el-button size="small" type="primary" plain style="margin-left: 12px" @click="downloadAgent">
            <el-icon><Download /></el-icon>
            下载 adb_agent.py
          </el-button>
          <el-button size="small" style="margin-left: 4px" @click="downloadAgentRequirements">
            <el-icon><Download /></el-icon>
            依赖文件
          </el-button>
        </div>

        <!-- Step 2: 安装依赖 -->
        <div class="setup-step">
          <el-tag type="primary" size="small" round>2</el-tag>
          <span style="font-weight: 500; margin-left: 8px">安装 Python 依赖</span>
          <el-tooltip content="点击复制命令" placement="top">
            <code class="copy-cmd" @click="copyAgentInstallCmd">
              pip install -r requirements-agent.txt
            </code>
          </el-tooltip>
          <el-button size="small" text style="margin-left: 4px" @click="copyAgentInstallCmd">
            <el-icon><CopyDocument /></el-icon>
          </el-button>
        </div>

        <!-- Step 3: 启动 Agent -->
        <div class="setup-step">
          <el-tag type="primary" size="small" round>3</el-tag>
          <span style="font-weight: 500; margin-left: 8px">启动 Agent（远程主机执行）</span>
          <el-tooltip content="点击复制命令" placement="top">
            <code class="copy-cmd" @click="copyAgentRunCmd">
              {{ agentRunCmd }}
            </code>
          </el-tooltip>
          <el-button size="small" text style="margin-left: 4px" @click="copyAgentRunCmd">
            <el-icon><CopyDocument /></el-icon>
          </el-button>
        </div>

        <!-- 提示 -->
        <el-alert type="info" :closable="false" style="margin-top: 12px" show-icon>
          <template #title>
            <span style="font-size: 12px">
              将以上文件复制到<strong>拥有 Android 设备的远程主机</strong>上执行。
              启动后设备将自动显示在下方设备列表中。
              要求：远程主机已安装 Python 3.7+ 和 ADB 工具。
            </span>
          </template>
        </el-alert>
      </div>
    </el-dialog>

    <!-- 状态筛选栏 -->
    <el-card shadow="never" style="margin-top: 16px">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <span style="font-size: 13px; color: #606266; margin-right: 8px">设备状态：</span>
          <el-checkbox-group v-model="statusFilters" @change="onFilterChange" size="small">
            <el-checkbox label="online">在线</el-checkbox>
            <el-checkbox label="available">可用</el-checkbox>
            <el-checkbox label="locked">已锁定</el-checkbox>
            <el-checkbox label="offline">离线</el-checkbox>
          </el-checkbox-group>
        </el-col>
        <el-col :span="4">
          <span style="font-size: 13px; color: #606266; margin-right: 8px">连接类型：</span>
          <el-select 
            v-model="connectionTypeFilter" 
            placeholder="全部" 
            clearable 
            size="small" 
            style="width: 120px"
            @change="onFilterChange"
          >
            <el-option label="USB连接" value="usb" />
            <el-option label="远程设备" value="remote" />
            <el-option label="本地模拟器" value="emulator" />
            <el-option label="远程模拟器" value="remote_emulator" />
            <el-option label="Agent代理" value="agent_device" />
          </el-select>
        </el-col>
        <el-col :span="14" style="text-align: right">
          <span style="font-size: 12px; color: #909399">
            共 {{ devices.length }} 台设备
            <template v-if="statusFilters.length > 0 || connectionTypeFilter">
              （已筛选）
            </template>
          </span>
        </el-col>
      </el-row>
    </el-card>

    <!-- 设备列表 -->
    <el-table
      v-loading="loading"
      :data="devices"
      style="width: 100%; margin-top: 12px"
      :empty-text="emptyText"
    >
      <el-table-column prop="name" label="设备名称" min-width="150">
        <template #default="{ row }">
          <span>{{ row.name || row.device_id }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="device_id" label="设备序列号" min-width="180" />

      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="locked_by" label="锁定用户" width="120">
        <template #default="{ row }">
          <span v-if="row.locked_by_name">
            {{ row.locked_by_name }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column prop="locked_at" label="锁定时间" width="180">
        <template #default="{ row }">
          <span v-if="row.locked_at">
            {{ formatDate(row.locked_at) }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column prop="android_version" label="Android版本" width="120" />

      <el-table-column prop="connection_type" label="连接类型" width="120">
        <template #default="{ row }">
          <el-tag
            :type="getConnectionTypeTag(row.connection_type)"
            size="small"
          >
            {{ getConnectionTypeName(row.connection_type) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="ip_address" label="IP地址" width="150">
        <template #default="{ row }">
          <span v-if="row.ip_address">
            {{ row.ip_address }}
            <el-tag v-if="row.connection_type === 'agent_device'" type="info" size="small" style="margin-left: 4px">
              远程
            </el-tag>
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column label="Agent主机" width="160">
        <template #default="{ row }">
          <span v-if="row.agent_host_info">
            <span style="font-size: 12px;">
              {{ row.agent_host_info.host_id }}
            </span>
            <br/>
            <span style="font-size: 11px; color: #909399;">
              {{ row.agent_host_info.ip_address }}
              <el-tag :type="row.agent_host_info.status === 'online' ? 'success' : 'info'" size="small" style="margin-left: 4px">
                {{ row.agent_host_info.status === 'online' ? '在线' : '离线' }}
              </el-tag>
            </span>
          </span>
          <span v-else-if="row.connection_type === 'agent_device'" style="color: #909399; font-size: 12px;">
            Agent离线
          </span>
          <span v-else style="color: #c0c4cc;">-</span>
        </template>
      </el-table-column>

      <el-table-column prop="usage_count" label="使用次数" width="100" />

      <el-table-column prop="updated_at" label="更新时间" width="180">
        <template #default="{ row }">
          {{ formatDate(row.updated_at) }}
        </template>
      </el-table-column>

      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'available' || row.status === 'online'"
            link
            size="small"
            type="primary"
            @click="lockDevice(row)"
          >
            锁定
          </el-button>
          <el-button
            v-if="row.status === 'locked'"
            link
            size="small"
            type="success"
            @click="unlockDevice(row)"
          >
            解锁
          </el-button>
          <el-button
            v-if="isRemoteDevice(row.connection_type) && row.status === 'offline'"
            link
            size="small"
            type="warning"
            :loading="reconnectingDevices[row.id]"
            @click="reconnectDevice(row)"
          >
            重连
          </el-button>
          <el-button
            link
            size="small"
            @click="viewDeviceInfo(row)"
          >
            详情
          </el-button>
          <el-button
            v-if="isRemoteDevice(row.connection_type) && (row.status === 'online' || row.status === 'available')"
            link
            size="small"
            type="warning"
            @click="disconnectDevice(row)"
          >
            断开
          </el-button>
          <el-button
            link
            size="small"
            type="danger"
            @click="handleDeleteDevice(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 添加远程设备对话框 -->
    <el-dialog
      v-model="addRemoteDialogVisible"
      title="添加远程设备"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="remoteDeviceFormRef"
        :model="remoteDeviceForm"
        :rules="remoteDeviceRules"
        label-width="100px"
      >
        <el-form-item label="IP地址" prop="ip_address">
          <el-input
            v-model="remoteDeviceForm.ip_address"
            placeholder="请输入远程设备IP地址"
          />
        </el-form-item>

        <el-form-item label="端口" prop="port">
          <el-input-number
            v-model="remoteDeviceForm.port"
            :min="1"
            :max="65535"
            placeholder="默认5555"
            style="width: 100%"
          />
        </el-form-item>

        <el-alert
          title="提示"
          type="info"
          :closable="false"
          style="margin-top: 10px"
        >
          <div>请确保：</div>
          <div>1. 远程设备已开启ADB调试</div>
          <div>2. 远程设备已开启网络ADB（adb tcpip 5555）</div>
          <div>3. 网络连接正常</div>
        </el-alert>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="addRemoteDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="connecting"
            @click="connectRemoteDevice"
          >
            连接
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 设备详情对话框 -->
    <el-dialog
      v-model="deviceInfoDialogVisible"
      title="设备详情"
      width="600px"
    >
      <el-descriptions v-if="selectedDevice" :column="2" border>
        <el-descriptions-item label="设备名称">
          {{ selectedDevice.name || selectedDevice.device_id }}
        </el-descriptions-item>
        <el-descriptions-item label="设备序列号">
          {{ selectedDevice.device_id }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(selectedDevice.status)" size="small">
            {{ getStatusText(selectedDevice.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="锁定用户">
          {{ selectedDevice.locked_by_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="锁定时间">
          {{ selectedDevice.locked_at ? formatDate(selectedDevice.locked_at) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="Android版本">
          {{ selectedDevice.android_version || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="连接类型">
          <el-tag
            :type="getConnectionTypeTag(selectedDevice.connection_type)"
            size="small"
          >
            {{ getConnectionTypeName(selectedDevice.connection_type) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="IP地址">
          {{ selectedDevice.ip_address || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="端口">
          {{ selectedDevice.port || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="selectedDevice.agent_host_info" label="Agent主机">
          {{ selectedDevice.agent_host_info.host_id }}
          ({{ selectedDevice.agent_host_info.ip_address }})
        </el-descriptions-item>
        <el-descriptions-item label="使用次数">
          {{ selectedDevice.usage_count || 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatDate(selectedDevice.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="更新时间">
          {{ formatDate(selectedDevice.updated_at) }}
        </el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="deviceInfoDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Monitor, Download, CopyDocument } from '@element-plus/icons-vue'
import {
  getDeviceList,
  discoverDevices,
  lockDevice as apiLockDevice,
  unlockDevice as apiUnlockDevice,
  connectDevice,
  disconnectDevice as apiDisconnectDevice,
  deleteDevice,
  getAgentHosts,
  agentSync,
  getAgentDownloadUrl,
  getAgentRequirementsUrl
} from '@/api/app-automation'
import { getDeviceStatusType, getDeviceStatusText, formatDateTime } from '@/utils/app-automation-helpers'

// Refs
const remoteDeviceFormRef = ref(null)

// 响应式数据
const devices = ref([])
const loading = ref(false)
const refreshing = ref(false)
const connecting = ref(false)
const reconnectingDevices = ref({})
const addRemoteDialogVisible = ref(false)
const deviceInfoDialogVisible = ref(false)
const selectedDevice = ref(null)
const emptyText = ref('暂无设备，请点击刷新设备或添加远程设备')
const refreshTimer = ref(null)

// 筛选条件
const statusFilters = ref(['online', 'available', 'locked'])
const connectionTypeFilter = ref('')

const remoteDeviceForm = ref({
  ip_address: '',
  port: 5555
})

const remoteDeviceRules = {
  ip_address: [
    { required: true, message: '请输入IP地址', trigger: 'blur' },
    {
      pattern: /^(\d{1,3}\.){3}\d{1,3}$/,
      message: '请输入有效的IP地址',
      trigger: 'blur'
    }
  ],
  port: [
    { required: true, message: '请输入端口号', trigger: 'blur' }
  ]
}

// ========== Agent 远程代理相关 ==========
const showAgentDialog = ref(false)
const agentHosts = ref([])

const agentDeviceCount = computed(() => {
  return agentHosts.value.reduce((sum, h) => sum + (h.device_count_display || h.device_count || 0), 0)
})

const agentRunCmd = computed(() => {
  const origin = window.location.origin
  const wsUrl = origin.replace(/^http/, 'ws')
  return `python adb_agent.py --server ${wsUrl}`
})

const fetchAgentHosts = async () => {
  try {
    const res = await getAgentHosts()
    if (res.data && res.data.data) {
      agentHosts.value = res.data.data
    }
  } catch (e) {
    // 静默失败，Agent 端点在新部署前可能不可用
    console.debug('获取 Agent 主机列表失败:', e)
  }
}

const downloadAgent = () => {
  window.open(getAgentDownloadUrl(), '_blank')
  ElMessage.success('正在下载 adb_agent.py')
}

const downloadAgentRequirements = () => {
  window.open(getAgentRequirementsUrl(), '_blank')
  ElMessage.success('正在下载 requirements-agent.txt')
}

const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    // fallback
    const el = document.createElement('textarea')
    el.value = text
    document.body.appendChild(el)
    el.select()
    document.execCommand('copy')
    document.body.removeChild(el)
    ElMessage.success('已复制到剪贴板')
  }
}

const copyAgentInstallCmd = () => {
  copyToClipboard('pip install -r requirements-agent.txt')
}

const copyAgentRunCmd = () => {
  copyToClipboard(agentRunCmd.value)
}

// 方法
const buildFilterParams = () => {
  const params = { page: 1, page_size: 1000 }
  // 状态筛选：后端DjangoFilterBackend支持逗号分隔多值
  if (statusFilters.value.length > 0 && statusFilters.value.length < 4) {
    // 如果选了全部4种状态则不下发筛选，避免URL过长
    params.status = statusFilters.value.join(',')
  }
  if (connectionTypeFilter.value) {
    params.connection_type = connectionTypeFilter.value
  }
  return params
}

const onFilterChange = () => {
  getDevices()
}

const getDevices = async () => {
  loading.value = true
  try {
    const params = buildFilterParams()
    const res = await getDeviceList(params)
    devices.value = res.data.results || []
    if (devices.value.length === 0) {
      emptyText.value = '暂无设备，请点击刷新设备或添加远程设备'
    }
  } catch (error) {
    console.error('获取设备列表失败:', error)
    ElMessage.error('获取设备列表失败: ' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const refreshDevices = async () => {
  refreshing.value = true
  try {
    const res = await discoverDevices()
    if (res.data.success) {
      // 刷新完成后按筛选条件重新获取（确保展示经过筛选的设备）
      await getDevices()
      ElMessage.success(res.data.message || '设备列表已刷新')
    } else {
      ElMessage.error(res.data.message || '刷新设备列表失败')
    }
  } catch (error) {
    console.error('刷新设备列表失败:', error)
    ElMessage.error('刷新设备列表失败: ' + (error.message || '未知错误'))
  } finally {
    refreshing.value = false
  }
}

const showAddRemoteDialog = () => {
  addRemoteDialogVisible.value = true
  remoteDeviceForm.value = {
    ip_address: '',
    port: 5555
  }
  if (remoteDeviceFormRef.value) {
    remoteDeviceFormRef.value.clearValidate()
  }
}

const connectRemoteDevice = async () => {
  if (!remoteDeviceFormRef.value) return
  
  remoteDeviceFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    connecting.value = true
    try {
      const res = await connectDevice({
        ip_address: remoteDeviceForm.value.ip_address,
        port: remoteDeviceForm.value.port
      })
      
      if (res.data.success) {
        ElMessage.success(res.data.message || '远程设备连接成功')
        addRemoteDialogVisible.value = false
        await getDevices()
      } else {
        ElMessage.error(res.data.message || '连接远程设备失败')
      }
    } catch (error) {
      console.error('连接远程设备失败:', error)
      ElMessage.error('连接远程设备失败: ' + (error.message || '未知错误'))
    } finally {
      connecting.value = false
    }
  })
}

const reconnectDevice = async (device) => {
  if (!device.ip_address || !device.port) {
    ElMessage.error('设备信息不完整，无法重连')
    return
  }

  reconnectingDevices.value[device.id] = true
  
  try {
    const res = await connectDevice({
      ip_address: device.ip_address,
      port: device.port
    })

    if (res.data.success) {
      ElMessage.success('设备重连成功')
      await getDevices()
    } else {
      ElMessage.error(res.data.message || '设备重连失败，请检查设备网络连接')
    }
  } catch (error) {
    console.error('设备重连失败:', error)
    ElMessage.error('设备重连失败，请检查设备网络连接')
  } finally {
    reconnectingDevices.value[device.id] = false
  }
}

const disconnectDevice = async (device) => {
  try {
    await ElMessageBox.confirm(
      `确定要断开设备 ${device.name || device.device_id} 的连接吗？`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const res = await apiDisconnectDevice(device.id)

    if (res.data.success) {
      ElMessage.success('设备已断开')
      await getDevices()
    } else {
      ElMessage.error(res.data.message || '断开设备失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('断开设备失败:', error)
      ElMessage.error('断开设备失败: ' + (error.message || '未知错误'))
    }
  }
}

const viewDeviceInfo = (device) => {
  selectedDevice.value = device
  deviceInfoDialogVisible.value = true
}

const lockDevice = async (device) => {
  try {
    await ElMessageBox.confirm(
      `确定要锁定设备 ${device.name || device.device_id} 吗？`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const res = await apiLockDevice(device.id)

    if (res.data.success) {
      ElMessage.success('设备已锁定')
      await getDevices()
    } else {
      ElMessage.error(res.data.message || '锁定设备失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('锁定设备失败:', error)
      ElMessage.error('锁定设备失败: ' + (error.message || '未知错误'))
    }
  }
}

const unlockDevice = async (device) => {
  try {
    await ElMessageBox.confirm(
      `确定要解锁设备 ${device.name || device.device_id} 吗？`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const res = await apiUnlockDevice(device.id)

    if (res.data.success) {
      ElMessage.success('设备已解锁')
      await getDevices()
    } else {
      ElMessage.error(res.data.message || '解锁设备失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('解锁设备失败:', error)
      ElMessage.error('解锁设备失败: ' + (error.message || '未知错误'))
    }
  }
}

const handleDeleteDevice = async (device) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除设备 ${device.name || device.device_id} 吗？删除后将无法恢复。`,
      '删除设备',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: false
      }
    )

    const res = await deleteDevice(device.id)

    if (res.status === 204 || res.status === 200) {
      ElMessage.success('设备已删除')
      await getDevices()
    } else {
      ElMessage.error(res.data?.message || '删除设备失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除设备失败:', error)
      ElMessage.error('删除设备失败: ' + (error.message || '未知错误'))
    }
  }
}

const formatDate = formatDateTime
const getStatusType = getDeviceStatusType
const getStatusText = getDeviceStatusText

const getConnectionType = (type) => {
  // emulator, remote_emulator, remote, usb, agent_device 等
  if (type === 'emulator' || type === 'usb' || type === 'real_device') {
    return 'local'
  }
  return 'remote'
}

const getConnectionTypeTag = (type) => {
  if (type === 'agent_device') return 'success'
  return getConnectionType(type) === 'local' ? 'primary' : 'warning'
}

const getConnectionTypeName = (type) => {
  const typeMap = {
    'emulator': '本地模拟器',
    'remote_emulator': '远程模拟器',
    'remote': '远程设备',
    'usb': 'USB连接',
    'real_device': '真实设备',
    'agent_device': 'Agent代理'
  }
  return typeMap[type] || type
}

const isRemoteDevice = (type) => {
  return type === 'remote_emulator' || type === 'remote' || type === 'agent_device'
}

// 生命周期
onMounted(() => {
  getDevices()
  fetchAgentHosts()

  // 30秒自动刷新设备列表和 Agent 状态
  refreshTimer.value = setInterval(() => {
    getDevices()
    fetchAgentHosts()
  }, 30000)
})

onBeforeUnmount(() => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
  }
})
</script>

<style scoped lang="scss">
.device-management {
  padding: 20px;
}

.device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;

  h3 {
    margin: 0;
    font-size: 20px;
    color: #303133;
  }
}

.device-actions {
  display: flex;
  gap: 10px;
}

.dialog-footer {
  text-align: right;
}

.agent-setup-steps {
  .setup-step {
    display: flex;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px dashed #ebeef5;

    &:last-of-type {
      border-bottom: none;
    }
  }

  .copy-cmd {
    margin-left: 8px;
    padding: 4px 10px;
    background: #f5f7fa;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'Consolas', 'Courier New', monospace;
    color: #409eff;
    cursor: pointer;
    max-width: 500px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    &:hover {
      background: #ecf5ff;
      border-color: #a0cfff;
    }
  }
}
</style>
