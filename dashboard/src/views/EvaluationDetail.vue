<script setup lang="ts">
import { computed } from 'vue'

import { useStoredEvaluation } from '../api'
import ErrorBox from '../components/ErrorBox.vue'
import Spinner from '../components/Spinner.vue'
import { formatScore } from '../format'

const props = defineProps<{ evaluationId: string }>()
const evalId = computed(() => props.evaluationId)
const { data, isLoading, error } = useStoredEvaluation(evalId)

// The evaluation id format is `<timestamp>-<safe-call-id>`. We restore the
// original call id by stripping the leading timestamp so the back link works.
const inferredCallId = computed(() => {
  const parts = props.evaluationId.split('-')
  if (parts.length < 2) return null
  return parts.slice(1).join('-')
})
</script>

<template>
  <section class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <RouterLink to="/" class="text-sm font-medium text-ink-500 hover:text-ink-900">
          ← Failure Inbox
        </RouterLink>
        <h1 class="mt-2 text-2xl font-bold text-ink-900">Evaluation</h1>
        <div class="mt-1 font-mono text-xs text-ink-500">{{ evaluationId }}</div>
      </div>
      <RouterLink
        v-if="inferredCallId"
        :to="{ name: 'call', params: { callId: inferredCallId } }"
        class="btn-ghost"
      >
        View call
      </RouterLink>
    </div>

    <div v-if="isLoading" class="card p-6"><Spinner label="Loading evaluation…" /></div>
    <ErrorBox v-else-if="error" :error="error" />
    <div v-else-if="data" class="space-y-6">
      <div class="card grid gap-3 p-5 sm:grid-cols-3">
        <div>
          <div class="label">Scenario</div>
          <div class="font-mono text-sm">{{ data.scenario_id }}</div>
        </div>
        <div>
          <div class="label">Score</div>
          <div
            :class="data.passed ? 'text-emerald-600' : 'text-rose-600'"
            class="text-2xl font-semibold"
          >
            {{ formatScore(data.score) }}
          </div>
        </div>
        <div>
          <div class="label">Status</div>
          <span :class="data.passed ? 'pill-pass' : 'pill-fail'">
            {{ data.passed ? 'PASS' : 'FAIL' }}
          </span>
          <div class="mt-1 flex flex-wrap gap-1">
            <span v-for="cat in data.failure_summary" :key="cat" class="pill-fail">
              {{ cat }}
            </span>
          </div>
        </div>
      </div>

      <div class="card p-5">
        <h2 class="mb-3 text-base font-semibold text-ink-900">Metric breakdown</h2>
        <table class="w-full text-sm">
          <thead class="text-left text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th class="py-2">Metric</th>
              <th class="py-2">Value</th>
              <th class="py-2">Threshold</th>
              <th class="py-2 text-right">Status</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-ink-100">
            <tr v-for="m in Object.values(data.metrics)" :key="m.name">
              <td class="py-2 pr-2 font-mono text-xs text-ink-700">{{ m.name }}</td>
              <td class="py-2">
                {{ m.value.toFixed(2) }}<span class="text-xs text-ink-400">{{ m.unit }}</span>
              </td>
              <td class="py-2 text-ink-500">{{ m.threshold ?? '—' }}</td>
              <td class="py-2 text-right">
                <span :class="m.passed ? 'pill-pass' : 'pill-fail'">
                  {{ m.passed ? 'pass' : 'fail' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card p-5">
        <h2 class="mb-3 text-base font-semibold text-ink-900">Failures</h2>
        <ul v-if="data.failures.length" class="space-y-1 text-sm text-rose-700">
          <li v-for="f in data.failures" :key="f">• {{ f }}</li>
        </ul>
        <div v-else class="text-sm text-ink-400">None recorded.</div>
      </div>
    </div>
  </section>
</template>
