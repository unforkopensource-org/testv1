<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ text: string; label?: string }>()
const copied = ref(false)

async function copy() {
  try {
    await navigator.clipboard.writeText(props.text)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    // Older browsers without async clipboard — silently no-op rather than
    // throwing, since the dashboard is a local tool and the YAML is also
    // visible on screen for manual selection.
  }
}
</script>

<template>
  <button class="btn-ghost" type="button" @click="copy">
    <span v-if="copied">Copied!</span>
    <span v-else>{{ label ?? 'Copy' }}</span>
  </button>
</template>
