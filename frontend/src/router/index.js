import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../App.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue') },
      { path: 'documents', name: 'documents', component: () => import('../views/Documents.vue') },
      { path: 'documents/new', name: 'document-new', component: () => import('../views/DocumentEdit.vue') },
      { path: 'documents/:id/edit', name: 'document-edit', component: () => import('../views/DocumentEdit.vue') },
      { path: 'documents/:id', name: 'document-detail', component: () => import('../views/DocumentDetail.vue') },
      { path: 'chat', name: 'chat', component: () => import('../views/Chat.vue') },
      { path: 'approval', name: 'approval', component: () => import('../views/Approval.vue') },
      { path: 'rules', name: 'rules', component: () => import('../views/Rules.vue') },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (to.meta.public) return true
  const auth = useAuthStore()
  if (!auth.isLoggedIn) return { name: 'login' }
  return true
})

export default router
