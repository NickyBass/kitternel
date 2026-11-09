export type BackendStatus = { message: string }

export async function loadBackend(signal: AbortSignal): Promise<BackendStatus> {
  const [greeting, readiness] = await Promise.all([
    fetch('/api/hello', { signal, headers: { Accept: 'application/json' } }),
    fetch('/health/ready', { signal, headers: { Accept: 'application/json' } }),
  ])
  if (!greeting.ok || !readiness.ok) throw new Error('Backend unavailable')
  const hello: unknown = await greeting.json()
  const health: unknown = await readiness.json()
  if (typeof hello !== 'object' || hello === null || !('message' in hello) || typeof hello.message !== 'string') {
    throw new Error('Invalid greeting response')
  }
  if (typeof health !== 'object' || health === null || !('status' in health) || health.status !== 'ready') {
    throw new Error('Backend unavailable')
  }
  return { message: hello.message.trim() }
}
