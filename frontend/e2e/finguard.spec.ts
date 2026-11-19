import { expect, test, type Page } from '@playwright/test'

async function mockApi(page: Page) {
  await page.route(/http:\/\/(127\.0\.0\.1|localhost):8000\/|\/api\//, async (route) => {
    const url = route.request().url()
    if (url.includes('/auth/login')) {
      return route.fulfill({ json: { access_token: 'tok', refresh_token: 'ref', token_type: 'bearer' } })
    }
    if (url.includes('/auth/me')) {
      return route.fulfill({ json: { id: 'u1', email: 'admin@finguard.com', full_name: 'FinGuard Admin', role: 'ADMIN', status: 'ACTIVE', mfa_enabled: false } })
    }
    if (url.includes('/balance')) {
      return route.fulfill({ json: { account_id: 'acc-1', balance_cents: 150000, currency: 'EUR' } })
    }
    if (url.includes('/transactions')) {
      return route.fulfill({ json: { account_id: 'acc-1', transactions: [] } })
    }
    if (url.includes('/transfers')) {
      return route.fulfill({ json: { transaction_id: 'tr-1', status: 'COMPLETED', source_account_id: 'acc-1', destination_account_id: 'acc-2', amount_cents: 10000, currency: 'EUR', source_balance_cents: 140000, destination_balance_cents: 60000 } })
    }
    if (url.includes('/fraud/assess') || url.includes('/risk')) {
      return route.fulfill({ json: { rule_assessment: { score: 18, decision: 'APPROVE', reason_codes: [] }, ml_assessment: { ml_prediction: 'LEGIT', fraud_probability: 0.18 }, review_recommended: false, automatic_block: false } })
    }
    return route.fulfill({ json: {} })
  })
}

test('login, transfer, and fraud workflow', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.fill('#auth-email', 'admin@finguard.com')
  await page.fill('#auth-password', 'AdminPass123!')
  await page.getByRole('button', { name: /se connecter/i }).click()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()

  await page.getByRole('button', { name: /new transfer/i }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByLabel(/amount/i).fill('100')
  await page.getByRole('button', { name: /review transfer/i }).click()
  await page.getByRole('button', { name: /confirm transfer/i }).click()
  await expect(page.getByText(/COMPLETED/i)).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeHidden()

  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Fraud Detection' }).click()
  await expect(page.getByRole('heading', { name: /fraud risk assessment/i })).toBeVisible()
  await page.locator('#risk-amount').fill('250')
  await page.locator('form button[type="submit"]').click()
  await expect(page.getByText(/APPROVE/i)).toBeVisible()
})
