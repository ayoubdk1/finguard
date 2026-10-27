// FinGuard API Service

const API_BASE_URL = '/api'

// Account balance returned by FastAPI
export interface AccountBalance {
    account_id: string
    currency: string
    balance_cents: number
}

// Reusable HTTP GET function
async function apiGet<T>(endpoint: string): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${endpoint}`)

    if (!response.ok) {
        throw new Error(
            `API request failed: ${response.status}`
        )
    }

    return response.json() as Promise<T>
}

// Check backend connection
export async function checkBackendHealth() {
    return apiGet<{ status: string }>('/health')
}

// Get the balance of a customer account
export async function getAccountBalance(
    accountId: string
): Promise<AccountBalance> {
    return apiGet<AccountBalance>(
        `/accounts/${encodeURIComponent(accountId)}/balance`
    )
}
// Transaction returned by FastAPI
export interface TransactionHistoryItem {
    transaction_id: string
    created_at: string
    description: string
    status: string
    amount_cents: number
    currency: string
}

// Account transaction history response
export interface TransactionHistoryResponse {
    account_id: string
    transactions: TransactionHistoryItem[]
}

// Retrieve transactions for one account
export async function getAccountTransactions(
    accountId: string
): Promise<TransactionHistoryResponse> {
    return apiGet<TransactionHistoryResponse>(
        `/accounts/${encodeURIComponent(accountId)}/transactions`
    )
}