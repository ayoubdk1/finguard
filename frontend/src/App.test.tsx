import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import App from './App'

import {
    getAccountBalance,
    getAccountTransactions,
} from './services/api'

// Mock FastAPI functions
vi.mock('./services/api', () => ({
    getAccountBalance: vi.fn(),
    getAccountTransactions: vi.fn(),
    createTransfer: vi.fn(),
    assessRisk: vi.fn(),
    getEventMonitoring: vi.fn(),
}))

const ALICE_ID = '007c9f83-03db-48fd-bdae-9024fea8f52a'

describe('FinGuard Dashboard', () => {

    beforeEach(() => {
        vi.clearAllMocks()

        // Provide a predictable UUID for the transfer form
        vi.stubGlobal('crypto', {
            randomUUID: () => 'test-transfer-key',
        })

        // Simulate real balances
        vi.mocked(getAccountBalance).mockImplementation(async (accountId) => ({
            account_id: accountId,
            currency: 'TND',
            balance_cents: accountId === ALICE_ID ? 2900 : 2100,
        }))

        // Simulate transaction history
        vi.mocked(getAccountTransactions).mockImplementation(async (accountId) => ({
            account_id: accountId,
            transactions: [],
        }))
    })

    it('displays the total balance from FastAPI', async () => {
        render(<App />)

        expect(
            await screen.findByText(/5,000/)
        ).toBeInTheDocument()

        expect(
            getAccountBalance
        ).toHaveBeenCalledTimes(2)
    })

    it('navigates to the Accounts page', async () => {
        const user = userEvent.setup()

        render(<App />)

        await user.click(
            screen.getByRole('button', { name: /Accounts/ })
        )

        expect(
            screen.getByRole('heading', { name: 'Accounts' })
        ).toBeInTheDocument()
    })

})