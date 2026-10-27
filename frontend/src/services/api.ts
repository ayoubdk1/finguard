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
// ============================================
// SIMULATED TRANSFER
// ============================================

export interface TransferRequest {
    source_account_id: string
    destination_account_id: string
    amount_cents: number
    description: string
}

export interface TransferResponse {
    transaction_id: string
    status: string
    source_account_id: string
    destination_account_id: string
    amount_cents: number
    currency: string
    source_balance_cents: number
    destination_balance_cents: number
}
export async function createTransfer(
    transfer: TransferRequest,
    idempotencyKey: string
): Promise<TransferResponse> {

    // Validate transfer amount
    if (
        !Number.isSafeInteger(transfer.amount_cents) ||
        transfer.amount_cents <= 0
    ) {
        throw new Error('Amount must be a positive integer in cents')
    }

    if (
        transfer.source_account_id ===
        transfer.destination_account_id
    ) {
        throw new Error('Source and destination must be different')
    }

    if (!idempotencyKey.trim()) {
        throw new Error('An idempotency key is required')
    }

    // Send the transfer to FastAPI
    const response = await fetch('/api/transfers', {
        method: 'POST',

        headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': idempotencyKey,
        },

        body: JSON.stringify(transfer),
    })

    // Handle API errors
    if (!response.ok) {
        const errorData: unknown = await response
            .json()
            .catch(() => null)

        let message = `Transfer failed (HTTP ${response.status})`

        if (
            errorData !== null &&
            typeof errorData === 'object' &&
            'detail' in errorData &&
            typeof errorData.detail === 'string'
        ) {
            message = errorData.detail
        }

        throw new Error(message)
    }

    return response.json() as Promise<TransferResponse>
}