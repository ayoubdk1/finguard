import './App.css'

const transactions = [
  {
    id: 'TX-001',
    name: 'Transfer to Bob',
    date: '27 Oct 2026',
    amount: '-100 cents',
    status: 'POSTED',
  },
  {
    id: 'TX-002',
    name: 'Account funding',
    date: '26 Oct 2026',
    amount: '+5,000 cents',
    status: 'POSTED',
  },
  {
    id: 'TX-003',
    name: 'Transfer to Alice',
    date: '25 Oct 2026',
    amount: '+500 cents',
    status: 'POSTED',
  },
]

const menuItems = [
  { icon: '▦', label: 'Dashboard' },
  { icon: '▤', label: 'Accounts' },
  { icon: '⇄', label: 'Transfers' },
  { icon: '≡', label: 'Transactions' },
  { icon: '◇', label: 'Fraud Detection' },
  { icon: '◉', label: 'Event Monitoring' },
]

function App() {
  return (
    <div className="app-layout">

      {/* SIDEBAR */}
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
                <span className="menu-icon">{item.icon}</span>
                <span>{item.label}</span>
                {index !== 0 && <small>Soon</small>}
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

      {/* MAIN CONTENT */}
      <main className="main-content">

        {/* HEADER */}
        <header className="topbar">
          <div>
            <span className="breadcrumb">Workspace / Overview</span>
          </div>

          <div className="topbar-right">
            <span className="demo-badge">● DEMO MODE</span>
            <div className="avatar">FG</div>
          </div>
        </header>

        {/* PAGE TITLE */}
        <section className="page-heading">
          <div>
            <p className="eyebrow">FINANCIAL OVERVIEW</p>
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

        {/* STATISTICS */}
        <section className="stats-grid">

          <div className="stat-card">
            <div className="stat-top">
              <span>Total Balance</span>
              <span className="stat-icon">◎</span>
            </div>
            <h2>5,000 <small>cents</small></h2>
            <p>Across demo customer accounts</p>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span>Customer Accounts</span>
              <span className="stat-icon">▣</span>
            </div>
            <h2>2</h2>
            <p>Simulated accounts</p>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span>Recent Transactions</span>
              <span className="stat-icon">⇄</span>
            </div>
            <h2>3</h2>
            <p>Sample transaction records</p>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span>Fraud Monitoring</span>
              <span className="stat-icon">◇</span>
            </div>
            <h2 className="green-text">Enabled</h2>
            <p>Rules + ML prototype</p>
          </div>

        </section>

        {/* CONTENT GRID */}
        <section className="dashboard-grid">

          {/* TRANSACTION TABLE */}
          <div className="panel transactions-panel">

            <div className="panel-header">
              <div>
                <h3>Recent Transactions</h3>
                <p>Latest simulated financial activity</p>
              </div>
              <span className="panel-tag">DEMO DATA</span>
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
                  {transactions.map((tx) => (
                    <tr key={tx.id}>
                      <td>
                        <div className="transaction-name">
                          {tx.name}
                        </div>
                        <span className="transaction-id">
                          {tx.id}
                        </span>
                      </td>
                      <td>{tx.date}</td>
                      <td className="amount-cell">
                        {tx.amount}
                      </td>
                      <td>
                        <span className="status-badge">
                          {tx.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

          </div>

          {/* RIGHT COLUMN */}
          <div className="side-panels">

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
                  <strong>Fraud Detection Ready</strong>
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
                <span>Live API connection</span>
                <strong className="pending">Pending</strong>
              </div>
            </div>

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

        <footer className="footer">
          © 2026 FinGuard — Simulated FinTech Platform
        </footer>

      </main>
    </div>
  )
}

export default App