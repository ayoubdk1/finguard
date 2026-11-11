import { useState } from 'react'
import {
  confirmPasswordReset,
  loginUser,
  registerUser,
  requestPasswordReset,
} from './services/api'

interface LoginFormProps {
  onSuccess: () => void
}

type AuthMode = 'login' | 'register' | 'forgot' | 'reset'

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
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
      if (mode === 'register') {
        await registerUser(email, fullName, password)
        await loginUser(email, password)
        onSuccess()
      } else if (mode === 'login') {
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
        setInfoMessage('Votre mot de passe a ?t? r?initialis? avec succ?s. Vous pouvez maintenant vous connecter.')
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
    if (mode === 'register') return 'Cr?er un compte FinGuard'
    if (mode === 'forgot') return 'Mot de passe oubli?'
    if (mode === 'reset') return 'R?initialiser le mot de passe'
    return 'Connexion FinGuard'
  }

  const getSubtitle = () => {
    if (mode === 'register') return 'Inscrivez-vous pour acc?der ? votre tableau de bord'
    if (mode === 'forgot') return 'Entrez votre adresse email pour recevoir un jeton de r?initialisation'
    if (mode === 'reset') return 'Choisissez votre nouveau mot de passe s?curis? (12 caract?res min.)'
    return 'Entrez vos identifiants pour continuer'
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
        {mode === 'register' && (
          <div>
            <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Nom complet</label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="ex. Alice Martin"
              style={inputStyle}
            />
          </div>
        )}

        {(mode === 'login' || mode === 'register' || mode === 'forgot') && (
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

        {(mode === 'login' || mode === 'register') && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <label style={{ fontSize: '13px', color: '#cbd5e1' }}>Mot de passe (12 caract?res min.)</label>
              {mode === 'login' && (
                <button
                  type="button"
                  onClick={() => switchMode('forgot')}
                  style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', fontSize: '12px', textDecoration: 'underline', padding: 0 }}
                >
                  Mot de passe oubli? ?
                </button>
              )}
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
              <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Jeton de r?initialisation</label>
              <input
                type="text"
                required
                value={resetToken}
                onChange={(e) => setResetToken(e.target.value)}
                placeholder="Collez votre jeton de r?initialisation"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Nouveau mot de passe (12 caract?res min.)</label>
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
            : mode === 'register'
            ? "S'inscrire"
            : mode === 'forgot'
            ? 'Envoyer le lien de r?initialisation'
            : mode === 'reset'
            ? 'Mettre ? jour le mot de passe'
            : 'Se connecter'}
        </button>
      </form>

      <div style={{ marginTop: '20px', textAlign: 'center', fontSize: '13px', color: '#94a3b8' }}>
        {mode === 'login' ? (
          <>
            Pas encore de compte ?{' '}
            <button
              type="button"
              onClick={() => switchMode('register')}
              style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', textDecoration: 'underline', padding: 0, font: 'inherit' }}
            >
              Cr?er un compte
            </button>
          </>
        ) : (
          <>
            Retour ? la connexion ?{' '}
            <button
              type="button"
              onClick={() => switchMode('login')}
              style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', textDecoration: 'underline', padding: 0, font: 'inherit' }}
            >
              Se connecter
            </button>
          </>
        )}
      </div>
    </div>
  )
}
