import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import axe from 'axe-core'
import App from './App'
import { LoginForm } from './LoginForm'
import SecuritySettings from './SecuritySettings'

vi.mock('./services/api', () => ({
  getAccountBalance: vi.fn().mockResolvedValue({ account_id: '1', balance: 1000, currency: 'EUR' }),
  getAccountTransactions: vi.fn().mockResolvedValue({ account_id: '1', transactions: [] }),
  createTransfer: vi.fn(),
  assessRisk: vi.fn(),
  getEventMonitoring: vi.fn(),
  getMySessions: vi.fn().mockResolvedValue({ sessions: [], total_active: 0 }),
}))

describe('Accessibility (axe-core)', () => {
  it('LoginForm has no axe violations', async () => {
    const { container } = render(<LoginForm onSuccess={vi.fn()} />)
    const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(res.violations).toEqual([])
  })

  it('SecuritySettings has no axe violations', async () => {
    const { container } = render(<SecuritySettings currentUser={{ email: 'a@b.com', role: 'CUSTOMER', mfa_enabled: false }} onUserUpdated={vi.fn()} />)
    const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(res.violations).toEqual([])
  })

  it('App dashboard has no axe violations', async () => {
    const { container } = render(<App />)
    const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(res.violations).toEqual([])
  })
})
