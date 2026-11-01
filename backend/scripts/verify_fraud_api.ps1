# ============================================
# FINGUARD REAL FRAUD API VERIFICATION
# ============================================

$body = @{
    amount_cents = 150000
    transfers_last_10min = 4
    account_age_minutes = 60
    failed_transfers_last_hour = 3
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://localhost:5173/api/risk/assess" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body |
    ConvertTo-Json -Depth 10

