import { useEffect, useState, type FormEvent } from 'react'

import {
  getAccountBalance,
  getAccountTransactions,
  createTransfer,
  type AccountBalance,
  type TransactionHistoryItem,
  type TransferResponse,
} from './services/api'

import './App.css'

// ============================================
// ACCOUNT IDS
// ============================================

const ALICE_ACCOUNT_ID = '007c9f83-03db-48fd-bdae-9024fea8f52a'
const BOB_ACCOUNT_ID = 'b72238cf-a238-4fac-81a1-6421f192f7c7'

const customerAccounts = [
  {
    id: ALICE_ACCOUNT_ID,
    name: 'Alice',
    type: 'CUSTOMER',
  },
  {
    id: BOB_ACCOUNT_ID,
    name: 'Bob',
    type: 'CUSTOMER',
  },
]

// ============================================
// SIDEBAR MENU
// ============================================

const menuItems = [
  { icon: '▦', label: 'Dashboard' },
  { icon: '▤', label: 'Accounts' },
  { icon: '⇄', label: 'Transfers' },
  { icon: '≡', label: 'Transactions' },
  { icon: '◇', label: 'Fraud Detection' },
  { icon: '◉', label: 'Event Monitoring' },
]

function App() {
  const [activePage, setActivePage] = useState<'Dashboard' | 'Accounts'>(
    'Dashboard'
  )

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

  const [transferRequestKey, setTransferRequestKey] =
    useState(() => crypto.randomUUID())

  // ============================================
  // LOAD REAL ACCOUNT BALANCES
  // ============================================

  useEffect(() => {
    let cancelled = false

    async function loadBalances() {
      try {
        const results = await Promise.all([
          getAccountBalance(ALICE_ACCOUNT_ID),
          getAccountBalance(BOB_ACCOUNT_ID),
        ])

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
  }, [])

  // ============================================
  // LOAD REAL TRANSACTION HISTORY
  // ============================================

  useEffect(() => {
    let cancelled = false

    async function loadTransactions() {
      try {

        const response = await getAccountTransactions(
          ALICE_ACCOUNT_ID
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
  }, [])

  // ============================================
  // CALCULATE TOTAL BALANCE
  // ============================================

  const totalBalanceCents = balances?.reduce(
    (total, account) => total + account.balance_cents,
    0
  )

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
    setTransferFrom(ALICE_ACCOUNT_ID)
    setTransferTo(BOB_ACCOUNT_ID)

    setTransferAmount('')
    setTransferDescription('')

    setTransferFormError('')
    setIsTransferReview(false)

    setTransferSubmitting(false)
    setTransferResult(null)

    // Unique key for each NEW transfer
    setTransferRequestKey(crypto.randomUUID())

    setShowTransferModal(true)
  }

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
      setTransferFormError('Source and destination accounts must be different')
      return
    }

    const amount = Number(transferAmount)
    if (!Number.isSafeInteger(amount) || amount <= 0) {
      setTransferFormError('Please enter a valid positive amount in cents')
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
      // 1. Execute the simulated transfer
      const result = await createTransfer(
        {
          source_account_id: transferFrom,
          destination_account_id: transferTo,
          amount_cents: amount,
          description: transferDescription,
        },
        transferRequestKey
      )

      // 2. Save the successful response
      setTransferResult(result)

      // 3. Immediately update displayed balances
      setBalances((current) =>
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
        const updatedBalances = await Promise.all([
          getAccountBalance(ALICE_ACCOUNT_ID),
          getAccountBalance(BOB_ACCOUNT_ID),
        ])

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
  // DASHBOARD INTERFACE
  // ============================================

  return (
    <div className="app-layout">

      {/* ===================================== */}
      {/* SIDEBAR */}
      {/* ===================================== */}

      <aside className="sidebar">

        <div className="brand">
          <div className="brand-icon">F</div>

          <div>
            <h2>FinGuard</h2>
            <p>Financial Intelligence</p>
          </div>
        </div>

        <div className="sidebar-section">

          <p className="section-label">WORKSPACE</p>

          <nav aria-label="Main navigation">

            {menuItems.map((item, index) => (
              <button
                key={item.label}
                type="button"
                className={`menu-item ${
                  activePage === item.label ? 'active' : ''
                }`}
                disabled={index > 1}
                onClick={() => {
                  setActivePage(index === 0 ? 'Dashboard' : 'Accounts')
                }}
              >
                <span className="menu-icon">
                  {item.icon}
                </span>

                <span>{item.label}</span>

                {index > 1 && <small>Soon</small>}
              </button>
            ))}

          </nav>

        </div>

        <div className="sidebar-bottom">

          <div className="system-indicator">
            <span className="indicator-dot"></span>
            <span>Demo Environment</span>
          </div>

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

            <span className="demo-badge">
              ● DEMO MODE
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
                : 'ACCOUNT MANAGEMENT'}
            </p>

            <h1>{activePage}</h1>

            <p>
              {activePage === 'Dashboard'
                ? 'Monitor financial activity, account balances, and transaction risk.'
                : 'View customer accounts and their current balances.'}
            </p>
          </div>

          <button
            className="primary-button"
            type="button"
            onClick={openTransferModal}
          >
            + New Transfer
          </button>

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
              <span className="stat-icon">◎</span>
            </div>

            <h2>
              {balances
                ? totalBalanceCents?.toLocaleString('en-US')
                : balanceError
                  ? 'Unavailable'
                  : 'Loading...'
              }

              {' '}

              <small>cents</small>
            </h2>

            <p>
              {balanceError
                ? 'Could not load balances from FastAPI'
                : balances
                  ? 'Live balance — Alice and Bob'
                  : 'Connecting to PostgreSQL...'
              }
            </p>

          </div>

          {/* CUSTOMER ACCOUNTS */}

          <div className="stat-card">

            <div className="stat-top">
              <span>Customer Accounts</span>
              <span className="stat-icon">▣</span>
            </div>

            <h2>2</h2>

            <p>Selected customer accounts</p>

          </div>

          {/* RECENT TRANSACTIONS */}

          <div className="stat-card">

            <div className="stat-top">
              <span>Recent Transactions</span>
              <span className="stat-icon">⇄</span>
            </div>

            <h2>
              {historyLoading
                ? '...'
                : historyError
                  ? '—'
                  : transactions.length
              }
            </h2>

            <p>
              {historyError
                ? 'Transaction history unavailable'
                : "Alice's account activity"
              }
            </p>

          </div>

          {/* FRAUD MONITORING */}

          <div className="stat-card">

            <div className="stat-top">
              <span>Fraud Monitoring</span>
              <span className="stat-icon">◇</span>
            </div>

            <h2 className="green-text">
              Enabled
            </h2>

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

                <p>
                  Live transaction history — Alice's account
                </p>
              </div>

              <span className="panel-tag">
                {historyLoading
                  ? 'LOADING'
                  : historyError
                    ? 'API ERROR'
                    : 'LIVE DATA'
                }
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
                      <td colSpan={4}>
                        Loading transactions...
                      </td>
                    </tr>

                  ) : historyError ? (

                    <tr>
                      <td colSpan={4}>
                        Unable to load transaction history.
                      </td>
                    </tr>

                  ) : transactions.length === 0 ? (

                    <tr>
                      <td colSpan={4}>
                        No transactions found.
                      </td>
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

                <div className="fraud-icon">◇</div>

                <div>

                  <strong>
                    Fraud Detection Ready
                  </strong>

                  <p>
                    Rule-based scoring and Gradient
                    Boosting are implemented.
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
                <strong className="pending">
                  Pending
                </strong>
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
                Components implemented in the backend.
                Live dashboard monitoring is coming next.
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

                <p>
                  Real account balances retrieved from PostgreSQL.
                </p>
              </div>

              <span className="panel-tag">
                LIVE DATA
              </span>
            </div>

            <div className="account-grid">

              {customerAccounts.map((account) => {

                const accountBalance = balances?.find(
                  (item) => item.account_id === account.id
                )

                return (

                  <article className="account-card" key={account.id}>

                    <div className="account-card-top">

                      <div className="account-avatar">
                        {account.name.charAt(0)}
                      </div>

                      <span className="account-status">
                        CUSTOMER
                      </span>

                    </div>

                    <h3>{account.name}</h3>

                    <p className="account-id">
                      {account.id}
                    </p>

                    <div className="account-balance">

                      <span>Available Balance</span>

                      <h2>
                        {accountBalance
                          ? accountBalance.balance_cents.toLocaleString('en-US')
                          : balanceError
                            ? 'Unavailable'
                            : 'Loading...'
                        }

                        {accountBalance && (
                          <small> cents</small>
                        )}
                      </h2>

                    </div>

                    <div className="account-footer">

                      <span>Currency</span>

                      <strong>
                        {accountBalance?.currency ?? 'TND'}
                      </strong>

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
                ×
              </button>

            </div>

            {transferResult ? (

              <div className="transfer-success" role="status">

                <div className="success-icon">✓</div>

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
                    {transferResult.amount_cents.toLocaleString('en-US')} cents
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

                <label htmlFor="transfer-from">
                  From Account
                </label>

                <select
                  id="transfer-from"
                  value={transferFrom}
                  onChange={(event) => setTransferFrom(event.target.value)}
                >
                  <option value={ALICE_ACCOUNT_ID}>
                    Alice — TND
                  </option>

                  <option value={BOB_ACCOUNT_ID}>
                    Bob — TND
                  </option>
                </select>

                {/* DESTINATION ACCOUNT */}

                <label htmlFor="transfer-to">
                  To Account
                </label>

                <select
                  id="transfer-to"
                  value={transferTo}
                  onChange={(event) => setTransferTo(event.target.value)}
                >
                  <option value={ALICE_ACCOUNT_ID}>
                    Alice — TND
                  </option>

                  <option value={BOB_ACCOUNT_ID}>
                    Bob — TND
                  </option>
                </select>

                {/* AMOUNT */}

                <label htmlFor="transfer-amount">
                  Amount (cents)
                </label>

                <input
                  id="transfer-amount"
                  type="text"
                  inputMode="numeric"
                  placeholder="Example: 100"
                  value={transferAmount}
                  onChange={(event) => setTransferAmount(event.target.value)}
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

                  <button
                    type="submit"
                    className="primary-button"
                  >
                    Review Transfer →
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
                    {Number(transferAmount).toLocaleString('en-US')} cents
                  </strong>
                </div>

                <div className="review-row">
                  <span>Currency</span>
                  <strong>TND</strong>
                </div>

                <div className="review-row">
                  <span>Description</span>
                  <strong>{transferDescription || 'No description'}</strong>
                </div>

                <div className="transfer-info">
                  This is a simulated transfer.
                  No transaction has been submitted yet.
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
                    onClick={() => setIsTransferReview(false)}
                    disabled={transferSubmitting}
                  >
                    ← Edit
                  </button>

                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void handleConfirmTransfer()}
                    disabled={transferSubmitting}
                  >
                    {transferSubmitting
                      ? 'Processing Transfer...'
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