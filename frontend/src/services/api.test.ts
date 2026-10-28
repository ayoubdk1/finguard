import {
    describe,
    it,
    expect,
    vi,
} from 'vitest'

import { createTransfer } from './api'

// ============================================
// TEST DATA
// ============================================

const validTransfer = {
    source_account_id: 'alice-account-id',
    destination_account_id: 'bob-account-id',
    amount_cents: 100,
    description: 'Automated transfer test',
}

// ============================================
// TRANSFER API TESTS
// ============================================

describe('FinGuard Transfer API', () => {

    // ==========================================
    // TEST 1 — SUCCESSFUL TRANSFER REQUEST
    // ==========================================

    it('sends a valid transfer to FastAPI', async () => {

        const mockResponse = {
            transaction_id: 'transaction-123',
            status: 'POSTED',
            amount_cents: 100,
        }

        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => mockResponse,
        })

        vi.stubGlobal('fetch', fetchMock)

        const result = await createTransfer(
            validTransfer,
            'test-key-123'
        )

        expect(result.status).toBe('POSTED')

        expect(fetchMock).toHaveBeenCalledWith(
            '/api/transfers',
            {
                method: 'POST',

                headers: {
                    'Content-Type': 'application/json',
                    'Idempotency-Key': 'test-key-123',
                },

                body: JSON.stringify(validTransfer),
            }
        )
    })

    // ==========================================
    // TEST 2 — INVALID AMOUNT
    // ==========================================

    it('rejects a transfer with amount zero', async () => {

        const fetchMock = vi.fn()

        vi.stubGlobal('fetch', fetchMock)

        await expect(
            createTransfer(
                {
                    ...validTransfer,
                    amount_cents: 0,
                },
                'test-key-456'
            )
        ).rejects.toThrow(
            'Amount must be a positive integer in cents'
        )

        expect(fetchMock).not.toHaveBeenCalled()
    })

    // ==========================================
    // TEST 3 — SAME SOURCE AND DESTINATION
    // ==========================================

    it('rejects transfers to the same account', async () => {

        const fetchMock = vi.fn()

        vi.stubGlobal('fetch', fetchMock)

        await expect(
            createTransfer(
                {
                    ...validTransfer,
                    destination_account_id: 'alice-account-id',
                },
                'test-key-789'
            )
        ).rejects.toThrow(
            'Source and destination must be different'
        )

        expect(fetchMock).not.toHaveBeenCalled()
    })

    // ==========================================
    // TEST 4 — IDEMPOTENCY KEY REUSE
    // ==========================================

    it('preserves the same key when retrying a request', async () => {

        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,

            json: async () => ({
                transaction_id: 'transaction-123',
                status: 'POSTED',
            }),
        })

        vi.stubGlobal('fetch', fetchMock)

        const sameKey = 'stable-transfer-key'

        await createTransfer(validTransfer, sameKey)

        await createTransfer(validTransfer, sameKey)

        expect(fetchMock).toHaveBeenCalledTimes(2)

        for (const call of fetchMock.mock.calls) {

            const requestOptions = call[1]

            expect(
                requestOptions.headers['Idempotency-Key']
            ).toBe(sameKey)

            expect(
                requestOptions.body
            ).toBe(JSON.stringify(validTransfer))
        }
    })

})