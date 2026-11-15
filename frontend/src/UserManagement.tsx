import { useEffect, useState } from 'react'
import {
  createAdminUser,
  getAdminUserLoginHistory,
  getAdminUserSessions,
  listAdminUsers,
  resetAdminUserPassword,
  revokeAdminUserSession,
  updateAdminUser,
  type ActiveSessionItem,
  type AdminUser,
  type LoginHistoryEntry,
  type UserRole,
  type UserStatus,
} from './services/api'

export function UserManagement() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // New user form
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('CUSTOMER')

  // Selected user details (sessions + login history)
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [history, setHistory] = useState<LoginHistoryEntry[]>([])
  const [sessions, setSessions] = useState<ActiveSessionItem[]>([])
  const [resetPwValue, setResetPwValue] = useState('')

  const loadUsers = async () => {
    setLoading(true)
    try {
      const list = await listAdminUsers()
      setUsers(list)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    listAdminUsers()
      .then((list) => {
        if (active) setUsers(list)
      })
      .catch((err) => {
        if (active)
          setError(err instanceof Error ? err.message : 'Erreur de chargement')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)
    try {
      await createAdminUser({
        email,
        full_name: fullName,
        password,
        role,
        status: 'ACTIVE',
      })
      setEmail('')
      setFullName('')
      setPassword('')
      setRole('CUSTOMER')
      setSuccessMsg('Utilisateur créé avec succès.')
      await loadUsers()
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Erreur lors de la création'
      )
    }
  }

  const handleStatusChange = async (
    user: AdminUser,
    nextStatus: UserStatus
  ) => {
    setError(null)
    setSuccessMsg(null)
    try {
      const updated = await updateAdminUser(user.id, { status: nextStatus })
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
      if (selectedUser?.id === updated.id) {
        setSelectedUser(updated)
        const s = await getAdminUserSessions(updated.id)
        setSessions(s.sessions)
      }
      setSuccessMsg(
        `Statut de ${updated.email} mis à jour : ${updated.status}`
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de mise à jour')
    }
  }

  const handleRoleChange = async (user: AdminUser, nextRole: UserRole) => {
    setError(null)
    setSuccessMsg(null)
    try {
      const updated = await updateAdminUser(user.id, { role: nextRole })
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
      setSuccessMsg(`Rôle de ${updated.email} mis à jour : ${updated.role}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de mise à jour')
    }
  }

  const inspectUser = async (user: AdminUser) => {
    setSelectedUser(user)
    setError(null)
    try {
      const [h, s] = await Promise.all([
        getAdminUserLoginHistory(user.id),
        getAdminUserSessions(user.id),
      ])
      setHistory(h)
      setSessions(s.sessions)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Impossible de charger les détails'
      )
    }
  }

  const handleAdminResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedUser) return
    setError(null)
    setSuccessMsg(null)
    try {
      await resetAdminUserPassword(selectedUser.id, resetPwValue)
      setResetPwValue('')
      setSuccessMsg(
        `Mot de passe réinitialisé pour ${selectedUser.email} (sessions révoquées).`
      )
      const s = await getAdminUserSessions(selectedUser.id)
      setSessions(s.sessions)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Erreur lors de la réinitialisation'
      )
    }
  }

  const handleRevokeSession = async (sessionId: string) => {
    if (!selectedUser) return
    try {
      await revokeAdminUserSession(selectedUser.id, sessionId)
      const s = await getAdminUserSessions(selectedUser.id)
      setSessions(s.sessions)
      setSuccessMsg('Session révoquée.')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Erreur lors de la révocation'
      )
    }
  }

  return (
    <section className="admin-page">
      {error && (
        <div className="auth-alert-error" role="alert">
          {error}
        </div>
      )}
      {successMsg && (
        <div className="auth-alert-info" role="status">
          {successMsg}
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <div>
            <h3>Créer un compte utilisateur (Admin uniquement)</h3>
            <p>Provisionner un nouvel accès RBAC sécurisé</p>
          </div>
          <span className="panel-tag">RBAC ADMIN</span>
        </div>

        <form onSubmit={handleCreateUser} className="admin-create-grid">
          <input
            type="email"
            required
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="admin-input"
          />
          <input
            type="text"
            required
            placeholder="Nom complet"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="admin-input"
          />
          <input
            type="password"
            required
            minLength={12}
            placeholder="Mot de passe (12+ car.)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="admin-input"
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className="admin-select"
          >
            <option value="CUSTOMER">CUSTOMER</option>
            <option value="FRAUD_ANALYST">FRAUD_ANALYST</option>
            <option value="AUDITOR">AUDITOR</option>
            <option value="ADMIN">ADMIN</option>
          </select>
          <button type="submit" className="primary-button">
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
            Créer
          </button>
        </form>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div>
            <h3>Utilisateurs ({users.length})</h3>
            <p>Contrôle des rôles, statuts et sessions actives</p>
          </div>
        </div>

        {loading ? (
          <p className="events-message">Chargement...</p>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Nom</th>
                  <th>Rôle</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <strong style={{ color: 'var(--color-foreground)' }}>
                        {u.email}
                      </strong>
                    </td>
                    <td>{u.full_name}</td>
                    <td>
                      <select
                        value={u.role}
                        onChange={(e) =>
                          void handleRoleChange(u, e.target.value as UserRole)
                        }
                        className="admin-select"
                        style={{ maxWidth: '170px' }}
                      >
                        <option value="CUSTOMER">CUSTOMER</option>
                        <option value="FRAUD_ANALYST">FRAUD_ANALYST</option>
                        <option value="AUDITOR">AUDITOR</option>
                        <option value="ADMIN">ADMIN</option>
                      </select>
                    </td>
                    <td>
                      <select
                        value={u.status}
                        onChange={(e) =>
                          void handleStatusChange(
                            u,
                            e.target.value as UserStatus
                          )
                        }
                        className="admin-select"
                        style={{ maxWidth: '150px' }}
                      >
                        <option value="ACTIVE">ACTIVE</option>
                        <option value="SUSPENDED">SUSPENDED</option>
                        <option value="DISABLED">DISABLED</option>
                      </select>
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() => void inspectUser(u)}
                        className="admin-action-btn"
                      >
                        <svg
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden="true"
                        >
                          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                        </svg>
                        Sécurité / Sessions
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedUser && (
        <div className="panel">
          <div className="panel-header">
            <div>
              <h3>Détails sécurité : {selectedUser.email}</h3>
              <p>Réinitialisation de mot de passe, sessions et audit de connexion</p>
            </div>
          </div>

          <form
            onSubmit={handleAdminResetPassword}
            style={{
              display: 'flex',
              gap: '10px',
              marginBottom: '24px',
              flexWrap: 'wrap',
            }}
          >
            <input
              type="password"
              required
              minLength={12}
              placeholder="Nouveau mot de passe (12+ caractères)"
              value={resetPwValue}
              onChange={(e) => setResetPwValue(e.target.value)}
              className="admin-input"
              style={{ maxWidth: '300px' }}
            />
            <button type="submit" className="admin-warning-btn">
              Réinitialiser le mot de passe
            </button>
          </form>

          <h4
            style={{
              fontSize: '13px',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--color-muted-foreground)',
              marginBottom: '10px',
            }}
          >
            Sessions actives ({sessions.length})
          </h4>
          {sessions.length === 0 ? (
            <p
              style={{
                color: 'var(--color-muted-foreground)',
                fontSize: '13px',
                marginBottom: '20px',
              }}
            >
              Aucune session active.
            </p>
          ) : (
            <ul className="admin-list">
              {sessions.map((s) => (
                <li key={s.id} className="admin-list-item">
                  <span>
                    IP: {s.ip_address || 'N/A'} — {s.user_agent || 'Client'}
                  </span>
                  <button
                    type="button"
                    onClick={() => void handleRevokeSession(s.id)}
                    className="admin-danger-btn"
                  >
                    Révoquer
                  </button>
                </li>
              ))}
            </ul>
          )}

          <h4
            style={{
              fontSize: '13px',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--color-muted-foreground)',
              marginBottom: '10px',
            }}
          >
            Historique des connexions ({history.length})
          </h4>
          {history.length === 0 ? (
            <p
              style={{
                color: 'var(--color-muted-foreground)',
                fontSize: '13px',
              }}
            >
              Aucune tentative enregistrée.
            </p>
          ) : (
            <ul className="admin-list" style={{ marginBottom: 0 }}>
              {history.map((h) => (
                <li
                  key={h.id}
                  className="admin-list-item"
                  style={{
                    color: h.success
                      ? 'var(--color-success)'
                      : 'var(--color-destructive)',
                  }}
                >
                  <span>
                    [{h.success ? 'SUCCÈS' : 'ÉCHEC'}]{' '}
                    {new Date(h.created_at).toLocaleString()} — IP:{' '}
                    {h.ip_address || 'N/A'}
                    {h.failure_reason ? ` (${h.failure_reason})` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
