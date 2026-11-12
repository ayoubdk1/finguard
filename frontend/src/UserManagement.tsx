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
        if (active) setError(err instanceof Error ? err.message : 'Erreur de chargement')
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
      await createAdminUser({ email, full_name: fullName, password, role, status: 'ACTIVE' })
      setEmail('')
      setFullName('')
      setPassword('')
      setRole('CUSTOMER')
      setSuccessMsg('Utilisateur cr?? avec succ?s.')
      await loadUsers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la cr?ation')
    }
  }

  const handleStatusChange = async (user: AdminUser, nextStatus: UserStatus) => {
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
      setSuccessMsg(`Statut de ${updated.email} mis ? jour : ${updated.status}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de mise ? jour')
    }
  }

  const handleRoleChange = async (user: AdminUser, nextRole: UserRole) => {
    setError(null)
    setSuccessMsg(null)
    try {
      const updated = await updateAdminUser(user.id, { role: nextRole })
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
      setSuccessMsg(`R?le de ${updated.email} mis ? jour : ${updated.role}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de mise ? jour')
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
      setError(err instanceof Error ? err.message : 'Impossible de charger les d?tails')
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
      setSuccessMsg(`Mot de passe r?initialis? pour ${selectedUser.email} (sessions r?voqu?es).`)
      const s = await getAdminUserSessions(selectedUser.id)
      setSessions(s.sessions)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la r?initialisation')
    }
  }

  const handleRevokeSession = async (sessionId: string) => {
    if (!selectedUser) return
    try {
      await revokeAdminUserSession(selectedUser.id, sessionId)
      const s = await getAdminUserSessions(selectedUser.id)
      setSessions(s.sessions)
      setSuccessMsg('Session r?voqu?e.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la r?vocation')
    }
  }

  const cardStyle: React.CSSProperties = {
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: '10px',
    padding: '20px',
    marginBottom: '20px',
    color: '#e2e8f0',
  }

  const inputStyle: React.CSSProperties = {
    padding: '8px 10px',
    borderRadius: '6px',
    border: '1px solid #334155',
    background: '#1e293b',
    color: '#fff',
    fontSize: '13px',
  }

  return (
    <section style={{ padding: '8px 0' }}>
      {error && (
        <div style={{ padding: '12px', marginBottom: '16px', background: '#451a1a', border: '1px solid #dc2626', borderRadius: '6px', color: '#fca5a5' }}>
          {error}
        </div>
      )}
      {successMsg && (
        <div style={{ padding: '12px', marginBottom: '16px', background: '#064e3b', border: '1px solid #10b981', borderRadius: '6px', color: '#a7f3d0' }}>
          {successMsg}
        </div>
      )}

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0, marginBottom: '14px' }}>Cr?er un compte utilisateur (Admin uniquement)</h3>
        <form onSubmit={handleCreateUser} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px', alignItems: 'end' }}>
          <input type="email" required placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} style={inputStyle} />
          <input type="text" required placeholder="Nom complet" value={fullName} onChange={(e) => setFullName(e.target.value)} style={inputStyle} />
          <input type="password" required minLength={12} placeholder="Mot de passe (12+ car.)" value={password} onChange={(e) => setPassword(e.target.value)} style={inputStyle} />
          <select value={role} onChange={(e) => setRole(e.target.value as UserRole)} style={inputStyle}>
            <option value="CUSTOMER">CUSTOMER</option>
            <option value="FRAUD_ANALYST">FRAUD_ANALYST</option>
            <option value="AUDITOR">AUDITOR</option>
            <option value="ADMIN">ADMIN</option>
          </select>
          <button type="submit" style={{ padding: '9px 14px', borderRadius: '6px', border: 'none', background: '#2563eb', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
            + Cr?er
          </button>
        </form>
      </div>

      <div style={cardStyle}>
        <h3 style={{ marginTop: 0, marginBottom: '14px' }}>Utilisateurs ({users.length})</h3>
        {loading ? (
          <p>Chargement...</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ textAlign: 'left', borderBottom: '1px solid #334155', color: '#94a3b8' }}>
                  <th style={{ padding: '8px' }}>Email</th>
                  <th style={{ padding: '8px' }}>Nom</th>
                  <th style={{ padding: '8px' }}>R?le</th>
                  <th style={{ padding: '8px' }}>Statut</th>
                  <th style={{ padding: '8px' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} style={{ borderBottom: '1px solid #1e293b' }}>
                    <td style={{ padding: '8px' }}>{u.email}</td>
                    <td style={{ padding: '8px' }}>{u.full_name}</td>
                    <td style={{ padding: '8px' }}>
                      <select value={u.role} onChange={(e) => void handleRoleChange(u, e.target.value as UserRole)} style={inputStyle}>
                        <option value="CUSTOMER">CUSTOMER</option>
                        <option value="FRAUD_ANALYST">FRAUD_ANALYST</option>
                        <option value="AUDITOR">AUDITOR</option>
                        <option value="ADMIN">ADMIN</option>
                      </select>
                    </td>
                    <td style={{ padding: '8px' }}>
                      <select value={u.status} onChange={(e) => void handleStatusChange(u, e.target.value as UserStatus)} style={inputStyle}>
                        <option value="ACTIVE">ACTIVE</option>
                        <option value="SUSPENDED">SUSPENDED</option>
                        <option value="DISABLED">DISABLED</option>
                      </select>
                    </td>
                    <td style={{ padding: '8px' }}>
                      <button
                        type="button"
                        onClick={() => void inspectUser(u)}
                        style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid #334155', background: '#1e293b', color: '#38bdf8', cursor: 'pointer' }}
                      >
                        S?curit? / Sessions
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
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0 }}>D?tails s?curit? : {selectedUser.email}</h3>

          <form onSubmit={handleAdminResetPassword} style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
            <input
              type="password"
              required
              minLength={12}
              placeholder="Nouveau mot de passe (12+ caract?res)"
              value={resetPwValue}
              onChange={(e) => setResetPwValue(e.target.value)}
              style={{ ...inputStyle, minWidth: '260px' }}
            />
            <button type="submit" style={{ padding: '8px 14px', borderRadius: '6px', border: 'none', background: '#d97706', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
              R?initialiser le mot de passe
            </button>
          </form>

          <h4>Sessions actives ({sessions.length})</h4>
          {sessions.length === 0 ? (
            <p style={{ color: '#94a3b8', fontSize: '13px' }}>Aucune session active.</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, marginBottom: '20px' }}>
              {sessions.map((s) => (
                <li key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px', borderBottom: '1px solid #1e293b', fontSize: '13px' }}>
                  <span>IP: {s.ip_address || 'N/A'} ? {s.user_agent || 'Client'}</span>
                  <button
                    type="button"
                    onClick={() => void handleRevokeSession(s.id)}
                    style={{ padding: '4px 10px', borderRadius: '6px', border: 'none', background: '#dc2626', color: '#fff', cursor: 'pointer' }}
                  >
                    R?voquer
                  </button>
                </li>
              ))}
            </ul>
          )}

          <h4>Historique des connexions ({history.length})</h4>
          {history.length === 0 ? (
            <p style={{ color: '#94a3b8', fontSize: '13px' }}>Aucune tentative enregistr?e.</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {history.map((h) => (
                <li key={h.id} style={{ padding: '6px 0', borderBottom: '1px solid #1e293b', fontSize: '13px', color: h.success ? '#86efac' : '#fca5a5' }}>
                  [{h.success ? 'SUCC?S' : '?CHEC'}] {new Date(h.created_at).toLocaleString()} ? IP: {h.ip_address || 'N/A'}
                  {h.failure_reason ? ` (${h.failure_reason})` : ''}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
