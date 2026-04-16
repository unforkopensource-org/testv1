<script setup lang="ts">
defineProps<{ error: unknown }>()

function describe(err: unknown): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return 'Unknown error'
}
</script>

<template>
  <div
    class="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800"
  >
    <div class="font-semibold">Something went wrong</div>
    <div class="mt-1 font-mono text-xs">{{ describe(error) }}</div>
  </div>
</template>
