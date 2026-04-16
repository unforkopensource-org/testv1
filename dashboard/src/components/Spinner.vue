<script setup lang="ts">
defineProps<{ label?: string }>()
</script>

<template>
  <div class="flex items-center gap-2 text-sm text-ink-400">
    <span
      class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-ink-300 border-t-ink-700"
    />
    <span v-if="label">{{ label }}</span>
  </div>
</template>
