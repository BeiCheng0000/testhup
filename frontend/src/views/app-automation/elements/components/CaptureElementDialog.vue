<template>
  <el-dialog
    v-model="dialogVisible"
    title="从设备截图创建元素"
    width="96vw"
    top="2vh"
    @close="handleClose"
  >
    <div class="capture-container">
      <!-- 左侧：截图画布 -->
      <div class="capture-left">
        <div
          v-if="capturedImage"
          ref="imageWrapper"
          class="image-wrapper"
          @mousedown="handleMouseDown"
          @mousemove="handleMouseMove"
          @mouseup="handleMouseUp"
          @mouseleave="handleMouseUp"
        >
          <img
            ref="imageRef"
            :src="capturedImage"
            @load="handleImageLoad"
            class="capture-image"
          />
          <!-- UI层级元素高亮（weditor风格：点击截图查找元素，单个高亮） -->
          <div
            v-if="formData.element_type === 'uiautomator' && highlightedUIElement && highlightedUIElement.bounds"
            class="hierarchy-highlight"
            :style="getHierarchyRectStyle(highlightedUIElement.bounds)"
            :class="{ 'hierarchy-selected': selectedUIElement === highlightedUIElement }"
          >
            <div class="hierarchy-tooltip">
              {{ highlightedUIElement.resource_id || highlightedUIElement.text || highlightedUIElement.content_desc || highlightedUIElement.class_name }}
              <span v-if="highlightedUIElement.clickable" style="color:#67c23a"> [可点击]</span>
            </div>
          </div>
          <!-- 悬浮预览提示（未选中时悬浮在元素上） -->
          <div
            v-if="formData.element_type === 'uiautomator' && hoveredUIElement && !selectedUIElement && hoveredUIElement.bounds"
            class="hierarchy-highlight hierarchy-hover-preview"
            :style="getHierarchyRectStyle(hoveredUIElement.bounds)"
          >
            <div class="hierarchy-tooltip">
              {{ hoveredUIElement.resource_id || hoveredUIElement.text || hoveredUIElement.content_desc || hoveredUIElement.class_name }}
              <span v-if="hoveredUIElement.clickable" style="color:#67c23a"> [可点击]</span>
            </div>
          </div>
          <!-- 选区框 -->
          <div
            v-if="selection"
            class="selection-box"
            :style="selectionStyle"
            @mousedown.stop="handleSelectionMouseDown"
          >
            <button class="selection-close" @click.stop="clearSelection">×</button>
            <div class="selection-info">{{ selectionInfo }}</div>
            <!-- 8个调整手柄 -->
            <span
              v-for="handle in resizeHandles"
              :key="handle"
              class="resize-handle"
              :class="`resize-handle-${handle}`"
              @mousedown.stop="handleResizeStart(handle, $event)"
            ></span>
          </div>
        </div>
        <div v-else class="empty-state">
          <el-empty description="请先从设备截图" />
        </div>
      </div>

      <!-- 右侧：配置表单 -->
      <div class="capture-right">
        <el-form :model="formData" ref="formRef" label-width="110px" size="small">
          <!-- 设备选择和截图 -->
          <el-form-item label="选择设备">
            <el-select v-model="selectedDevice" placeholder="选择设备" style="width: 100%" :loading="devicesLoading">
              <el-option 
                v-for="device in devices" 
                :key="device.id" 
                :label="device.device_id" 
                :value="device.id" 
              />
            </el-select>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" :loading="capturing" :disabled="!selectedDevice" @click="captureScreen">
              从设备截图
            </el-button>
          </el-form-item>

          <!-- Region和Pos值（根据元素类型显示） -->
          <el-form-item label="Region 值" v-if="formData.element_type === 'region'">
            <el-input v-model="regionValue" readonly placeholder="在截图上拖拽框选区域" />
          </el-form-item>

          <el-form-item label="Pos 值" v-if="formData.element_type === 'pos'">
            <el-input v-model="posValue" readonly placeholder="在截图上单击选择坐标" />
          </el-form-item>

          <el-divider content-position="left">元素信息</el-divider>

          <!-- 元素名称 -->
          <el-form-item label="元素名称" required>
            <el-input v-model="formData.name" placeholder="如：登录按钮" />
          </el-form-item>

          <!-- 所属项目 -->
          <el-form-item label="所属项目">
            <el-select v-model="formData.project" placeholder="请选择项目" clearable filterable style="width: 100%">
              <el-option v-for="p in projectList" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>

          <!-- 元素类型 -->
          <el-form-item label="元素类型" required>
            <el-radio-group v-model="formData.element_type">
              <el-radio value="image">图片元素</el-radio>
              <el-radio value="pos">坐标元素</el-radio>
              <el-radio value="region">区域元素</el-radio>
              <el-radio value="uiautomator">UI层级定位</el-radio>
            </el-radio-group>
          </el-form-item>

          <!-- 标签 -->
          <el-form-item label="标签">
            <el-select v-model="formData.tags" multiple filterable allow-create placeholder="输入标签后回车" style="width: 100%">
              <el-option label="登录" value="登录" />
            </el-select>
            <div style="color: #909399; font-size: 12px; margin-top: 5px;">
              💡 提示：输入标签回车创建
            </div>
          </el-form-item>

          <!-- 图片类型特有配置 -->
          <template v-if="formData.element_type === 'image'">
            <el-divider content-position="left">图片配置</el-divider>

            <!-- 图片分类 -->
            <el-form-item label="图片分类" required>
              <div style="display: flex; gap: 10px;">
                <el-select
                  v-model="formData.image_category"
                  placeholder="选择分类"
                  filterable
                  style="flex: 1;"
                >
                  <el-option 
                    v-for="cat in imageCategories" 
                    :key="cat.name || cat" 
                    :label="cat.name || cat" 
                    :value="cat.name || cat"
                  >
                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                      <span>{{ cat.name || cat }}</span>
                      <el-button
                        v-if="(cat.name || cat) !== 'common'"
                        type="danger"
                        size="small"
                        link
                        :icon="Delete"
                        @click.stop="handleDeleteCategory(cat.name || cat)"
                        title="删除分类"
                        style="padding: 0; margin-left: 8px;"
                      />
                    </div>
                  </el-option>
                </el-select>
                <el-button 
                  type="primary" 
                  :icon="Plus" 
                  @click="showCreateCategoryDialog"
                  title="创建新分类"
                />
              </div>
              <div style="color: #909399; font-size: 12px; margin-top: 5px;">
                💡 提示：图片将保存到 Template/&lt;分类&gt;/ 目录下
              </div>
            </el-form-item>

            <el-form-item label="模板文件名" required>
              <el-input v-model="templateFileName" placeholder="如：login_btn.png" />
              <div style="color: #909399; font-size: 12px; margin-top: 5px;">
                💡 提示：建议使用有意义的英文文件名
              </div>
            </el-form-item>

            <!-- 当前保存路径 -->
            <el-form-item label="保存路径">
              <el-input :value="imageSavePath" readonly>
                <template #prepend>
                  <el-icon><FolderOpened /></el-icon>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item label="匹配阈值">
              <el-slider v-model="formData.config.image_threshold" :min="0.5" :max="1.0" :step="0.05" show-input />
              <div style="color: #909399; font-size: 12px; margin-top: 5px;">
                💡 提示：值越高匹配越严格，默认 0.7
              </div>
            </el-form-item>

            <el-form-item label="颜色模式">
              <el-switch
                v-model="formData.config.rgb"
                active-text="RGB彩色"
                inactive-text="灰度"
              />
              <div style="color: #909399; font-size: 12px; margin-top: 5px;">
                💡 提示：RGB彩色适用于彩色界面，灰度适用于单色或对颜色不敏感的场景
              </div>
            </el-form-item>
          </template>

          <!-- UI层级定位类型特有配置 -->
          <template v-if="formData.element_type === 'uiautomator'">
            <el-divider content-position="left">UI层级定位配置</el-divider>

            <el-form-item label="定位方式" required>
              <el-select v-model="formData.uiautomator.locator_type" style="width: 100%" @change="onUserSelectLocatorType">
                <el-option label="resource-id (推荐)" value="resource_id" />
                <el-option label="text" value="text" />
                <el-option label="class name" value="class_name" />
                <el-option label="XPath" value="xpath" />
                <el-option label="content-desc" value="content_desc" />
              </el-select>
            </el-form-item>

            <el-form-item label="定位值" required>
              <el-input v-model="formData.uiautomator.locator_value" placeholder="从截图中点选元素自动填充" />
            </el-form-item>

            <!-- 选中元素信息 -->
            <el-form-item v-if="selectedUIElement" label="元素信息">
              <div class="uia-info-card">
                <div class="uia-info-row">
                  <el-tag size="small" type="info">{{ selectedUIElement.class_name }}</el-tag>
                  <el-tag v-if="selectedUIElement.clickable" size="small" type="success" style="margin-left: 4px;">可点击</el-tag>
                  <el-tag v-if="selectedUIElement.checkable" size="small" type="warning" style="margin-left: 4px;">可勾选</el-tag>
                  <el-tag v-if="selectedUIElement.scrollable" size="small" style="margin-left: 4px;">可滚动</el-tag>
                </div>
                <div class="uia-info-row uia-info-label">resource-id</div>
                <div class="uia-info-row uia-info-value">{{ selectedUIElement.resource_id || '(无)' }}</div>
                <div class="uia-info-row uia-info-label">class (全名)</div>
                <div class="uia-info-row uia-info-value">{{ selectedUIElement.class_name_full || selectedUIElement.class_name }}</div>
                <div class="uia-info-row uia-info-label">text</div>
                <div class="uia-info-row uia-info-value">{{ selectedUIElement.text || '(无)' }}</div>
                <div class="uia-info-row uia-info-label">content-desc</div>
                <div class="uia-info-row uia-info-value">{{ selectedUIElement.content_desc || '(无)' }}</div>
                <div class="uia-info-row uia-info-label">XPath</div>
                <div class="uia-info-row uia-info-value uia-info-mono">{{ selectedUIElement.xpath }}</div>
                <div class="uia-info-row uia-info-label">Bounds</div>
                <div class="uia-info-row uia-info-value">[{{ selectedUIElement.bounds?.join(', ') }}]</div>
                <div v-if="selectedUIElement.package" class="uia-info-row uia-info-label">Package</div>
                <div v-if="selectedUIElement.package" class="uia-info-row uia-info-value">{{ selectedUIElement.package }}</div>
                <div class="uia-info-row uia-info-meta">
                  层级: {{ selectedUIElement.depth }} | 索引: {{ selectedUIElement.index }}
                </div>
              </div>
            </el-form-item>

            <!-- 备选定位 -->
            <el-form-item label="备选定位">
              <div 
                v-for="(fb, idx) in formData.uiautomator.fallback_locators" 
                :key="idx" 
                style="display: flex; gap: 4px; margin-bottom: 4px; align-items: center;"
              >
                <el-select v-model="fb.type" style="width: 110px" size="small">
                  <el-option label="resource-id" value="resource_id" />
                  <el-option label="text" value="text" />
                  <el-option label="xpath" value="xpath" />
                  <el-option label="class name" value="class_name" />
                </el-select>
                <el-input v-model="fb.value" placeholder="备选值" size="small" style="flex: 1;" />
                <el-button @click="removeFallbackLocator(idx)" :icon="Delete" circle size="small" type="danger" plain />
              </div>
              <el-button @click="addFallbackLocator" size="small" type="primary" plain style="margin-top: 4px;">
                + 添加备选定位
              </el-button>
              <div style="color: #909399; font-size: 11px; margin-top: 4px;">
                当主定位失败时按顺序尝试备选定位
              </div>
            </el-form-item>

            <el-form-item v-if="!hierarchyElements.length && !hierarchyLoading">
              <el-alert type="info" :closable="false" show-icon>
                <template #title>
                  选择"UI层级定位"类型后，请先截图，系统会自动加载可交互元素
                </template>
              </el-alert>
            </el-form-item>

            <el-form-item v-if="hierarchyLoading">
              <el-alert type="warning" :closable="false" show-icon title="正在加载UI层级信息..." />
            </el-form-item>
          </template>
        </el-form>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting" :disabled="!canSave">
        保存元素
      </el-button>
    </template>
  </el-dialog>
  
  <!-- 创建图片分类对话框 -->
  <el-dialog
    v-model="createCategoryVisible"
    title="创建图片分类"
    width="400px"
  >
    <el-form>
      <el-form-item label="分类名称">
        <el-input 
          v-model="newCategoryName" 
          placeholder="如：button, icon, menu"
          @keyup.enter="handleCreateCategory"
        />
        <div style="color: #909399; font-size: 12px; margin-top: 5px;">
          💡 只能包含字母、数字、下划线和中划线
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createCategoryVisible = false">取消</el-button>
      <el-button type="primary" @click="handleCreateCategory" :loading="creatingCategory">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick } from 'vue'
import type { PropType } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

interface ProjectItem {
  id: number
  name: string
}
import { FolderOpened, Plus, Delete, Loading } from '@element-plus/icons-vue'
import {
  getDeviceList,
  captureDeviceScreenshot,
  dumpDeviceHierarchy,
  uploadAppElementImage,
  createAppElement,
  getAppImageCategories,
  createAppImageCategory,
  deleteAppImageCategory
} from '@/api/app-automation'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectList: { type: Array as PropType<ProjectItem[]>, default: () => [] }
})

const emit = defineEmits(['update:modelValue', 'success'])

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 状态
const formRef = ref(null)
const imageRef = ref(null)
const imageWrapper = ref(null)
const submitting = ref(false)

// 设备相关
const devices = ref([])
const devicesLoading = ref(false)
const selectedDevice = ref(null)
const capturing = ref(false)
const capturedImage = ref('')

// 截图选区
const selection = ref(null)
const selecting = ref(false)
const startPoint = ref(null)
const action = ref(null) // 'create', 'move', 'resize'
const resizeHandle = ref(null)
const moveOffset = ref(null)
const imageSize = ref({ width: 0, height: 0 })

// UI层级元素（weditor风格：通过坐标匹配查找元素）
const hierarchyElements = ref([])
const selectedUIElement = ref(null)
const hoveredUIElement = ref(null)
const highlightedUIElement = ref(null)  // 当前高亮显示的元素（选中或悬浮）
const hierarchyLoading = ref(false)
const userSelectedLocatorType = ref(false) // 用户是否手动选择了定位方式
const programmaticLocatorChange = ref(false) // 防止 @change 事件覆盖程序式设置
const refreshingElement = ref(false) // 正在刷新元素属性

// 调整手柄列表
const resizeHandles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']

// 表单数据
const formData = reactive({
  name: '',
  element_type: 'image',
  image_category: 'common',
  project: null,
  tags: [],
  config: {
    image_threshold: 0.7,
    rgb: false,
    x: 0,
    y: 0,
    x1: 0,
    y1: 0,
    x2: 0,
    y2: 0,
    image_path: '',
    file_hash: ''
  },
  uiautomator: {
    locator_type: 'resource_id',
    locator_value: '',
    fallback_locators: [],
    bounds: null,
    class_name: '',
    text: '',
    content_desc: '',
    screenshot_base64: ''
  }
})

const templateFileName = ref('')
const imageCategories = ref([])
const createCategoryVisible = ref(false)
const newCategoryName = ref('')
const creatingCategory = ref(false)

// 计算属性
const regionValue = computed(() => {
  if (formData.config.x1 && formData.config.y1 && formData.config.x2 && formData.config.y2) {
    return `${formData.config.x1},${formData.config.y1},${formData.config.x2},${formData.config.y2}`
  }
  return ''
})

const posValue = computed(() => {
  if (formData.config.x && formData.config.y) {
    return `${formData.config.x},${formData.config.y}`
  }
  return ''
})

const selectionStyle = computed(() => {
  if (!selection.value) return {}
  const x1 = Math.min(selection.value.x1, selection.value.x2)
  const y1 = Math.min(selection.value.y1, selection.value.y2)
  const x2 = Math.max(selection.value.x1, selection.value.x2)
  const y2 = Math.max(selection.value.y1, selection.value.y2)
  return {
    left: `${x1}px`,
    top: `${y1}px`,
    width: `${x2 - x1}px`,
    height: `${y2 - y1}px`
  }
})

const selectionInfo = computed(() => {
  if (!selection.value) return ''
  const width = Math.abs(selection.value.x2 - selection.value.x1)
  const height = Math.abs(selection.value.y2 - selection.value.y1)
  return `${Math.round(width)} × ${Math.round(height)}`
})

// 计算图片保存路径
const imageSavePath = computed(() => {
  const imageCategory = formData.image_category || 'common'
  const filename = templateFileName.value || 'template.png'
  return `Template/${imageCategory}/${filename}`
})

// 是否可以保存
const canSave = computed(() => {
  if (!formData.name) return false
  if (formData.element_type === 'image') {
    return capturedImage.value && templateFileName.value && formData.image_category
  } else if (formData.element_type === 'pos') {
    return formData.config.x && formData.config.y
  } else if (formData.element_type === 'region') {
    return formData.config.x1 && formData.config.y1 && formData.config.x2 && formData.config.y2
  } else if (formData.element_type === 'uiautomator') {
    return formData.uiautomator.locator_type && formData.uiautomator.locator_value
  }
  return false
})

// 加载设备列表（排除离线设备，只显示可用的）
const loadDevices = async () => {
  devicesLoading.value = true
  try {
    const { data } = await getDeviceList({ status: 'online,available,locked', page_size: 1000 })
    devices.value = data.results || []
  } catch (error) {
    console.error('加载设备列表失败:', error)
    ElMessage.error('加载设备列表失败')
  } finally {
    devicesLoading.value = false
  }
}

// 从设备截图
const captureScreen = async () => {
  if (!selectedDevice.value) {
    ElMessage.warning('请先选择设备')
    return
  }

  capturing.value = true
  try {
    if (formData.element_type === 'uiautomator') {
      // uiautomator 类型：使用 dumpDeviceHierarchy 一次性获取截图+层级
      // 确保截图和层级来自同一时刻，避免数据不同步
      const { data } = await dumpDeviceHierarchy(selectedDevice.value, { skipScreenshot: false })
      
      if (data.success && data.data) {
        if (data.data.screenshot) {
          capturedImage.value = data.data.screenshot
        }
        hierarchyElements.value = data.data.elements || []
        if (data.data.resolution) {
          imageSize.value = { 
            width: data.data.resolution.width, 
            height: data.data.resolution.height 
          }
        }
        ElMessage.success(`截图成功，加载了 ${hierarchyElements.value.length} 个可交互元素`)
      } else {
        ElMessage.error(data.msg || '获取截图和层级失败')
      }
    } else {
      // 非 uiautomator 类型：只需截图
      const { data } = await captureDeviceScreenshot(selectedDevice.value)
      
      if (data.success && data.data) {
        capturedImage.value = data.data.content || data.content || ''
        if (!capturedImage.value) {
          throw new Error('截图数据为空')
        }
        ElMessage.success('截图成功')
      } else {
        ElMessage.error(data.message || '截图失败')
      }
    }
  } catch (error) {
    console.error('截图失败:', error)
    const errMsg = error?.response?.data?.msg || error?.response?.data?.message || '截图失败'
    ElMessage.error(errMsg)
  } finally {
    capturing.value = false
  }
}

// 加载UI层级信息（始终重新截图确保数据一致）
const loadHierarchy = async () => {
  if (!selectedDevice.value) return
  
  hierarchyLoading.value = true
  hierarchyElements.value = []
  selectedUIElement.value = null
  
  try {
    // 始终获取新鲜截图+层级，确保数据来自同一时刻（与 weditor 行为一致）
    const { data } = await dumpDeviceHierarchy(selectedDevice.value, { skipScreenshot: false })
    
    if (data.success && data.data) {
      if (data.data.screenshot) {
        capturedImage.value = data.data.screenshot
      }
      if (data.data.resolution) {
        imageSize.value = { 
          width: data.data.resolution.width, 
          height: data.data.resolution.height 
        }
      }
      hierarchyElements.value = data.data.elements || []
      ElMessage.success(`加载了 ${hierarchyElements.value.length} 个可交互元素`)
    } else {
      ElMessage.error(data.msg || '获取UI层级失败')
    }
  } catch (error) {
    console.error('获取UI层级失败:', error)
    const errMsg = error?.response?.data?.msg || '获取UI层级失败，请确保设备已开启USB调试'
    ElMessage.error(errMsg)
  } finally {
    hierarchyLoading.value = false
  }
}

// 根据 bounds 计算叠加层矩形样式
const getHierarchyRectStyle = (bounds) => {
  if (!bounds || bounds.length < 4 || !imageRef.value) return { display: 'none' }
  const imgEl = imageRef.value
  const imgWidth = imgEl.clientWidth
  const imgHeight = imgEl.clientHeight
  // 使用图片原始分辨率作为首选，后端返回的屏幕分辨率作为回退
  const naturalW = imgEl.naturalWidth || imageSize.value.width || imgEl.width || 1
  const naturalH = imgEl.naturalHeight || imageSize.value.height || imgEl.height || 1
  const scaleX = imgWidth / naturalW
  const scaleY = imgHeight / naturalH
  
  // 将 bounds 坐标转换为显示坐标，并 clamp 在图片边界内
  const x1 = Math.max(0, Math.min(imgWidth, bounds[0] * scaleX))
  const y1 = Math.max(0, Math.min(imgHeight, bounds[1] * scaleY))
  const x2 = Math.max(0, Math.min(imgWidth, bounds[2] * scaleX))
  const y2 = Math.max(0, Math.min(imgHeight, bounds[3] * scaleY))
  
  const w = x2 - x1
  const h = y2 - y1
  
  // 元素超出图片范围或尺寸为 0，隐藏
  if (w <= 0 || h <= 0) return { display: 'none' }
  
  return {
    left: `${x1}px`,
    top: `${y1}px`,
    width: `${w}px`,
    height: `${Math.max(h, 8)}px`  // 最小高度 8px 保证可点击
  }
}

// ============ Weditor风格：坐标匹配查找元素 ============

// 将截图画布上的显示坐标转换为设备物理坐标
const displayToDeviceCoords = (displayX, displayY) => {
  if (!imageRef.value) return null
  const imgEl = imageRef.value
  const naturalW = imgEl.naturalWidth || imageSize.value.width || imgEl.width || 1
  const naturalH = imgEl.naturalHeight || imageSize.value.height || imgEl.height || 1
  const clientW = imgEl.clientWidth || 1
  const clientH = imgEl.clientHeight || 1
  const scaleX = naturalW / clientW
  const scaleY = naturalH / clientH
  return {
    x: Math.round(displayX * scaleX),
    y: Math.round(displayY * scaleY),
    scaleX,
    scaleY,
    naturalW,
    naturalH
  }
}

// weditor核心算法：给定设备坐标，查找包含该点的最深（面积最小）元素
const findElementAtPoint = (deviceX, deviceY) => {
  if (!hierarchyElements.value || hierarchyElements.value.length === 0) return null
  
  let bestElement = null
  let bestArea = Infinity
  
  for (const elem of hierarchyElements.value) {
    const bounds = elem.bounds
    if (!bounds || bounds.length < 4) continue
    
    // 判断点是否在元素 bounds 范围内
    if (deviceX >= bounds[0] && deviceX <= bounds[2] && 
        deviceY >= bounds[1] && deviceY <= bounds[3]) {
      const area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
      // 选择面积最小的（最深/最精确的叶子节点）
      if (area > 0 && area < bestArea) {
        bestArea = area
        bestElement = elem
      }
    }
  }
  
  return bestElement
}

// 点击截图上的位置，查找并选中对应的UI元素
const clickToFindElement = (displayX, displayY) => {
  const coords = displayToDeviceCoords(displayX, displayY)
  if (!coords) return null
  
  const elem = findElementAtPoint(coords.x, coords.y)
  if (elem) {
    highlightedUIElement.value = elem
    selectUIElement(elem)
    hoveredUIElement.value = null  // 点击后清除悬浮状态
  }
  return elem
}

// ============ 元素选择 ============
const selectUIElement = (elem) => {
  // 直接使用已加载的层级数据，不需要重新请求后端
  // loadHierarchy 返回的元素数据已经包含 text、resource_id 等所有属性
  selectedUIElement.value = elem
  applyElementToForm(elem)
}

// 将元素数据应用到表单（提取为独立函数复用）
const applyElementToForm = (elem) => {
  // 如果用户手动选择了定位方式，优先用该方式填充
  if (userSelectedLocatorType.value) {
    const currentType = formData.uiautomator.locator_type
    let value = ''
    switch (currentType) {
      case 'resource_id': value = elem.resource_id || ''; break
      case 'text': value = elem.text || ''; break
      case 'xpath': value = elem.xpath || ''; break
      case 'class_name': value = elem.class_name_full || elem.class_name || ''; break
      case 'content_desc': value = elem.content_desc || ''; break
    }
    if (value) {
      formData.uiautomator.locator_value = value
    } else {
      formData.uiautomator.locator_value = ''
      ElMessage.warning(`该元素没有 "${currentType}" 类型的值，请尝试其他定位方式`)
    }
  } else {
    autoSelectLocatorType(elem)
  }
  
  // 填充元素信息
  formData.uiautomator.bounds = elem.bounds
  formData.uiautomator.class_name = elem.class_name_full || elem.class_name
  formData.uiautomator.text = elem.text
  formData.uiautomator.content_desc = elem.content_desc
  
  // 自动生成备选定位
  const fallbacks = []
  if (elem.resource_id && formData.uiautomator.locator_type !== 'resource_id') {
    fallbacks.push({ type: 'resource_id', value: elem.resource_id })
  }
  if (elem.text && formData.uiautomator.locator_type !== 'text') {
    fallbacks.push({ type: 'text', value: elem.text })
  }
  if (elem.xpath && formData.uiautomator.locator_type !== 'xpath') {
    fallbacks.push({ type: 'xpath', value: elem.xpath })
  }
  formData.uiautomator.fallback_locators = fallbacks
}

// 自动选择最佳定位策略
const autoSelectLocatorType = (elem) => {
  let type, value
  if (elem.resource_id) {
    type = 'resource_id'; value = elem.resource_id
  } else if (elem.text) {
    type = 'text'; value = elem.text
  } else if (elem.xpath) {
    type = 'xpath'; value = elem.xpath
  } else {
    type = 'class_name'; value = elem.class_name_full || elem.class_name
  }
  setLocatorTypeProgrammatic(type, value)
}

// 添加备选定位
const addFallbackLocator = () => {
  formData.uiautomator.fallback_locators.push({ type: 'resource_id', value: '' })
}

// 移除备选定位
const removeFallbackLocator = (idx) => {
  formData.uiautomator.fallback_locators.splice(idx, 1)
}

// 图片加载完成
const handleImageLoad = () => {
  if (imageRef.value) {
    imageSize.value = {
      width: imageRef.value.naturalWidth || imageRef.value.width,
      height: imageRef.value.naturalHeight || imageRef.value.height
    }
    // 强制更新 hierarchy overlay 以适应新的图片尺寸
    if (imageWrapper.value) {
      // display:table 元素需要触发重绘以确保子元素绝对定位正确
      imageWrapper.value.style.minHeight = imageRef.value.clientHeight + 'px'
    }
  }
}

// 获取图片容器位置
const getImageRect = () => {
  if (!imageWrapper.value || !imageRef.value) return null
  return imageWrapper.value.getBoundingClientRect()
}

// 将选区坐标转换为实际图片坐标
const getSelectionInNatural = () => {
  if (!selection.value || !imageRef.value) return null
  const scaleX = imageSize.value.width / imageRef.value.clientWidth
  const scaleY = imageSize.value.height / imageRef.value.clientHeight
  const x1 = Math.min(selection.value.x1, selection.value.x2)
  const y1 = Math.min(selection.value.y1, selection.value.y2)
  const x2 = Math.max(selection.value.x1, selection.value.x2)
  const y2 = Math.max(selection.value.y1, selection.value.y2)
  return {
    x1: Math.round(x1 * scaleX),
    y1: Math.round(y1 * scaleY),
    x2: Math.round(x2 * scaleX),
    y2: Math.round(y2 * scaleY)
  }
}

// 更新配置值
const updateSelectionValues = () => {
  const natural = getSelectionInNatural()
  if (natural) {
    formData.config.x1 = natural.x1
    formData.config.y1 = natural.y1
    formData.config.x2 = natural.x2
    formData.config.y2 = natural.y2
  }
}

// ============ 鼠标事件处理 ============

const handleMouseDown = (e) => {
  if (!capturedImage.value || !imageWrapper.value) return
  const rect = getImageRect()
  if (!rect) return
  const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
  const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height))
  
  selecting.value = true
  startPoint.value = { x, y }
  
  if (formData.element_type === 'uiautomator' && hierarchyElements.value.length > 0) {
    // weditor模式：记录起始点用于判断点击/拖拽，不创建选区
    action.value = 'uiautomator_click'
    selection.value = null
  } else {
    // 其他模式：拉框选区
    action.value = 'create'
    selection.value = { x1: x, y1: y, x2: x, y2: y }
  }
  e.preventDefault()
}

const handleMouseMove = (e) => {
  if (!imageWrapper.value) return
  
  const rect = getImageRect()
  if (!rect) return
  const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
  const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height))
  
  // weditor悬浮预览（非拖拽状态下）
  if (formData.element_type === 'uiautomator' && 
      hierarchyElements.value.length > 0 && 
      !selecting.value) {
    const coords = displayToDeviceCoords(x, y)
    if (coords) {
      const found = findElementAtPoint(coords.x, coords.y)
      if (found !== hoveredUIElement.value) {
        hoveredUIElement.value = found
        // 未选中时也显示悬浮高亮
        if (!selectedUIElement.value) {
          highlightedUIElement.value = found
        }
      }
    }
    return
  }
  
  if (!selecting.value) return
  
  // uiautomator拖拽中不做操作
  if (action.value === 'uiautomator_click') return
  
  // --- 以下为区域选区逻辑 ---
  if (!selection.value) return
  
  if (action.value === 'create' && startPoint.value) {
    selection.value = { x1: startPoint.value.x, y1: startPoint.value.y, x2: x, y2: y }
  } else if (action.value === 'move' && moveOffset.value) {
    const width = Math.abs(selection.value.x2 - selection.value.x1)
    const height = Math.abs(selection.value.y2 - selection.value.y1)
    const left = Math.max(0, Math.min(x - moveOffset.value.x, rect.width - width))
    const top = Math.max(0, Math.min(y - moveOffset.value.y, rect.height - height))
    selection.value = { x1: left, y1: top, x2: left + width, y2: top + height }
  } else if (action.value === 'resize' && resizeHandle.value) {
    selection.value = resizeSelection(selection.value, resizeHandle.value, x, y, rect)
  }
  e.preventDefault()
}

const handleMouseUp = (e) => {
  if (!selecting.value) {
    // mouseleave 时清除悬浮预览
    if (hoveredUIElement.value && !selectedUIElement.value) {
      hoveredUIElement.value = null
      highlightedUIElement.value = null
    }
    return
  }
  
  const isMouseLeave = e && e.type === 'mouseleave'
  
  // --- weditor模式：点击查找元素 ---
  if (action.value === 'uiautomator_click') {
    if (!isMouseLeave && startPoint.value && imageWrapper.value) {
      const rect = getImageRect()
      if (rect) {
        const upX = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
        const upY = Math.max(0, Math.min(e.clientY - rect.top, rect.height))
        const dx = Math.abs(upX - startPoint.value.x)
        const dy = Math.abs(upY - startPoint.value.y)
        
        if (dx < 5 && dy < 5) {
          // 点击：查找最深元素
          const elem = clickToFindElement(upX, upY)
          if (!elem) {
            ElMessage.info('点击位置未找到UI元素，请重试')
          }
        }
        // 拖拽在uiautomator模式下不做操作
      }
    }
    selecting.value = false
    startPoint.value = null
    action.value = null
    return
  }
  
  // --- 区域选区逻辑 ---
  if (action.value === 'create' && selection.value) {
    const width = Math.abs(selection.value.x2 - selection.value.x1)
    const height = Math.abs(selection.value.y2 - selection.value.y1)
    if (width < 5 && height < 5) {
      // 单击设置坐标
      if (imageRef.value) {
        const scaleX = imageSize.value.width / imageRef.value.clientWidth
        const scaleY = imageSize.value.height / imageRef.value.clientHeight
        formData.config.x = Math.round(selection.value.x1 * scaleX)
        formData.config.y = Math.round(selection.value.y1 * scaleY)
      }
      selection.value = null
    } else {
      updateSelectionValues()
    }
  } else if (action.value === 'move' || action.value === 'resize') {
    updateSelectionValues()
  }
  selecting.value = false
  startPoint.value = null
  action.value = null
  resizeHandle.value = null
  moveOffset.value = null
}

const handleSelectionMouseDown = (e) => {
  if (!imageWrapper.value) return
  const rect = getImageRect()
  if (!rect || !selection.value) return
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  const x1 = Math.min(selection.value.x1, selection.value.x2)
  const y1 = Math.min(selection.value.y1, selection.value.y2)
  selecting.value = true
  action.value = 'move'
  moveOffset.value = { x: x - x1, y: y - y1 }
  e.preventDefault()
}

const handleResizeStart = (handle, e) => {
  if (!imageWrapper.value) return
  selecting.value = true
  action.value = 'resize'
  resizeHandle.value = handle
  e.preventDefault()
}

const resizeSelection = (sel, handle, x, y, rect) => {
  let { x1, y1, x2, y2 } = sel
  const clampX = Math.max(0, Math.min(x, rect.width))
  const clampY = Math.max(0, Math.min(y, rect.height))
  if (handle.includes('n')) y1 = clampY
  if (handle.includes('s')) y2 = clampY
  if (handle.includes('w')) x1 = clampX
  if (handle.includes('e')) x2 = clampX
  return { x1, y1, x2, y2 }
}

const clearSelection = () => {
  selection.value = null
  action.value = null
  resizeHandle.value = null
  moveOffset.value = null
  formData.config.x1 = 0
  formData.config.y1 = 0
  formData.config.x2 = 0
  formData.config.y2 = 0
}

// 提交表单
const handleSubmit = async () => {
  if (!formData.name) {
    ElMessage.warning('请输入元素名称')
    return
  }

  if (formData.element_type === 'image') {
    if (!capturedImage.value) {
      ElMessage.warning('请先截图')
      return
    }
    if (!templateFileName.value) {
      ElMessage.warning('请输入模板文件名')
      return
    }
    if (!formData.image_category) {
      ElMessage.warning('请选择图片分类')
      return
    }
  } else if (formData.element_type === 'pos') {
    if (!formData.config.x || !formData.config.y) {
      ElMessage.warning('请设置坐标')
      return
    }
  } else if (formData.element_type === 'region') {
    if (!formData.config.x1 || !formData.config.y1 || !formData.config.x2 || !formData.config.y2) {
      ElMessage.warning('请框选区域')
      return
    }
  } else if (formData.element_type === 'uiautomator') {
    if (!formData.uiautomator.locator_type || !formData.uiautomator.locator_value) {
      ElMessage.warning('请设置定位方式和定位值')
      return
    }
  }

  submitting.value = true

  try {
    // UI层级定位类型：直接提交，无需上传图片
    if (formData.element_type === 'uiautomator') {
      // 生成元素截图缩略图
      let screenshotBase64 = ''
      if (selectedUIElement.value && selectedUIElement.value.bounds && imageRef.value) {
        try {
          const bounds = selectedUIElement.value.bounds
          const img = imageRef.value
          const scaleX = (img.naturalWidth || img.width) / img.clientWidth
          const scaleY = (img.naturalHeight || img.height) / img.clientHeight
          
          const canvas = document.createElement('canvas')
          const w = Math.round((bounds[2] - bounds[0]) * scaleX)
          const h = Math.round((bounds[3] - bounds[1]) * scaleY)
          canvas.width = w
          canvas.height = h
          const ctx = canvas.getContext('2d')
          if (ctx) {
            ctx.drawImage(img, 
              Math.round(bounds[0] * scaleX), Math.round(bounds[1] * scaleY), w, h,
              0, 0, w, h
            )
            screenshotBase64 = canvas.toDataURL('image/png')
          }
        } catch (e) {
          console.warn('生成元素缩略图失败:', e)
        }
      }
      
      const submitData = {
        name: formData.name,
        element_type: 'uiautomator',
        project: formData.project || null,
        tags: formData.tags,
        config: {
          locator_type: formData.uiautomator.locator_type,
          locator_value: formData.uiautomator.locator_value,
          fallback_locators: formData.uiautomator.fallback_locators.filter(fb => fb.type && fb.value),
          bounds: formData.uiautomator.bounds,
          class_name: formData.uiautomator.class_name,
          text: formData.uiautomator.text,
          content_desc: formData.uiautomator.content_desc,
          screenshot_base64: screenshotBase64
        }
      }
      
      await createAppElement(submitData)
      ElMessage.success('创建成功')
      emit('success')
      handleClose()
      return
    }
    
    if (formData.element_type === 'image' && capturedImage.value) {
      let imageBlob

      // 裁剪图片
      if (selection.value && imageRef.value) {
        const img = imageRef.value
        const sel = selection.value
        const scaleX = imageSize.value.width / img.clientWidth
        const scaleY = imageSize.value.height / img.clientHeight
        
        // 计算裁剪区域
        const x1 = Math.min(sel.x1, sel.x2)
        const y1 = Math.min(sel.y1, sel.y2)
        const x2 = Math.max(sel.x1, sel.x2)
        const y2 = Math.max(sel.y1, sel.y2)
        const width = x2 - x1
        const height = y2 - y1
        
        // 转换为实际图片坐标
        const cropX = Math.round(x1 * scaleX)
        const cropY = Math.round(y1 * scaleY)
        const cropWidth = Math.round(width * scaleX)
        const cropHeight = Math.round(height * scaleY)

        const canvas = document.createElement('canvas')
        canvas.width = cropWidth
        canvas.height = cropHeight
        const ctx = canvas.getContext('2d')

        if (ctx) {
          ctx.drawImage(img, cropX, cropY, cropWidth, cropHeight, 0, 0, cropWidth, cropHeight)
          imageBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
        }
      } else {
        const base64Data = capturedImage.value.split(',')[1]
        imageBlob = base64ToBlob(base64Data, 'image/png')
      }

      if (!imageBlob) {
        ElMessage.error('图片处理失败')
        submitting.value = false
        return
      }

      const file = new File([imageBlob], templateFileName.value, { type: 'image/png' })
      
      try {
        const { data: uploadData } = await uploadAppElementImage(
          file,
          formData.image_category || 'common'
        )
        
        if (uploadData.success) {
          formData.config.image_path = uploadData.data.image_path
          formData.config.file_hash = uploadData.data.file_hash
          ElMessage.success(`图片已上传: ${uploadData.data.image_path}`)
        } else {
          // 显示详细的错误信息
          let errorMessage = uploadData.message || '上传图片失败'
          
          if (uploadData.detail) {
            errorMessage += `\n\n${uploadData.detail}`
          }
          if (uploadData.suggestion) {
            errorMessage += `\n\n💡 建议：${uploadData.suggestion}`
          }
          
          if (uploadData.data?.existing_element) {
            const existing = uploadData.data.existing_element
            errorMessage += `\n\n已存在元素：${existing.name} (ID: ${existing.id})`
            if (existing.image_path) {
              errorMessage += `\n文件路径：${existing.image_path}`
            }
          }
          
          ElMessage.error({
            message: errorMessage,
            duration: 8000,
            showClose: true
          })
          submitting.value = false
          return
        }
      } catch (uploadError) {
        console.error('图片上传异常:', uploadError)
        let errorMessage = '图片上传失败'
        
        if (uploadError.response?.data) {
          const data = uploadError.response.data
          errorMessage = data.message || data.detail || errorMessage
        } else if (uploadError.message) {
          errorMessage += `: ${uploadError.message}`
        }
        
        ElMessage.error({
          message: errorMessage,
          duration: 5000,
          showClose: true
        })
        submitting.value = false
        return
      }
    }

    // 准备提交数据
    const submitData = {
      name: formData.name,
      element_type: formData.element_type,
      project: formData.project || null,
      tags: formData.tags,
      config: {
        ...formData.config,
        image_category: formData.image_category || 'common'
      }
    }

    // DRF ModelViewSet 的 create 方法直接返回序列化数据，没有 success 字段
    await createAppElement(submitData)
    ElMessage.success('创建成功')
    emit('success')
    handleClose()
  } catch (error) {
    console.error('创建失败:', error)
    
    // 显示详细的错误信息
    let errorMessage = '创建失败'
    
    if (error.response?.data) {
      const data = error.response.data
      if (data.message) {
        errorMessage = data.message
      } else if (data.detail) {
        errorMessage = data.detail
      } else if (data.config) {
        const configErrors = data.config
        if (Array.isArray(configErrors)) {
          errorMessage = `配置错误: ${configErrors.join(', ')}`
        } else if (typeof configErrors === 'object') {
          errorMessage = `配置错误: ${JSON.stringify(configErrors)}`
        }
      }
      errorMessage += ` (状态码: ${error.response.status})`
    } else if (error.request) {
      errorMessage = '网络错误: 无法连接到服务器，请检查网络连接'
    } else if (error.message) {
      errorMessage = `错误: ${error.message}`
    }
    
    ElMessage.error({
      message: errorMessage,
      duration: 8000,
      showClose: true
    })
  } finally {
    submitting.value = false
  }
}

const base64ToBlob = (base64, type = 'image/png') => {
  const byteCharacters = atob(base64)
  const byteNumbers = new Array(byteCharacters.length)
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i)
  }
  const byteArray = new Uint8Array(byteNumbers)
  return new Blob([byteArray], { type })
}

const handleClose = () => {
  emit('update:modelValue', false)
  Object.assign(formData, {
    name: '',
    element_type: 'image',
    image_category: 'common',
    project: null,
    tags: [],
    config: {
      image_threshold: 0.7,
      rgb: false,
      x: 0,
      y: 0,
      x1: 0,
      y1: 0,
      x2: 0,
      y2: 0,
      image_path: '',
      file_hash: ''
    },
    uiautomator: {
      locator_type: 'resource_id',
      locator_value: '',
      fallback_locators: [],
      bounds: null,
      class_name: '',
      text: '',
      content_desc: '',
      screenshot_base64: ''
    }
  })
  templateFileName.value = ''
  capturedImage.value = ''
  selection.value = null
  action.value = null
  hierarchyElements.value = []
  selectedUIElement.value = null
  hoveredUIElement.value = null
  hierarchyLoading.value = false
  userSelectedLocatorType.value = false
  programmaticLocatorChange.value = false
  refreshingElement.value = false
}

// 加载图片分类列表
const loadImageCategories = async () => {
  try {
    const { data } = await getAppImageCategories()
    if (data.success && Array.isArray(data.data)) {
      // 后端返回的是对象数组 [{name: 'common', path: 'common'}]
      // 转换为字符串数组以兼容现有代码
      imageCategories.value = data.data.map(cat => cat.name || cat)
    }
  } catch (error) {
    console.error('加载图片分类失败:', error)
    imageCategories.value = ['common']
  }
}

// 显示创建分类对话框
const showCreateCategoryDialog = () => {
  newCategoryName.value = ''
  createCategoryVisible.value = true
}

// 创建新分类
const handleCreateCategory = async () => {
  if (!newCategoryName.value.trim()) {
    ElMessage.warning('请输入分类名称')
    return
  }
  
  try {
    creatingCategory.value = true
    const { data } = await createAppImageCategory(newCategoryName.value.trim())
    
    if (data.success) {
      ElMessage.success('创建成功')
      // 刷新分类列表
      await loadImageCategories()
      // 自动选中新创建的分类
      formData.image_category = data.data.name
      // 关闭对话框
      createCategoryVisible.value = false
    } else {
      ElMessage.error(data.message || '创建失败')
    }
  } catch (error) {
    console.error('创建分类失败:', error)
    ElMessage.error('创建失败')
  } finally {
    creatingCategory.value = false
  }
}

// 删除分类
const handleDeleteCategory = async (categoryName) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除分类 "${categoryName}" 吗？只能删除空目录。`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    
    const { data } = await deleteAppImageCategory(categoryName)
    
    if (data.success) {
      ElMessage.success('删除成功')
      // 刷新分类列表
      await loadImageCategories()
      // 如果当前选中的分类被删除，切换到 common
      if (formData.image_category === categoryName) {
        formData.image_category = 'common'
      }
    } else {
      ElMessage.error(data.message || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除分类失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

watch(() => props.modelValue, (val) => {
  if (val) {
    loadDevices()
    loadImageCategories()
  }
})

// 切换到UI层级定位时，如果已有截图则自动加载层级信息
watch(() => formData.element_type, (newType, oldType) => {
  if (newType === 'uiautomator' && capturedImage.value) {
    // 如果已有截图但层级未加载，自动加载
    if (!hierarchyElements.value.length && !hierarchyLoading.value) {
      loadHierarchy()
    }
  }
  // 切出 uiautomator 模式时清理层级相关状态
  if (oldType === 'uiautomator' && newType !== 'uiautomator') {
    selectedUIElement.value = null
    hoveredUIElement.value = null
    highlightedUIElement.value = null
    userSelectedLocatorType.value = false
    formData.uiautomator.locator_type = 'resource_id'
    formData.uiautomator.locator_value = ''
    formData.uiautomator.bounds = null
    formData.uiautomator.class_name = ''
    formData.uiautomator.text = ''
    formData.uiautomator.content_desc = ''
    formData.uiautomator.fallback_locators = []
  }
  // 切换定位类型时重置手动选择标记
  if (newType !== 'uiautomator') {
    userSelectedLocatorType.value = false
  }
})

// 用户通过下拉框手动选择定位方式（仅 @change 事件触发，程序式修改不会触发）
const onUserSelectLocatorType = () => {
  // 如果是程序式修改触发的 change 事件，忽略
  if (programmaticLocatorChange.value) return
  userSelectedLocatorType.value = true
}

// 程序式设置定位方式（不触发用户选择标记）
const setLocatorTypeProgrammatic = (type, value) => {
  programmaticLocatorChange.value = true
  userSelectedLocatorType.value = false
  formData.uiautomator.locator_type = type
  formData.uiautomator.locator_value = value
  // 在 Vue 完成响应式更新后再恢复标志
  nextTick(() => {
    programmaticLocatorChange.value = false
  })
}
</script>

<style scoped>
/* el-dialog body 作为 flex 容器，精确控制高度 */
:deep(.el-dialog__body) {
  height: calc(100vh - 145px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.capture-container {
  display: flex;
  gap: 20px;
  flex: 1;
  min-height: 0;
}

.capture-left {
  flex: 1;
  min-width: 0;
  min-height: 0;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: auto;
  background: #f5f7fa;
}

.image-wrapper {
  position: relative;
  cursor: crosshair;
  display: block;
  width: fit-content;
  margin: 0 auto;
  line-height: 0;
}

.capture-image {
  max-width: 100%;
  height: auto;
  display: block;
  user-select: none;
  pointer-events: none;
}

.selection-box {
  position: absolute;
  border: 2px solid #409eff;
  background: rgba(64, 158, 255, 0.1);
  cursor: move;
  pointer-events: auto;
}

.selection-info {
  position: absolute;
  top: -25px;
  left: 0;
  background: #409eff;
  color: white;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  white-space: nowrap;
  pointer-events: none;
}

.selection-close {
  position: absolute;
  top: -10px;
  right: -10px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #f56c6c;
  color: white;
  border: none;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  pointer-events: auto;
  z-index: 10;
}

.selection-close:hover {
  background: #f78989;
}

.resize-handle {
  position: absolute;
  width: 8px;
  height: 8px;
  background: #409eff;
  border: 1px solid white;
  border-radius: 50%;
  pointer-events: auto;
  z-index: 5;
}

.resize-handle-nw { top: -5px; left: -5px; cursor: nwse-resize; }
.resize-handle-n { top: -5px; left: 50%; transform: translateX(-50%); cursor: ns-resize; }
.resize-handle-ne { top: -5px; right: -5px; cursor: nesw-resize; }
.resize-handle-e { top: 50%; right: -5px; transform: translateY(-50%); cursor: ew-resize; }
.resize-handle-se { bottom: -5px; right: -5px; cursor: nwse-resize; }
.resize-handle-s { bottom: -5px; left: 50%; transform: translateX(-50%); cursor: ns-resize; }
.resize-handle-sw { bottom: -5px; left: -5px; cursor: nesw-resize; }
.resize-handle-w { top: 50%; left: -5px; transform: translateY(-50%); cursor: ew-resize; }

.capture-right {
  width: 400px;
  flex-shrink: 0;
  overflow-y: auto;
  padding-right: 10px;
}

.empty-state {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

/* UI层级元素高亮（weditor风格：单个元素高亮） */
.hierarchy-highlight {
  position: absolute;
  border: 2px solid #409eff;
  background: rgba(64, 158, 255, 0.15);
  pointer-events: none;
  z-index: 10;
  transition: all 0.15s ease;
  overflow: visible;
}

.hierarchy-highlight.hierarchy-selected {
  border-color: #1a73e8;
  border-width: 2.5px;
  background: rgba(26, 115, 232, 0.2);
  box-shadow: 0 0 6px rgba(26, 115, 232, 0.4);
  z-index: 11;
}

/* 悬浮预览（未选中时的预览高亮） */
.hierarchy-hover-preview {
  border-color: rgba(255, 165, 0, 0.7);
  background: rgba(255, 165, 0, 0.08);
  border-style: dashed;
  z-index: 9;
}

.hierarchy-tooltip {
  position: absolute;
  top: -22px;
  left: 0;
  background: rgba(0, 0, 0, 0.85);
  color: white;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  white-space: nowrap;
  pointer-events: none;
  z-index: 20;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.uia-info-card {
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
  width: 100%;
  font-size: 12px;
  line-height: 1.6;
  max-height: 260px;
  overflow-y: auto;
}

.uia-info-row {
  margin-bottom: 2px;
}

.uia-info-label {
  font-size: 10px;
  color: #909399;
  text-transform: none;
  margin-top: 4px;
  line-height: 1.4;
}

.uia-info-value {
  font-size: 12px;
  color: #303133;
  word-break: break-all;
  overflow-wrap: break-word;
  line-height: 1.5;
  padding: 1px 0;
}

.uia-info-mono {
  font-family: 'Courier New', Courier, monospace;
  font-size: 11px;
  background: #f0f0f0;
  padding: 2px 4px;
  border-radius: 2px;
  display: inline-block;
  max-width: 100%;
}

.uia-info-meta {
  font-size: 11px;
  color: #C0C4CC;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid #e4e7ed;
}
</style>
