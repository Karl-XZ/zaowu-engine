import { motion } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, errMsg, uid } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useToast } from '../lib/toast'
import AiCad from './AiCad'

const LABELS: Record<string, string> = { length: '长 L', width: '宽 W', thickness: '厚 T', hole_d: '孔径 ⌀', hole_spacing: '孔中心距', corner_r: '圆角 R',
  diameter: '直径 ⌀', height: '高 H', chamfer: '倒角', wall: '壁厚', lid_clearance: '盖间隙' }

export default function Cad() {
  const [sp] = useSearchParams()
  const [advanced, setAdvanced] = useState(Boolean(sp.get('from')))
  return <main>
    <AiCad />
    <details open={advanced} onToggle={e => setAdvanced(e.currentTarget.open)} style={{ borderTop: '3px solid var(--ink)' }}>
      <summary style={{ padding: '20px var(--gutter)', cursor: 'pointer', fontWeight: 700 }}>高级模式：使用固定模板、手动填写尺寸</summary>
      {advanced && <TemplateCad />}
    </details>
  </main>
}

function TemplateCad() {
  const [sp] = useSearchParams()
  const { user, refresh } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const [templates, setTemplates] = useState<Record<string, any>>({})
  const [text, setText] = useState('')
  const [kind, setKind] = useState('nameplate')
  const [params, setParams] = useState<Record<string, number>>({})
  const [errors, setErrors] = useState<string[]>([])
  const [parent, setParent] = useState<string | null>(sp.get('from'))
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [checked, setChecked] = useState('')
  const validationKey = JSON.stringify([kind, params])
  const idem = useMemo(() => uid(), [params, kind]) // eslint-disable-line

  useEffect(() => {
    api('/api/v1/cad/templates').then((t) => { setTemplates(t); if (!parent) setParams(t.nameplate.params) }).catch(() => {})
    if (parent) api(`/api/v1/models/${parent}`).then((m: any) => { if (m.cad?.mode === 'ai') { setParent(null); setParams({}); toast('这是 AI 生成的作品，请在上方描述新的需求'); return }; if (m.cad) { setKind(m.cad.template); setParams(m.cad.params); setLabel(m.cad.label || '') } }).catch(() => setParent(null))
  }, []) // eslint-disable-line

  useEffect(() => {
    if (!user || !Object.keys(params).length) return
    let alive = true
    const t = setTimeout(() => api('/api/v1/cad/validate', { body: { template: kind, params } }).then((r: any) => {
      if (alive) { setErrors(r.errors); setChecked(validationKey) }
    }).catch((e) => { if (alive) { setErrors([errMsg(e)]); setChecked('') } }), 250)
    return () => { alive = false; clearTimeout(t) }
  }, [params, kind, user])

  const parse = async () => {
    if (!user) return nav('/login?next=/cad')
    if (parsing || busy) return
    setParsing(true)
    try {
      const r = await api('/api/v1/cad/parse', { body: { text } })
      setKind(r.template); setParams(r.params); setErrors(r.errors); setParent(null)
      if (r.missing.length) toast(`没识别到：${r.missing.map((k: string) => LABELS[k]).join('、')}，已用模板默认值，请在参数表确认`)
    } catch (e) { toast(errMsg(e), true) } finally { setParsing(false) }
  }
  const go = async () => {
    if (!user) return nav('/login?next=/cad')
    setBusy(true)
    try {
      const r = await api('/api/v1/cad/generate', { body: { template: kind, params, label, parentModelId: parent, idempotencyKey: idem } })
      await refresh()
      toast(r.free ? '纯参数重建 · 不计次' : '已预留 1 次额度，合格交付后扣除')
      nav(`/tasks/${r.taskId}`)
    } catch (e: any) {
      if (e.status === 402) nav('/pay?next=/cad')
      toast(errMsg(e), true)
    } finally { setBusy(false) }
  }
  const t = templates[kind]

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', maxWidth: 1440, margin: '0 auto' }}>
      <section aria-label="参数" style={{ flex: '1 1 420px', minWidth: 0, borderRight: '3px solid var(--ink)', padding: '28px clamp(16px, 3vw, 40px)', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <span className="display" style={{ fontSize: 12, fontWeight: 700, letterSpacing: 4, color: 'var(--red)' }}>ENGINE B · PRECISE CAD</span>
        <label htmlFor="nl" className="label" style={{ margin: 0 }}>用一句话描述（会自动抽取参数）</label>
        <textarea id="nl" className="textarea" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button className="btn btn-ink btn-sm" disabled={parsing || busy} onClick={parse}>{parsing ? '抽取中…' : '抽取参数'}</button>
          {Object.entries(templates).map(([k, v]: any) => (
            <button key={k} className="chip" style={{ cursor: 'pointer', minHeight: 40, background: kind === k ? 'var(--red)' : 'transparent', color: kind === k ? 'var(--paper)' : 'var(--ink)', borderColor: kind === k ? 'var(--red)' : 'var(--ink)' }}
              onClick={() => { setKind(k); setParams(v.params); setParent(null) }}>{v.name}</button>
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {t && <span className="chip chip-ink">模板：{t.name} {t.version}</span>}
          <span className="chip chip-red mono">本地模板 · 外部 API 调用 0</span>
          {parent && <span className="chip" style={{ background: 'var(--ink)', color: 'var(--paper)' }}>参数重建 · 不计次</span>}
        </div>
        <div className="panel">
          <div className="panel-head"><span>参数表</span><span className="mono">单位 mm</span></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
            {Object.entries(params).map(([k, v], i) => (
              <label key={k} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '10px 14px', borderRight: i % 2 === 0 ? '2px solid var(--ink)' : 0, borderBottom: '2px solid var(--ink)', fontSize: 12, fontWeight: 700 }}>
                {LABELS[k] || k}
                <input type="number" step="0.01" value={v} disabled={busy || parsing} onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })} className="mono"
                  style={{ border: 0, background: 'transparent', fontSize: 24, fontWeight: 700, minHeight: 36, padding: 0, width: '100%' }} />
              </label>
            ))}
          </div>
        </div>
        <label><span className="label">刻字备注（写入文件名与作品名）</span><input className="input" value={label} maxLength={32} onChange={(e) => setLabel(e.target.value)} placeholder="例如：毕业快乐" /></label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }} aria-live="polite">
          {errors.length === 0 ? <div style={{ border: '2px solid var(--ink)', padding: '10px 14px', fontSize: 14, display: 'flex', justifyContent: 'space-between' }}><span>材料规则校验 · 单色树脂</span><b className="mono">{!user ? '登录后校验' : checked !== validationKey ? '等待校验…' : '参数通过 ✓'}</b></div>
            : errors.map((e) => <motion.div key={e} initial={{ x: -20, opacity: 0 }} animate={{ x: 0, opacity: 1 }} style={{ background: 'var(--red)', color: 'var(--paper)', padding: '10px 14px', fontSize: 14 }}>{e}</motion.div>)}
        </div>
        <p style={{ margin: 0, fontSize: 12 }}>尺寸以输入参数为准；工程图为示意图。生成 STL/3MF 网格，当前不提供 STEP；打印精度和适配间隙需由生产商确认。</p>
        <button className="btn btn-red btn-lg" disabled={busy || parsing || (Boolean(user) && (errors.length > 0 || checked !== validationKey))} onClick={go} style={{ justifyContent: 'space-between' }}>
          <span>{busy ? '建模中…' : parent ? '重建模型' : '生成并校验'}</span>
          <span style={{ fontSize: 12, textAlign: 'right', lineHeight: 1.4 }}>{parent ? `不计次 · 今日 ${user?.quota.cadRebuilds ?? 0}/${user?.quota.cadRebuildLimit ?? 30}` : '合格交付后\n消耗 1 次额度'}</span>
        </button>
      </section>
      <section aria-label="工程图" style={{ flex: '999 1 600px', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '20px clamp(16px, 3vw, 40px)', borderBottom: '3px solid var(--ink)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 'clamp(28px, 3vw, 46px)', fontWeight: 900 }}>{t?.name || ''} <span className="display" style={{ color: 'var(--red)' }}>{headline(kind, params)}</span></h1>
          <span className="mono" style={{ fontSize: 12, fontWeight: 700 }}>实时工程图 · 随参数重绘</span>
        </div>
        <div className="grid-paper" style={{ flex: 1, overflow: 'auto', padding: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 520 }}>
          <Drawing kind={kind} p={params} />
        </div>
      </section>
    </div>
  )
}

function headline(kind: string, p: Record<string, number>) {
  if (!p) return ''
  if (kind === 'base') return `⌀${p.diameter}×${p.height}`
  if (kind === 'box') return `${p.length}×${p.width}×${p.height}`
  return `${p.length}×${p.width}×${p.thickness}`
}

function Drawing({ kind, p }: { kind: string; p: Record<string, number> }) {
  if (!p || !Object.keys(p).length) return null
  const W = 720, H = 460
  const L = kind === 'base' ? p.diameter : p.length, Wd = kind === 'base' ? p.diameter : p.width
  const s = Math.min(520 / (L || 1), 230 / (Wd || 1))
  const x0 = (W - L * s) / 2, y0 = 80
  const draw = { initial: { pathLength: 0, opacity: 0 }, animate: { pathLength: 1, opacity: 1 }, transition: { duration: 0.9, ease: 'easeInOut' } } as const
  const r = Math.min((p.corner_r || 0) * s, Wd * s / 2)
  const holes: { cx: number; cy: number; r: number }[] = []
  if (kind === 'nameplate') for (const sx of [-1, 1]) holes.push({ cx: W / 2 + sx * (p.hole_spacing / 2) * s, cy: y0 + (Wd * s) / 2, r: (p.hole_d / 2) * s })
  if (kind === 'keychain') holes.push({ cx: x0 + (p.hole_d / 2 + 4) * s, cy: y0 + (Wd * s) / 2, r: (p.hole_d / 2) * s })
  const T = kind === 'base' ? p.height : kind === 'box' ? p.height : p.thickness
  const sideH = Math.max(6, Math.min(80, T * s))
  const key = JSON.stringify(p) + kind
  return (
    <svg key={key} viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 820 }} role="img" aria-label={`工程图 ${headline(kind, p)} 毫米`}>
      <text x={x0} y={30} fontFamily="Unbounded" fontSize="11" fontWeight="700" letterSpacing="3">TOP VIEW · 1:{(1 / s).toFixed(2)}</text>
      {kind === 'base'
        ? <motion.circle cx={W / 2} cy={y0 + (Wd * s) / 2} r={(L * s) / 2} fill="#F1EBDD" stroke="#141210" strokeWidth="4" {...draw} />
        : <motion.rect x={x0} y={y0} width={L * s} height={Wd * s} rx={kind === 'box' ? 4 * s : r} fill="#F1EBDD" stroke="#141210" strokeWidth="4" {...draw} />}
      {kind === 'box' && <motion.rect x={x0 + p.wall * s} y={y0 + p.wall * s} width={(L - 2 * p.wall) * s} height={(Wd - 2 * p.wall) * s} rx={2 * s} fill="none" stroke="#141210" strokeWidth="2" strokeDasharray="6 5" {...draw} />}
      {holes.map((h, i) => (
        <g key={i}>
          <motion.circle cx={h.cx} cy={h.cy} r={h.r} fill="none" stroke="#D52B1E" strokeWidth="4" {...draw} />
          <line x1={h.cx} y1={y0 - 12} x2={h.cx} y2={y0 + Wd * s + 12} stroke="#141210" strokeDasharray="4 4" />
        </g>
      ))}
      <line x1={x0 - 12} y1={y0 + (Wd * s) / 2} x2={x0 + L * s + 12} y2={y0 + (Wd * s) / 2} stroke="#141210" strokeDasharray="4 4" />
      {/* 尺寸线 */}
      <motion.path d={`M${x0} ${y0 - 34} H${x0 + L * s} M${x0} ${y0 - 42} V${y0 - 26} M${x0 + L * s} ${y0 - 42} V${y0 - 26}`} stroke="#141210" strokeWidth="2" {...draw} />
      <text x={W / 2} y={y0 - 40} textAnchor="middle" fontFamily="JetBrains Mono" fontSize="14" fontWeight="700" style={{ paintOrder: 'stroke', stroke: '#F1EBDD', strokeWidth: 8 }}>{L?.toFixed(2)}</text>
      <motion.path d={`M${x0 + L * s + 30} ${y0} V${y0 + Wd * s} M${x0 + L * s + 22} ${y0} H${x0 + L * s + 38} M${x0 + L * s + 22} ${y0 + Wd * s} H${x0 + L * s + 38}`} stroke="#141210" strokeWidth="2" {...draw} />
      <text x={x0 + L * s + 44} y={y0 + (Wd * s) / 2 + 5} fontFamily="JetBrains Mono" fontSize="14" fontWeight="700">{Wd?.toFixed(2)}</text>
      {kind === 'nameplate' && <>
        <path d={`M${holes[0].cx} ${y0 + Wd * s + 30} H${holes[1].cx}`} stroke="#D52B1E" strokeWidth="2" />
        <text x={W / 2} y={y0 + Wd * s + 26} textAnchor="middle" fontFamily="JetBrains Mono" fontSize="14" fontWeight="700" fill="#D52B1E" style={{ paintOrder: 'stroke', stroke: '#F1EBDD', strokeWidth: 8 }}>{p.hole_spacing?.toFixed(2)}</text>
      </>}
      {holes.length > 0 && <text x={holes[0].cx - 10} y={holes[0].cy + holes[0].r + 22} fontFamily="JetBrains Mono" fontSize="13" fontWeight="700" fill="#D52B1E">{holes.length}×⌀{p.hole_d}</text>}
      <text x={x0} y={y0 + Wd * s + 74} fontFamily="Unbounded" fontSize="11" fontWeight="700" letterSpacing="3">SIDE VIEW</text>
      <motion.rect x={x0} y={y0 + Wd * s + 90} width={L * s} height={sideH} fill="#141210" initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} style={{ originX: 0 }} transition={{ duration: 0.8 }} />
      <text x={x0 + L * s + 14} y={y0 + Wd * s + 90 + sideH / 2 + 5} fontFamily="JetBrains Mono" fontSize="14" fontWeight="700">{T?.toFixed(2)}</text>
      <rect x={20} y={y0} width={30} height={30} fill="#D52B1E" />
      <rect x={20} y={y0 + 40} width={30} height={100} fill="#141210" />
    </svg>
  )
}

