import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, errMsg, uid } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useToast } from '../lib/toast'

type Material = { id: string; name: string; validated: boolean; color: boolean; min_wall_mm: number; min_size_mm: number; max_size_mm: number; note: string }
type Concept = { version: number; parentVersion: number | null; instruction: string; dimension: string; summary: string; imageUrl: string; qc: any }
type Msg = { role: 'user' | 'ai' | 'block' | 'system'; text: string; version?: number; dimension?: string; turn?: number; suggestion?: string }
type Session = {
  id: string; title: string; state: string; turnsUsed: number; turnsLimit: number; turnsRemaining: number; currentVersion: number
  confirmedVersion: number | null; material: { id: string; name: string; color: boolean; note: string }; sizeMm: number; purpose: string
  checklist: { key: string; label: string; value: string }[]; messages: Msg[]; concepts: Concept[]; taskId: string | null; taskState: string | null
}

export default function Create() {
  const { sid } = useParams()
  return sid ? <Studio sid={sid} /> : <Setup />
}

/* ------------------------- 第一步：材料 / 尺寸 / 一句话 ------------------------- */
function Setup() {
  const { user, refresh } = useAuth()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const toast = useToast()
  const [mats, setMats] = useState<Material[]>([])
  const [mat, setMat] = useState('mono_resin')
  const [size, setSize] = useState(60)
  const [purpose, setPurpose] = useState('桌面摆件')
  const [prompt, setPrompt] = useState(params.get('prompt') || '')
  const [issues, setIssues] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const idem = useMemo(() => uid(), [])

  useEffect(() => { api<Material[]>('/api/v1/materials').then(setMats).catch(() => {}) }, [])
  useEffect(() => {
    if (!user || prompt.trim().length < 2) { setIssues([]); return }
    const t = setTimeout(() => {
      api('/api/v1/design-sessions/preflight', { body: { prompt, materialId: mat, sizeMm: size } })
        .then((r: any) => setIssues(r.issues)).catch(() => {})
    }, 450)
    return () => clearTimeout(t)
  }, [prompt, mat, size, user])

  const blocked = issues.some((i) => i.level === 'block')
  const q = user?.quota
  const start = async () => {
    if (!user) return nav('/login?next=/create')
    setBusy(true)
    try {
      const s = await api<Session>('/api/v1/design-sessions', { body: { prompt, materialId: mat, sizeMm: size, purpose, idempotencyKey: idem } })
      await refresh()
      nav(`/create/${s.id}`)
    } catch (e: any) {
      if (e.status === 402) { toast('今日免费额度已用完，支付 ¥5 后继续', true); nav('/pay?next=/create') }
      else toast(errMsg(e), true)
    } finally { setBusy(false) }
  }
  const m = mats.find((x) => x.id === mat)

  return (
    <main className="wrap" style={{ padding: 'clamp(32px, 5vw, 72px) var(--gutter)', display: 'flex', flexWrap: 'wrap', gap: 48 }}>
      <div style={{ flex: '1 1 380px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <span className="display" style={{ fontSize: 12, fontWeight: 700, letterSpacing: 4, color: 'var(--red)' }}>NEW DESIGN SESSION</span>
        <h1 style={{ margin: 0, fontSize: 'clamp(48px, 6vw, 96px)', fontWeight: 900, lineHeight: 0.98 }}>想送<br />什么<span style={{ color: 'var(--red)' }}>礼物？</span></h1>
        <p style={{ margin: 0, fontSize: 16, lineHeight: 1.8, maxWidth: 440 }}>先定材料和尺寸，再说一句话。AI 会画出第一张效果图，你可以通过对话调整 <b>最多 10 次</b>，满意了再转成 3D。</p>
        <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {['开启设计会预留 1 次额度', '模型通过制造预检才正式扣除', '放弃或失败会退回额度'].map((t, i) => (
            <li key={t} style={{ display: 'flex', gap: 12, alignItems: 'center', fontSize: 14 }}>
              <span className="display" style={{ width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: i === 1 ? 'var(--red)' : 'var(--ink)', color: 'var(--paper)', fontWeight: 900, fontSize: 13 }}>{i + 1}</span>{t}
            </li>
          ))}
        </ol>
        {q && <p className="mono" style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>今日免费剩余 {q.freeRemaining}/{q.freeTotal}{q.paidCredits ? ` · 付费次数 ${q.paidCredits}` : ''}</p>}
        {q?.blockReason && <p style={{ margin: 0, background: 'var(--red)', color: 'var(--paper)', padding: 12, fontSize: 14 }}>{q.blockReason}</p>}
      </div>

      <div style={{ flex: '2 1 560px', display: 'flex', flexDirection: 'column', gap: 0, border: '3px solid var(--ink)', boxShadow: '14px 14px 0 var(--ink)', background: 'var(--paper)' }}>
        <Step n="01" title="材料与尺寸">
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
            <legend className="label">目标材料（只开放已验证档案）</legend>
            {mats.map((x) => (
              <label key={x.id} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 14, cursor: x.validated ? 'pointer' : 'not-allowed',
                border: `3px ${x.validated ? 'solid' : 'dashed'} ${x.validated ? 'var(--ink)' : '#8A8075'}`,
                background: mat === x.id ? 'var(--ink)' : 'transparent', color: mat === x.id ? 'var(--paper)' : x.validated ? 'var(--ink)' : 'var(--muted)' }}>
                <input type="radio" name="mat" checked={mat === x.id} disabled={!x.validated} onChange={() => setMat(x.id)} style={{ accentColor: '#D52B1E', margin: 0 }} />
                <b style={{ fontSize: 16 }}>{x.name}</b>
                <span className="mono" style={{ fontSize: 11 }}>{x.validated ? `壁厚 ≥ ${x.min_wall_mm} mm · ${x.color ? '全彩' : '单色'}` : '验证中'}</span>
              </label>
            ))}
          </fieldset>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'flex-end', marginTop: 18 }}>
            <label style={{ display: 'flex', flexDirection: 'column' }}>
              <span className="label">目标高度</span>
              <span style={{ display: 'flex', border: '3px solid var(--ink)', background: 'var(--paper-2)' }}>
                <input type="number" value={size} min={m?.min_size_mm} max={m?.max_size_mm} onChange={(e) => setSize(Number(e.target.value))} className="mono"
                  style={{ width: 100, minHeight: 48, border: 0, padding: '0 12px', fontSize: 22, fontWeight: 700, background: 'transparent' }} />
                <span className="mono" style={{ display: 'flex', alignItems: 'center', padding: '0 12px', borderLeft: '3px solid var(--ink)', fontWeight: 700 }}>mm</span>
              </span>
            </label>
            <input type="range" aria-label="高度滑块" min={m?.min_size_mm || 15} max={Math.min(150, m?.max_size_mm || 150)} value={size} onChange={(e) => setSize(Number(e.target.value))}
              style={{ flex: '1 1 200px', accentColor: '#D52B1E', height: 44 }} />
            <label style={{ display: 'flex', flexDirection: 'column' }}>
              <span className="label">用途</span>
              <select className="select" value={purpose} onChange={(e) => setPurpose(e.target.value)} style={{ minHeight: 54 }}>
                {['桌面摆件', '钥匙扣挂件', '纪念品', '车载摆件'].map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
          </div>
        </Step>
        <Step n="02" title="说一句话">
          <label htmlFor="pr" className="label">描述你的礼物</label>
          <textarea id="pr" className="textarea" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={400}
            placeholder="例如：一个站在月亮上的 Q 版小熊，送给闺蜜" />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            {['一只戴围巾的橘猫，坐在圆形底座上', '抱着星星的 Q 版小熊', '戴礼帽的柴犬，生日礼物'].map((s) => (
              <button key={s} className="chip" style={{ cursor: 'pointer', minHeight: 36 }} onClick={() => setPrompt(s)}>{s}</button>
            ))}
          </div>
          <AnimatePresence>
            {issues.map((i, k) => (
              <motion.div key={i.code + k} initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}
                style={{ marginTop: 12, padding: '12px 14px', background: i.level === 'block' ? 'var(--red)' : 'transparent', color: i.level === 'block' ? 'var(--paper)' : 'var(--ink)', border: '3px solid ' + (i.level === 'block' ? 'var(--red)' : 'var(--ink)'), fontSize: 14, lineHeight: 1.6 }}>
                <b>{i.level === 'block' ? '生成前拦截 · ' : '提示 · '}</b>{i.message} {i.suggestion}
              </motion.div>
            ))}
          </AnimatePresence>
        </Step>
        <div style={{ padding: 24, borderTop: '3px solid var(--ink)' }}>
          <button className="btn btn-red btn-lg" style={{ width: '100%', justifyContent: 'space-between' }} disabled={busy || blocked || prompt.trim().length < 2} onClick={start}>
            <span>{busy ? '正在画第一张效果图…' : user ? '生成效果图' : '登录后开始'}</span>
            <span style={{ fontSize: 13, textAlign: 'right', lineHeight: 1.4 }}>预留 1 次额度<br />合格交付才扣</span>
          </button>
          {busy && <div className="loading-stripes" style={{ height: 8, marginTop: 12 }} />}
        </div>
      </div>
    </main>
  )
}

function Step({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <section style={{ padding: 24, borderTop: n === '01' ? 0 : '3px solid var(--ink)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 16 }}>
        <span className="display" style={{ fontSize: 40, fontWeight: 900, lineHeight: 1, color: 'var(--red)' }}>{n}</span>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 900 }}>{title}</h2>
      </div>
      {children}
    </section>
  )
}

/* ------------------------- 第二步：对话设计工作室 ------------------------- */
function Studio({ sid }: { sid: string }) {
  const [s, setS] = useState<Session | null>(null)
  const [view, setView] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState<'turn' | 'confirm' | null>(null)
  const toast = useToast()
  const nav = useNavigate()
  const { refresh } = useAuth()
  const chatRef = useRef<HTMLDivElement>(null)
  const idem = useMemo(() => uid(), [])

  const load = () => api<Session>(`/api/v1/design-sessions/${sid}`).then((x) => { setS(x); return x }).catch((e) => toast(errMsg(e), true))
  useEffect(() => {
    load()
    const refresh = () => { if (document.visibilityState === 'visible') load() }
    const timer = window.setInterval(refresh, 90_000)
    window.addEventListener('focus', refresh)
    return () => { clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [sid]) // eslint-disable-line
  useEffect(() => { chatRef.current?.scrollTo({ top: 1e6, behavior: 'smooth' }) }, [s?.messages.length])
  useEffect(() => {
    if (s?.state !== 'generating') return
    const timer = window.setInterval(load, 3000)
    return () => clearInterval(timer)
  }, [sid, s?.state]) // eslint-disable-line

  if (!s) return <div className="loading-stripes" style={{ height: 8 }} />
  const shown = view ?? s.currentVersion
  const concept = s.concepts.find((c) => c.version === shown) || s.concepts[s.concepts.length - 1]
  if (!concept) return <main className="wrap" style={{ padding: '48px var(--gutter)' }}>
    <h1>{s.state === 'generating' ? '第一张效果图正在生成…' : '这个设计尚无可用效果图'}</h1>
    {s.state === 'generating' ? <><p>生成服务正在处理，页面会自动更新。请勿重复提交。</p><div className="loading-stripes" style={{ height: 8 }} /></>
      : <><p>请开始新设计，失败时预留的生成额度会恢复。</p><Link className="btn btn-red" to="/create">开始新设计</Link></>}
  </main>
  const ended = !['concept_ready', 'adjusting'].includes(s.state)
  const out = s.turnsRemaining <= 0

  const send = async (instruction: string) => {
    if (!instruction.trim() || busy) return
    setBusy('turn')
    try {
      const x = await api<Session>(`/api/v1/design-sessions/${sid}/turns`, { body: { instruction, baseVersion: view ?? undefined } })
      setS(x); setView(null); setText('')
      const last = x.messages[x.messages.length - 1]
      if (last.role === 'block') toast('这次修改被提前拦下，没有消耗调整次数')
    } catch (e) { toast(errMsg(e), true) } finally { setBusy(null) }
  }
  const confirm = async () => {
    setBusy('confirm')
    try {
      const r = await api<{ taskId: string }>(`/api/v1/design-sessions/${sid}/confirm`, { body: { version: concept.version, idempotencyKey: idem } })
      await refresh()
      nav(`/tasks/${r.taskId}`)
    } catch (e: any) {
      if (e.status === 402) nav(`/pay?next=/create/${sid}`)
      toast(errMsg(e), true)
    } finally { setBusy(null) }
  }
  const abandon = async () => {
    if (!window.confirm('放弃这个设计？预留的额度会退回，但今天最多放弃 3 个设计。')) return
    setBusy('confirm')
    try {
      await api(`/api/v1/design-sessions/${sid}/abandon`, { body: {} })
      await refresh(); nav('/create')
    } catch (e) { toast(errMsg(e), true) } finally { setBusy(null) }
  }

  return (
    <main>
      {/* 会话条 */}
      <div style={{ background: 'var(--ink)', color: 'var(--paper)', borderBottom: '3px solid var(--ink)' }}>
        <div className="wrap" style={{ padding: '12px var(--gutter)', display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, fontSize: 14 }}>
            <span className="display" style={{ fontSize: 11, fontWeight: 700, letterSpacing: 3, color: 'var(--red)' }}>设计会话</span>
            <span className="chip" style={{ borderColor: 'var(--paper)' }}>{s.material.name}</span>
            <span className="chip mono" style={{ borderColor: 'var(--paper)' }}>H {s.sizeMm} mm</span>
            <span className="chip" style={{ borderColor: 'var(--paper)' }}>{s.purpose}</span>
          </div>
          <TurnMeter used={s.turnsUsed} limit={s.turnsLimit} />
        </div>
      </div>

      <div className="wrap" style={{ display: 'flex', flexWrap: 'wrap', padding: 0, maxWidth: 1440 }}>
        {/* 对话 */}
        <section aria-label="对话" style={{ flex: '1 1 420px', minWidth: 0, borderRight: '3px solid var(--ink)', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 136px)', minHeight: 560 }}>
          <div ref={chatRef} style={{ flex: 1, overflowY: 'auto', padding: '20px clamp(16px, 2.4vw, 28px)', display: 'flex', flexDirection: 'column', gap: 12 }} aria-live="polite">
            {s.messages.map((m, i) => <Bubble key={i} m={m} onPick={(v) => setView(v)} onSuggest={(t) => setText(t)} active={m.version === shown} />)}
            {busy === 'turn' && <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mono" style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 10 }}><span className="loading-stripes" style={{ width: 60, height: 10 }} />正在重绘…</motion.div>}
          </div>
          <div style={{ borderTop: '3px solid var(--ink)', padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {view !== null && view !== s.currentVersion && <div className="mono" style={{ fontSize: 12 }}>将以 v{view} 为基础调整 · <button className="chip" style={{ cursor: 'pointer' }} onClick={() => setView(null)}>改回最新</button></div>}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {[['造型', '表情再开心一点'], ['风格', '换成软软的黏土质感'], ['颜色', '颜色换成暖粉色']].map(([k, v]) => (
                <button key={k} className="chip" style={{ cursor: 'pointer', minHeight: 36 }} disabled={ended || out} onClick={() => setText(v)}>{k}</button>
              ))}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); send(text) }} style={{ display: 'flex', border: '3px solid var(--ink)', background: 'var(--paper-2)' }}>
              <label htmlFor="msg" className="sr-only">输入调整意见</label>
              <input id="msg" value={text} onChange={(e) => setText(e.target.value)} disabled={ended || out || !!busy} maxLength={200}
                placeholder={out ? '10 次调整已用完，选一版转 3D 吧' : ended ? '设计已结束' : '说说想怎么改…'}
                style={{ flex: 1, minWidth: 0, minHeight: 56, border: 0, padding: '0 16px', fontSize: 16, background: 'transparent', fontFamily: 'inherit' }} />
              <button className="btn btn-ink" disabled={ended || out || !!busy || !text.trim()} style={{ minHeight: 56, border: 0, borderLeft: '3px solid var(--ink)', fontSize: 15 }}>
                发送 · 第 {Math.min(s.turnsUsed + 1, s.turnsLimit)}/{s.turnsLimit} 次
              </button>
            </form>
          </div>
        </section>

        {/* 效果图舞台 */}
        <section aria-label="效果图" style={{ flex: '999 1 560px', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ position: 'relative', flex: 1, minHeight: 440, overflow: 'hidden', background: 'radial-gradient(ellipse at 50% 42%, #FBF7EE, #DCD2BF)' }}>
            <AnimatePresence mode="popLayout">
              <motion.img key={concept.version} src={concept.imageUrl} alt={`效果图 v${concept.version}：${concept.summary}`}
                initial={{ clipPath: 'polygon(0 0, 0 0, 0 100%, 0 100%)', scale: 1.06 }}
                animate={{ clipPath: 'polygon(0 0, 100% 0, 100% 100%, 0 100%)', scale: 1 }}
                exit={{ opacity: 0 }} transition={{ duration: 0.8, ease: [0.7, 0, 0.2, 1] }}
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }} />
            </AnimatePresence>
            <div style={{ position: 'absolute', left: 20, top: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span className="display" style={{ fontSize: 11, fontWeight: 700, letterSpacing: 3 }}>AI 效果图</span>
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                <motion.span key={concept.version} initial={{ y: -30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="display" style={{ fontSize: 60, fontWeight: 900, lineHeight: 1, color: 'var(--red)' }}>v{concept.version}</motion.span>
                <span style={{ fontWeight: 700 }}>{concept.summary}</span>
              </span>
            </div>
            <div style={{ position: 'absolute', right: 20, top: 18, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
              <span className="mono" style={{ fontSize: 12, fontWeight: 700, background: 'var(--ink)', color: 'var(--paper)', padding: '6px 10px' }}>
                图像完整性 {concept.qc?.imageIntegrity ? '✓' : '待验证'} · 结构规则 {concept.qc?.integratedBase ? '已要求一体底座' : '需调整'}
              </span>
              <span className="mono" style={{ fontSize: 12, fontWeight: 700, border: '2px solid var(--ink)', padding: '4px 10px', background: 'var(--paper)' }}>{concept.qc?.passed ? '可尝试转 3D，造型与悬空仍需人工确认' : '需调整后再转'}</span>
            </div>
          </div>
          <div style={{ borderTop: '3px solid var(--ink)', padding: '14px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 700 }}><span>版本 · 点任一版回看，可直接确认或以它为基础继续改</span><span className="mono">v0 + {s.turnsLimit} 次调整</span></div>
            <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
              {Array.from({ length: s.turnsLimit + 1 }, (_, v) => {
                const c = s.concepts.find((x) => x.version === v)
                return c ? (
                  <motion.button key={v} layout onClick={() => setView(v)} aria-label={`查看 v${v}`} aria-pressed={shown === v}
                    initial={{ scale: 0, rotate: -20 }} animate={{ scale: 1, rotate: 0 }}
                    style={{ flex: '0 0 auto', width: 78, height: 78, padding: 0, position: 'relative', cursor: 'pointer', background: '#EFE7D7',
                      border: shown === v ? '4px solid var(--red)' : '2px solid var(--ink)' }}>
                    <img src={c.imageUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    <span className="mono" style={{ position: 'absolute', left: 3, top: 1, fontSize: 10, fontWeight: 700, color: shown === v ? 'var(--red)' : 'var(--ink)' }}>v{v}</span>
                  </motion.button>
                ) : (
                  <span key={v} className="mono" style={{ flex: '0 0 auto', width: 78, height: 78, border: '2px dashed #8A8075', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: 'var(--muted)' }}>v{v}</span>
                )
              })}
            </div>
          </div>
          <div style={{ borderTop: '3px solid var(--ink)', padding: '16px 20px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
            {s.taskId && s.taskState !== 'FAILED_REFUND' ? (
              <Link to={`/tasks/${s.taskId}`} className="btn btn-ink btn-lg" style={{ flex: '1 1 320px' }}>查看 3D 生成进度 →</Link>
            ) : (
              <button className="btn btn-red btn-lg" style={{ flex: '1 1 320px', justifyContent: 'space-between' }} disabled={!!busy || s.state === 'abandoned' || s.state === 'expired' || !concept.qc?.passed} onClick={confirm}>
                <span>{busy === 'confirm' ? '提交中…' : `确认 v${concept.version}，转成 3D →`}</span>
                <span style={{ fontSize: 12, textAlign: 'right', lineHeight: 1.5 }}>修复 · 预检 · 切片<br />合格才扣已预留的 1 次</span>
              </button>
            )}
            <div style={{ flex: '0 1 300px', fontSize: 12, lineHeight: 1.7, color: 'var(--muted)' }}>
              硬性要素：{s.checklist.map((c) => `${c.label} ${c.value}`).join(' · ')}。3D 与确认的效果图主体明显不符，可在交付后 24 小时内申诉。
              {!ended && <> <button onClick={abandon} style={{ border: 0, background: 'none', textDecoration: 'underline', cursor: 'pointer', color: 'var(--ink)', fontSize: 12, padding: 0 }}>放弃这个设计</button></>}
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}

function TurnMeter({ used, limit }: { used: number; limit: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14 }} aria-label={`剩余调整 ${limit - used} 次，共 ${limit} 次`}>
      <span style={{ fontSize: 13, fontWeight: 700 }}>剩余调整</span>
      <div aria-hidden style={{ display: 'flex', gap: 4 }}>
        {Array.from({ length: limit }, (_, i) => (
          <motion.span key={i} initial={false} animate={{ backgroundColor: i < used ? '#D52B1E' : 'rgba(0,0,0,0)', scale: i === used - 1 ? [1, 1.5, 1] : 1 }}
            transition={{ duration: 0.45 }} style={{ width: 18, height: 22, border: '2px solid var(--paper)', display: 'block' }} />
        ))}
      </div>
      <motion.span key={used} initial={{ y: -16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="display" style={{ fontSize: 28, fontWeight: 900, lineHeight: 1 }}>
        {limit - used}<span style={{ fontSize: 14, color: 'var(--rule-2)' }}>/{limit}</span>
      </motion.span>
    </div>
  )
}

function Bubble({ m, onPick, onSuggest, active }: { m: Msg; onPick: (v: number) => void; onSuggest: (t: string) => void; active: boolean }) {
  if (m.role === 'user') {
    return (
      <motion.div initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} style={{ alignSelf: 'flex-end', maxWidth: '84%', background: 'var(--ink)', color: 'var(--paper)', padding: '12px 16px', fontSize: 15, lineHeight: 1.6 }}>
        {m.text}
      </motion.div>
    )
  }
  if (m.role === 'block') {
    return (
      <motion.div initial={{ scale: 0.9, rotate: -2, opacity: 0 }} animate={{ scale: 1, rotate: 0, opacity: 1 }} role="status"
        style={{ alignSelf: 'stretch', background: 'var(--red)', color: 'var(--paper)', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <b>{m.text}</b>
        {m.suggestion && <span style={{ fontSize: 14, lineHeight: 1.6 }}>建议：{m.suggestion} <b>本次未消耗调整次数。</b></span>}
        {m.suggestion && <button className="btn btn-ink btn-sm" style={{ alignSelf: 'flex-start', '--sh': 'var(--paper)' } as any} onClick={() => onSuggest('改成抱在手里，和身体连在一起')}>换个能打印的说法</button>}
      </motion.div>
    )
  }
  if (m.role === 'system') return <div className="mono" style={{ alignSelf: 'center', fontSize: 12, fontWeight: 700, border: '2px solid var(--ink)', padding: '4px 10px' }}>{m.text}</div>
  return (
    <motion.div initial={{ x: -40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} style={{ alignSelf: 'flex-start', maxWidth: '92%', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
      {m.version !== undefined && (
        <button onClick={() => onPick(m.version!)} className="mono" style={{ flex: '0 0 auto', fontSize: 12, fontWeight: 700, padding: '3px 8px', cursor: 'pointer',
          border: '2px solid ' + (active ? 'var(--red)' : 'var(--ink)'), background: active ? 'var(--red)' : 'var(--paper)', color: active ? 'var(--paper)' : 'var(--ink)' }}>v{m.version}</button>
      )}
      <span style={{ fontSize: 14, lineHeight: 1.7 }}>
        {m.dimension && <span className="mono" style={{ display: 'block', fontSize: 11, color: 'var(--red)' }}>{m.dimension} · 第 {m.turn} 次</span>}
        {m.text}
      </span>
    </motion.div>
  )
}
