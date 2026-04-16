<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()
const isActiveInbox = computed(() => route.name === 'inbox')
const isActiveRuns = computed(() => route.name === 'runs' || route.name === 'run')
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <header class="border-b border-ink-200 bg-white">
      <div class="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-3">
        <div class="flex items-center gap-3">
          <RouterLink to="/" class="flex items-center gap-2 text-ink-900">
            <span class="grid h-9 w-9 place-items-center rounded-xl bg-ink-900 text-white">
              <span class="text-sm font-bold">DB</span>
            </span>
            <div>
              <div class="text-sm font-semibold leading-none">Decibench</div>
              <div class="text-[11px] uppercase tracking-widest text-ink-400">
                Failure Workbench
              </div>
            </div>
          </RouterLink>
          <nav class="ml-4 flex items-center gap-1">
            <RouterLink
              to="/"
              class="rounded-md px-3 py-1.5 text-sm font-medium"
              :class="
                isActiveInbox
                  ? 'bg-ink-900 text-white'
                  : 'text-ink-600 hover:bg-ink-100'
              "
            >
              Failure Inbox
            </RouterLink>
            <RouterLink
              to="/runs"
              class="rounded-md px-3 py-1.5 text-sm font-medium"
              :class="
                isActiveRuns
                  ? 'bg-ink-900 text-white'
                  : 'text-ink-600 hover:bg-ink-100'
              "
            >
              Runs
            </RouterLink>
          </nav>
        </div>
        <div class="flex items-center gap-2 text-xs text-ink-500">
          <span class="pill-muted">v1.0.0</span>
          <a
            href="https://github.com/anthropics/decibench"
            target="_blank"
            rel="noreferrer"
            class="text-ink-400 hover:text-ink-700"
          >
            GitHub
          </a>
        </div>
      </div>
    </header>

    <main class="mx-auto w-full max-w-7xl flex-1 px-6 py-6">
      <RouterView />
    </main>

    <footer class="border-t border-ink-100 py-4 text-center text-xs text-ink-400">
      Decibench is local-first and reads from <code>.decibench/decibench.sqlite</code>.
    </footer>
  </div>
</template>
