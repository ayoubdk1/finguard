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
  assessRisk,
  getAccountBalance,
  getAccountTransactions,
} from './services/api'

// ============================================
// MOCK FASTAPI FUNCTIONS
// ============================================

vi.mock('./services/api', () => ({
  getAccountBalance: vi.fn(),
  getAccountTransactions: vi.fn(),
  createTransfer: vi.fn(),
  assessRisk: vi.fn(),
  getEventMonitoring: vi.fn(),
}))

// ============================================
// TEST ACCOUNT IDS
// ============================================

const ALICE_ID =
  '007c9f83-03db-48fd-bdae-9024fea8f52a'

// ============================================
// MOCK FRAUD ASSESSMENT RESULT
// ============================================

const mockRiskResult = {
  rule_assessment: {
    score: 100,
    decision: 'SIMULATED_HOLD',
    reason_codes: [
      'HIGH_AMOUNT',
      'HIGH_VELOCITY',
      'NEW_ACCOUNT',
      'FAILED_TRANSFERS',
    ],
  },

  ml_assessment: {
    ml_prediction: 'FRAUD',
    fraud_probability: 0.875,
    model: 'GradientBoosting',
  },

  review_recommended: true,
  automatic_block: false,
}

// ============================================
// TEST SETUP
// ============================================

beforeEach(() => {
  vi.resetAllMocks()

  sessionStorage.clear()

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
// HELPER: OPEN FRAUD DETECTION PAGE
// ============================================

async function openFraudPage() {
  const user = userEvent.setup()

  render(<App />)

  await user.click(
    screen.getByRole('button', {
      name: /Fraud Detection/i,
    })
  )

  return user
}

// ============================================
// FRAUD DETECTION TESTS
// ============================================

describe('FinGuard Fraud Detection', () => {

  // ==========================================
  // TEST 1 — PAGE NAVIGATION
  // ==========================================

  it('opens the Fraud Detection page', async () => {
    await openFraudPage()

    expect(
      screen.getByRole('heading', {
        name: 'Fraud Detection',
      })
    ).toBeInTheDocument()

    expect(
      screen.getByRole('button', {
        name: /Analyze Transaction/i,
      })
    ).toBeInTheDocument()
  })

  // ==========================================
  // TEST 2 — SUCCESSFUL FRAUD ASSESSMENT
  // ==========================================

  it('displays rule-based and ML assessment results', async () => {
    vi.mocked(assessRisk).mockResolvedValue(
      mockRiskResult
    )

    const user = await openFraudPage()

    await user.click(
      screen.getByRole('button', {
        name: /Analyze Transaction/i,
      })
    )

    await waitFor(() => {
      expect(assessRisk).toHaveBeenCalledTimes(1)
    })

    // Verify request payload
    expect(assessRisk).toHaveBeenCalledWith({
      amount_cents: 150000,
      transfers_last_10min: 4,
      account_age_minutes: 60,
      failed_transfers_last_hour: 3,
    })

    // Verify risk score
    expect(
      await screen.findByText('100')
    ).toBeInTheDocument()

    // Verify decision
    expect(
      screen.getByText(/SIMULATED_HOLD/i)
    ).toBeInTheDocument()

    // Verify ML prediction
    expect(
      screen.getByText('FRAUD')
    ).toBeInTheDocument()

    // Verify probability
    expect(
      screen.getByText('87.5%')
    ).toBeInTheDocument()

    // Verify recommendation
    expect(
      screen.getByText('Recommended')
    ).toBeInTheDocument()
  })

  // ==========================================
  // TEST 3 — INVALID INPUT VALIDATION
  // ==========================================

  it('rejects negative transaction amounts', async () => {
    const user = await openFraudPage()

    const amountInput = screen.getByLabelText(
      /Transaction Amount/i
    )

    await user.clear(amountInput)
    await user.type(amountInput, '-100')

    await user.click(
      screen.getByRole('button', {
        name: /Analyze Transaction/i,
      })
    )

    expect(
      screen.getByRole('alert')
    ).toHaveTextContent(
      /non-negative whole numbers/i
    )

    // Invalid data must never reach FastAPI
    expect(assessRisk).not.toHaveBeenCalled()
  })

  // ==========================================
  // TEST 4 — FASTAPI ERROR HANDLING
  // ==========================================

  it('displays an error when the API fails', async () => {
    vi.mocked(assessRisk).mockRejectedValue(
      new Error('Fraud service unavailable')
    )

    const user = await openFraudPage()

    await user.click(
      screen.getByRole('button', {
        name: /Analyze Transaction/i,
      })
    )

    expect(
      await screen.findByRole('alert')
    ).toHaveTextContent(
      'Fraud service unavailable'
    )

    expect(assessRisk).toHaveBeenCalledTimes(1)
  })

  // ==========================================
  // TEST 5 — PREVENT DUPLICATE SUBMISSIONS
  // ==========================================

  it('disables analysis while a request is processing', async () => {
    vi.mocked(assessRisk).mockImplementation(
      () => new Promise(() => {})
    )

    const user = await openFraudPage()

    await user.click(
      screen.getByRole('button', {
        name: /Analyze Transaction/i,
      })
    )

    await waitFor(() => {
      expect(assessRisk).toHaveBeenCalledTimes(1)
    })

    expect(
      screen.getByRole('button', {
        name: /Analyzing Transaction/i,
      })
    ).toBeDisabled()
  })

})
