<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="6"><stat-card label="待审批单据" :value="stats.pending_documents" color="#409eff" /></el-col>
      <el-col :span="6"><stat-card label="我的待办任务" :value="stats.pending_approval_tasks" color="#e6a23c" /></el-col>
      <el-col :span="6"><stat-card label="高风险事项" :value="stats.risk_counts?.high" color="#f56c6c" /></el-col>
      <el-col :span="6"><stat-card label="中风险事项" :value="stats.risk_counts?.medium" color="#e6a23c" /></el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="12">
        <el-card header="单据类型分布">
          <el-empty v-if="!hasDist" description="暂无单据数据" style="height:280px" />
          <div v-else ref="pieRef" style="height:300px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="最近单据">
          <el-table :data="stats.recent_documents || []" size="small">
            <el-table-column prop="document_no" label="编号" width="200" />
            <el-table-column prop="document_type" label="类型" width="110" />
            <el-table-column prop="total_amount" label="金额" width="100" />
            <el-table-column prop="document_status" label="状态" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount, defineComponent, h } from 'vue'
import * as echarts from 'echarts'
import api from '../api'

const stats = reactive({})
const pieRef = ref(null)
let chart = null
const hasDist = ref(false)

const statCard = defineComponent({
  props: { label: String, value: Number, color: String },
  setup(props) {
    return () => h('el-card', {}, [
      h('div', { style: 'font-size:28px;font-weight:700;color:' + props.color }, String(props.value ?? 0)),
      h('div', { style: 'color:#999;margin-top:6px' }, props.label),
    ])
  },
})

async function load() {
  const data = await api.get('/dashboard/stats')
  Object.assign(stats, data)
  const dist = data.document_type_distribution || {}
  hasDist.value = Object.keys(dist).length > 0
  if (hasDist.value) {
    await nextTick()
    if (pieRef.value) {
      chart = echarts.init(pieRef.value)
      chart.setOption({
        tooltip: { trigger: 'item' },
        series: [{
          type: 'pie', radius: '60%',
          data: Object.entries(dist).map(([k, v]) => ({ name: k, value: v })),
        }],
      })
    }
  }
}

onMounted(load)
onBeforeUnmount(() => chart?.dispose())
</script>
