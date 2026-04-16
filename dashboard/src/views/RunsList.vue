<script setup lang="ts">
import { useRuns } from '../api'
import ErrorBox from '../components/ErrorBox.vue'
import Spinner from '../components/Spinner.vue'
import { formatScore, relativeTime } from '../format'

const { data, isLoading, error } = useRuns()
</script>

<template>
  <section class="space-y-4">
    <div>
      <h1 class="text-2xl font-bold text-ink-900">Runs</h1>
      <p class="mt-1 text-sm text-ink-500">Suite-style runs created by `decibench run`.</p>
    </div>

    <div v-if="isLoading" class="card p-6"><Spinner label="Loading runs…" /></div>
    <ErrorBox v-else-if="error" :error="error" />
    <div v-else-if="!data || data.length === 0" class="card p-10 text-center text-ink-500">
      No runs yet. Try <code>decibench run --suite quick --target demo://</code>.
    </div>
    <div v-else class="card overflow-hidden">
      <table class="min-w-full divide-y divide-ink-100 text-sm">
        <thead class="bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
          <tr>
            <th class="px-4 py-3">Suite</th>
            <th class="px-4 py-3">Target</th>
            <th class="px-4 py-3">Score</th>
            <th class="px-4 py-3">Pass / Fail</th>
            <th class="px-4 py-3">When</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-ink-100 bg-white">
          <tr
            v-for="run in data"
            :key="run.id"
            class="cursor-pointer hover:bg-ink-50"
            @click="$router.push({ name: 'run', params: { runId: run.id } })"
          >
            <td class="px-4 py-3 font-medium">{{ run.suite }}</td>
            <td class="px-4 py-3 break-all">{{ run.target }}</td>
            <td
              class="px-4 py-3 font-semibold"
              :class="run.score >= 80 ? 'text-emerald-600' : 'text-rose-600'"
            >
              {{ formatScore(run.score) }}
            </td>
            <td class="px-4 py-3 text-xs">
              <span class="pill-pass mr-1">{{ run.passed }} pass</span>
              <span v-if="run.failed > 0" class="pill-fail">{{ run.failed }} fail</span>
            </td>
            <td class="px-4 py-3 text-xs text-ink-500">{{ relativeTime(run.timestamp) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
