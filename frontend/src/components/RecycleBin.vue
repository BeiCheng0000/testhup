<template>
  <el-dialog
    :model-value="visible"
    :title="$t('recycleBin.title')"
    width="800px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-table v-loading="loading" :data="deletedItems" empty-text="回收站为空">
      <el-table-column prop="name" :label="$t('recycleBin.projectName')" min-width="200" show-overflow-tooltip />
      <el-table-column prop="deleted_at" :label="$t('recycleBin.deletedAt')" width="180">
        <template #default="{ row }">{{ formatDate(row.deleted_at) }}</template>
      </el-table-column>
      <el-table-column :label="$t('recycleBin.actions')" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="handleRestore(row)">
            {{ $t('recycleBin.restore') }}
          </el-button>
          <el-button size="small" type="danger" @click="handleHardDelete(row)">
            {{ $t('recycleBin.permanentlyDelete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">{{ $t('common.close') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'

const props = defineProps({
  visible: Boolean,
  api: { type: Object, required: true },
  restoreUrl: { type: String, required: true },
  deletedUrl: { type: String, required: true },
})

const emit = defineEmits(['update:visible', 'restored', 'hardDeleted'])

const { t } = useI18n()
const loading = ref(false)
const deletedItems = ref([])

const fetchDeleted = async () => {
  loading.value = true
  try {
    const res = await props.api.get(props.deletedUrl)
    deletedItems.value = res.data?.results || res.data || []
  } catch {
    deletedItems.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, (val) => {
  if (val) fetchDeleted()
})

const handleRestore = async (row) => {
  try {
    await ElMessageBox.confirm(
      t('recycleBin.restoreConfirm', { name: row.name }),
      t('recycleBin.restoreTitle'),
      { type: 'info' }
    )
    await props.api.post(`${props.restoreUrl}${row.id}/restore/`)
    ElMessage.success(t('recycleBin.restoreSuccess'))
    emit('restored')
    fetchDeleted()
  } catch (e) {
    if (e !== 'cancel') { /* ignore cancel */ }
  }
}

const handleHardDelete = async (row) => {
  try {
    const { value } = await ElMessageBox.prompt(
      t('recycleBin.hardDeletePrompt', { name: row.name }),
      t('recycleBin.hardDeleteTitle'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'error',
        inputValidator: (val) => val === row.name ? true : t('recycleBin.nameMismatch'),
      }
    )
    if (value === row.name) {
      const hardDeleteUrl = `${props.restoreUrl}${row.id}/hard-delete/`
      await props.api.post(hardDeleteUrl)
      ElMessage.success(t('recycleBin.hardDeleteSuccess'))
      emit('hardDeleted')
      fetchDeleted()
    }
  } catch (e) {
    if (e !== 'cancel') { /* ignore cancel */ }
  }
}

const formatDate = (dateString) => {
  if (!dateString) return '-'
  return dayjs(dateString).format('YYYY-MM-DD HH:mm')
}
</script>
