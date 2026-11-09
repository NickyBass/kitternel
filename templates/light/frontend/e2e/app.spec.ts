import { expect, test } from '@playwright/test'

test('production frontend connects to the real SQLite-backed API', async ({ page, request }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  const api = await request.get('/api/hello')
  expect(api.ok()).toBeTruthy()
  const hello = await api.json() as { message: string }
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Build something/ })).toBeVisible()
  await expect(page.getByText(hello.message, { exact: true })).toBeVisible()
  await expect(page.getByText('Backend ready · SQLite connected')).toBeVisible()
  await page.screenshot({ path: 'test-results/light-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 375, height: 812 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: 'test-results/light-mobile.png', fullPage: true })
  await page.goto('/example/client-route')
  await expect(page.getByText(hello.message, { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('frontend displays a safe failure state when API is unavailable', async ({ page }) => {
  await page.route('**/api/hello', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"service_unavailable"}' }))
  await page.goto('/')
  await expect(page.getByText('Could not reach the backend.')).toBeVisible()
})
