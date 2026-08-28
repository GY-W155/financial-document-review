import { defineStore } from 'pinia'
import api from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null'),
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    roles: (s) => (s.user?.roles || []).map((r) => (typeof r === 'string' ? r : r.role_code)),
    roleNames: (s) => (s.user?.roles || []).map((r) => (typeof r === 'string' ? r : r.role_name || r.role_code)),
    hasRole: (s) => (...codes) => s.roles.some((r) => codes.includes(r)),
  },
  actions: {
    async login(username, password) {
      const data = await api.post('/auth/login', { username, password })
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('user', JSON.stringify(data.user))
      return data
    },
    async logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    },
  },
})
