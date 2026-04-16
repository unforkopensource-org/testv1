import { VueQueryPlugin } from '@tanstack/vue-query'
import { createApp } from 'vue'

import App from './App.vue'
import { router } from './router'
import './styles.css'

const app = createApp(App)
app.use(router)
app.use(VueQueryPlugin, {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        // Failure inbox refresh cadence — fast enough for live triage but
        // doesn't hammer the local SQLite store on long views.
        refetchOnWindowFocus: false,
        staleTime: 10_000,
        retry: 1,
      },
    },
  },
})
app.mount('#app')
