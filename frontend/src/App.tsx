import { useEffect, useState } from 'react'

import {
  getAccountBalance,
  getAccountTransactions,
  type AccountBalance,
  type TransactionHistoryItem,
} from './services/api'

import './App.css'

// ============================================
// ACCOUNT IDS
// ============================================

const ALICE_ACCOUNT_ID = '007c9f83-03db-48fd-bdae-9024fea8f52a'
const BOB_ACCOUNT_ID = 'b72238cf-a238-4fac-81a1-6421f192f7c7'

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

              <div
                key={item.label}
                className={`menu-item ${index === 0 ? 'active' : ''}`}
              >

                <span className="menu-icon">
                  {item.icon}
                </span>

                <span>{item.label}</span>

                {index !== 0 && (
                  <small>Soon</small>
                )}

              </div>

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
              Workspace / Overview
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
              FINANCIAL OVERVIEW
            </p>

            <h1>Dashboard</h1>

            <p>
              Monitor financial activity, account balances,
              and transaction risk.
            </p>

          </div>

          <button className="primary-button" disabled>
            + New Transfer
          </button>

        </section>

        {/* ===================================== */}
        {/* STATISTICS */}
        {/* ===================================== */}

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

        {/* FOOTER */}

        <footer className="footer">
          © 2026 FinGuard — Simulated FinTech Platform
        </footer>

      </main>

    </div>
  )
}

export default App