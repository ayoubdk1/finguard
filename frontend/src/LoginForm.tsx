import { useState } from 'react'
import { loginUser, registerUser } from './services/api'

interface LoginFormProps {
  onSuccess: () => void
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (isRegister) {
        await registerUser(email, fullName, password)
        // Automatically login after registration
        await loginUser(email, password)
      } else {
        await loginUser(email, password)
      }
      onSuccess()
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('An unexpected error occurred')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: '60px auto', padding: '32px', border: '1px solid #334155', borderRadius: '12px', background: '#0f172a', color: '#f8fafc' }}>
      <h2 style={{ textAlign: 'center', marginBottom: 8, fontSize: '24px' }}>
        {isRegister ? 'Cr?er un compte FinGuard' : 'Connexion FinGuard'}
      </h2>
      <p style={{ textAlign: 'center', color: '#94a3b8', fontSize: '14px', marginBottom: 24 }}>
        {isRegister ? 'Inscrivez-vous pour acc?der ? votre tableau de bord' : 'Entrez vos identifiants pour continuer'}
      </p>

      {error && (
        <div style={{ padding: '12px', marginBottom: '16px', background: '#451a1a', border: '1px solid #dc2626', borderRadius: '6px', color: '#fca5a5', fontSize: '14px' }}>
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {isRegister && (
          <div>
            <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Nom complet</label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="ex. Alice Martin"
              style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#fff', fontSize: '14px', boxSizing: 'border-box' }}
            />
          </div>
        )}

        <div>
          <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Adresse email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="alice@example.com"
            style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#fff', fontSize: '14px', boxSizing: 'border-box' }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', color: '#cbd5e1' }}>Mot de passe (12 caract?res min.)</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="????????????"
            style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#fff', fontSize: '14px', boxSizing: 'border-box' }}
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          style={{ width: '100%', padding: '12px', borderRadius: '6px', border: 'none', background: '#2563eb', color: '#fff', fontWeight: 600, fontSize: '15px', cursor: loading ? 'not-allowed' : 'pointer', marginTop: '8px' }}
        >
          {loading ? 'Chargement...' : isRegister ? 'S?inscrire' : 'Se connecter'}
        </button>
      </form>

      <div style={{ marginTop: '20px', textAlign: 'center', fontSize: '13px', color: '#94a3b8' }}>
        {isRegister ? 'D?j? un compte ?' : 'Pas encore de compte ?'}{' '}
        <button
          type="button"
          onClick={() => { setIsRegister(!isRegister); setError(null); }}
          style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', textDecoration: 'underline', padding: 0, font: 'inherit' }}
        >
          {isRegister ? 'Se connecter' : 'Cr?er un compte'}
        </button>
      </div>
    </div>
  )
}
