import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'

const routes = [
  {
    path: '/',
    name: 'analytics',
    component: DashboardView,
    meta: { title: 'Analytics' },
  },
  {
    path: '/replay/:id?',
    name: 'replay',
    component: () => import('../views/ReplayView.vue'),
    meta: { title: 'Session Replay' },
  },
  {
    path: '/models',
    name: 'models',
    component: () => import('../views/ModelsView.vue'),
    meta: { title: 'Models' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from) {
    // keep scroll position when only switching sessions inside the replay view
    if (to.name === 'replay' && from.name === 'replay') return false
    return { top: 0 }
  },
})

router.afterEach((to) => {
  const t = to.meta?.title
  document.title = t ? `${t} · DealMind AI` : 'DealMind AI · Basket Intelligence'
})

export default router
