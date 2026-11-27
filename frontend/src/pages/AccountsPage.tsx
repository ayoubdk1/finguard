import type { AccountBalance } from '../services/api'

export interface AccountSummary {
  id: string
  name: string
  currency: string
  type: string
}

interface AccountsPageProps {
  accounts: AccountSummary[]
  balances: AccountBalance[] | null
  balanceError: boolean | string | null
}

export function AccountsPage({ accounts, balances, balanceError }: AccountsPageProps) {
  return (
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
          const accountBalance = balances?.find((item) => item.account_id === account.id)
          return (
            <article className="account-card" key={account.id}>
              <div className="account-card-top">
                <div className="account-avatar">{account.name.charAt(0)}</div>
                <span className="account-status">CUSTOMER</span>
              </div>

              <h3>{account.name}</h3>
              <p className="account-id">{account.id}</p>

              <div className="account-balance">
                <span>Available Balance</span>
                <h2>
                  {accountBalance
                    ? accountBalance.balance_cents.toLocaleString('en-US')
                    : balanceError
                      ? 'Unavailable'
                      : 'Loading...'}
                  {accountBalance && <small> cents</small>}
                </h2>
              </div>

              <div className="account-footer">
                <span>Currency</span>
                <strong>{accountBalance?.currency ?? account.currency ?? 'TND'}</strong>
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
  )
}
