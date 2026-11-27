<script setup>
defineProps({
  variant: { type: String, default: 'card' }, // 'dashboard' | 'replay-list' | 'replay-detail' | 'card'
})
</script>

<template>
  <div v-if="variant === 'dashboard'" class="sk-dash">
    <div class="sk-kpis">
      <div v-for="i in 5" :key="i" class="card sk-kpi">
        <div class="skeleton" style="width: 32px; height: 28px" />
        <div class="skeleton" style="width: 72%; height: 28px; margin-top: 12px" />
        <div class="skeleton" style="width: 55%; height: 12px; margin-top: 8px" />
      </div>
    </div>
    <div class="card sk-funnel">
      <div class="skeleton" style="width: 100%; height: 240px; border-radius: 12px" />
    </div>
    <div class="sk-cols">
      <div class="card"><div class="skeleton" style="width: 100%; height: 210px" /></div>
      <div class="card"><div class="skeleton" style="width: 100%; height: 210px" /></div>
    </div>
  </div>

  <div v-else-if="variant === 'replay-list'" class="sk-rlist">
    <div v-for="i in 6" :key="i" class="sk-rcard">
      <div class="skeleton" style="width: 40%; height: 15px" />
      <div class="skeleton" style="width: 100%; height: 18px; margin-top: 8px" />
      <div class="skeleton" style="width: 75%; height: 11px; margin-top: 8px" />
    </div>
  </div>

  <div v-else-if="variant === 'replay-detail'" class="sk-rdetail">
    <div class="skeleton" style="width: 240px; height: 26px" />
    <div class="sk-pills">
      <div v-for="i in 5" :key="i" class="skeleton" style="height: 54px; border-radius: 10px" />
    </div>
    <div class="skeleton" style="width: 100%; height: 185px; border-radius: 12px" />
    <div class="skeleton" style="width: 100%; height: 160px; border-radius: 12px" />
  </div>

  <div v-else class="card">
    <div class="skeleton" style="width: 40%; height: 18px" />
    <div class="skeleton" style="width: 100%; height: 120px; margin-top: 14px" />
  </div>
</template>

<style scoped>
.sk-dash {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.sk-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}
.sk-kpi {
  padding: 18px;
}
.sk-cols {
  display: grid;
  grid-template-columns: 1.35fr 1fr;
  gap: 16px;
}
.sk-rlist {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sk-rcard {
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--bg-card-2);
}
.sk-rdetail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sk-pills {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 1100px) {
  .sk-kpis,
  .sk-pills {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .sk-cols {
    grid-template-columns: 1fr;
  }
}
</style>
