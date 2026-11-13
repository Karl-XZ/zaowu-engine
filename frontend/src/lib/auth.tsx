import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, tokenStore } from './api'

export type Quota = {
  freeTotal: number; freeUsed: number; freeReserved: number; freeRemaining: number; paidCredits: number
  priceFen: number; resetAt: string; paidEngineBlocked: boolean; blockReason: string | null
  failedAttempts: number; failedAttemptsLimit: number; cadRebuilds: number; cadRebuildLimit: number
}
export type User = { id: string; email: string; nickname: string; isAdmin: boolean; quota: Quota }

type Ctx = {
  user: User | null; ready: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, nickname: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}
const AuthCtx = createContext<Ctx>(null as any)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) { setUser(null); return }
    try { setUser(await api<User>('/api/v1/auth/me')) } catch { tokenStore.set(null); setUser(null) }
  }, [])

  useEffect(() => { refresh().finally(() => setReady(true)) }, [refresh])

  const login = async (email: string, password: string) => {
    const r = await api<{ token: string; user: User }>('/api/v1/auth/login', { body: { email, password } })
    tokenStore.set(r.token); setUser(r.user)
  }
  const register = async (email: string, password: string, nickname: string) => {
    const r = await api<{ token: string; user: User }>('/api/v1/auth/register', { body: { email, password, nickname, privacyConsent: true } })
    tokenStore.set(r.token); setUser(r.user)
  }
  const logout = () => { tokenStore.set(null); setUser(null) }

  return <AuthCtx.Provider value={{ user, ready, login, register, logout, refresh }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
