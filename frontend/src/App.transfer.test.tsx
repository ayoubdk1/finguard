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
  waitFor,
} from '@testing-library/react'

import userEvent from '@testing-library/user-event'

import App from './App'

import {
  createTransfer,
  getAccountBalance,
  getAccountTransactions,
} from './services/api'

// ============================================
// MOCK FASTAPI
// ============================================

vi.mock('./services/api', () => ({
  getAccountBalance: vi.fn(),
  getAccountTransactions: vi.fn(),
  createTransfer: vi.fn(),
  assessRisk: vi.fn(),
  getEventMonitoring: vi.fn(),
}))

const ALICE_ID =
  '007c9f83-03db-48fd-bdae-9024fea8f52a'

const BOB_ID =
  'b72238cf-a238-4fac-81a1-6421f192f7c7'

// ============================================
// TEST SETUP
// ============================================

beforeEach(() => {
  sessionStorage.clear()

  vi.clearAllMocks()

  vi.stubGlobal('crypto', {
    randomUUID: () =>
      '11111111-1111-4111-8111-111111111111',
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
// HELPER: OPEN TRANSFER FORM
// ============================================

async function openTransferForm() {
  const user = userEvent.setup()

  render(<App />)

  // Wait until balances have loaded
  await screen.findByText(/Live balance — Alice and Bob/i)

  await user.click(
    screen.getByRole('button', {
      name: /New Transfer/i,
    })
  )

  return user
}

// ============================================
// TRANSFER FORM TESTS
// ============================================

describe('FinGuard Transfer Form', () => {

  // TEST 1 — OPEN MODAL

  it('opens the New Transfer modal', async () => {
    await openTransferForm()

    expect(
      screen.getByRole('dialog', {
        name: /New Transfer/i,
      })
    ).toBeInTheDocument()
  })

  // TEST 2 — INVALID AMOUNT

  it('rejects zero-cent transfers', async () => {
    const user = await openTransferForm()

    await user.type(
      screen.getByLabelText(/Amount \(cents\)/i),
      '0'
    )

    await user.click(
      screen.getByRole('button', {
        name: /Review Transfer/i,
      })
    )

    expect(
      screen.getByRole('alert')
    ).toHaveTextContent(/positive whole number/i)

    expect(createTransfer).not.toHaveBeenCalled()
  })

  // TEST 3 — SAME ACCOUNT

  it('rejects transfers between the same account', async () => {
    const user = await openTransferForm()

    await user.selectOptions(
      screen.getByLabelText(/To Account/i),
      ALICE_ID
    )

    await user.type(
      screen.getByLabelText(/Amount \(cents\)/i),
      '100'
    )

    await user.click(
      screen.getByRole('button', {
        name: /Review Transfer/i,
      })
    )

    expect(
      screen.getByRole('alert')
    ).toHaveTextContent(/different accounts/i)

    expect(createTransfer).not.toHaveBeenCalled()
  })

  // TEST 4 — INSUFFICIENT FUNDS

  it('rejects transfers exceeding available balance', async () => {
    const user = await openTransferForm()

    await user.type(
      screen.getByLabelText(/Amount \(cents\)/i),
      '3000'
    )

    await user.click(
      screen.getByRole('button', {
        name: /Review Transfer/i,
      })
    )

    expect(
      screen.getByRole('alert')
    ).toHaveTextContent(/Insufficient funds/i)

    expect(createTransfer).not.toHaveBeenCalled()
  })

  // TEST 5 — REVIEW BEFORE SUBMISSION

  it('reviews a valid transfer before submitting', async () => {
    const user = await openTransferForm()

    await user.type(
      screen.getByLabelText(/Amount \(cents\)/i),
      '100'
    )

    await user.type(
      screen.getByLabelText(/Description/i),
      'Automated UI test'
    )

    await user.click(
      screen.getByRole('button', {
        name: /Review Transfer/i,
      })
    )

    expect(
      screen.getByRole('heading', {
        name: 'Review Transfer',
      })
    ).toBeInTheDocument()

    expect(
      screen.getByText('100 cents')
    ).toBeInTheDocument()

    // No transfer until confirmation
    expect(createTransfer).not.toHaveBeenCalled()
  })

  // TEST 6 — PREVENT DOUBLE SUBMISSION

  it('disables confirmation while a transfer is processing', async () => {
    // Simulate a request that has not completed yet
    vi.mocked(createTransfer).mockImplementation(
      () => new Promise(() => {})
    )

    const user = await openTransferForm()

    await user.type(
      screen.getByLabelText(/Amount \(cents\)/i),
      '100'
    )

    await user.click(
      screen.getByRole('button', {
        name: /Review Transfer/i,
      })
    )

    await user.click(
      screen.getByRole('button', {
        name: /Confirm Transfer/i,
      })
    )

    await waitFor(() => {
      expect(createTransfer).toHaveBeenCalledTimes(1)
    })

    expect(
      screen.getByRole('button', {
        name: /Processing Transfer/i,
      })
    ).toBeDisabled()

    // The same request must retain its key
    expect(createTransfer).toHaveBeenCalledWith(
      {
        source_account_id: ALICE_ID,
        destination_account_id: BOB_ID,
        amount_cents: 100,
        description: '',
      },
      '11111111-1111-4111-8111-111111111111'
    )
  })

})

