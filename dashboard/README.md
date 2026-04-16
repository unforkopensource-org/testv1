# Decibench Dashboard

Vue 3 + Vite + TypeScript + Tailwind failure-analysis workbench for the
[Decibench](../README.md) FastAPI server.

## Stack

- **Vue 3** (Composition API + `<script setup>`)
- **TypeScript** (`strict: true`)
- **Vite** for dev/build
- **Tailwind CSS** for styling
- **Vue Router** (hash mode — works as a single static `index.html`)
- **TanStack Query** for typed, cached API state
- **Apache ECharts** for span/timeline visuals

## Develop

```bash
cd dashboard
npm install
npm run dev          # Vite dev server on :5173 — proxies /runs, /calls, etc to :8000
```

In a separate shell run the FastAPI server:

```bash
decibench serve --port 8000
```

## Build

```bash
npm run build
```

Output is written to `../src/decibench/api/static/` and shipped inside the
Python package, so `pip install decibench && decibench serve` works without
needing Node at install time.
