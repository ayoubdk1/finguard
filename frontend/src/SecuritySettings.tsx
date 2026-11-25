import { type FormEvent, useEffect, useState } from 'react'
import QRCode from 'qrcode'
import {
  type ActiveSessionItem,
  changePassword,
  disableMfa,
  enableMfa,
  getMySessions,
  regenerateBackupCodes,
  revokeMySession,
  setupMfa,
} from './services/api'

interface SecurityUser {
  email?: string
  role?: string
  mfa_enabled?: boolean
}

interface SecuritySettingsProps {
  currentUser: SecurityUser | null
  onUserUpdated: () => Promise<void> | void
}

export default function SecuritySettings({ currentUser, onUserUpdated }: SecuritySettingsProps) {
  const [setupPwd, setSetupPwd] = useState('')
  const [qrDataUrl, setQrDataUrl] = useState('')
  const [mfaSecret, setMfaSecret] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [backupCodes, setBackupCodes] = useState<string[]>([])
  const [disablePwd, setDisablePwd] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [mfaMsg, setMfaMsg] = useState('')
  const [mfaErr, setMfaErr] = useState('')

  const [curPwd, setCurPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [pwdMsg, setPwdMsg] = useState('')
  const [pwdErr, setPwdErr] = useState('')

  const [sessions, setSessions] = useState<ActiveSessionItem[]>([])
  const [sessErr, setSessErr] = useState('')

  async function loadSessions() {
    setSessErr('')
    try {
      const data = await getMySessions()
      setSessions(data.sessions)
    } catch (e) {
      setSessErr(e instanceof Error ? e.message : 'Failed to load sessions')
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        const data = await getMySessions()
        setSessions(data.sessions)
      } catch (e) {
        setSessErr(e instanceof Error ? e.message : 'Failed to load sessions')
      }
    })()
  }, [])

  async function handleStartMfa(e: FormEvent) {
    e.preventDefault(); setMfaErr(''); setMfaMsg('')
    try {
      const data = await setupMfa(setupPwd)
      setSetupPwd('')
      setMfaSecret(data.secret)
      setQrDataUrl(await QRCode.toDataURL(data.otpauth_uri))
    } catch (err) { setMfaErr(err instanceof Error ? err.message : 'MFA setup failed') }
  }

  async function handleEnableMfa(e: FormEvent) {
    e.preventDefault(); setMfaErr(''); setMfaMsg('')
    try {
      const res = await enableMfa(totpCode.trim())
      setBackupCodes(res.backup_codes); setQrDataUrl(''); setMfaSecret(''); setTotpCode('')
      setMfaMsg('MFA enabled. Save your backup codes below.')
      await onUserUpdated()
    } catch (e) { setMfaErr(e instanceof Error ? e.message : 'Invalid code') }
  }

  async function handleDisableMfa(e: FormEvent) {
    e.preventDefault(); setMfaErr(''); setMfaMsg('')
    try {
      await disableMfa(disablePwd, disableCode.trim())
      setDisablePwd(''); setDisableCode(''); setBackupCodes([])
      setMfaMsg('MFA disabled.'); await onUserUpdated()
    } catch (e) { setMfaErr(e instanceof Error ? e.message : 'Failed to disable MFA') }
  }

  async function handleRegenCodes() {
    setMfaErr(''); setMfaMsg('')
    try {
      const res = await regenerateBackupCodes()
      setBackupCodes(res.backup_codes)
      setMfaMsg('New backup codes generated.')
    } catch (e) { setMfaErr(e instanceof Error ? e.message : 'Failed to regenerate codes') }
  }

  async function handleChangePwd(e: FormEvent) {
    e.preventDefault(); setPwdErr(''); setPwdMsg('')
    if (newPwd !== confirmPwd) { setPwdErr('Passwords do not match.'); return }
    try {
      await changePassword(curPwd, newPwd)
      setCurPwd(''); setNewPwd(''); setConfirmPwd('')
      setPwdMsg('Password changed. Other sessions were revoked.')
    } catch (e) { setPwdErr(e instanceof Error ? e.message : 'Password change failed') }
  }

  async function handleRevoke(id: string) {
    setSessErr('')
    try { await revokeMySession(id); await loadSessions() }
    catch (e) { setSessErr(e instanceof Error ? e.message : 'Failed to revoke session') }
  }

  return (
    <div className="dashboard-grid" style={{ display: 'grid', gap: '1.5rem' }}>
      <section className="panel-card" aria-labelledby="mfa-heading">
        <div className="panel-header">
          <h2 id="mfa-heading">Two-Factor Authentication (MFA)</h2>
          <span className="status-badge">{currentUser?.mfa_enabled ? 'Enabled' : 'Disabled'}</span>
        </div>
        {mfaErr && <p className="error-banner" role="alert">{mfaErr}</p>}
        {mfaMsg && <p className="success-banner" aria-live="polite">{mfaMsg}</p>}
        {!currentUser?.mfa_enabled ? (
          <div>
            {!qrDataUrl ? (
              <form onSubmit={handleStartMfa} className="form-grid">
                <div className="field">
                  <label htmlFor="mfa-setup-pwd">Current password</label>
                  <input id="mfa-setup-pwd" type="password" value={setupPwd} onChange={(e) => setSetupPwd(e.target.value)} required />
                </div>
                <button type="submit" className="primary-btn">Set up MFA</button>
              </form>
            ) : (
              <form onSubmit={handleEnableMfa} className="form-grid">
                <img src={qrDataUrl} alt="MFA QR Code" width={180} height={180} />
                <p>Manual secret: <code>{mfaSecret}</code></p>
                <div className="field">
                  <label htmlFor="mfa-enable-code">Verification code (6 digits)</label>
                  <input id="mfa-enable-code" value={totpCode} onChange={(e) => setTotpCode(e.target.value)} maxLength={6} required />
                </div>
                <button type="submit" className="primary-btn">Verify and Enable MFA</button>
              </form>
            )}
          </div>
        ) : (
          <div style={{ display: 'grid', gap: '1rem' }}>
            <button type="button" className="secondary-btn" onClick={handleRegenCodes}>Regenerate Backup Codes</button>
            <form onSubmit={handleDisableMfa} className="form-grid">
              <div className="field">
                <label htmlFor="mfa-disable-pwd">Current password</label>
                <input id="mfa-disable-pwd" type="password" value={disablePwd} onChange={(e) => setDisablePwd(e.target.value)} required />
              </div>
              <div className="field">
                <label htmlFor="mfa-disable-code">Authenticator code</label>
                <input id="mfa-disable-code" value={disableCode} onChange={(e) => setDisableCode(e.target.value)} maxLength={6} required />
              </div>
              <button type="submit" className="danger-btn">Disable MFA</button>
            </form>
          </div>
        )}
        {backupCodes.length > 0 && (
          <div style={{ marginTop: '1rem' }}>
            <h3>Backup Codes (save securely)</h3>
            <ul>{backupCodes.map((c) => <li key={c}><code>{c}</code></li>)}</ul>
          </div>
        )}
      </section>

      <section className="panel-card" aria-labelledby="pwd-heading">
        <h2 id="pwd-heading">Change Password</h2>
        {pwdErr && <p className="error-banner" role="alert">{pwdErr}</p>}
        {pwdMsg && <p className="success-banner" aria-live="polite">{pwdMsg}</p>}
        <form onSubmit={handleChangePwd} className="form-grid">
          <div className="field">
            <label htmlFor="cur-pwd">Current password</label>
            <input id="cur-pwd" type="password" value={curPwd} onChange={(e) => setCurPwd(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="new-pwd">New password</label>
            <input id="new-pwd" type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="confirm-pwd">Confirm new password</label>
            <input id="confirm-pwd" type="password" value={confirmPwd} onChange={(e) => setConfirmPwd(e.target.value)} required />
          </div>
          <button type="submit" className="primary-btn">Update Password</button>
        </form>
      </section>

      <section className="panel-card" aria-labelledby="sess-heading">
        <div className="panel-header">
          <h2 id="sess-heading">Active Sessions ({sessions.length})</h2>
          <button type="button" className="secondary-btn" onClick={loadSessions}>Refresh</button>
        </div>
        {sessErr && <p className="error-banner" role="alert">{sessErr}</p>}
        <ul>
          {sessions.map((s) => (
            <li key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0' }}>
              <span>{s.user_agent || 'Unknown device'} - {s.ip_address || 'Unknown IP'} (expires {new Date(s.expires_at).toLocaleString()})</span>
              <button type="button" className="danger-btn" onClick={() => handleRevoke(s.id)}>Revoke</button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
