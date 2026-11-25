import { useState } from 'react'
import {
  confirmPasswordReset,
  loginMfa,
  loginUser,
  requestPasswordReset,
} from './services/api'

interface LoginFormProps {
  onSuccess: () => void
}

type AuthMode = 'login' | 'mfa' | 'forgot' | 'reset'

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [mfaToken, setMfaToken] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [infoMessage, setInfoMessage] = useState<string | null>(null)

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode)
    setError(null)
    setInfoMessage(null)
    if (nextMode === 'login') {
      setMfaToken('')
      setMfaCode('')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setInfoMessage(null)
    setLoading(true)

    try {
      if (mode === 'login') {
        const res = await loginUser(email, password)
        if (res.mfa_required && res.mfa_token) {
          setMfaToken(res.mfa_token)
          setMfaCode('')
          setMode('mfa')
        } else {
          onSuccess()
        }
      } else if (mode === 'mfa') {
        await loginMfa(mfaToken, mfaCode.trim())
        onSuccess()
      } else if (mode === 'forgot') {
        const res = await requestPasswordReset(email)
        if (res.reset_token) {
          setResetToken(res.reset_token)
        }
        setInfoMessage(res.message)
        setMode('reset')
      } else if (mode === 'reset') {
        await confirmPasswordReset(resetToken, newPassword)
        setPassword('')
        setNewPassword('')
        setResetToken('')
        setMode('login')
        setInfoMessage(
          'Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.'
        )
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Une erreur inattendue est survenue')
      }
    } finally {
      setLoading(false)
    }
  }

  const getTitle = () => {
    if (mode === 'mfa') return 'Vérification à deux facteurs'
    if (mode === 'forgot') return 'Mot de passe oublié'
    if (mode === 'reset') return 'Réinitialiser le mot de passe'
    return 'Connexion FinGuard'
  }

  const getSubtitle = () => {
    if (mode === 'mfa')
      return "Entrez le code ? 6 chiffres de votre application d'authentification ou un code de secours"
    if (mode === 'forgot')
      return 'Entrez votre adresse email pour recevoir un jeton de réinitialisation'
    if (mode === 'reset')
      return 'Choisissez votre nouveau mot de passe sécurisé (12 caractères min.)'
    return 'Accès privé réservé aux utilisateurs autorisés'
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-icon" aria-hidden="true">
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <div>
            <div
              style={{
                fontSize: '18px',
                fontWeight: 700,
                letterSpacing: '-0.02em',
              }}
            >
              FinGuard
            </div>
            <div
              style={{
                fontSize: '11px',
                color: 'var(--color-muted-foreground)',
              }}
            >
              Financial Security &amp; Ledger
            </div>
          </div>
        </div>

        <h2 className="auth-title">{getTitle()}</h2>
        <p className="auth-subtitle">{getSubtitle()}</p>

        {error && (
          <div className="auth-alert-error" role="alert">
            {error}
          </div>
        )}

        {infoMessage && (
          <div className="auth-alert-info" role="status">
            {infoMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          {(mode === 'login' || mode === 'forgot') && (
            <div className="auth-field">
              <label htmlFor="auth-email">Adresse email</label>
              <input
                id="auth-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="alice@example.com"
                className="auth-input"
              />
            </div>
          )}

          {mode === 'login' && (
            <div className="auth-field">
              <div className="auth-field-header">
                <label htmlFor="auth-password" style={{ marginBottom: 0 }}>
                  Mot de passe
                </label>
                <button
                  type="button"
                  onClick={() => switchMode('forgot')}
                  className="auth-link-btn"
                >
                  Mot de passe oublié ?
                </button>
              </div>
              <input
                id="auth-password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="auth-input"
              />
            </div>
          )}

          {mode === 'mfa' && (
            <div className="auth-field">
              <label htmlFor="auth-mfa-code">Code MFA ou code de secours</label>
              <input
                id="auth-mfa-code"
                type="text"
                required
                autoComplete="one-time-code"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                placeholder="123456"
                className="auth-input"
              />
            </div>
          )}

          {mode === 'reset' && (
            <>
              <div className="auth-field">
                <label htmlFor="auth-reset-token">
                  Jeton de réinitialisation
                </label>
                <input
                  id="auth-reset-token"
                  type="text"
                  required
                  value={resetToken}
                  onChange={(e) => setResetToken(e.target.value)}
                  placeholder="Collez votre jeton de réinitialisation"
                  className="auth-input"
                />
              </div>

              <div className="auth-field">
                <label htmlFor="auth-new-password">
                  Nouveau mot de passe (12 caractères min.)
                </label>
                <input
                  id="auth-new-password"
                  type="password"
                  required
                  minLength={12}
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="auth-input"
                />
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            className="auth-submit-btn"
          >
            {loading
              ? 'Chargement...'
              : mode === 'forgot'
                ? 'Envoyer le lien de réinitialisation'
                : mode === 'reset'
                  ? 'Mettre à jour le mot de passe'
                  : 'Se connecter'}
          </button>
        </form>

        {mode !== 'login' && (
          <div className="auth-footer">
            Retour à la connexion ?{' '}
            <button
              type="button"
              onClick={() => switchMode('login')}
              className="auth-link-btn"
            >
              Se connecter
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
