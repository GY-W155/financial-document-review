<template>
  <el-container v-if="!isLoginPage" class="layout">
    <el-aside width="220px">
      <div class="brand">📋 财务风险审核</div>
      <el-menu :default-active="$route.path" router class="menu">
        <el-menu-item index="/dashboard"><el-icon><DataBoard /></el-icon> 工作台</el-menu-item>
        <el-menu-item index="/documents"><el-icon><Document /></el-icon> 单据管理</el-menu-item>
        <el-menu-item index="/chat"><el-icon><ChatDotRound /></el-icon> 智能审核</el-menu-item>
        <el-menu-item index="/approval"><el-icon><Stamp /></el-icon> 审批任务</el-menu-item>
        <el-menu-item index="/rules"><el-icon><Setting /></el-icon> 规则配置</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="page-title">{{ pageTitle }}</div>
        <div class="user-box">
          <span class="name">{{ auth.user?.display_name || auth.user?.username }}</span>
          <span class="roles" v-for="rn in auth.roleNames" :key="rn">{{ rn }}</span>
          <el-button link type="danger" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
  <router-view v-else />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isLoginPage = computed(() => route.path === '/login')
const pageTitle = computed(() => {
  const map = {
    '/dashboard': '审核工作台', '/documents': '单据管理', '/chat': '智能审核对话',
    '/approval': '审批任务', '/rules': '规则配置',
  }
  const hit = Object.keys(map).find((k) => route.path.startsWith(k))
  return hit ? map[hit] : route.path
})

async function logout() {
  await auth.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
</script>

<style>
body { margin: 0; background: #f5f7fa; }
.layout { height: 100vh; }
.brand { height: 60px; display: flex; align-items: center; padding: 0 20px; font-weight: 700; color: #409eff; }
.menu { border-right: none; }
.header { background: #fff; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e4e7ed; }
.user-box { display: flex; gap: 10px; align-items: center; font-size: 14px; }
.roles { background: #ecf5ff; color: #409eff; border-radius: 4px; padding: 2px 6px; font-size: 12px; }
.el-main { padding: 20px; }
</style>
