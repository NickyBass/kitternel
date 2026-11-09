import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

function responses(message: string) {
  return vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(JSON.stringify(
    url === '/api/hello' ? { message } : { status: 'ready' },
  ), { status: 200 })))
}

describe('backend connection', () => {
  it('shows loading while requests are pending', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<App />)
    expect(screen.getByText('Connecting to the backend…')).toBeInTheDocument()
  })
  it('renders the actual greeting and ready state', async () => {
    vi.stubGlobal('fetch', responses('Hello from the test database.'))
    render(<App />)
    expect(await screen.findByText('Hello from the test database.')).toBeInTheDocument()
    expect(screen.getByText('Backend ready · SQLite connected')).toBeInTheDocument()
  })
  it('handles an empty greeting', async () => {
    vi.stubGlobal('fetch', responses('   '))
    render(<App />)
    expect(await screen.findByText('No greeting has been configured yet.')).toBeInTheDocument()
  })
  it('handles failure and allows retry', async () => {
    const fetch = vi.fn().mockRejectedValue(new Error('private internal error'))
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    expect(await screen.findByText('Could not reach the backend.')).toBeInTheDocument()
    expect(screen.queryByText('private internal error')).not.toBeInTheDocument()
    fetch.mockImplementation(responses('Recovered greeting'))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Recovered greeting')).toBeInTheDocument()
  })
  it('rejects malformed successful responses', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}', { status: 200 }))))
    render(<App />)
    expect(await screen.findByText('Could not reach the backend.')).toBeInTheDocument()
  })
})
