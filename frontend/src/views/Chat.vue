<template>
  <el-card class="chat-card">
    <div class="header">
      <h3>智能审核对话</h3>
      <el-button size="small" @click="newSession">新会话</el-button>
    </div>
    <div class="msgs" ref="boxRef">
      <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
        <div class="bubble">{{ m.content }}</div>
      </div>
    </div>
    <div class="input">
      <el-input v-model="text" placeholder="输入单据类型或编号，如：帮我分析对公付款单 DN-XXX-20260827-1234" @keyup.enter="send" />
      <el-button type="primary" @click="send">发送</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const messages = ref([])
const text = ref('')
const sessionId = ref(null)
const boxRef = ref(null)

async function newSession() {
  const r = await api.post('/review-sessions', {})
  sessionId.value = r.id
  messages.value = [{ id: 1, role: 'assistant', content: '您好，请告诉我单据类型与单据编号。' }]
  scroll()
}
async function send() {
  if (!text.value.trim()) return
  const content = text.value.trim()
  text.value = ''
  messages.value.push({ id: Date.now(), role: 'user', content })
  try {
    const r = await api.post(`/review-sessions/${sessionId.value}/messages`, { content })
    messages.value.push({ id: Date.now() + 1, role: 'assistant', content: r.reply_text })
    if (r.data?.task_id) ElMessage.success('分析完成，可在单据详情查看')
  } catch (e) {}
  scroll()
}
async function scroll() {
  await nextTick()
  boxRef.value && (boxRef.value.scrollTop = boxRef.value.scrollHeight)
}

onMounted(newSession)
</script>

<style scoped>
.chat-card { height: calc(100vh - 60px); display: flex; flex-direction: column; }
.header { display: flex; justify-content: space-between; align-items: center; }
.header h3 { margin: 0; }
.msgs { flex: 1; overflow-y: auto; padding: 12px; background: #fafafa; border-radius: 6px; margin: 12px 0; }
.msg { display: flex; margin: 8px 0; }
.msg.user { justify-content: flex-end; }
.bubble { max-width: 70%; padding: 8px 12px; border-radius: 8px; white-space: pre-wrap; }
.msg.user .bubble { background: #409eff; color: #fff; }
.msg.assistant .bubble { background: #fff; border: 1px solid #e4e7ed; }
.input { display: flex; gap: 8px; }
</style>
