<template>
  <el-card>
    <el-tabs v-model="tab">
      <el-tab-pane label="待办任务" name="pending">
        <el-table :data="pendingTasks" size="small">
          <el-table-column prop="document_no" label="单据编号" width="210" />
          <el-table-column prop="document_type" label="类型" width="110" />
          <el-table-column prop="node_name" label="审批节点" width="120" />
          <el-table-column prop="total_amount" label="金额" width="100" />
          <el-table-column prop="created_at" label="发起时间" width="180" />
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button type="success" size="small" @click="act(row, 'approve')">通过</el-button>
              <el-button type="warning" size="small" @click="act(row, 'return')">退回</el-button>
              <el-button type="danger" size="small" @click="act(row, 'reject')">驳回</el-button>
              <el-button link type="primary" size="small" @click="$router.push('/documents/' + row.document_id)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="全部任务" name="all">
        <el-table :data="allTasks" size="small">
          <el-table-column prop="document_no" label="单据编号" width="210" />
          <el-table-column prop="node_name" label="节点" width="120" />
          <el-table-column prop="approver_role" label="审批角色" width="120" />
          <el-table-column prop="task_status" label="状态" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const tab = ref('pending')
const pendingTasks = ref([])
const allTasks = ref([])

async function load() {
  pendingTasks.value = (await api.get('/approval/tasks', { params: { status: 'pending' } })).items || []
  allTasks.value = (await api.get('/approval/tasks', { params: {} })).items || []
}
async function act(row, action) {
  const comment = await ElMessageBox.prompt('请输入审批意见', '审批') .catch(() => null)
  if (!comment) return
  await api.post(`/approval/tasks/${row.task_id}/${action}`, null, { params: { comment: comment.value } })
  ElMessage.success('处理成功')
  load()
}

onMounted(load)
</script>
