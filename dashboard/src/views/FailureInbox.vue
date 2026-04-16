<script setup lang="ts">
import { computed, reactive } from 'vue'

import {
  type FailureInboxFilters,
  useFailureInbox,
  useFailureStats,
} from '../api'
import ErrorBox from '../components/ErrorBox.vue'
import Spinner from '../components/Spinner.vue'
import { formatScore, relativeTime } from '../format'

const filters = reactive<FailureInboxFilters>({
  failed_only: true,
  source: null,
  category: null,
  max_score: null,
  q: null,
  limit: 100,
})

const { data: stats, isLoading: statsLoading } = useFailureStats()
const { data: rows, isLoading, error } = useFailureInbox(() => filters)

const sortedSources = computed(() =>
  Object.entries(stats.value?.sources ?? {}).sort((a, b) => b[1] - a[1]),
)
const sortedCategories = computed(() =>
  Object.entries(stats.value?.categories ?? {}).sort((a, b) => b[1] - a[1]),
)
</script>

<template>
  <section class="space-y-6">
    <div>
      <h1 class="text-2xl font-bold tracking-tight text-ink-900">Failure Inbox</h1>
      <p class="mt-1 text-sm text-ink-500">
        Stored evaluations from imported and live calls — failed-first.
      </p>
    </div>

    <!-- Aggregate header -->
    <div v-if="statsLoading" class="card p-4"><Spinner label="Loading stats…" /></div>
    <div v-else-if="stats" class="grid gap-3 sm:grid-cols-4">
      <div class="card p-4">
        <div class="label">Total evaluations</div>
        <div class="text-2xl font-semibold">{{ stats.total_evaluations }}</div>
      </div>
      <div class="card p-4">
        <div class="label">Failed</div>
        <div class="text-2xl font-semibold text-rose-600">{{ stats.failed }}</div>
      </div>
      <div class="card p-4">
        <div class="label">Passed</div>
        <div class="text-2xl font-semibold text-emerald-600">{{ stats.passed }}</div>
      </div>
      <div class="card p-4">
        <div class="label">Avg score</div>
        <div class="text-2xl font-semibold">{{ formatScore(stats.score.avg) }}</div>
        <div class="text-xs text-ink-400">
          range {{ formatScore(stats.score.min) }} – {{ formatScore(stats.score.max) }}
        </div>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="card grid gap-3 p-4 md:grid-cols-5">
      <div class="md:col-span-2">
        <label class="label">Search</label>
        <input
          v-model="filters.q"
          class="input"
          placeholder="call id, scenario or source"
        />
      </div>
      <div>
        <label class="label">Source</label>
        <select v-model="filters.source" class="input">
          <option :value="null">All</option>
          <option
            v-for="[name, n] in sortedSources"
            :key="name"
            :value="name"
          >
            {{ name }} ({{ n }})
          </option>
        </select>
      </div>
      <div>
        <label class="label">Failed category</label>
        <select v-model="filters.category" class="input">
          <option :value="null">Any</option>
          <option
            v-for="[name, n] in sortedCategories"
            :key="name"
            :value="name"
          >
            {{ name }} ({{ n }})
          </option>
        </select>
      </div>
      <div>
        <label class="label">Max score</label>
        <input
          v-model.number="filters.max_score"
          class="input"
          type="number"
          min="0"
          max="100"
          placeholder="100"
        />
        <label class="mt-2 flex items-center gap-2 text-xs font-medium text-ink-600">
          <input v-model="filters.failed_only" type="checkbox" /> failed only
        </label>
      </div>
    </div>

    <!-- Results table -->
    <div v-if="isLoading" class="card p-6"><Spinner label="Loading…" /></div>
    <ErrorBox v-else-if="error" :error="error" />
    <div v-else-if="!rows || rows.length === 0" class="card p-10 text-center text-ink-500">
      No matching evaluations.
    </div>
    <div v-else class="card overflow-hidden">
      <table class="min-w-full divide-y divide-ink-100 text-sm">
        <thead class="bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
          <tr>
            <th class="px-4 py-3">Call</th>
            <th class="px-4 py-3">Source</th>
            <th class="px-4 py-3">Score</th>
            <th class="px-4 py-3">Failed categories</th>
            <th class="px-4 py-3">When</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-ink-100 bg-white">
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer hover:bg-ink-50"
            @click="$router.push({ name: 'call', params: { callId: row.call_id } })"
          >
            <td class="px-4 py-3 font-mono text-xs text-ink-700">{{ row.call_id }}</td>
            <td class="px-4 py-3">
              <span class="pill-info">{{ row.source }}</span>
            </td>
            <td class="px-4 py-3">
              <span
                :class="row.passed ? 'text-emerald-600' : 'text-rose-600'"
                class="font-semibold"
              >
                {{ formatScore(row.score) }}
              </span>
            </td>
            <td class="px-4 py-3">
              <div v-if="row.failure_summary.length === 0" class="text-ink-400">—</div>
              <div v-else class="flex flex-wrap gap-1">
                <span
                  v-for="cat in row.failure_summary"
                  :key="cat"
                  class="pill-fail"
                >
                  {{ cat }}
                </span>
              </div>
            </td>
            <td class="px-4 py-3 text-xs text-ink-500">{{ relativeTime(row.evaluated_at) }}</td>
            <td class="px-4 py-3 text-right">
              <RouterLink
                :to="{ name: 'evaluation', params: { evaluationId: row.id } }"
                class="text-xs font-medium text-ink-700 hover:text-ink-900"
                @click.stop
              >
                Evaluation →
              </RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
