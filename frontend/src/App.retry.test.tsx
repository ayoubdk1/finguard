import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'

import {
  render,
  screen,
} from '@testing-library/react'

import userEvent from '@testing-library/user-event'

import App from './App'

import {
  createTransfer,
  getAccountBalance,
  getAccountTransactions,
} from './services/api'

// ============================================
// TEST CONSTANTS
// ============================================

const ALICE_ID =
  '007c9f83-03db-48fd-bdae-9024fea8f52a'

const BOB_ID =
  'b72238cf-a238-4fac-81a1-6421f192f7c7'

const STORAGE_KEY = 'finguard.pendingTransfer'

const TEST_KEY =
  '11111111-1111-4111-8111-111111111111'

// ============================================
// MOCK API FUNCTIONS
// ============================================

vi.mock('./services/api', () => ({
  getAccountBalance: vi.fn(),
  getAccountTransactions: vi.fn(),
  createTransfer: vi.fn(),
  assessRisk: vi.fn(),
  getEventMonitoring: vi.fn(),
}))

// ============================================
// SUCCESSFUL TRANSFER RESPONSE
// ============================================

const successfulTransfer = {
  transaction_id: 'test-transaction-123',
  status: 'POSTED',
  source_account_id: ALICE_ID,
  destination_account_id: BOB_ID,
  amount_cents: 100,
  currency: 'TND',
  source_balance_cents: 2800,
  destination_balance_cents: 2200,
}

// ============================================
// SETUP BEFORE EACH TEST
// ============================================

beforeEach(() => {
  vi.resetAllMocks()

  sessionStorage.clear()

  vi.stubGlobal('crypto', {
    randomUUID: () => TEST_KEY,
  })

  vi.mocked(getAccountBalance).mockImplementation(
    async (accountId) => ({
      account_id: accountId,
      currency: 'TND',
      balance_cents:
        accountId === ALICE_ID ? 2900 : 2100,
    })
  )

  vi.mocked(getAccountTransactions).mockImplementation(
    async (accountId) => ({
      account_id: accountId,
      transactions: [],
    })
  )
})

// ============================================
// HELPER: PREPARE A TRANSFER
// ============================================

async function prepareTransfer(
  amount = '100',
  description = 'Retry test'
) {
  const user = userEvent.setup()

  const view = render(<App />)

  // Wait for balances to load
  await screen.findByText(
    /Live balance — Alice and Bob/i
  )

  // Open transfer modal
  await user.click(
    screen.getByRole('button', {
      name: /New Transfer/i,
    })
  )

  // Enter amount
  await user.type(
    screen.getByLabelText(/Amount \(cents\)/i),
    amount
  )

  // Enter description
  await user.type(
    screen.getByLabelText(/Description/i),
    description
  )

  // Review the transfer
  await user.click(
    screen.getByRole('button', {
      name: /Review Transfer/i,
    })
  )

  return {
    user,
    unmount: view.unmount,
  }
}

// ============================================
// SAFE RETRY TESTS
// ============================================

describe('FinGuard Safe Transfer Retries', () => {

  // ==========================================
  // TEST 1 — NETWORK FAILURE AND RETRY
  // ==========================================

  it('retries using the same payload and idempotency key', async () => {

    // First request fails
    vi.mocked(createTransfer)
      .mockRejectedValueOnce(
        new Error('Network interrupted')
      )
      .mockResolvedValueOnce(successfulTransfer)

    const { user } = await prepareTransfer()

    // First submission
    await user.click(
      screen.getByRole('button', {
        name: /Confirm Transfer/i,
      })
    )

    // Verify error appears
    expect(
      await screen.findByRole('alert')
    ).toHaveTextContent('Network interrupted')

    expect(createTransfer).toHaveBeenCalledTimes(1)

    // Verify request was saved
    const saved = JSON.parse(
      sessionStorage.getItem(STORAGE_KEY) ?? '{}'
    )

    expect(saved.key).toBe(TEST_KEY)

    expect(saved.payload.amount_cents).toBe(100)

    expect(saved.payload.source_account_id).toBe(
      ALICE_ID
    )

    expect(saved.payload.destination_account_id).toBe(
      BOB_ID
    )

    // Retry the same request
    await user.click(
      screen.getByRole('button', {
        name: /Retry Same Transfer/i,
      })
    )

    // Verify success
    expect(
      await screen.findByRole('heading', {
        name: /Transfer Successful/i,
      })
    ).toBeInTheDocument()

    // Two API calls were made
    expect(createTransfer).toHaveBeenCalledTimes(2)

    // Both calls must use EXACTLY the same arguments
    const calls = vi.mocked(createTransfer).mock.calls

    expect(calls[1]).toEqual(calls[0])

    // Pending request must be cleared after success
    expect(
      sessionStorage.getItem(STORAGE_KEY)
    ).toBeNull()

  })

  // ==========================================
  // TEST 2 — RECOVERY AFTER PAGE REMOUNT
  // ==========================================

  it('restores an interrupted transfer after remounting', async () => {

    vi.mocked(createTransfer).mockRejectedValueOnce(
      new Error('Connection lost')
    )

    const { user, unmount } = await prepareTransfer(
      '125',
      'Persistent retry test'
    )

    // Submit first attempt
    await user.click(
      screen.getByRole('button', {
        name: /Confirm Transfer/i,
      })
    )

    // Wait for retry state
    await screen.findByRole('button', {
      name: /Retry Same Transfer/i,
    })

    // Capture saved request
    const savedBefore = sessionStorage.getItem(
      STORAGE_KEY
    )

    expect(savedBefore).not.toBeNull()

    expect(createTransfer).toHaveBeenCalledTimes(1)

    // Simulate leaving the page
    unmount()

    // Reopen the application
    render(<App />)

    await screen.findByText(
      /Live balance — Alice and Bob/i
    )

    // Open transfer modal again
    await user.click(
      screen.getByRole('button', {
        name: /New Transfer/i,
      })
    )

    // The review screen should be restored
    expect(
      screen.getByRole('heading', {
        name: /Review Transfer/i,
      })
    ).toBeInTheDocument()

    // Original amount remains unchanged
    expect(
      screen.getByText('125 cents')
    ).toBeInTheDocument()

    // The application must NOT automatically resubmit
    expect(createTransfer).toHaveBeenCalledTimes(1)

    // Saved request is still identical
    expect(
      sessionStorage.getItem(STORAGE_KEY)
    ).toBe(savedBefore)

    expect(
      screen.getByRole('button', {
        name: /Retry Same Transfer/i,
      })
    ).toBeInTheDocument()

  })

  // ==========================================
  // TEST 3 — REPEATED NETWORK FAILURES
  // ==========================================

  it('preserves the original request after multiple failures', async () => {

    vi.mocked(createTransfer)
      .mockRejectedValueOnce(
        new Error('First connection failure')
      )
      .mockRejectedValueOnce(
        new Error('Second connection failure')
      )

    const { user } = await prepareTransfer()

    // First attempt
    await user.click(
      screen.getByRole('button', {
        name: /Confirm Transfer/i,
      })
    )

    expect(
      await screen.findByRole('alert')
    ).toHaveTextContent('First connection failure')

    // Retry
    await user.click(
      screen.getByRole('button', {
        name: /Retry Same Transfer/i,
      })
    )

    expect(
      await screen.findByText(
        /Second connection failure/i
      )
    ).toBeInTheDocument()

    // Two attempts, same data
    expect(createTransfer).toHaveBeenCalledTimes(2)

    const calls = vi.mocked(createTransfer).mock.calls

    expect(calls[1]).toEqual(calls[0])

    // Request should remain saved
    const saved = JSON.parse(
      sessionStorage.getItem(STORAGE_KEY) ?? '{}'
    )

    expect(saved.key).toBe(TEST_KEY)

    expect(saved.payload.amount_cents).toBe(100)

    // User can still retry
    expect(
      screen.getByRole('button', {
        name: /Retry Same Transfer/i,
      })
    ).toBeEnabled()

  })

})
