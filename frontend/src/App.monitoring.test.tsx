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
  within,
  waitFor,
} from '@testing-library/react'

import userEvent from '@testing-library/user-event'

import App from './App'

import {
  getAccountBalance,
  getAccountTransactions,
  getEventMonitoring,
  type EventMonitoringResponse,
} from './services/api'

// ============================================
// TEST ACCOUNT IDS
// ============================================

const ALICE_ID =
  '007c9f83-03db-48fd-bdae-9024fea8f52a'

const EVENT_ID_1 =
  '11111111-1111-4111-8111-111111111111'

const EVENT_ID_2 =
  '22222222-2222-4222-8222-222222222222'

const EVENT_ID_3 =
  '33333333-3333-4333-8333-333333333333'

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

// ============================================
// MOCK EVENT MONITORING RESPONSE
// ============================================

const mockMonitoringData: EventMonitoringResponse = {

  total_events: 3,
  pending_events: 1,
  published_events: 2,
  processed_events: 1,

  recent_events: [

    {
      event_id: EVENT_ID_1,

      aggregate_id:
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',

      event_type: 'TransferPosted',

      created_at: '2026-10-28T10:00:00+00:00',
      published_at: '2026-10-28T10:01:00+00:00',
      processed_at: '2026-10-28T10:02:00+00:00',

      publish_attempts: 1,
      status: 'PROCESSED',
    },

    {
      event_id: EVENT_ID_2,

      aggregate_id:
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',

      event_type: 'TransferPosted',

      created_at: '2026-10-28T11:00:00+00:00',
      published_at: '2026-10-28T11:01:00+00:00',
      processed_at: null,

      publish_attempts: 2,
      status: 'PUBLISHED',
    },

    {
      event_id: EVENT_ID_3,

      aggregate_id:
        'cccccccc-cccc-4ccc-8ccc-cccccccccccc',

      event_type: 'TransferPosted',

      created_at: '2026-10-28T12:00:00+00:00',
      published_at: null,
      processed_at: null,

      publish_attempts: 0,
      status: 'PENDING',
    },

  ],
}

// ============================================
// EMPTY EVENT RESPONSE
// ============================================

const emptyMonitoringData: EventMonitoringResponse = {
  total_events: 0,
  pending_events: 0,
  published_events: 0,
  processed_events: 0,
  recent_events: [],
}

// ============================================
// BEFORE EACH TEST
// ============================================

beforeEach(() => {

  vi.resetAllMocks()

  sessionStorage.clear()

  vi.stubGlobal('crypto', {
    randomUUID: () =>
      '44444444-4444-4444-8444-444444444444',
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

  vi.mocked(getEventMonitoring).mockResolvedValue(
    mockMonitoringData
  )

})

// ============================================
// HELPER: OPEN EVENT MONITORING
// ============================================

async function openMonitoringPage() {

  const user = userEvent.setup()

  render(<App />)

  await user.click(
    screen.getByRole('button', {
      name: /Event Monitoring/i,
    })
  )

  return user
}

// ============================================
// EVENT MONITORING TESTS
// ============================================

describe('FinGuard Event Monitoring', () => {

  // ==========================================
  // TEST 1 — NAVIGATION
  // ==========================================

  it('opens the Event Monitoring page', async () => {

    await openMonitoringPage()

    expect(
      screen.getByRole('heading', {
        name: 'Event Stream Monitoring',
      })
    ).toBeInTheDocument()

    await waitFor(() => {
      expect(getEventMonitoring).toHaveBeenCalled()
    })

  })

  // ==========================================
  // TEST 2 — EVENT STATISTICS
  // ==========================================

  it('displays the correct event statistics', async () => {

    await openMonitoringPage()

    await screen.findByText('PROCESSED')

    const expectedCounts = [
      ['Total Events', '3'],
      ['Pending Events', '1'],
      ['Published Events', '2'],
      ['Processed Events', '1'],
    ]

    for (const [label, count] of expectedCounts) {

      const card = screen
        .getByText(label)
        .closest('.events-stat-card')

      expect(card).not.toBeNull()

      expect(
        within(card as HTMLElement).getByRole(
          'heading',
          { name: count }
        )
      ).toBeInTheDocument()

    }

  })

  // ==========================================
  // TEST 3 — EVENT LIFECYCLE STATUSES
  // ==========================================

  it('displays pending, published and processed statuses', async () => {

    await openMonitoringPage()

    const processed = await screen.findByText(
      'PROCESSED'
    )

    expect(processed).toHaveClass(
      'events-status-processed'
    )

    expect(
      screen.getByText('PUBLISHED')
    ).toHaveClass(
      'events-status-published'
    )

    expect(
      screen.getByText('PENDING')
    ).toHaveClass(
      'events-status-pending'
    )

    // Verify real event identifiers are represented
    expect(
      screen.getByTitle(EVENT_ID_1)
    ).toBeInTheDocument()

    expect(
      screen.getByTitle(EVENT_ID_2)
    ).toBeInTheDocument()

    expect(
      screen.getByTitle(EVENT_ID_3)
    ).toBeInTheDocument()

  })

  // ==========================================
  // TEST 4 — EMPTY HISTORY
  // ==========================================

  it('handles an empty event history', async () => {

    vi.mocked(getEventMonitoring).mockResolvedValue(
      emptyMonitoringData
    )

    await openMonitoringPage()

    expect(
      await screen.findByText('No events found.')
    ).toBeInTheDocument()

    expect(
      getEventMonitoring
    ).toHaveBeenCalled()

  })

  // ==========================================
  // TEST 5 — API ERROR HANDLING
  // ==========================================

  it('displays an error when monitoring API fails', async () => {

    vi.mocked(getEventMonitoring).mockRejectedValue(
      new Error('Monitoring service unavailable')
    )

    await openMonitoringPage()

    expect(
      await screen.findByRole('alert')
    ).toHaveTextContent(
      'Monitoring service unavailable'
    )

    expect(
      getEventMonitoring
    ).toHaveBeenCalled()

  })

  // ==========================================
  // TEST 6 — MANUAL REFRESH
  // ==========================================

  it('refreshes monitoring data when requested', async () => {

    vi.mocked(getEventMonitoring)
      .mockResolvedValueOnce(emptyMonitoringData)
      .mockResolvedValueOnce(mockMonitoringData)

    const user = await openMonitoringPage()

    // First response contains no events
    expect(
      await screen.findByText('No events found.')
    ).toBeInTheDocument()

    // Refresh from the Event Monitoring page
    await user.click(
      screen.getByRole('button', {
        name: '↻ Refresh',
      })
    )

    // The second response contains event data
    expect(
      await screen.findByText('PROCESSED')
    ).toBeInTheDocument()

    await waitFor(() => {
      expect(
        getEventMonitoring
      ).toHaveBeenCalledTimes(2)
    })

  })

})

