<script setup lang="ts">
import { computed } from 'vue'

import { useRun } from '../api'
import ErrorBox from '../components/ErrorBox.vue'
import Spinner from '../components/Spinner.vue'
import { formatDuration, formatScore, formatTimestamp } from '../format'

const props = defineProps<{ runId: string }>()
const runId = computed(() => props.runId)
const { data, isLoading, error } = useRun(runId)
</script>

<template>
  <section class="space-y-4">
    <div>
      <RouterLink to="/runs" class="text-sm font-medium text-ink-500 hover:text-ink-900">
        ← Runs
      </RouterLink>
      <h1 class="mt-2 text-2xl font-bold text-ink-900">Run</h1>
      <div class="mt-1 font-mono text-xs text-ink-500">{{ runId }}</div>
    </div>

    <div v-if="isLoading" class="card p-6"><Spinner label="Loading run…" /></div>
    <ErrorBox v-else-if="error" :error="error" />
    <div v-else-if="data" class="space-y-4">
      <div class="card grid gap-3 p-5 sm:grid-cols-4">
        <div>
          <div class="label">Suite</div>
          <div>{{ data.suite }}</div>
        </div>
        <div>
          <div class="label">Target</div>
          <div class="break-all">{{ data.target }}</div>
        </div>
        <div>
          <div class="label">Score</div>
          <div
            class="text-2xl font-semibold"
            :class="data.decibench_score >= 80 ? 'text-emerald-600' : 'text-rose-600'"
          >
            {{ formatScore(data.decibench_score) }}
          </div>
        </div>
        <div>
          <div class="label">When</div>
          <div class="text-sm">{{ formatTimestamp(data.timestamp) }}</div>
          <div class="text-xs text-ink-400">
            {{ formatDuration(data.duration_seconds * 1000) }}
          </div>
        </div>
      </div>

      <div class="card overflow-hidden">
        <table class="min-w-full divide-y divide-ink-100 text-sm">
          <thead class="bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th class="px-4 py-3">Scenario</th>
              <th class="px-4 py-3">Score</th>
              <th class="px-4 py-3">Failures</th>
              <th class="px-4 py-3">Duration</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-ink-100 bg-white">
            <tr v-for="er in data.results" :key="er.scenario_id">
              <td class="px-4 py-3 font-mono text-xs">{{ er.scenario_id }}</td>
              <td
                class="px-4 py-3 font-semibold"
                :class="er.passed ? 'text-emerald-600' : 'text-rose-600'"
              >
                {{ formatScore(er.score) }}
              </td>
              <td class="px-4 py-3">
                <div v-if="er.failure_summary.length === 0" class="text-ink-400">—</div>
                <div v-else class="flex flex-wrap gap-1">
                  <span
                    v-for="cat in er.failure_summary"
                    :key="cat"
                    class="pill-fail"
                  >
                    {{ cat }}
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 text-ink-500">{{ formatDuration(er.duration_ms) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
