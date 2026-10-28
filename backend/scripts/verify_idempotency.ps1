# ============================================
# FINGUARD BACKEND IDEMPOTENCY VERIFICATION
# ============================================

$baseUrl = "http://localhost:5173/api"

$alice = "007c9f83-03db-48fd-bdae-9024fea8f52a"
$bob = "b72238cf-a238-4fac-81a1-6421f192f7c7"

# Generate one unique key for this test
$key = [guid]::NewGuid().ToString()

# Create one transfer payload
$payload = @{
    source_account_id = $alice
    destination_account_id = $bob
    amount_cents = 1
    description = "Backend idempotency verification"
} | ConvertTo-Json -Compress

# Fetch balances BEFORE
$aliceBefore = Invoke-RestMethod `
    -Uri "$baseUrl/accounts/$alice/balance"

$bobBefore = Invoke-RestMethod `
    -Uri "$baseUrl/accounts/$bob/balance"

Write-Host "Balances BEFORE:"
Write-Host "Alice: $($aliceBefore.balance_cents)"
Write-Host "Bob:   $($bobBefore.balance_cents)"

# ============================================
# FIRST REQUEST
# ============================================

$first = Invoke-RestMethod `
    -Uri "$baseUrl/transfers" `
    -Method Post `
    -ContentType "application/json" `
    -Headers @{
        "Idempotency-Key" = $key
    } `
    -Body $payload

Write-Host "First transaction: $($first.transaction_id)"

# ============================================
# SECOND REQUEST — EXACT SAME KEY AND PAYLOAD
# ============================================

$second = Invoke-RestMethod `
    -Uri "$baseUrl/transfers" `
    -Method Post `
    -ContentType "application/json" `
    -Headers @{
        "Idempotency-Key" = $key
    } `
    -Body $payload

Write-Host "Second transaction: $($second.transaction_id)"

# ============================================
# FETCH BALANCES AFTER BOTH REQUESTS
# ============================================

$aliceAfter = Invoke-RestMethod `
    -Uri "$baseUrl/accounts/$alice/balance"

$bobAfter = Invoke-RestMethod `
    -Uri "$baseUrl/accounts/$bob/balance"

$aliceDebited = (
    $aliceBefore.balance_cents - $aliceAfter.balance_cents
)

$bobCredited = (
    $bobAfter.balance_cents - $bobBefore.balance_cents
)

Write-Host ""
Write-Host "Alice debited: $aliceDebited cents"
Write-Host "Bob credited:  $bobCredited cents"

# ============================================
# VERIFY IDEMPOTENCY
# ============================================

if (
    $first.transaction_id -ne $second.transaction_id
) {
    throw "FAILED: Duplicate transaction IDs differ!"
}

if (
    $aliceDebited -ne 1 -or
    $bobCredited -ne 1
) {
    throw "FAILED: Balances changed more than once!"
}

Write-Host ""
Write-Host "SUCCESS: Backend idempotency verified!"

