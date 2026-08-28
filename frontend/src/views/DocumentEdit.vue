<template>
  <el-card :header="isEdit ? '编辑单据' : '新建单据'">
    <el-form :model="form" label-width="110px">
      <el-row :gutter="16">
        <el-form-item label="单据类型"><el-select v-model="form.document_type">
          <el-option v-for="t in docTypes" :key="t" :label="t" :value="t" /></el-select></el-form-item>
        <el-form-item label="申请部门"><el-input v-model="form.applicant_department" /></el-form-item>
        <el-form-item label="预算部门"><el-input v-model="form.budget_department" /></el-form-item>
        <el-form-item label="费用类别"><el-input v-model="form.expense_category" /></el-form-item>
      </el-row>
      <el-row :gutter="16">
        <el-form-item label="收款单位"><el-input v-model="form.payee_name" /></el-form-item>
        <el-form-item label="收款账号"><el-input v-model="form.payee_account" /></el-form-item>
        <el-form-item label="总金额"><el-input-number v-model="form.total_amount" :min="0" :precision="2" /></el-form-item>
        <el-form-item label="币种"><el-input v-model="form.currency" /></el-form-item>
      </el-row>
      <el-row :gutter="16">
        <el-form-item label="申请日期"><el-date-picker v-model="form.apply_date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="合同编号" v-if="showExtra.contract"><el-input v-model="form.extra_fields.contract_no" /></el-form-item>
        <el-form-item label="合同金额" v-if="showExtra.contract"><el-input-number v-model="form.extra_fields.contract_amount" :precision="2" /></el-form-item>
        <el-form-item label="付款比例" v-if="showExtra.contract"><el-input-number v-model="form.extra_fields.payment_ratio" :min="0" :max="1" :step="0.1" /></el-form-item>
      </el-row>
      <el-form-item label="事由"><el-input v-model="form.reason_text" type="textarea" :rows="2" /></el-form-item>

      <el-divider content-position="left">费用/付款明细</el-divider>
      <el-table :data="form.line_items" size="small">
        <el-table-column label="类型" width="90">
          <template #default="{ row }"><el-select v-model="row.item_type"><el-option label="支出" value="expense" /><el-option label="付款" value="payment" /></el-select></template>
        </el-table-column>
        <el-table-column label="项目名称"><template #default="{ row }"><el-input v-model="row.item_name" /></template></el-table-column>
        <el-table-column label="金额" width="140"><template #default="{ row }"><el-input-number v-model="row.amount" :precision="2" /></template></el-table-column>
        <el-table-column label="消费日期" width="160"><template #default="{ row }"><el-date-picker v-model="row.expense_date" value-format="YYYY-MM-DD" /></template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row, $index }"><el-button link type="danger" @click="form.line_items.splice($index,1)">删除</el-button></template></el-table-column>
      </el-table>
      <el-button size="small" @click="lineItems.push({ item_type:'expense', item_name:'', amount:0, quantity:1, unit_price:0 })">＋ 添加明细</el-button>

      <div style="margin-top:24px">
        <el-button type="primary" :loading="saving" @click="save">保存草稿</el-button>
        <el-button type="success" :loading="saving" @click="save(true)">保存并提交审批</el-button>
      </div>
    </el-form>
  </el-card>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const route = useRoute()
const router = useRouter()
const docTypes = ['对公付款单', '预付款单', '批量付款单', '费用报销单', '差旅报销单']
const isEdit = computed(() => !!route.params.id)
const saving = ref(false)

const showExtra = computed(() => ['对公付款单', '预付款单'].includes(form.document_type))

const form = reactive({
  document_type: '费用报销单', applicant_department: '', budget_department: '', payee_name: '',
  payee_account: '', expense_category: '', total_amount: 0, currency: 'CNY', apply_date: '',
  reason_text: '', extra_fields: {}, line_items: [],
})

async function load() {
  if (!isEdit.value) return
  const d = await api.get(`/documents/${route.params.id}`)
  Object.assign(form, {
    document_type: d.document_type, applicant_department: d.applicant_department,
    budget_department: d.budget_department, payee_name: d.payee_name, payee_account: d.payee_account,
    expense_category: d.expense_category, total_amount: d.total_amount, currency: d.currency,
    apply_date: d.apply_date, reason_text: d.reason_text, extra_fields: d.extra_fields || {},
    line_items: d.line_items.map((l) => ({ item_type: l.item_type, item_name: l.item_name, amount: l.amount, quantity: l.quantity, unit_price: l.unit_price, expense_date: l.expense_date })),
  })
}

async function save(submit = false) {
  saving.value = true
  try {
    let id = route.params.id
    if (isEdit.value) {
      await api.patch(`/documents/${id}`, form)
    } else {
      const d = await api.post('/documents', form)
      id = d.id
    }
    if (submit) {
      await api.post(`/documents/${id}/submit`)
      ElMessage.success('已保存并提交审批')
    } else {
      ElMessage.success('已保存草稿')
    }
    router.push('/documents/' + id)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
