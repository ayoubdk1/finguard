// FinGuard API Service

const API_BASE_URL = '/api'

const ACCESS_TOKEN_KEY = 'finguard_access_token'
const REFRESH_TOKEN_KEY = 'finguard_refresh_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setTokens(accessToken: string, refreshToken?: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  }
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

function getAuthHeaders(): Record<string, string> {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    clearTokens()
    return null
  }

  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })

    if (!response.ok) {
      clearTokens()
      return null
    }

    const data = await response.json()
    setTokens(data.access_token, data.refresh_token)
    return data.access_token
  } catch {
    clearTokens()
    return null
  }
}

async function fetchWithAuth(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = {
    ...getAuthHeaders(),
    ...(options.headers || {}),
  }

  let response = await fetch(url, { ...options, headers })

  if (response.status === 401 && getRefreshToken()) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      const retryHeaders = {
        ...(options.headers || {}),
        Authorization: `Bearer ${newToken}`,
      }
      response = await fetch(url, { ...options, headers: retryHeaders })
    }
  }

  return response
}


// Account balance returned by FastAPI
export interface AccountBalance {
  account_id: string
  currency: string
  balance_cents: number
}
export interface CustomerAccount {
  id: string
  user_id: string | null
  name: string
  account_type: string
  currency: string
  created_at: string
}
// Reusable HTTP GET function with Auth & Refresh
async function apiGet<T>(endpoint: string): Promise<T> {
  const response = await fetchWithAuth(`${API_BASE_URL}${endpoint}`)

  if (!response.ok) {
    let message = `API request failed: ${response.status}`
    try {
      const errorData = await response.json()
      if (errorData && typeof errorData.detail === 'string') {
        message = errorData.detail
      }
    } catch {
      // ignore
    }
    throw new Error(message)
  }

  return response.json() as Promise<T>
}

// Check backend connection
export async function checkBackendHealth() {
  return apiGet<{ status: string }>('/health')
}
// Retrieve customer accounts available to the authenticated user
export async function getAccounts(): Promise<CustomerAccount[]> {
  return apiGet<CustomerAccount[]>('/accounts')
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
// ============================================
// FRAUD RISK ASSESSMENT
// ============================================

export interface RiskAssessmentRequest {
  amount_cents: number
  transfers_last_10min: number
  account_age_minutes: number
  failed_transfers_last_hour: number
}

export interface RiskAssessmentResponse {
  rule_assessment: {
    score: number
    decision: string
    reason_codes: string[]
  }

  ml_assessment: {
    ml_prediction: string
    fraud_probability: number
    model?: string
  }

  review_recommended: boolean
  automatic_block: boolean
}

export async function assessRisk(
  payload: RiskAssessmentRequest
): Promise<RiskAssessmentResponse> {

  const response = await fetch('/api/risk/assess', {
    method: 'POST',

    headers: {
      'Content-Type': 'application/json',
    },

    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const errorData: unknown = await response
      .json()
      .catch(() => null)

    let message = `Risk assessment failed (HTTP ${response.status})`

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

  return response.json() as Promise<RiskAssessmentResponse>
}

// ============================================
// MONITORING EVENT
// ============================================

export interface MonitoringEvent {
  event_id: string
  event_type: string
  aggregate_id: string

  created_at: string
  published_at: string | null
  processed_at: string | null

  publish_attempts: number

  status: 'PENDING' | 'PUBLISHED' | 'PROCESSED'
}

export interface EventMonitoringResponse {
  total_events: number
  pending_events: number
  published_events: number
  processed_events: number
  recent_events: MonitoringEvent[]
}

export async function getEventMonitoring(): Promise<EventMonitoringResponse> {
  return apiGet<EventMonitoringResponse>('/monitoring/events')
}

// ============================================
// AUTHENTICATION API
// ============================================

export interface UserProfile {
  id: string
  email: string
  full_name: string
  role: string
  created_at: string
}

export interface AuthTokenResponse {
  access_token: string
  refresh_token?: string
  token_type: string
}

export async function loginUser(
  email: string,
  password: string
): Promise<AuthTokenResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!response.ok) {
    let message = 'Login failed'
    try {
      const errorData = await response.json()
      if (errorData && typeof errorData.detail === 'string') {
        message = errorData.detail
      }
    } catch {
      // ignore
    }
    throw new Error(message)
  }

  const data = (await response.json()) as AuthTokenResponse
  setTokens(data.access_token, data.refresh_token)
  return data
}

export async function registerUser(
  email: string,
  fullName: string,
  password: string
): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, full_name: fullName, password }),
  })

  if (!response.ok) {
    let message = 'Registration failed'
    try {
      const errorData = await response.json()
      if (errorData && typeof errorData.detail === 'string') {
        message = errorData.detail
      }
    } catch {
      // ignore
    }
    throw new Error(message)
  }

  return response.json() as Promise<UserProfile>
}

export async function getCurrentUser(): Promise<UserProfile> {
  return apiGet<UserProfile>('/auth/me')
}

export async function logoutUser(): Promise<void> {
  const refreshToken = getRefreshToken()
  if (refreshToken) {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
    } catch {
      // ignore
    }
  }
  clearTokens()
}


export interface ForgotPasswordResponse {
  message: string
  reset_token?: string | null
}

export async function requestPasswordReset(email: string): Promise<ForgotPasswordResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })

  if (!response.ok) {
    let message = 'Password reset request failed'
    try {
      const errorData = await response.json()
      if (errorData && typeof errorData.detail === 'string') {
        message = errorData.detail
      }
    } catch {
      // ignore
    }
    throw new Error(message)
  }

  return response.json() as Promise<ForgotPasswordResponse>
}

export async function confirmPasswordReset(
  resetToken: string,
  newPassword: string
): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reset_token: resetToken, new_password: newPassword }),
  })

  if (!response.ok) {
    let message = 'Password reset failed'
    try {
      const errorData = await response.json()
      if (errorData && typeof errorData.detail === 'string') {
        message = errorData.detail
      }
    } catch {
      // ignore
    }
    throw new Error(message)
  }

  return response.json() as Promise<{ status: string }>
}
