export class ApiError extends Error {
  status: number
  detail: any
  constructor(status: number, detail: any) {
    super(typeof detail === 'string' ? detail : detail?.message || '请求失败')
    this.status = status
    this.detail = detail
  }
}

const TOKEN_KEY = 'zaowu.token'
export const tokenStore = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t: string | null) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* 私密模式 */ } },
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any; raw?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const t = tokenStore.get()
  if (t) headers.Authorization = `Bearer ${t}`
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(path, { method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined })
  if (opts.raw) return res as any
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data)
  return data as T
}

export function errMsg(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail
    if (typeof d === 'string') return d
    if (d?.preflight) return d.preflight.issues.filter((i: any) => i.level === 'block').map((i: any) => `${i.message}${i.suggestion ? ' ' + i.suggestion : ''}`).join('；')
    if (d?.errors) return d.errors.join('；')
    if (Array.isArray(d)) return d.map((x: any) => x.msg).join('；')
    return e.message
  }
  return (e as Error)?.message || '出错了'
}

export const uid = () => (crypto?.randomUUID?.() || Math.random().toString(36).slice(2) + Date.now().toString(36)).replace(/-/g, '')

export const fen = (n: number) => `¥${(n / 100).toFixed(2)}`
