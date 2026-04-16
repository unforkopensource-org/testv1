<script setup lang="ts">
import * as echarts from 'echarts/core'
import { CustomChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { CallTimeline } from '../api'

echarts.use([CustomChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ timeline: CallTimeline }>()
const container = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

// Color spans by component (asr/llm/tts/...) so eyeballing failure modes is
// instant: heavy LLM bars say "model is slow", heavy ASR says "STT is slow".
const PALETTE: Record<string, string> = {
  asr: '#6366f1',
  llm: '#0ea5e9',
  tts: '#22c55e',
  tool_call: '#f97316',
  turn_latency: '#a855f7',
  network: '#64748b',
}

function colorFor(name: string): string {
  return PALETTE[name] ?? '#475569'
}

function render() {
  if (!container.value) return
  if (!chart) chart = echarts.init(container.value)

  const spans = props.timeline.spans
  const componentNames = Array.from(new Set(spans.map((s) => s.name)))
  const data = spans.map((s) => ({
    name: s.name,
    value: [componentNames.indexOf(s.name), s.start_ms, s.end_ms, s.duration_ms],
    itemStyle: { color: colorFor(s.name) },
  }))

  chart.setOption({
    tooltip: {
      formatter: (params: { value: number[]; name: string }) =>
        `<b>${params.name}</b><br/>` +
        `start ${params.value[1].toFixed(0)} ms<br/>` +
        `end ${params.value[2].toFixed(0)} ms<br/>` +
        `duration ${params.value[3].toFixed(1)} ms`,
    },
    legend: {
      data: componentNames,
      top: 0,
    },
    grid: { left: 80, right: 24, top: 36, bottom: 30 },
    xAxis: {
      type: 'value',
      name: 'ms',
      min: 0,
      max: Math.max(props.timeline.duration_ms, ...spans.map((s) => s.end_ms)),
    },
    yAxis: {
      type: 'category',
      data: componentNames,
    },
    series: [
      {
        type: 'custom',
        name: 'spans',
        renderItem: (
          _params: unknown,
          api: {
            value: (i: number) => number
            coord: (xy: number[]) => number[]
            size: (xy: number[]) => number[]
            style: () => Record<string, unknown>
          },
        ) => {
          const categoryIndex = api.value(0)
          const start = api.coord([api.value(1), categoryIndex])
          const end = api.coord([api.value(2), categoryIndex])
          const height = api.size([0, 1])[1] * 0.6
          return {
            type: 'rect',
            shape: {
              x: start[0],
              y: start[1] - height / 2,
              width: Math.max(end[0] - start[0], 1),
              height,
            },
            style: api.style(),
          }
        },
        encode: { x: [1, 2], y: 0 },
        data,
      },
    ],
  })
}

onMounted(() => {
  render()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})

watch(
  () => props.timeline,
  () => render(),
  { deep: true },
)

function handleResize() {
  chart?.resize()
}
</script>

<template>
  <div ref="container" class="h-72 w-full" />
</template>
