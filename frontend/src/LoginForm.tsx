import { useState } from 'react'
import {
  confirmPasswordReset,
  loginUser,
  requestPasswordReset,
} from './services/api'

interface LoginFormProps {
  onSuccess: () => void
}

type AuthMode = 'login' | 'forgot' | 'reset'

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [infoMessage, setInfoMessage] = useState<string | null>(null)

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode)
    setError(null)
    setInfoMessage(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setInfoMessage(null)
    setLoading(true)

    try {
      if (mode === 'login') {
        await loginUser(email, password)
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
        setInfoMessage('Votre mot de passe a ?t? réinitialisé avec succès. Vous pouvez maintenant vous connecter.')
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
    if (mode === 'forgot') return 'Mot de passe oublié'
    if (mode === 'reset') return 'Réinitialiser le mot de passe'
    return 'Connexion FinGuard'
  }

  const getSubtitle = () => {
    if (mode === 'forgot') return 'Entrez votre adresse email pour recevoir un jeton de réinitialisation'
    if (mode === 'reset') return 'Choisissez votre nouveau mot de passe sécurisé (12 caractères min.)'
    return 'Accès privé réservé aux utilisateurs autorisés'
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 12px',
    borderRadius: '6px',
    border: '1px solid #334155',
    background: '#1e293b',
    color: '#fff',
    fontSize: '14px',
    boxSizing: 'border-box',
  }

  return (
    <div style={{ maxWidth: 420, margin: '60px auto', padding: '32px', border: '1px solid #334155', borderRadius: '12px', background: '#0f172a', color: '#f8fafc' }}>
      <h2 style={{ textAlign: 'center', marginBottom: 8, fontSize: '24px' }}>
        {getTitle()}
      </h2>
      <p style={{ textAlign: 'center', color: '#94a3b8', fontSize: '14px', marginBottom: 24 }}>
        {getSubtitle()}
      </p>

      {error && (
        <div style={{ padding: '12px', marginBottom: '16px', background: '#451a1a', border: '1px solid #dc2626', borderRadius: '6px', color: '#fca5a5', fontSize: '14px' }}>
          {error}
        </div>
      )}

      {infoMessage && (
        <div style={{ padding: '12px', marginBottom: '16px', background: '#064e3b', border: '1px solid #10b981', borderRadius: '6px', color: '#a7f3d0', fontSize: '14px' }}>
          {infoMessage}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {(mode === 'login' || mode === 'forgot') && (
          <div>
            <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Adresse email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="alice@example.com"
              style={inputStyle}
            />
          </div>
        )}

        {mode === 'login' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <label style={{ fontSize: '13px', color: '#cbd5e1' }}>Mot de passe</label>
              <button
                type="button"
                onClick={() => switchMode('forgot')}
                style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', fontSize: '12px', textDecoration: 'underline', padding: 0 }}
              >
                Mot de passe oublié ?
              </button>
            </div>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="????????????"
              style={inputStyle}
            />
          </div>
        )}

        {mode === 'reset' && (
          <>
            <div>
              <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Jeton de réinitialisation</label>
              <input
                type="text"
                required
                value={resetToken}
                onChange={(e) => setResetToken(e.target.value)}
                placeholder="Collez votre jeton de réinitialisation"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Nouveau mot de passe (12 caractères min.)</label>
              <input
                type="password"
                required
                minLength={12}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="????????????"
                style={inputStyle}
              />
            </div>
          </>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{ width: '100%', padding: '12px', borderRadius: '6px', border: 'none', background: '#2563eb', color: '#fff', fontWeight: 600, fontSize: '15px', cursor: loading ? 'not-allowed' : 'pointer', marginTop: '8px' }}
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
        <div style={{ marginTop: '20px', textAlign: 'center', fontSize: '13px', color: '#94a3b8' }}>
          Retour à la connexion ?{' '}
          <button
            type="button"
            onClick={() => switchMode('login')}
            style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', textDecoration: 'underline', padding: 0, font: 'inherit' }}
          >
            Se connecter
          </button>
        </div>
      )}
    </div>
  )
}
