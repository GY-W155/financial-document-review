<template>
  <el-card>
    <div class="toolbar">
      <el-form inline @submit.prevent>
        <el-form-item><el-input v-model="q.keyword" placeholder="编号/收款方/事由" clearable @change="load" /></el-form-item>
        <el-form-item>
          <el-select v-model="q.document_type" placeholder="类型" clearable @change="load">
            <el-option v-for="t in docTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-select v-model="q.status" placeholder="状态" clearable @change="load">
            <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item><el-button type="primary" @click="load">查询</el-button></el-form-item>
      </el-form>
      <el-button type="success" @click="$router.push('/documents/new')">＋ 新建单据</el-button>
    </div>

    <el-table :data="items" @row-click="(r) => $router.push('/documents/' + r.id)">
      <el-table-column prop="document_no" label="单据编号" width="210" />
      <el-table-column prop="document_type" label="类型" width="110" />
      <el-table-column prop="applicant_department" label="申请部门" width="100" />
      <el-table-column prop="payee_name" label="收款单位" />
      <el-table-column prop="total_amount" label="总金额" width="100">
        <template #default="{ row }">{{ row.total_amount }} {{ row.currency }}</template>
      </el-table-column>
      <el-table-column prop="document_status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.document_status)">{{ row.document_status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="$router.push('/documents/' + row.id)">详情</el-button>
          <el-button v-if="['draft','returned'].includes(row.document_status)" link type="success" @click.stop="copy(row)">复制</el-button>
          <el-button v-if="['draft','returned'].includes(row.document_status)" link type="warning" @click.stop="submit(row)">提交</el-button>
          <el-button v-if="['pending_review','reviewing'].includes(row.document_status)" link type="danger" @click.stop="withdraw(row)">撤回</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:16px" layout="total, prev, pager, next" :total="total"
      :page-size="q.page_size" v-model:current-page="q.page" @current-change="load" />
  </el-card>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const docTypes = ['对公付款单', '预付款单', '批量付款单', '费用报销单', '差旅报销单']
const statuses = ['draft', 'pending_review', 'reviewing', 'returned', 'approved', 'rejected', 'withdrawn', 'voided']
const items = ref([])
const total = ref(0)
const q = reactive({ keyword: '', document_type: '', status: '', page: 1, page_size: 10 })

const statusType = (s) => ({ draft: 'info', approved: 'success', rejected: 'danger', returned: 'warning', withdrawn: '', voided: 'info' }[s] || '')

async function load() {
  const data = await api.get('/documents', { params: { ...q, apply_from: undefined, apply_to: undefined } })
  items.value = data.items
  total.value = data.total
}

async function submit(row) {
  await ElMessageBox.confirm('提交后将进入审批流程并创建分析任务，确认？', '提交审批')
  await api.post(`/documents/${row.id}/submit`)
  ElMessage.success('已提交审批')
  load()
}
async function copy(row) {
  await api.post(`/documents/${row.id}/copy`)
  ElMessage.success('已复制为新草稿')
  load()
}
async function withdraw(row) {
  await ElMessageBox.confirm('确认撤回该单据？', '撤回')
  await api.post(`/documents/${row.id}/withdraw`)
  ElMessage.success('已撤回')
  load()
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; }
</style>
