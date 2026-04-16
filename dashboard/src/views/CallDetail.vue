<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  useCallLatestEvaluation,
  useCallTimeline,
  useCallTrace,
  useEvaluateCall,
  useGenerateRegression,
} from '../api'
import CopyButton from '../components/CopyButton.vue'
import ErrorBox from '../components/ErrorBox.vue'
import SpanTimelineChart from '../components/SpanTimelineChart.vue'
import Spinner from '../components/Spinner.vue'
import {
  formatDuration,
  formatScore,
  formatTimestamp,
  relativeTime,
} from '../format'

const props = defineProps<{ callId: string }>()
const callIdRef = computed(() => props.callId)

const { data: trace, isLoading: traceLoading, error: traceError } = useCallTrace(callIdRef)
const { data: timeline, isLoading: timelineLoading } = useCallTimeline(callIdRef)
const {
  data: latestEval,
  isLoading: evalLoading,
  refetch: refetchEval,
} = useCallLatestEvaluation(callIdRef)

const evaluateMutation = useEvaluateCall()
const regressionMutation = useGenerateRegression()
const regression = ref<{ scenario_id: string; yaml: string } | null>(null)

async function runEvaluation() {
  await evaluateMutation.mutateAsync(props.callId)
  await refetchEval()
}

async function generate() {
  regression.value = await regressionMutation.mutateAsync(props.callId)
}

function downloadYaml() {
  if (!regression.value) return
  const blob = new Blob([regression.value.yaml], { type: 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${regression.value.scenario_id}.yaml`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <section class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <RouterLink to="/" class="text-sm font-medium text-ink-500 hover:text-ink-900">
          ← Failure Inbox
        </RouterLink>
        <h1 class="mt-2 text-2xl font-bold text-ink-900">Call Detail</h1>
        <div class="mt-1 font-mono text-xs text-ink-500">{{ callId }}</div>
      </div>
      <div class="flex gap-2">
        <button
          class="btn-ghost"
          :disabled="evaluateMutation.isPending.value"
          @click="runEvaluation"
        >
          {{ evaluateMutation.isPending.value ? 'Evaluating…' : 'Re-evaluate' }}
        </button>
        <button
          class="btn-primary"
          :disabled="regressionMutation.isPending.value"
          @click="generate"
        >
          {{ regressionMutation.isPending.value ? 'Generating…' : 'Generate regression' }}
        </button>
      </div>
    </div>

    <ErrorBox v-if="traceError" :error="traceError" />

    <!-- Header card -->
    <div v-if="traceLoading" class="card p-6"><Spinner label="Loading call…" /></div>
    <div v-else-if="trace" class="grid gap-3 sm:grid-cols-4">
      <div class="card p-4">
        <div class="label">Source</div>
        <div class="text-base font-semibold">{{ trace.source }}</div>
      </div>
      <div class="card p-4">
        <div class="label">Target</div>
        <div class="break-all text-sm">{{ trace.target || '—' }}</div>
      </div>
      <div class="card p-4">
        <div class="label">Started</div>
        <div class="text-sm">{{ formatTimestamp(trace.started_at) }}</div>
        <div class="text-xs text-ink-400">{{ relativeTime(trace.started_at) }}</div>
      </div>
      <div class="card p-4">
        <div class="label">Duration</div>
        <div class="text-base font-semibold">{{ formatDuration(trace.duration_ms) }}</div>
      </div>
    </div>

    <!-- Latest evaluation summary -->
    <div class="card p-5">
      <div class="flex items-center justify-between">
        <div>
          <div class="label">Latest evaluation</div>
          <div v-if="evalLoading" class="text-sm text-ink-500"><Spinner /></div>
          <div v-else-if="!latestEval" class="text-sm text-ink-500">
            No evaluation yet. Click <strong>Re-evaluate</strong>.
          </div>
          <div v-else class="flex items-center gap-3">
            <span
              :class="latestEval.passed ? 'text-emerald-600' : 'text-rose-600'"
              class="text-xl font-bold"
            >
              {{ formatScore(latestEval.score) }}
            </span>
            <span :class="latestEval.passed ? 'pill-pass' : 'pill-fail'">
              {{ latestEval.passed ? 'PASS' : 'FAIL' }}
            </span>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="cat in latestEval.failure_summary"
                :key="cat"
                class="pill-fail"
              >
                {{ cat }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="latestEval" class="mt-4 grid gap-3 md:grid-cols-2">
        <div>
          <h3 class="label">Failures</h3>
          <ul v-if="latestEval.failures.length" class="space-y-1 text-sm text-rose-700">
            <li v-for="f in latestEval.failures" :key="f">• {{ f }}</li>
          </ul>
          <div v-else class="text-sm text-ink-400">No failure details captured.</div>
        </div>
        <div>
          <h3 class="label">Metrics</h3>
          <table class="w-full text-sm">
            <tbody>
              <tr v-for="m in Object.values(latestEval.metrics)" :key="m.name">
                <td class="py-1 pr-2 font-mono text-xs text-ink-600">{{ m.name }}</td>
                <td class="py-1">
                  <span :class="m.passed ? 'text-emerald-600' : 'text-rose-600'">
                    {{ m.value.toFixed(2) }}<span class="text-xs text-ink-400">{{ m.unit }}</span>
                  </span>
                </td>
                <td class="py-1 text-right">
                  <span :class="m.passed ? 'pill-pass' : 'pill-fail'">
                    {{ m.passed ? 'pass' : 'fail' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Timeline -->
    <div class="card p-5">
      <h2 class="mb-3 text-base font-semibold text-ink-900">Component timing</h2>
      <div v-if="timelineLoading"><Spinner label="Building timeline…" /></div>
      <div
        v-else-if="!timeline || timeline.spans.length === 0"
        class="text-sm text-ink-400"
      >
        No spans recorded for this call.
      </div>
      <SpanTimelineChart v-else :timeline="timeline" />
    </div>

    <!-- Transcript -->
    <div v-if="trace" class="card p-5">
      <h2 class="mb-3 text-base font-semibold text-ink-900">Transcript</h2>
      <div v-if="trace.transcript.length === 0" class="text-sm text-ink-400">
        No transcript on this call.
      </div>
      <ul v-else class="space-y-2">
        <li
          v-for="(seg, i) in trace.transcript"
          :key="i"
          class="rounded-md border border-ink-100 px-3 py-2 text-sm"
          :class="seg.role === 'caller' ? 'bg-ink-50' : 'bg-white'"
        >
          <div class="text-xs uppercase tracking-wide text-ink-400">
            {{ seg.role }} · {{ Math.round(seg.start_ms) }}–{{ Math.round(seg.end_ms) }}ms
          </div>
          <div class="mt-1 text-ink-800">{{ seg.text }}</div>
        </li>
      </ul>
    </div>

    <!-- Regression result -->
    <div v-if="regression" class="card p-5">
      <div class="mb-2 flex items-center justify-between">
        <div>
          <h2 class="text-base font-semibold text-ink-900">Regression scenario</h2>
          <div class="font-mono text-xs text-ink-500">{{ regression.scenario_id }}</div>
        </div>
        <div class="flex gap-2">
          <CopyButton :text="regression.yaml" label="Copy YAML" />
          <button class="btn-primary" @click="downloadYaml">Download .yaml</button>
        </div>
      </div>
      <pre
        class="overflow-x-auto rounded-lg bg-ink-900 p-4 text-xs text-ink-50"
      ><code>{{ regression.yaml }}</code></pre>
    </div>
  </section>
</template>
