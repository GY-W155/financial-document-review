<template>
  <el-card>
    <el-tabs v-model="tab">
      <el-tab-pane label="审核规则" name="rules">
        <el-table :data="rules" size="small">
          <el-table-column prop="rule_code" label="规则编码" width="200" />
          <el-table-column prop="rule_name" label="规则名称" />
          <el-table-column prop="rule_category" label="分类" width="120" />
          <el-table-column label="阈值参数" width="260">
            <template #default="{ row }">
              <code>{{ JSON.stringify(row.threshold) }}</code>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="editRule(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="市场价参考" name="market">
        <el-table :data="prices" size="small">
          <el-table-column prop="item_name" label="项目" />
          <el-table-column prop="specification" label="规格" />
          <el-table-column prop="region" label="地区" width="100" />
          <el-table-column prop="price_min" label="最低价" width="100" />
          <el-table-column prop="price_max" label="最高价" width="100" />
          <el-table-column prop="source_name" label="来源" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="审批流程" name="workflow">
        <el-table :data="workflows" size="small" row-key="id">
          <el-table-column prop="workflow_name" label="名称" width="180" />
          <el-table-column prop="document_type" label="单据类型" width="120" />
          <el-table-column label="节点">
            <template #default="{ row }">
              <el-tag v-for="n in row.nodes" :key="n.id" style="margin-right:6px">{{ n.node_name }}(${{ n.node_order }})</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dialogVisible" title="编辑规则阈值" width="500px">
      <el-form label-width="100px">
        <el-form-item label="规则名称">{{ currentRule?.rule_name }}</el-form-item>
        <el-form-item v-for="(v, k) in currentRule?.threshold" :key="k" :label="k">
          <el-input-number v-model="currentRule.threshold[k]" :precision="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">取消</el-button>
        <el-button type="primary" @click="saveRule">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const tab = ref('rules')
const rules = ref([])
const prices = ref([])
const workflows = ref([])
const dialogVisible = ref(false)
const currentRule = ref(null)

async function load() {
  rules.value = (await api.get('/rules')) || []
  prices.value = (await api.get('/rules/market-prices')) || []
  workflows.value = (await api.get('/approval/workflows')) || []
}
function editRule(row) { currentRule.value = row; dialogVisible.value = true }
async function saveRule() {
  await api.patch(`/rules/${currentRule.value.id}`, { threshold: currentRule.value.threshold })
  ElMessage.success('已保存')
  dialogVisible.value = false
  load()
}
onMounted(load)
</script>
