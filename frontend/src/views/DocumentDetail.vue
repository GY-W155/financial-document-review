<template>
  <div v-if="doc">
    <el-page-header @back="$router.back()">
      <template #content>{{ doc.document_no }}（{{ doc.document_type }}）</template>
      <template #extra>
        <el-tag :type="statusType(doc.document_status)">{{ doc.document_status }}</el-tag>
        <el-button type="warning" style="margin-left:8px" @click="$router.push('/documents/' + doc.id + '/edit')" v-if="['draft','returned'].includes(doc.document_status)">编辑</el-button>
        <el-button type="success" @click="runAnalysis">发起风险分析</el-button>
      </template>
    </el-page-header>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="16">
        <el-card header="单据信息">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="单据编号">{{ doc.document_no }}</el-descriptions-item>
            <el-descriptions-item label="类型">{{ doc.document_type }}</el-descriptions-item>
            <el-descriptions-item label="申请部门">{{ doc.applicant_department }}</el-descriptions-item>
            <el-descriptions-item label="预算部门">{{ doc.budget_department }}</el-descriptions-item>
            <el-descriptions-item label="收款单位">{{ doc.payee_name }}</el-descriptions-item>
            <el-descriptions-item label="收款账号">{{ doc.payee_account }}</el-descriptions-item>
            <el-descriptions-item label="总金额">{{ doc.total_amount }} {{ doc.currency }}</el-descriptions-item>
            <el-descriptions-item label="申请日期">{{ doc.apply_date }}</el-descriptions-item>
            <el-descriptions-item label="事由" :span="2">{{ doc.reason_text }}</el-descriptions-item>
          </el-descriptions>
          <div v-if="Object.keys(doc.extra_fields || {}).length" style="margin-top:10px">
            <el-tag v-for="(v,k) in doc.extra_fields" :key="k" style="margin-right:6px">{{ k }}: {{ v }}</el-tag>
          </div>
        </el-card>

        <el-card header="费用/付款明细" style="margin-top:16px">
          <el-table :data="doc.line_items" size="small">
            <el-table-column prop="item_type" label="类型" width="90" />
            <el-table-column prop="item_name" label="项目" />
            <el-table-column prop="expense_date" label="日期" width="120" />
            <el-table-column prop="expense_location" label="地点" width="140" />
            <el-table-column prop="amount" label="金额" width="120" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card header="附件">
          <el-upload :http-request="upload" :show-file-list="false">
            <el-button size="small" type="primary">上传附件</el-button>
          </el-upload>
          <el-table :data="doc.attachments" size="small" style="margin-top:10px">
            <el-table-column prop="file_name" label="文件名">
              <template #default="{ row }"><el-link type="primary" @click="download(row)">{{ row.file_name }}</el-link></template>
            </el-table-column>
            <el-table-column prop="parse_status" label="解析状态" width="100">
              <template #default="{ row }"><el-tag size="small" :type="parseType(row.parse_status)">{{ row.parse_status }}</el-tag></template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button link type="warning" size="small" @click="parse(row)">解析</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card header="金额核对" style="margin-top:16px">
          <el-table :data="amountRows" size="small">
            <el-table-column prop="label" label="来源" width="90" />
            <el-table-column prop="value" label="金额" />
          </el-table>
          <el-alert v-if="amount.diffs" type="warning" :closable="false" style="margin-top:8px"
            :title="'明细-单差异 ' + amount.diffs.line_vs_document + '；发票-单差异 ' + amount.diffs.invoice_vs_document" />
        </el-card>
      </el-col>
    </el-row>

    <el-card header="风险分析结果" style="margin-top:16px">
      <el-empty v-if="!report" description="尚未分析，点击右上角「发起风险分析」" />
      <template v-else>
        <el-alert type="error" :closable="false" style="margin-bottom:12px"
          :title="`整体风险等级：${report.overall_risk_level.toUpperCase()} ｜ 处理建议：${report.recommendation}`" />
        <el-table :data="findings" size="small">
          <el-table-column prop="risk_level" label="等级" width="80">
            <template #default="{ row }"><el-tag :type="levelType(row.risk_level)">{{ row.risk_level }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="risk_type" label="规则" width="200" />
          <el-table-column prop="risk_title" label="风险项" width="220" />
          <el-table-column prop="description" label="说明" />
          <el-table-column prop="suggestion_text" label="处理建议" width="180" />
          <el-table-column label="复核" width="120">
            <template #default="{ row }">
              <el-select :model-value="row.review_status" size="small" @change="(v) => review(row, v)">
                <el-option label="待处理" value="pending" /><el-option label="已确认" value="confirmed" /><el-option label="已排除" value="dismissed" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
        <el-collapse style="margin-top:12px">
          <el-collapse-item title="查看完整报告 Markdown"><pre class="md">{{ report.report_markdown }}</pre></el-collapse-item>
        </el-collapse>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const route = useRoute()
const doc = ref(null)
const amount = ref({})
const report = ref(null)
const findings = ref([])

const amountRows = computed(() => ([
  { label: '单据总金额', value: amount.value.document_total },
  { label: '明细合计', value: amount.value.line_total },
  { label: '发票合计', value: amount.value.invoice_total },
  { label: '合同金额', value: amount.value.contract_total },
  { label: '付款金额', value: amount.value.payment_total },
].filter(x => x.value !== undefined)))

const statusType = (s) => ({ approved:'success', rejected:'danger', returned:'warning', draft:'info' }[s] || '')
const levelType = (l) => ({ high:'danger', medium:'warning', low:'info' }[l] || 'info')
const parseType = (s) => ({ succeeded:'success', failed:'danger', manual_review:'warning' }[s] || '')

async function load() {
  const id = route.params.id
  doc.value = await api.get(`/documents/${id}`)
  try {
    const ac = await api.get(`/documents/${id}/amount-comparison`)
    if (ac.document_total !== undefined) amount.value = ac
  } catch {}
}
async function upload(options) {
  const fd = new FormData()
  fd.append('file', options.file)
  await api.post(`/documents/${route.params.id}/attachments`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  ElMessage.success('上传成功')
  load()
}
async function download(row) {
  const resp = await api.get(`/documents/${route.params.id}/attachments/${row.id}`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp)
  const a = document.createElement('a'); a.href = url; a.download = row.file_name; a.click()
  URL.revokeObjectURL(url)
}
async function parse(row) {
  const r = await api.post(`/documents/${route.params.id}/attachments/${row.id}/parse`)
  ElMessage.success('解析状态：' + r.parse_status)
  load()
}
async function runAnalysis() {
  const r = await api.post(`/documents/${route.params.id}/analysis`)
  ElMessage.success(`分析完成：整体风险 ${r.overall_level}`)
  await loadAnalysis(r.task_id)
}
async function loadAnalysis(taskId) {
  report.value = await api.get(`/analysis/tasks/${taskId}/report`)
  findings.value = await api.get(`/analysis/tasks/${taskId}/findings`)
  load()
}
async function review(row, v) {
  await api.patch(`/analysis/risk-findings/${row.id}/review-status`, { review_status: v })
  row.review_status = v
}

onMounted(load)
</script>

<style scoped>
.md { background: #f5f5f5; padding: 12px; border-radius: 6px; white-space: pre-wrap; }
</style>
