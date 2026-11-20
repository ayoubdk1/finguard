import * as apiClient from './services/api'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'

import { LoginForm } from './LoginForm'
import { UserManagement } from './UserManagement'
import SecuritySettings from './SecuritySettings'
import {
  getCurrentUser,
  logoutUser,
  type UserProfile,
  getAccountBalance,
  getAccountTransactions,
  createTransfer,
  assessRisk,
  getEventMonitoring,
  type AccountBalance,
  type TransactionHistoryItem,
  type TransferRequest,
  type TransferResponse,
  type RiskAssessmentResponse,
  type EventMonitoringResponse,
} from './services/api'

import './App.css'

// ============================================
// ACCOUNT IDS
// ============================================

const ALICE_ACCOUNT_ID = '007c9f83-03db-48fd-bdae-9024fea8f52a'
const BOB_ACCOUNT_ID = 'b72238cf-a238-4fac-81a1-6421f192f7c7'

const FALLBACK_DEMO_ACCOUNTS = [
  { id: ALICE_ACCOUNT_ID, name: 'Alice', currency: 'TND', type: 'CUSTOMER' },
  { id: BOB_ACCOUNT_ID, name: 'Bob', currency: 'TND', type: 'CUSTOMER' },
]

// ============================================
// CRISP VECTOR SVG ICONS (LUCIDE / HEROICONS)
// ============================================

const Icons: Record<string, ReactNode> = {
  Dashboard: (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.85"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect width="7" height="9" x="3" y="3" rx="1" />
      <rect width="7" height="5" x="14" y="3" rx="1" />
      <rect width="7" height="9" x="14" y="12" rx="1" />
      <rect width="7" height="5" x="3" y="16" rx="1" />
    </svg>
  ),
  Accounts: (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.85"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1" />
      <path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4" />
    </svg>
  ),
  Transfers: (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.85"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M8 3 4 7l4 4" />
      <path d="M4 7h16" />
      <path d="m16 21 4-4-4-4" />
      <path d="M20 17H4" />
    </svg>
  ),
  Transactions: (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.85"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9 5H2v7l6.29 6.29c.94.94 2.48.94 3.42 0l3.58-3.58c.94-.94.94-2.48 0-3.42L9 5Z" />
      <path d="M6 9.01V9" />
      <path d="m15 5 6.3 6.3a2.4 2.4 0 0 1 0 3.4L17 19" />
    </svg>
  ),
  'Fraud Detection': (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.85"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  ),
  'Event Monitoring': (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.85"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
  Users: (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.85"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  Security: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  ),
}

// ============================================
// SIDEBAR MENU
// ============================================

const menuItems = [
  { label: 'Dashboard' },
  { label: 'Accounts' },
  { label: 'Transfers' },
  { label: 'Transactions' },
  { label: 'Fraud Detection' },
  { label: 'Event Monitoring' },
  { label: 'Users' },
  { label: 'Security' },
]

type AccountMovement = TransactionHistoryItem & {
  accountId: string
  accountName: string
}

async function loadAccountMovements(
  accountsList: { id: string; name: string }[]
): Promise<AccountMovement[]> {
  if (accountsList.length === 0) return []
  const histories = await Promise.all(accountsList.map((a) => getAccountTransactions(a.id)))
  const movements: AccountMovement[] = histories.flatMap((hist, idx) =>
    hist.transactions.map((tx) => ({
      ...tx,
      accountId: accountsList[idx].id,
      accountName: accountsList[idx].name,
    }))
  )

  return movements.sort(
    (a, b) =>
      new Date(b.created_at).getTime() -
      new Date(a.created_at).getTime()
  )
}

// ============================================
// FORMAT EVENT TIMESTAMPS
// ============================================

function formatMonitoringDate(timestamp: string | null): string {
  if (!timestamp) {
    return '—'
  }

  const date = new Date(timestamp)

  if (Number.isNaN(date.getTime())) {
    return 'Invalid date'
  }

  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// ============================================
// SAFE TRANSFER RETRIES
// ============================================

interface PendingTransfer {
  key: string
  payload: TransferRequest
}

const PENDING_TRANSFER_STORAGE = 'finguard.pendingTransfer'

// Recover a transfer whose result is still uncertain
function readPendingTransfer(): PendingTransfer | null {
  try {
    const saved = window.sessionStorage.getItem(
      PENDING_TRANSFER_STORAGE
    )

    if (!saved) {
      return null
    }

    const data = JSON.parse(saved) as PendingTransfer

    if (
      typeof data.key !== 'string' ||
      !data.key ||
      !data.payload ||
      typeof data.payload.source_account_id !== 'string' ||
      typeof data.payload.destination_account_id !== 'string' ||
      typeof data.payload.description !== 'string' ||
      !Number.isSafeInteger(data.payload.amount_cents) ||
      data.payload.amount_cents <= 0
    ) {
      return null
    }

    return data
  } catch {
    return null
  }
}

function App() {
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    async function checkAuth() {
      if (
        typeof window !== 'undefined' &&
        window.localStorage?.getItem('finguard_access_token')
      ) {
        try {
          const user = await getCurrentUser()
          setCurrentUser(user)
        } catch {
          setCurrentUser(null)
        }
      }
      setAuthLoading(false)
    }
    checkAuth()
  }, [])

  const handleLogout = async () => {
    await logoutUser()
    setCurrentUser(null)
  }

  const [activePage, setActivePage] = useState<
    | 'Dashboard'
    | 'Accounts'
    | 'Transactions'
    | 'Fraud Detection'
    | 'Event Monitoring'
    | 'Users' | 'Security'
  >('Dashboard')

  // ============================================
  // DATA REFRESH
  // ============================================

  const [overviewRefreshKey, setOverviewRefreshKey] = useState(0)

  // ============================================
  // EVENT MONITORING STATES
  // ============================================

  const [eventMonitoring, setEventMonitoring] =
    useState<EventMonitoringResponse | null>(null)

  const [eventMonitoringLoading, setEventMonitoringLoading] =
    useState(true)

  const [eventMonitoringError, setEventMonitoringError] =
    useState('')

  const [eventRefreshVersion, setEventRefreshVersion] =
    useState(0)

  // ============================================
  // FRAUD DETECTION STATE
  // ============================================

  const [riskInputs, setRiskInputs] = useState({
    amount_cents: '150000',
    transfers_last_10min: '4',
    account_age_minutes: '60',
    failed_transfers_last_hour: '3',
  })

  const [riskLoading, setRiskLoading] = useState(false)
  const [riskError, setRiskError] = useState('')

  const [riskResult, setRiskResult] =
    useState<RiskAssessmentResponse | null>(null)

  // ============================================
  // ACCOUNT BALANCES STATE
  // ============================================

  const [balances, setBalances] = useState<AccountBalance[] | null>(null)
  const [balanceError, setBalanceError] = useState('')

  // ============================================
  // TRANSACTION HISTORY STATE
  // ============================================

  const [transactions, setTransactions] = useState<TransactionHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')

  // ============================================
  // TRANSFER MODAL STATE
  // ============================================

  const [showTransferModal, setShowTransferModal] = useState(false)
  const [isTransferReview, setIsTransferReview] = useState(false)
  const [transferFrom, setTransferFrom] = useState(ALICE_ACCOUNT_ID)
  const [transferTo, setTransferTo] = useState(BOB_ACCOUNT_ID)
  const [transferAmount, setTransferAmount] = useState('')
  const [transferDescription, setTransferDescription] = useState('')
  const [transferFormError, setTransferFormError] = useState('')

  const [transferSubmitting, setTransferSubmitting] = useState(false)

  const [transferResult, setTransferResult] =
    useState<TransferResponse | null>(null)

  // Saved request used for safe retries
  const [pendingTransfer, setPendingTransfer] =
    useState<PendingTransfer | null>(() => readPendingTransfer())

  const [transferRequestKey, setTransferRequestKey] =
    useState<string>(() => crypto.randomUUID())

  // ============================================
  // TRANSACTIONS PAGE STATE
  // ============================================

  const [allMovements, setAllMovements] = useState<AccountMovement[]>([])

  const [movementFilter, setMovementFilter] = useState<
    'all' | 'alice' | 'bob'
  >('all')

  const [movementsLoading, setMovementsLoading] = useState(true)
  const [movementsError, setMovementsError] = useState('')

  const [movementsRefreshKey, setMovementsRefreshKey] = useState(0)
  const [accounts, setAccounts] = useState(FALLBACK_DEMO_ACCOUNTS)

  useEffect(() => {
    let cancelled = false
    async function fetchAccounts() {
      try {
        const fn = apiClient.getAccounts
        if (typeof fn !== 'function') return
        const list = await fn()
        if (!cancelled && Array.isArray(list)) {
          const mapped = list.map((a) => ({ id: a.id, name: a.name, currency: a.currency, type: a.account_type }))
          setAccounts(mapped)
        }
      } catch {
        // Keep existing state on transient error
      }
    }
    void fetchAccounts()
    return () => { cancelled = true }
  }, [currentUser, overviewRefreshKey])

  // ============================================
  // LOAD REAL ACCOUNT BALANCES
  // ============================================

  useEffect(() => {
    let cancelled = false

    async function loadBalances() {
      setBalances(null)
      setBalanceError('')

      try {
        const results = await Promise.all(accounts.map((a) => getAccountBalance(a.id)))

        if (!cancelled) {
          setBalances(results)
          setBalanceError('')
        }
      } catch (error) {
        if (!cancelled) {
          setBalanceError(
            error instanceof Error
              ? error.message
              : 'Failed to load balances'
          )
        }
      }
    }

    void loadBalances()

    return () => {
      cancelled = true
    }
  }, [overviewRefreshKey, accounts])

  // ============================================
  // LOAD REAL TRANSACTION HISTORY
  // ============================================

  useEffect(() => {
    let cancelled = false

    async function loadTransactions() {
      setHistoryLoading(true)
      setHistoryError('')

      try {
        const response = await getAccountTransactions(
          accounts[0]?.id ?? ALICE_ACCOUNT_ID
        )

        if (!cancelled) {
          setTransactions(response.transactions)
          setHistoryError('')
        }
      } catch (error) {
        if (!cancelled) {
          setHistoryError(
            error instanceof Error
              ? error.message
              : 'Failed to load transactions'
          )
        }
      } finally {
        if (!cancelled) {
          setHistoryLoading(false)
        }
      }
    }

    void loadTransactions()

    return () => {
      cancelled = true
    }
  }, [overviewRefreshKey, accounts])

  // ============================================
  // CALCULATE TOTAL BALANCE
  // ============================================

  const totalBalanceCents = balances?.reduce(
    (total, account) => total + account.balance_cents,
    0
  )

  // ============================================
  // LOAD ACCOUNT TRANSACTIONS
  // ============================================

  useEffect(() => {
    let cancelled = false

    async function fetchMovements() {
      setMovementsLoading(true)

      try {
        const results = await loadAccountMovements(accounts)

        if (!cancelled) {
          setAllMovements(results)
          setMovementsError('')
        }
      } catch (error) {
        if (!cancelled) {
          setMovementsError(
            error instanceof Error
              ? error.message
              : 'Unable to load transactions'
          )
        }
      } finally {
        if (!cancelled) {
          setMovementsLoading(false)
        }
      }
    }

    void fetchMovements()

    return () => {
      cancelled = true
    }
  }, [movementsRefreshKey, accounts])

  const visibleMovements = allMovements.filter((tx) => {
    if (movementFilter === 'all') return true
    if (movementFilter === 'alice') return tx.accountId === (accounts[0]?.id ?? ALICE_ACCOUNT_ID)
    return tx.accountId === (accounts[1]?.id ?? BOB_ACCOUNT_ID)
  })

  // ============================================
  // TRANSFER MODAL HANDLERS
  // ============================================

  function getAccountName(accountId: string) {
    if (accountId === ALICE_ACCOUNT_ID) {
      return 'Alice — TND'
    }
    if (accountId === BOB_ACCOUNT_ID) {
      return 'Bob — TND'
    }
    return accountId
  }

  function openTransferModal() {
    // Check whether an earlier request is unresolved
    const saved = pendingTransfer ?? readPendingTransfer()

    setTransferFrom(
      saved?.payload.source_account_id ?? accounts[0]?.id ?? ALICE_ACCOUNT_ID
    )

    setTransferTo(
      saved?.payload.destination_account_id ?? accounts[1]?.id ?? accounts[0]?.id ?? BOB_ACCOUNT_ID
    )

    setTransferAmount(
      saved ? String(saved.payload.amount_cents) : ''
    )

    setTransferDescription(
      saved?.payload.description ?? ''
    )

    setTransferRequestKey(
      saved?.key ?? crypto.randomUUID()
    )

    setPendingTransfer(saved)

    setTransferFormError('')
    setTransferSubmitting(false)
    setTransferResult(null)

    // A saved attempt goes directly to the review screen
    setIsTransferReview(Boolean(saved))

    setShowTransferModal(true)
  }

  const transferModalRef = useRef<HTMLElement | null>(null)
  const lastFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!showTransferModal) return
    lastFocusRef.current = document.activeElement as HTMLElement | null
    transferModalRef.current?.focus()
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowTransferModal(false) }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      lastFocusRef.current?.focus()
    }
  }, [showTransferModal])

  function closeTransferModal() {
    if (transferSubmitting) return

    setShowTransferModal(false)
    setIsTransferReview(false)
    setTransferFormError('')
  }

  function handleReviewTransfer(event: FormEvent) {
    event.preventDefault()
    setTransferFormError('')

    if (transferFrom === transferTo) {
      setTransferFormError('Source and destination must be different accounts')
      return
    }

    const amount = Number(transferAmount)
    if (
      !/^[1-9]\d*$/.test(transferAmount) ||
      !Number.isSafeInteger(amount) ||
      amount <= 0
    ) {
      setTransferFormError('Please enter a positive whole number in cents')
      return
    }

    const sourceAccount = balances?.find(
      (acc) => acc.account_id === transferFrom
    )
    if (sourceAccount && amount > sourceAccount.balance_cents) {
      setTransferFormError('Insufficient funds in source account')
      return
    }

    setIsTransferReview(true)
  }

  // ============================================
  // CONFIRM AND EXECUTE TRANSFER
  // ============================================

  async function handleConfirmTransfer() {
    if (transferSubmitting || transferResult || !isTransferReview) {
      return
    }

    const amount = Number(transferAmount)

    // Validate amount again before submission
    if (
      !/^[1-9]\d*$/.test(transferAmount) ||
      !Number.isSafeInteger(amount)
    ) {
      setTransferFormError('Invalid transfer amount.')
      return
    }

    if (transferFrom === transferTo) {
      setTransferFormError('Choose different accounts.')
      return
    }

    setTransferSubmitting(true)
    setTransferFormError('')

    try {
      // ============================================
      // 1. REUSE OR CREATE THE TRANSFER ATTEMPT
      // ============================================

      let attempt = pendingTransfer

      if (!attempt) {
        attempt = {
          key: transferRequestKey,

          payload: {
            source_account_id: transferFrom,
            destination_account_id: transferTo,
            amount_cents: amount,
            description: transferDescription,
          },
        }

        // Save BEFORE sending to FastAPI
        window.sessionStorage.setItem(
          PENDING_TRANSFER_STORAGE,
          JSON.stringify(attempt)
        )

        setPendingTransfer(attempt)
      }

      // ============================================
      // 2. SUBMIT EXACTLY THE SAME REQUEST
      // ============================================

      const result = await createTransfer(
        attempt.payload,
        attempt.key
      )

      // 2. Save the successful response
      setTransferResult(result)

      // ============================================
      // 3. CLEAR SAVED REQUEST AFTER CONFIRMED SUCCESS
      // ============================================

      setPendingTransfer(null)

      try {
        window.sessionStorage.removeItem(
          PENDING_TRANSFER_STORAGE
        )
      } catch (error) {
        console.warn('Could not clear saved transfer:', error)
      }

      // Refresh the Transactions page after a successful transfer
      setMovementsRefreshKey((current) => current + 1)

      // 3. Immediately update displayed balances
      setBalances(
        (current) =>
          current?.map((account) => {
            if (account.account_id === result.source_account_id) {
              return {
                ...account,
                balance_cents: result.source_balance_cents,
              }
            }

            if (account.account_id === result.destination_account_id) {
              return {
                ...account,
                balance_cents: result.destination_balance_cents,
              }
            }

            return account
          }) ?? null
      )

      setBalanceError('')

      // 4. Refresh balances from PostgreSQL
      try {
        const updatedBalances = await Promise.all(accounts.map((a) => getAccountBalance(a.id)))

        setBalances(updatedBalances)
      } catch (error) {
        console.error('Balance refresh failed:', error)
        // Keep balances returned by the successful transfer
      }

      // 5. Refresh transaction history
      setHistoryLoading(true)

      try {
        const history = await getAccountTransactions(
          ALICE_ACCOUNT_ID
        )

        setTransactions(history.transactions)
        setHistoryError('')
      } catch (error) {
        console.error('Transaction history refresh failed:', error)

        setHistoryError(
          'Unable to refresh transaction history.'
        )
      } finally {
        setHistoryLoading(false)
      }
    } catch (error) {
      setTransferFormError(
        error instanceof Error
          ? error.message
          : 'Transfer request failed. Retry using the same key.'
      )
    } finally {
      setTransferSubmitting(false)
    }
  }

  // ============================================
  // FRAUD RISK ASSESSMENT
  // ============================================

  function updateRiskInput(
    field: keyof typeof riskInputs,
    value: string
  ) {
    setRiskInputs((current) => ({
      ...current,
      [field]: value,
    }))

    // Clear results when inputs change
    setRiskResult(null)
    setRiskError('')
  }

  async function handleAssessRisk(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault()

    if (riskLoading) return

    const rawValues = [
      riskInputs.amount_cents,
      riskInputs.transfers_last_10min,
      riskInputs.account_age_minutes,
      riskInputs.failed_transfers_last_hour,
    ]

    // Only non-negative whole numbers are accepted
    const valid = rawValues.every((value) => {
      return (
        /^(0|[1-9]\d*)$/.test(value) &&
        Number.isSafeInteger(Number(value))
      )
    })

    if (!valid) {
      setRiskError(
        'All fields must contain valid non-negative whole numbers.'
      )
      return
    }

    const [
      amount,
      transfers,
      accountAge,
      failedTransfers,
    ] = rawValues.map(Number)

    if (amount <= 0) {
      setRiskError('Transaction amount must be greater than zero.')
      return
    }

    setRiskLoading(true)
    setRiskError('')
    setRiskResult(null)

    try {
      const result = await assessRisk({
        amount_cents: amount,
        transfers_last_10min: transfers,
        account_age_minutes: accountAge,
        failed_transfers_last_hour: failedTransfers,
      })

      setRiskResult(result)
    } catch (error) {
      setRiskError(
        error instanceof Error
          ? error.message
          : 'Fraud assessment failed.'
      )
    } finally {
      setRiskLoading(false)
    }
  }

  // ============================================
  // LOAD EVENT MONITORING DATA
  // ============================================

  useEffect(() => {
    if (activePage !== 'Event Monitoring') {
      return
    }

    let cancelled = false

    async function loadEvents(showLoading: boolean) {
      if (showLoading) {
        setEventMonitoringLoading(true)
      }

      try {
        const data = await getEventMonitoring()

        if (!cancelled) {
          setEventMonitoring(data)
          setEventMonitoringError('')
        }
      } catch (error) {
        if (!cancelled) {
          setEventMonitoringError(
            error instanceof Error
              ? error.message
              : 'Failed to load event monitoring'
          )
        }
      } finally {
        if (!cancelled && showLoading) {
          setEventMonitoringLoading(false)
        }
      }
    }

    // Load immediately when opening the page
    void loadEvents(true)

    // Automatically refresh every 10 seconds
    const intervalId = window.setInterval(() => {
      void loadEvents(false)
    }, 10000)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [activePage, eventRefreshVersion])

  // ============================================
  // REFRESH ALL DASHBOARD DATA
  // ============================================

  function refreshDashboardData() {
    // Reload balances and dashboard transactions
    setOverviewRefreshKey((current) => current + 1)

    // Reload Alice and Bob's transaction movements
    setMovementsRefreshKey((current) => current + 1)

    // Reload event monitoring information
    setEventRefreshVersion((current) => current + 1)
  }

  // ============================================
  // DASHBOARD INTERFACE
  // ============================================

  if (authLoading && import.meta.env.MODE !== 'test') {
    return (
      <div className="auth-loading-screen">
        Vérification de la session...
      </div>
    )
  }

  if (!currentUser && import.meta.env.MODE !== 'test') {
    return (
      <LoginForm
        onSuccess={async () => {
          try {
            const u = await getCurrentUser()
            setCurrentUser(u)
          } catch {
            // ignore
          }
        }}
      />
    )
  }

  return (
    <div className="app-layout">
      {/* ===================================== */}
      {/* SIDEBAR */}
      {/* ===================================== */}

      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon" aria-hidden="true">
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.3"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>

          <div>
            <h2>FinGuard</h2>
            <p>Financial Intelligence</p>
          </div>
        </div>

        <div className="sidebar-section">
          <p className="section-label">WORKSPACE</p>

          <nav aria-label="Main navigation">
            {menuItems.filter((item) => !((item.label === 'Fraud Detection' || item.label === 'Event Monitoring') && currentUser?.role === 'CUSTOMER')).map((item) => {
              const available =
                item.label === 'Dashboard' ||
                item.label === 'Accounts' ||
                item.label === 'Transfers' ||
                item.label === 'Transactions' ||
                (item.label === 'Users' && currentUser?.role === 'ADMIN') ||
                item.label === 'Security' || (item.label === 'Fraud Detection' && currentUser?.role !== 'CUSTOMER') || (item.label === 'Event Monitoring' && currentUser?.role !== 'CUSTOMER') || (item.label === 'Fraud Detection' && currentUser?.role !== 'CUSTOMER') || (item.label === 'Event Monitoring' && currentUser?.role !== 'CUSTOMER')

              return (
                <button
                  key={item.label}
                  type="button"
                  className={`menu-item ${
                    activePage === item.label ? 'active' : ''
                  }`}
                  disabled={!available}
                  onClick={() => {
                    if (item.label === 'Transfers') {
                      openTransferModal()
                      return
                    }

                    if (
                      item.label === 'Dashboard' ||
                      item.label === 'Accounts' ||
                      item.label === 'Transactions' ||
                      item.label === 'Fraud Detection' ||
                      item.label === 'Event Monitoring' ||
                      item.label === 'Users' ||
                      item.label === 'Security'
                    ) {
                      setActivePage(item.label)
                    }
                  }}
                >
                  <span className="menu-icon">{Icons[item.label]}</span>
                  <span>{item.label}</span>

                  {!available && <small>Soon</small>}
                </button>
              )
            })}
          </nav>
        </div>

        <div className="sidebar-bottom">
          {currentUser ? (
            <div className="sidebar-user-card">
              <div className="sidebar-user-name">
                {currentUser.full_name}
              </div>
              <div className="sidebar-user-role">
                {currentUser.role}
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="sidebar-logout-btn"
              >
                Se déconnecter
              </button>
            </div>
          ) : (
            <div className="system-indicator">
              <span className="indicator-dot"></span>
              <span>Demo Mode</span>
            </div>
          )}

          <p>FinGuard v0.1</p>
        </div>
      </aside>

      {/* ===================================== */}
      {/* MAIN CONTENT */}
      {/* ===================================== */}

      <main className="main-content">
        {/* HEADER */}

        <header className="topbar">
          <div>
            <span className="breadcrumb">
              Workspace / {activePage}
            </span>
          </div>

          <div className="topbar-right">
            <button
              type="button"
              className="theme-toggle-btn"
              onClick={() =>
                setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))
              }
              aria-label="Toggle color theme"
            >
              {theme === 'dark' ? (
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                </svg>
              ) : (
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
                </svg>
              )}
              <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>
            </button>

            <span className="demo-badge">
              {currentUser ? currentUser.role : 'PRIVATE'}
            </span>

            <div className="avatar">FG</div>
          </div>
        </header>

        {/* ===================================== */}
        {/* PAGE TITLE */}
        {/* ===================================== */}

        <section className="page-heading">
          <div>
            <p className="eyebrow">
              {activePage === 'Dashboard'
                ? 'FINANCIAL OVERVIEW'
                : activePage === 'Accounts'
                  ? 'ACCOUNT MANAGEMENT'
                  : activePage === 'Transactions'
                    ? 'FINANCIAL ACTIVITY'
                    : activePage === 'Fraud Detection'
                      ? 'FRAUD INTELLIGENCE'
                      : activePage === 'Users'
                        ? 'ADMINISTRATION'
                        : activePage === 'Security'
                          ? 'ACCOUNT SECURITY'
                        : 'EVENT-DRIVEN ARCHITECTURE'}
            </p>

            <h1>{activePage}</h1>

            <p>
              {activePage === 'Dashboard'
                ? 'Monitor financial activity, account balances, and transaction risk.'
                : activePage === 'Accounts'
                  ? 'View customer accounts and their current balances.'
                  : activePage === 'Transactions'
                    ? 'Explore real transaction history across customer accounts.'
                    : activePage === 'Fraud Detection'
                      ? 'Analyze transaction risk using rules and machine learning.'
                      : activePage === 'Users'
                        ? 'Manage user accounts, statuses, login history, and active sessions.'
                        : activePage === 'Security'
                          ? 'Manage two-factor authentication, password, and active sessions.'
                        : 'Monitor transactional outbox events and consumer processing.'}
            </p>
          </div>

          <div className="page-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={refreshDashboardData}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                <path d="M3 3v5h5" />
                <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                <path d="M16 16h5v5" />
              </svg>
              Refresh Data
            </button>

            <button
              type="button"
              className="primary-button"
              onClick={openTransferModal}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
              New Transfer
            </button>
          </div>
        </section>

        {/* ===================================== */}
        {/* STATISTICS */}
        {/* ===================================== */}

        {activePage === 'Dashboard' && (
          <>
            <section className="stats-grid">
              {/* TOTAL BALANCE */}

              <div className="stat-card">
                <div className="stat-top">
                  <span>Total Balance</span>
                  <span className="stat-icon" aria-hidden="true">
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <line x1="12" x2="12" y1="2" y2="22" />
                      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                    </svg>
                  </span>
                </div>

                <h2>
                  {balances
                    ? totalBalanceCents?.toLocaleString('en-US')
                    : balanceError
                      ? 'Unavailable'
                      : 'Loading...'}{' '}
                  <small>cents</small>
                </h2>

                <p>
                  {balanceError
                    ? 'Could not load balances from FastAPI'
                    : balances
                      ? 'Live balance — Alice and Bob'
                      : 'Connecting to PostgreSQL...'}
                </p>
              </div>

              {/* CUSTOMER ACCOUNTS */}

              <div className="stat-card">
                <div className="stat-top">
                  <span>Customer Accounts</span>
                  <span className="stat-icon" aria-hidden="true">
                    {Icons.Accounts}
                  </span>
                </div>

                <h2>2</h2>

                <p>Selected customer accounts</p>
              </div>

              {/* RECENT TRANSACTIONS */}

              <div className="stat-card">
                <div className="stat-top">
                  <span>Recent Transactions</span>
                  <span className="stat-icon" aria-hidden="true">
                    {Icons.Transfers}
                  </span>
                </div>

                <h2>
                  {historyLoading
                    ? '...'
                    : historyError
                      ? '—'
                      : transactions.length}
                </h2>

                <p>
                  {historyError
                    ? 'Transaction history unavailable'
                    : "Alice's account activity"}
                </p>
              </div>

              {/* FRAUD MONITORING */}

              <div className="stat-card">
                <div className="stat-top">
                  <span>Fraud Monitoring</span>
                  <span className="stat-icon" aria-hidden="true">
                    {Icons['Fraud Detection']}
                  </span>
                </div>

                <h2 className="green-text">Enabled</h2>

                <p>Rules + ML prototype</p>
              </div>
            </section>

            {/* ===================================== */}
            {/* DASHBOARD GRID */}
            {/* ===================================== */}

            <section className="dashboard-grid">
              {/* ===================================== */}
              {/* REAL TRANSACTION HISTORY */}
              {/* ===================================== */}

              <div className="panel transactions-panel">
                <div className="panel-header">
                  <div>
                    <h3>Recent Transactions</h3>

                    <p>Live transaction history — Alice&apos;s account</p>
                  </div>

                  <span className="panel-tag">
                    {historyLoading
                      ? 'LOADING'
                      : historyError
                        ? 'API ERROR'
                        : 'LIVE DATA'}
                  </span>
                </div>

                <div className="table-wrapper">
                  <table>
                    <thead>
                      <tr>
                        <th>TRANSACTION</th>
                        <th>DATE</th>
                        <th>AMOUNT</th>
                        <th>STATUS</th>
                      </tr>
                    </thead>

                    <tbody>
                      {historyLoading ? (
                        <tr>
                          <td colSpan={4}>Loading transactions...</td>
                        </tr>
                      ) : historyError ? (
                        <tr>
                          <td colSpan={4}>
                            Unable to load transaction history.
                          </td>
                        </tr>
                      ) : transactions.length === 0 ? (
                        <tr>
                          <td colSpan={4}>No transactions found.</td>
                        </tr>
                      ) : (
                        transactions.slice(0, 5).map((tx) => (
                          <tr key={tx.transaction_id}>
                            <td>
                              <div className="transaction-name">
                                {tx.description || 'Financial transaction'}
                              </div>

                              <span className="transaction-id">
                                {tx.transaction_id.slice(0, 8)}
                              </span>
                            </td>

                            <td>
                              {new Date(tx.created_at).toLocaleDateString(
                                'en-GB',
                                {
                                  day: '2-digit',
                                  month: 'short',
                                  year: 'numeric',
                                }
                              )}
                            </td>

                            <td className="amount-cell">
                              {tx.amount_cents > 0 ? '+' : ''}
                              {tx.amount_cents.toLocaleString('en-US')}
                              {' cents'}
                            </td>

                            <td>
                              <span className="status-badge">
                                {tx.status}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* ===================================== */}
              {/* RIGHT PANELS */}
              {/* ===================================== */}

              <div className="side-panels">
                {/* FRAUD INTELLIGENCE */}

                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <h3>Fraud Intelligence</h3>
                      <p>Risk assessment engine</p>
                    </div>
                  </div>

                  <div className="fraud-card">
                    <div className="fraud-icon" aria-hidden="true">
                      {Icons['Fraud Detection']}
                    </div>

                    <div>
                      <strong>Fraud Detection Ready</strong>

                      <p>
                        Rule-based scoring and Gradient Boosting are
                        implemented.
                      </p>
                    </div>
                  </div>

                  <div className="fraud-detail">
                    <span>Rule-based engine</span>
                    <strong>Available</strong>
                  </div>

                  <div className="fraud-detail">
                    <span>Machine learning</span>
                    <strong>Available</strong>
                  </div>

                  <div className="fraud-detail">
                    <span>Live fraud API integration</span>
                    <strong className="pending">Pending</strong>
                  </div>
                </div>

                {/* SYSTEM ARCHITECTURE */}

                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <h3>System Architecture</h3>
                      <p>FinGuard infrastructure</p>
                    </div>
                  </div>

                  <div className="architecture-item">
                    <span className="architecture-dot"></span>
                    PostgreSQL Ledger
                  </div>

                  <div className="architecture-item">
                    <span className="architecture-dot"></span>
                    Transactional Outbox
                  </div>

                  <div className="architecture-item">
                    <span className="architecture-dot"></span>
                    Redpanda Streaming
                  </div>

                  <p className="architecture-note">
                    Components implemented in the backend. Live dashboard
                    monitoring is coming next.
                  </p>
                </div>
              </div>
            </section>
          </>
        )}

        {/* ============================================ */}
        {/* ACCOUNTS PAGE */}
        {/* ============================================ */}

        {activePage === 'Accounts' && (
          <section className="accounts-page">
            <div className="accounts-header">
              <div>
                <h2>Customer Accounts</h2>

                <p>Real account balances retrieved from PostgreSQL.</p>
              </div>

              <span className="panel-tag">LIVE DATA</span>
            </div>

            <div className="account-grid">
              {accounts.map((account) => {
                const accountBalance = balances?.find(
                  (item) => item.account_id === account.id
                )

                return (
                  <article className="account-card" key={account.id}>
                    <div className="account-card-top">
                      <div className="account-avatar">
                        {account.name.charAt(0)}
                      </div>

                      <span className="account-status">CUSTOMER</span>
                    </div>

                    <h3>{account.name}</h3>

                    <p className="account-id">{account.id}</p>

                    <div className="account-balance">
                      <span>Available Balance</span>

                      <h2>
                        {accountBalance
                          ? accountBalance.balance_cents.toLocaleString(
                              'en-US'
                            )
                          : balanceError
                            ? 'Unavailable'
                            : 'Loading...'}

                        {accountBalance && <small> cents</small>}
                      </h2>
                    </div>

                    <div className="account-footer">
                      <span>Currency</span>

                      <strong>{accountBalance?.currency ?? 'TND'}</strong>
                    </div>
                  </article>
                )
              })}
            </div>

            {balanceError && (
              <p className="transfer-error" role="alert">
                Could not retrieve account balances from FastAPI.
              </p>
            )}
          </section>
        )}

        {/* ============================================ */}
        {/* TRANSACTIONS PAGE */}
        {/* ============================================ */}

        {activePage === 'Transactions' && (
          <section className="transactions-page">
            <div className="transactions-page-header">
              <div>
                <h2>Transaction History</h2>
                <p>Financial movements retrieved from PostgreSQL.</p>
              </div>

              <span className="panel-tag">
                {movementsLoading
                  ? 'LOADING'
                  : movementsError
                    ? 'API ERROR'
                    : 'LIVE DATA'}
              </span>
            </div>

            {/* ACCOUNT FILTERS */}

            <div
              className="transaction-filters"
              role="group"
              aria-label="Filter transactions by account"
            >
              {(['all', 'alice', 'bob'] as const).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  className={`filter-button ${
                    movementFilter === filter ? 'selected' : ''
                  }`}
                  onClick={() => setMovementFilter(filter)}
                >
                  {filter === 'all'
                    ? 'All Accounts'
                    : filter === 'alice'
                      ? 'Alice'
                      : 'Bob'}
                </button>
              ))}
            </div>

            {/* TRANSACTION SUMMARY */}

            <div className="transaction-summary">
              <div>
                <span>Account movements</span>
                <h2>
                  {movementsLoading || movementsError
                    ? '—'
                    : visibleMovements.length}
                </h2>
              </div>

              <div>
                <span>Selected Account</span>
                <h2>
                  {movementFilter === 'all'
                    ? 'All'
                    : movementFilter === 'alice'
                      ? 'Alice'
                      : 'Bob'}
                </h2>
              </div>
            </div>

            {/* TRANSACTIONS TABLE */}

            <div className="panel">
              <div className="panel-header">
                <div>
                  <h3>Financial Activity</h3>
                  <p>Newest account movements first</p>
                </div>
              </div>

              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>ACCOUNT</th>
                      <th>TRANSACTION</th>
                      <th>DATE</th>
                      <th>AMOUNT</th>
                      <th>STATUS</th>
                    </tr>
                  </thead>

                  <tbody>
                    {movementsLoading ? (
                      <tr>
                        <td colSpan={5}>
                          Loading transaction history...
                        </td>
                      </tr>
                    ) : movementsError ? (
                      <tr>
                        <td colSpan={5}>
                          Unable to load transactions: {movementsError}
                        </td>
                      </tr>
                    ) : visibleMovements.length === 0 ? (
                      <tr>
                        <td colSpan={5}>No transactions found.</td>
                      </tr>
                    ) : (
                      visibleMovements.map((tx) => (
                        <tr
                          key={`${tx.accountId}-${tx.transaction_id}`}
                        >
                          <td>
                            <strong
                              style={{ color: 'var(--color-foreground)' }}
                            >
                              {tx.accountName}
                            </strong>
                          </td>

                          <td>
                            <div className="transaction-name">
                              {tx.description || 'Financial transaction'}
                            </div>

                            <span className="transaction-id">
                              {tx.transaction_id}
                            </span>
                          </td>

                          <td>
                            {new Date(tx.created_at).toLocaleString(
                              'en-GB',
                              {
                                day: '2-digit',
                                month: 'short',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              }
                            )}
                          </td>

                          <td
                            className={`amount-cell ${
                              tx.amount_cents >= 0
                                ? 'positive-amount'
                                : 'negative-amount'
                            }`}
                          >
                            {tx.amount_cents > 0 ? '+' : ''}
                            {tx.amount_cents.toLocaleString('en-US')}
                            {' cents'}
                          </td>

                          <td>
                            <span className="status-badge">
                              {tx.status}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <p className="transaction-note">
              Transfers between Alice and Bob appear as two account
              movements: one debit and one credit.
            </p>
          </section>
        )}

        {/* ============================================ */}
        {/* ADMINISTRATION / USERS PAGE */}
        {/* ============================================ */}

        {activePage === 'Users' && currentUser?.role === 'ADMIN' && (
          <UserManagement />
        )}

        {activePage === 'Security' && (
          <SecuritySettings currentUser={currentUser} onUserUpdated={async () => { setCurrentUser(await getCurrentUser()) }} />
        )}

        {/* ============================================ */}
        {/* FRAUD DETECTION PAGE */}
        {/* ============================================ */}

        {activePage === 'Fraud Detection' && currentUser?.role !== 'CUSTOMER' && (
          <section className="risk-page">
            <div className="risk-page-header">
              <div>
                <h2>Fraud Risk Assessment</h2>

                <p>
                  Analyze simulated transaction behavior using
                  FinGuard&apos;s risk detection engine.
                </p>
              </div>

              <span className="panel-tag">FASTAPI + ML</span>
            </div>

            <div className="risk-grid">
              {/* RISK ASSESSMENT FORM */}

              <div className="panel risk-form-panel">
                <div className="panel-header">
                  <div>
                    <h3>Transaction Analysis</h3>
                    <p>Enter transaction characteristics</p>
                  </div>
                </div>

                <form
                  className="risk-form"
                  onSubmit={(event) => void handleAssessRisk(event)}
                >
                  <label htmlFor="risk-amount">
                    Transaction Amount (cents)
                  </label>

                  <input
                    id="risk-amount"
                    type="text"
                    inputMode="numeric"
                    value={riskInputs.amount_cents}
                    onChange={(event) =>
                      updateRiskInput(
                        'amount_cents',
                        event.target.value
                      )
                    }
                    placeholder="Example: 150000"
                    required
                  />

                  <label htmlFor="risk-frequency">
                    Transfers in Last 10 Minutes
                  </label>

                  <input
                    id="risk-frequency"
                    type="text"
                    inputMode="numeric"
                    value={riskInputs.transfers_last_10min}
                    onChange={(event) =>
                      updateRiskInput(
                        'transfers_last_10min',
                        event.target.value
                      )
                    }
                    placeholder="Example: 4"
                    required
                  />

                  <label htmlFor="risk-age">
                    Account Age (minutes)
                  </label>

                  <input
                    id="risk-age"
                    type="text"
                    inputMode="numeric"
                    value={riskInputs.account_age_minutes}
                    onChange={(event) =>
                      updateRiskInput(
                        'account_age_minutes',
                        event.target.value
                      )
                    }
                    placeholder="Example: 60"
                    required
                  />

                  <label htmlFor="risk-failed">
                    Failed Transfers in Last Hour
                  </label>

                  <input
                    id="risk-failed"
                    type="text"
                    inputMode="numeric"
                    value={riskInputs.failed_transfers_last_hour}
                    onChange={(event) =>
                      updateRiskInput(
                        'failed_transfers_last_hour',
                        event.target.value
                      )
                    }
                    placeholder="Example: 3"
                    required
                  />

                  {riskError && (
                    <p className="transfer-error" role="alert">
                      {riskError}
                    </p>
                  )}

                  <button
                    type="submit"
                    className="primary-button risk-submit"
                    disabled={riskLoading}
                  >
                    {riskLoading
                      ? 'Analyzing Transaction...'
                      : 'Analyze Transaction'}
                  </button>
                </form>
              </div>

              {/* RISK ASSESSMENT RESULTS */}

              <div className="panel risk-results-panel">
                <div className="panel-header">
                  <div>
                    <h3>Risk Assessment Results</h3>
                    <p>Rule engine and machine learning</p>
                  </div>
                </div>

                {!riskResult ? (
                  <div className="risk-empty">
                    <div className="risk-empty-icon" aria-hidden="true">
                      <svg
                        width="26"
                        height="26"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
                        <path d="m9 12 2 2 4-4" />
                      </svg>
                    </div>

                    <h3>No assessment yet</h3>

                    <p>
                      Enter transaction characteristics and click
                      Analyze Transaction to see the results.
                    </p>
                  </div>
                ) : (
                  <div
                    className="risk-results"
                    aria-live="polite"
                  >
                    <div className="risk-score-card">
                      <span>Rule-Based Risk Score</span>

                      <h2>{riskResult.rule_assessment.score}</h2>

                      <p>
                        Decision: {riskResult.rule_assessment.decision}
                      </p>
                    </div>

                    <div className="risk-result-row">
                      <span>ML Prediction</span>

                      <strong>
                        {riskResult.ml_assessment.ml_prediction}
                      </strong>
                    </div>

                    <div className="risk-result-row">
                      <span>Fraud Probability</span>

                      <strong>
                        {(
                          riskResult.ml_assessment.fraud_probability * 100
                        ).toFixed(1)}
                        %
                      </strong>
                    </div>

                    <div className="risk-result-row">
                      <span>Manual Review</span>

                      <span
                        className={`risk-pill ${
                          riskResult.review_recommended
                            ? 'risk-warn'
                            : 'risk-ok'
                        }`}
                      >
                        {riskResult.review_recommended
                          ? 'Recommended'
                          : 'Not Recommended'}
                      </span>
                    </div>

                    <div className="risk-result-row">
                      <span>Automatic Block</span>

                      <strong>
                        {riskResult.automatic_block ? 'Yes' : 'No'}
                      </strong>
                    </div>

                    <div className="risk-reasons">
                      <h4>Risk Indicators</h4>

                      {riskResult.rule_assessment.reason_codes.length ===
                      0 ? (
                        <p>No rule-based risk indicators triggered.</p>
                      ) : (
                        <ul>
                          {riskResult.rule_assessment.reason_codes.map(
                            (reason, index) => (
                              <li key={`${reason}-${index}`}>
                                {reason.replaceAll('_', ' ')}
                              </li>
                            )
                          )}
                        </ul>
                      )}
                    </div>

                    <div className="risk-info">
                      This is an advisory risk assessment. It does not
                      execute, reject or block a transfer.
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>
        )}

        {/* ============================================ */}
        {/* EVENT MONITORING PAGE */}
        {/* ============================================ */}

        {activePage === 'Event Monitoring' && currentUser?.role !== 'CUSTOMER' && (
          <section className="events-page">
            {/* HEADER */}

            <div className="events-page-header">
              <div>
                <h2>Event Stream Monitoring</h2>

                <p>
                  Track PostgreSQL outbox publication and consumer
                  processing.
                </p>
              </div>

              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setEventRefreshVersion((current) => current + 1)
                }}
              >
                ↻ Refresh
              </button>
            </div>

            {/* LOADING AND ERROR MESSAGES */}

            {eventMonitoringLoading && (
              <p className="events-message">
                Loading event monitoring data...
              </p>
            )}

            {eventMonitoringError && (
              <p className="transfer-error" role="alert">
                Monitoring API error: {eventMonitoringError}
                {eventMonitoring
                  ? ' Displaying the last successfully retrieved data.'
                  : ''}
              </p>
            )}

            {/* EVENT STATISTICS */}

            {eventMonitoring && (
              <>
                <div className="events-stats-grid">
                  <div className="events-stat-card">
                    <span>Total Events</span>

                    <h2>{eventMonitoring.total_events}</h2>

                    <p>Created in PostgreSQL outbox</p>
                  </div>

                  <div className="events-stat-card">
                    <span>Pending Events</span>

                    <h2 className="events-pending-number">
                      {eventMonitoring.pending_events}
                    </h2>

                    <p>Awaiting successful publication</p>
                  </div>

                  <div className="events-stat-card">
                    <span>Published Events</span>

                    <h2 className="events-published-number">
                      {eventMonitoring.published_events}
                    </h2>

                    <p>Publication recorded</p>
                  </div>

                  <div className="events-stat-card">
                    <span>Processed Events</span>

                    <h2 className="events-processed-number">
                      {eventMonitoring.processed_events}
                    </h2>

                    <p>Recorded by the consumer</p>
                  </div>
                </div>

                {/* EVENT PIPELINE */}

                <div className="panel events-pipeline-panel">
                  <div className="panel-header">
                    <div>
                      <h3>Event Processing Pipeline</h3>
                      <p>FinGuard event-driven architecture</p>
                    </div>
                  </div>

                  <div className="events-pipeline">
                    <div className="pipeline-node">
                      <strong>PostgreSQL</strong>
                      <span>Transactional Outbox</span>
                    </div>

                    <span className="pipeline-arrow" aria-hidden="true">
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M5 12h14" />
                        <path d="m12 5 7 7-7 7" />
                      </svg>
                    </span>

                    <div className="pipeline-node">
                      <strong>Redpanda</strong>
                      <span>Event Streaming</span>
                    </div>

                    <span className="pipeline-arrow" aria-hidden="true">
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M5 12h14" />
                        <path d="m12 5 7 7-7 7" />
                      </svg>
                    </span>

                    <div className="pipeline-node">
                      <strong>Consumer</strong>
                      <span>Idempotent Processing</span>
                    </div>
                  </div>

                  <p className="events-pipeline-note">
                    Architecture overview. The counters above come from
                    PostgreSQL, not from live broker health checks.
                  </p>
                </div>

                {/* EVENT HISTORY */}

                <div className="panel events-history-panel">
                  <div className="panel-header">
                    <div>
                      <h3>Recent Events</h3>
                      <p>Latest outbox events from PostgreSQL</p>
                    </div>

                    <span className="panel-tag">
                      {eventMonitoringError
                        ? 'STALE DATA'
                        : 'LIVE DATA'}
                    </span>
                  </div>

                  <div className="table-wrapper">
                    <table className="events-table">
                      <thead>
                        <tr>
                          <th>EVENT ID</th>
                          <th>TRANSACTION ID</th>
                          <th>EVENT TYPE</th>
                          <th>CREATED AT</th>
                          <th>PUBLISHED AT</th>
                          <th>PROCESSED AT</th>
                          <th>STATUS</th>
                          <th>ATTEMPTS</th>
                        </tr>
                      </thead>

                      <tbody>
                        {eventMonitoring.recent_events.length === 0 ? (
                          <tr>
                            <td colSpan={8}>No events found.</td>
                          </tr>
                        ) : (
                          eventMonitoring.recent_events.map((event) => (
                            <tr key={event.event_id}>
                              <td>
                                <span
                                  className="transaction-id"
                                  title={event.event_id}
                                >
                                  {event.event_id.slice(0, 8)}...
                                </span>
                              </td>

                              <td>
                                <span
                                  className="transaction-id"
                                  title={event.aggregate_id}
                                >
                                  {event.aggregate_id.slice(0, 8)}...
                                </span>
                              </td>

                              <td>
                                <strong
                                  style={{
                                    color: 'var(--color-foreground)',
                                  }}
                                >
                                  {event.event_type}
                                </strong>
                              </td>

                              <td>
                                {formatMonitoringDate(event.created_at)}
                              </td>

                              <td>
                                {formatMonitoringDate(
                                  event.published_at
                                )}
                              </td>

                              <td>
                                {formatMonitoringDate(
                                  event.processed_at
                                )}
                              </td>

                              <td>
                                <span
                                  className={`events-status events-status-${event.status.toLowerCase()}`}
                                >
                                  {event.status}
                                </span>
                              </td>

                              <td>{event.publish_attempts}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  <p className="events-table-note">
                    Row statuses represent outbox publication. Consumer
                    processing is reported separately in the Processed
                    Events counter.
                  </p>
                </div>

                {/* AUTOMATIC REFRESH */}

                <p className="events-refresh-note">
                  <span className="indicator-dot" aria-hidden="true" />
                  Automatically refreshes every 10 seconds while this
                  page is open.
                </p>
              </>
            )}
          </section>
        )}

        {/* FOOTER */}

        <footer className="footer">
          © 2026 FinGuard — Simulated FinTech Platform
        </footer>
      </main>

      {/* ============================================ */}
      {/* NEW TRANSFER MODAL */}
      {/* ============================================ */}

      {showTransferModal && (
        <div className="transfer-overlay" onClick={closeTransferModal}>
          <section
            ref={transferModalRef}
            tabIndex={-1}
            className="transfer-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="transfer-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="transfer-modal-header">
              <div>
                <p className="eyebrow">FINGUARD PAYMENTS</p>
                <h2 id="transfer-title">
                  {isTransferReview ? 'Review Transfer' : 'New Transfer'}
                </h2>
                <p>Secure simulated financial transaction</p>
              </div>

              <button
                type="button"
                className="close-modal"
                onClick={closeTransferModal}
                aria-label="Close transfer form"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </div>

            {transferResult ? (
              <div className="transfer-success" role="status">
                <div className="success-icon" aria-hidden="true">
                  <svg
                    width="28"
                    height="28"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                </div>

                <h3>Transfer Successful!</h3>

                <p>
                  Your simulated transfer has been posted successfully.
                </p>

                <div className="review-row">
                  <span>Transaction ID</span>
                  <strong>{transferResult.transaction_id}</strong>
                </div>

                <div className="review-row">
                  <span>Amount</span>
                  <strong>
                    {transferResult.amount_cents.toLocaleString(
                      'en-US'
                    )}{' '}
                    cents
                  </strong>
                </div>

                <div className="review-row">
                  <span>Status</span>
                  <strong>{transferResult.status}</strong>
                </div>

                <div className="transfer-actions">
                  <button
                    type="button"
                    className="primary-button"
                    onClick={closeTransferModal}
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : !isTransferReview ? (
              <form
                className="transfer-form"
                onSubmit={handleReviewTransfer}
              >
                {/* SOURCE ACCOUNT */}

                <label htmlFor="transfer-from">From Account</label>

                <select
                  id="transfer-from"
                  value={transferFrom}
                  onChange={(event) =>
                    setTransferFrom(event.target.value)
                  }
                >
                  <option value={ALICE_ACCOUNT_ID}>Alice — TND</option>

                  <option value={BOB_ACCOUNT_ID}>Bob — TND</option>
                </select>

                {/* DESTINATION ACCOUNT */}

                <label htmlFor="transfer-to">To Account</label>

                <select
                  id="transfer-to"
                  value={transferTo}
                  onChange={(event) =>
                    setTransferTo(event.target.value)
                  }
                >
                  <option value={ALICE_ACCOUNT_ID}>Alice — TND</option>

                  <option value={BOB_ACCOUNT_ID}>Bob — TND</option>
                </select>

                {/* AMOUNT */}

                <label htmlFor="transfer-amount">Amount (cents)</label>

                <input
                  id="transfer-amount"
                  type="text"
                  inputMode="numeric"
                  placeholder="Example: 100"
                  value={transferAmount}
                  onChange={(event) =>
                    setTransferAmount(event.target.value)
                  }
                  required
                />

                {/* DESCRIPTION */}

                <label htmlFor="transfer-description">
                  Description
                </label>

                <textarea
                  id="transfer-description"
                  placeholder="Example: Payment to Bob"
                  value={transferDescription}
                  onChange={(event) =>
                    setTransferDescription(event.target.value)
                  }
                  rows={3}
                  maxLength={200}
                />

                {/* ERROR MESSAGE */}

                {transferFormError && (
                  <p className="transfer-error" role="alert">
                    {transferFormError}
                  </p>
                )}

                {/* ACTION BUTTONS */}

                <div className="transfer-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={closeTransferModal}
                  >
                    Cancel
                  </button>

                  <button type="submit" className="primary-button">
                    Review Transfer
                  </button>
                </div>
              </form>
            ) : (
              /* ==================================== */
              /* TRANSFER CONFIRMATION PREVIEW */
              /* ==================================== */

              <div className="transfer-review">
                <div className="review-row">
                  <span>From</span>
                  <strong>{getAccountName(transferFrom)}</strong>
                </div>

                <div className="review-row">
                  <span>To</span>
                  <strong>{getAccountName(transferTo)}</strong>
                </div>

                <div className="review-row">
                  <span>Amount</span>
                  <strong>
                    {Number(transferAmount).toLocaleString('en-US')}{' '}
                    cents
                  </strong>
                </div>

                <div className="review-row">
                  <span>Currency</span>
                  <strong>TND</strong>
                </div>

                <div className="review-row">
                  <span>Description</span>
                  <strong>
                    {transferDescription || 'No description'}
                  </strong>
                </div>

                <div className="transfer-info">
                  {pendingTransfer ? (
                    <>
                      This transfer may already have been processed.
                      Retry using the same request and idempotency key.
                      Do not create a new transfer until its outcome is
                      confirmed.
                    </>
                  ) : (
                    <>
                      This is a simulated transfer. No transaction has
                      been submitted yet.
                    </>
                  )}
                </div>

                {transferFormError && (
                  <p className="transfer-error" role="alert">
                    {transferFormError}
                  </p>
                )}

                <div className="transfer-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={
                      transferSubmitting || pendingTransfer !== null
                    }
                    onClick={() => setIsTransferReview(false)}
                  >
                    Edit
                  </button>

                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void handleConfirmTransfer()}
                    disabled={transferSubmitting}
                  >
                    {transferSubmitting
                      ? 'Processing Transfer...'
                      : pendingTransfer
                        ? 'Retry Same Transfer'
                        : 'Confirm Transfer'}
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

export default App
