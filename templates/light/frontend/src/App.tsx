import { useEffect, useState } from 'react'
import { loadBackend, type BackendStatus } from './api'

type State = { kind: 'loading' } | { kind: 'error' } | { kind: 'loaded'; data: BackendStatus }

export default function App() {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<State>({ kind: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)
    let active = true
    loadBackend(controller.signal).then(
      data => { if (active) setState({ kind: 'loaded', data }) },
      () => { if (active) setState({ kind: 'error' }) },
    ).finally(() => clearTimeout(timeout))
    return () => { active = false; controller.abort(); clearTimeout(timeout) }
  }, [attempt])
  function retry() {
    setState({ kind: 'loading' })
    setAttempt(value => value + 1)
  }
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 selection:bg-lime-200">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-8">
        <a href="/" className="text-xl font-bold tracking-tight" aria-label="Kitternel home">kitternel<span className="text-lime-700">.</span></a>
        <span className="rounded-full border border-stone-300 px-3 py-1 text-xs font-medium uppercase tracking-widest">Light / 0.1</span>
      </header>
      <main className="mx-auto max-w-5xl px-6 pb-16 pt-12 sm:pt-24">
        <p className="mb-5 text-xs font-semibold uppercase tracking-[0.2em] text-lime-800">Small footprint. Solid foundation.</p>
        <h1 className="max-w-3xl text-5xl font-semibold leading-tight tracking-tight sm:text-7xl">Build something<br />worth shipping.</h1>
        <p className="mt-6 max-w-xl text-lg leading-relaxed text-stone-600">A clear starting point for your next web application. Rust at the core, React at the surface, and SQLite keeping things simple.</p>
        <section aria-labelledby="connection-title" className="mt-12 rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="connection-title" className="text-lg font-semibold">Your stack, connected</h2>
            <span className="text-xs uppercase tracking-wider text-stone-500">Browser → Axum → SQLite</span>
          </div>
          <div role="status" aria-live="polite" className="mt-6 min-h-20">
            {state.kind === 'loading' && <p className="text-stone-600">Connecting to the backend…</p>}
            {state.kind === 'error' && <><p className="font-medium text-red-800">Could not reach the backend.</p><p className="mt-1 text-sm text-stone-600">Check the service and try again.</p><button type="button" onClick={retry} className="mt-4 rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-lime-700">Try again</button></>}
            {state.kind === 'loaded' && <><p className="mb-2 text-sm font-medium text-lime-800">Backend ready · SQLite connected</p><p className="text-xl tracking-tight">{state.data.message || 'No greeting has been configured yet.'}</p></>}
          </div>
        </section>
        <div className="mt-8 grid gap-4 text-sm text-stone-600 sm:grid-cols-3">
          <p><strong className="block text-stone-900">Rust + Axum</strong>One application process.</p>
          <p><strong className="block text-stone-900">SQLite</strong>Persistent data, fewer moving parts.</p>
          <p><strong className="block text-stone-900">React + TypeScript</strong>A familiar place to start.</p>
        </div>
      </main>
      <footer className="mx-auto max-w-5xl border-t border-stone-200 px-6 py-6 text-xs text-stone-500">Open source. Built for humans and AI agents. Foundation preview; authentication is not included.</footer>
    </div>
  )
}
