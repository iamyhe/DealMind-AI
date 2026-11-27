<script setup>
import { setMode, settings } from '@/services/config'

defineProps({
  title: { type: String, default: 'Unable to load data' },
  message: { type: String, default: 'Check that the FastAPI server is running or switch to Mock Data Mode.' },
  showMockSwitch: { type: Boolean, default: true },
})

defineEmits(['retry'])
</script>

<template>
  <div class="err-card card" role="alert">
    <div class="err-icon" aria-hidden="true">!</div>
    <div class="err-body">
      <div class="err-title">{{ title }}</div>
      <p class="err-msg">{{ message }}</p>
      <div class="err-actions">
        <button type="button" class="btn btn-sm btn-blue" @click="$emit('retry')">Retry</button>
        <button
          v-if="showMockSwitch && settings.mode === 'live'"
          type="button"
          class="btn btn-sm"
          @click="setMode('mock')"
        >
          Switch to Mock Mode
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.err-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  border-color: rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.06);
}
.err-icon {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: rgba(239, 68, 68, 0.16);
  color: #fca5a5;
  font-weight: 800;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.err-title {
  font-weight: 650;
  color: var(--text);
}
.err-msg {
  font-size: 0.82rem;
  color: var(--text-2);
  margin-top: 3px;
}
.err-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
</style>
