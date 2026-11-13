import { motion } from 'framer-motion'
import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, errMsg, tokenStore } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useToast } from '../lib/toast'

const ModelViewer = lazy(() => import('../components/ModelViewer'))

type Gen = { id: string; engine: string; state: string; stageLog: { state: string; at: string; note: string }[]; error: string
  modelVersionId: string | null; conceptVersion: number | null; sessionId: string | null; stages: { key: string; label: string }[] }

const ORDER = ['CREATED', 'QUEUED', 'RUNNING', 'PROCESSING_ASSET', 'MANUFACTURING_VALIDATION', 'REPAIRING', 'SLICE_CHECK', 'VERIFIED_DELIVERABLE']

export function TaskPage() {
  const { tid } = useParams()
  const [g, setG] = useState<Gen | null>(null)
  const nav = useNavigate()
  const { refresh } = useAuth()
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const x = await api<Gen>(`/api/v1/generations/${tid}`)
        if (!alive) return
        setG(x)
        if (x.state === 'VERIFIED_DELIVERABLE') { await refresh(); setTimeout(() => nav(`/models/${x.modelVersionId}`, { replace: true }), 1400); return }
        if (x.state === 'FAILED_REFUND') { refresh(); return }
      } catch { /* 网络抖动继续轮询 */ }
      if (alive) setTimeout(tick, 1200)
    }
    tick()
    return () => { alive = false }
  }, [tid]) // eslint-disable-line
  if (!g) return <div className="loading-stripes" style={{ height: 8 }} />
  const idx = ORDER.indexOf(g.state)
  const stageDone = (key: string) => key === 'CONCEPT' || (ORDER.indexOf(key) !== -1 && ORDER.indexOf(key) < idx) || g.state === 'VERIFIED_DELIVERABLE'
  const failed = g.state === 'FAILED_REFUND'
  return (
    <main>
      <Progress g={g} done={stageDone} />
      <section className="wrap" style={{ padding: 'clamp(40px, 6vw, 96px) var(--gutter)', display: 'flex', flexWrap: 'wrap', gap: 48, alignItems: 'center' }}>
        <div style={{ flex: '1 1 420px' }}>
          <span className="display" style={{ fontSize: 12, fontWeight: 700, letterSpacing: 4, color: 'var(--red)' }}>{failed ? 'FAILED · REFUNDED' : g.state}</span>
          <h1 style={{ margin: '12px 0 20px', fontSize: 'clamp(48px, 7vw, 120px)', fontWeight: 900, lineHeight: 0.95 }}>
            {failed ? <>没能交付，<br /><span style={{ color: 'var(--red)' }}>不扣次。</span></> : g.state === 'VERIFIED_DELIVERABLE' ? <>合格，<br /><span style={{ color: 'var(--red)' }}>交付！</span></> : <>正在<br /><span style={{ color: 'var(--red)' }}>成形…</span></>}
          </h1>
          {failed ? (
            <>
              <p style={{ fontSize: 16, lineHeight: 1.8, maxWidth: 520 }}>{g.error}。预留的额度已经退回{g.engine === 'creative' ? '，付费权益已恢复，可以随时申请原路退款' : ''}。</p>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                {g.sessionId && <Link className="btn btn-red" to={`/create/${g.sessionId}`}>回到对话设计</Link>}
                <Link className="btn" to={g.engine === 'cad' ? '/cad' : '/create'}>新的设计</Link>
              </div>
            </>
          ) : (
            <p style={{ fontSize: 16, lineHeight: 1.8, maxWidth: 520 }}>排队、生成、处理文件、修复预检、切片 —— 每一步都是真实进度，不把排队伪装成完成。页面可以离开，回到「我的作品」随时查看。</p>
          )}
        </div>
        <div style={{ flex: '1 1 420px' }}>
          <ol style={{ listStyle: 'none', margin: 0, padding: 0, borderLeft: '3px solid var(--ink)' }}>
            {g.stageLog.map((l, i) => (
              <motion.li key={i} initial={{ x: -30, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ delay: i * 0.05 }}
                style={{ display: 'flex', gap: 14, padding: '10px 16px', position: 'relative' }}>
                <span style={{ position: 'absolute', left: -9, top: 16, width: 14, height: 14, background: l.state === 'FAILED_REFUND' ? 'var(--red)' : i === g.stageLog.length - 1 ? 'var(--red)' : 'var(--ink)' }} />
                <span className="mono" style={{ fontSize: 12, width: 64, flex: '0 0 auto' }}>{new Date(l.at).toLocaleTimeString('zh-CN', { hour12: false })}</span>
                <span><b className="mono" style={{ fontSize: 13 }}>{l.state}</b><br /><span style={{ fontSize: 14 }}>{l.note}</span></span>
              </motion.li>
            ))}
          </ol>
          {!failed && g.state !== 'VERIFIED_DELIVERABLE' && <div className="loading-stripes" style={{ height: 10, marginTop: 16 }} />}
        </div>
      </section>
    </main>
  )
}

function Progress({ g, done }: { g: Gen; done: (k: string) => boolean }) {
  return (
    <ol aria-label="任务进度" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', borderBottom: '3px solid var(--ink)' }}>
      {g.stages.map((s, i) => {
        const last = s.key === 'VERIFIED_DELIVERABLE'
        const ok = done(s.key)
        const cur = !ok && (i === 0 || done(g.stages[i - 1].key)) && g.state !== 'FAILED_REFUND'
        return (
          <li key={s.key} style={{ flex: '1 1 140px', padding: '14px 20px', borderRight: '3px solid var(--ink)', position: 'relative', overflow: 'hidden',
            background: last && ok ? 'var(--red)' : 'transparent', color: last && ok ? 'var(--paper)' : 'var(--ink)' }}>
            {cur && <motion.span aria-hidden className="loading-stripes" style={{ position: 'absolute', left: 0, bottom: 0, height: 5, width: '100%' }} />}
            <span className="mono" style={{ display: 'block', fontSize: 11 }}>{String(i + 1).padStart(2, '0')}{s.key === 'CONCEPT' && g.conceptVersion !== null ? ` · v${g.conceptVersion}` : ''}</span>
            <b>{s.label} {ok ? '✓' : ''}</b>
          </li>
        )
      })}
    </ol>
  )
}

type ModelD = any

export function ModelPage() {
  const { mid } = useParams()
  const [m, setM] = useState<ModelD | null>(null)
  const toast = useToast()
  const nav = useNavigate()
  const [appealOpen, setAppealOpen] = useState(false)
  const [pick, setPick] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const load = () => api(`/api/v1/models/${mid}`).then(setM).catch((e) => toast(errMsg(e), true))
  useEffect(() => {
    load()
    const refresh = () => { if (document.visibilityState === 'visible') load() }
    window.addEventListener('focus', refresh)
    return () => { window.removeEventListener('focus', refresh) }
  }, [mid]) // eslint-disable-line
  if (!m) return <div className="loading-stripes" style={{ height: 8 }} />
  const items = m.report?.check?.items || []
  const sl = m.slice || {}
  const aiCad = m.engine === 'cad' && m.cad?.mode === 'ai'
  const kernel = m.report?.cad
  const download = async (fmt: string) => {
    if ((fmt === 'stl' || fmt === '3mf') && m.appeal.open && !window.confirm('下载正式生产文件后将不能再提交“主要需求未实现”申诉，确定下载？')) return
    if (busy) return
    setBusy(true)
    try {
      const fresh = await api<ModelD>(`/api/v1/models/${m.id}`)
      const response = await fetch(fresh.files[fmt])
      if (!response.ok) throw new Error('文件下载失败，请重试')
      const blob = await response.blob()
      await api(`/api/v1/models/${m.id}/downloaded?fmt=${fmt}`, { body: {} })
      const href = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = href; a.download = `zaowu_${m.id}.${fmt === 'report' ? 'json' : fmt}`; a.click()
      setTimeout(() => URL.revokeObjectURL(href), 30_000)
      load()
    } catch (e) { toast(errMsg(e), true) } finally { setBusy(false) }
  }
  const toJlc = async () => {
    if (busy) return
    setBusy(true)
    try {
      const r = await api(`/api/v1/print/${m.id}/package`, { body: {} })
      const res = await fetch(r.packageUrl, { headers: { Authorization: `Bearer ${tokenStore.get()}` } })
      if (!res.ok) throw new Error('生产文件包下载失败')
      const blob = await res.blob()
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `zaowu_${m.id.slice(0, 8)}.zip`; a.click()
      toast(r.mode === 'A' ? '已获取嘉立创报价' : `生产文件包已下载，正在打开嘉立创。请选择「${r.material}」上传 STL/3MF`)
      setTimeout(() => window.open(r.uploadUrl, '_blank'), 600)
      load()
    } catch (e) { toast(errMsg(e), true) } finally { setBusy(false) }
  }
  const submitAppeal = async () => {
    try {
      const r = await api(`/api/v1/models/${m.id}/appeal`, { body: { items: pick } })
      toast(r.message); setAppealOpen(false); load()
    } catch (e) { toast(errMsg(e), true) }
  }
  return (
    <main>
      <ol aria-label="交付进度" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', borderBottom: '3px solid var(--ink)' }}>
        {(m.engine === 'creative'
          ? [`效果图确认 · v${m.conceptVersion}${m.turns ? ` · 调整 ${m.turns.used}/${m.turns.limit}` : ''}`, '图生 3D', `修复 · ${m.report?.repairs?.length || 0} 处`, '几何预检', sl.estimated ? '切片估算' : '切片检查', '文件交付']
          : [aiCad ? 'AI 需求建模' : '本地模板建模', '内核实测', sl.estimated ? '切片估算' : '切片检查', '文件交付']).map((t, i, arr) => (
          <motion.li key={t} initial={{ y: -40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: i * 0.07 }}
            style={{ flex: '1 1 140px', padding: '14px 20px', borderRight: '3px solid var(--ink)', background: i === arr.length - 1 ? 'var(--red)' : 'transparent', color: i === arr.length - 1 ? 'var(--paper)' : 'var(--ink)' }}>
            <span className="mono" style={{ fontSize: 11 }}>{String(i + 1).padStart(2, '0')}</span><br /><b>{t} {i < arr.length - 1 ? '✓' : ''}</b>
          </motion.li>
        ))}
      </ol>
      <div style={{ display: 'flex', flexWrap: 'wrap', maxWidth: 1440, margin: '0 auto' }}>
        <section aria-label="三维预览" style={{ flex: '999 1 620px', minWidth: 0, position: 'relative', borderRight: '3px solid var(--ink)' }}>
          <div style={{ position: 'absolute', left: 24, top: 20, zIndex: 2, pointerEvents: 'none' }}>
            <h1 style={{ margin: 0, fontSize: 'clamp(32px, 4vw, 60px)', fontWeight: 900, lineHeight: 1 }}>{m.title}</h1>
            <span className="mono" style={{ fontSize: 12, fontWeight: 700 }}>
              {m.engine === 'creative' ? `来自效果图 v${m.conceptVersion} · Lux3D 图生 3D` : aiCad ? '来自你确认的需求' : '本地 CAD 模板'} · {m.material.name} · {m.dimensionMm.map((x: number) => x.toFixed(1)).join(' × ')} mm
            </span>
          </div>
          <motion.div aria-hidden initial={{ scale: 3, rotate: -40, opacity: 0 }} animate={{ scale: 1, rotate: -12, opacity: 1 }} transition={{ type: 'spring', stiffness: 420, damping: 16, delay: 0.5 }}
            style={{ position: 'absolute', right: 28, top: 90, zIndex: 2, border: '5px solid var(--red)', color: 'var(--red)', padding: '10px 18px', background: 'var(--paper)', display: 'flex', flexDirection: 'column', alignItems: 'center', pointerEvents: 'none' }}>
            <span className="display" style={{ fontSize: 22, fontWeight: 900, letterSpacing: 2 }}>VERIFIED</span>
            <span style={{ fontSize: 14, fontWeight: 900, letterSpacing: 6 }}>几何预检通过</span>
          </motion.div>
          {m.conceptUrl && (
            <figure style={{ position: 'absolute', right: 24, bottom: 84, zIndex: 2, margin: 0, width: 150, border: '3px solid var(--ink)', background: 'var(--paper)' }}>
              <img src={m.conceptUrl} alt={`确认的效果图 v${m.conceptVersion}`} style={{ width: '100%', aspectRatio: '1', objectFit: 'cover' }} />
              <figcaption className="mono" style={{ fontSize: 11, fontWeight: 700, padding: '4px 6px' }}>对照 · 效果图 v{m.conceptVersion}</figcaption>
            </figure>
          )}
          <Suspense fallback={<div className="loading-stripes" style={{ height: 8 }} />}><ModelViewer url={m.files.glb} height="calc(100vh - 140px)" /></Suspense>
        </section>
        <aside style={{ flex: '1 1 400px', minWidth: 0 }}>
          <div className="panel-head" style={{ padding: '18px 24px' }}><h2 style={{ margin: 0, fontSize: 20 }}>制造预检报告</h2><span className="mono" style={{ fontSize: 11 }}>{m.materialProfileVersion}</span></div>
          <p style={{ padding: '0 24px', fontSize: 13 }}>几何预检不保证可制造性，请由生产商复核。{sl.estimated ? '当前未运行真实切片器，支撑、耗材和工时为几何估算。' : ''}{m.report?.preview === 'source_materials' ? '预览保留原始材质外观，STL/3MF 使用处理后的网格。' : ''}{m.engine === 'cad' ? m.files.step ? '提供 STEP 实体文件及打印网格。' : '此版本提供网格文件。' : ''}</p>
          {aiCad && <section aria-label="已确认的设计需求" style={{ padding: '8px 24px 20px', borderBottom: '3px solid var(--ink)' }}>
            <h3 style={{ fontSize: 18 }}>这件作品的设计需求</h3>
            <p style={{ lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>{m.cad.summary}</p>
            {m.cad.requirements?.length > 0 && <ul>{m.cad.requirements.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>}
            {m.cad.assumptions?.length > 0 && <><b>确认的建议做法</b><ul>{m.cad.assumptions.map((a: string, i: number) => <li key={i}>{a}</li>)}</ul></>}
            <details><summary style={{ cursor: 'pointer', fontWeight: 700 }}>查看需求来源</summary><p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{m.cad.sourceText}</p>{m.cad.planId && <p style={{ fontSize: 12, overflowWrap: 'anywhere' }}>方案编号：{m.cad.planId}</p>}</details>
            {kernel && <><h3 style={{ fontSize: 16 }}>实体检查结果</h3><ul className="row-list">
              <li><span>检查工具</span><b>{kernel.kernel}</b></li>
              <li><span>实体有效性</span><b>{kernel.valid ? '通过' : '未通过'}</b></li>
              <li><span>独立部件</span><b>{kernel.solidCount} 个</b></li>
              <li><span>体积</span><b>{Number(kernel.volumeMm3).toFixed(1)} mm³</b></li>
              <li><span>实际大小</span><b>{kernel.dimensionMm?.map((n: number) => n.toFixed(1)).join(' × ')} mm</b></li>
            </ul></>}
          </section>}
          <ul className="row-list" style={{ padding: '0 24px' }}>
            {items.map((i: any, k: number) => (
              <motion.li key={i.key} initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ delay: 0.3 + k * 0.06 }}>
                <span>{i.label}</span><b style={{ color: i.ok ? 'var(--ink)' : 'var(--red)' }}>{i.value} {i.ok ? '✓' : '✗'}</b>
              </motion.li>
            ))}
            <li><span>切片 · {sl.estimated ? '几何估算' : sl.slicer}</span><b>{sl.supportVolumeCm3 ?? '-'} cm³ · {sl.printTimeMin ? `${Math.floor(sl.printTimeMin / 60)}h${sl.printTimeMin % 60}m` : '-'}</b></li>
            <li><span>首层接触面积</span><b>{sl.firstLayerAreaMm2 ?? '-'} mm²</b></li>
            <li><span>预计耗材</span><b>{sl.materialG ?? '-'} g</b></li>
            {m.report?.repairs?.length > 0 && <li style={{ flexDirection: 'column' }}><span style={{ display: 'flex', justifyContent: 'space-between' }}><span>自动修复</span><b style={{ color: 'var(--red)' }}>{m.report.repairs.length} 处 · 免费</b></span><span style={{ fontSize: 12, color: 'var(--muted)' }}>{m.report.repairs.join('；')}</span></li>}
          </ul>
          <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 10, borderBottom: '3px solid var(--ink)' }}>
            <span style={{ fontSize: 13, fontWeight: 700 }}>下载（同一版本永久免费）</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 8 }}>
              {[['step', 'STEP · 实体'], ['stl', 'STL · 打印'], ['3mf', '3MF'], ['glb', 'GLB · 预览'], ['report', '检测报告']].filter(([k]) => m.files[k]).map(([k, t]) => (
                <button key={k} disabled={busy} className="btn btn-sm mono" style={{ minHeight: 48, borderWidth: 3 }} onClick={() => download(k)}>{t}</button>
              ))}
            </div>
            <span className="mono" style={{ fontSize: 11, color: 'var(--muted)', wordBreak: 'break-all' }}>SHA-256 {m.fileHash.slice(0, 10)}…{m.fileHash.slice(-6)} · 已锁定</span>
          </div>
          <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <button disabled={busy} className="btn btn-red" style={{ flexDirection: 'column', alignItems: 'flex-start', padding: '16px 20px', minHeight: 0 }} onClick={toJlc}>
              <span style={{ fontSize: 22 }}>导出并前往嘉立创下单 →</span>
              <span style={{ fontSize: 12, fontWeight: 500 }}>制造费、工期与运费以嘉立创实际报价为准</span>
            </button>
            {m.appeal.claim ? (
              <span className="chip">申诉：{({ platform: '平台责任，已恢复额度', user: '不属平台责任', pending: '人工复核中' } as any)[m.appeal.claim.decision]}</span>
            ) : m.appeal.open ? (
              <button onClick={() => setAppealOpen(!appealOpen)} style={{ alignSelf: 'flex-start', border: 0, background: 'none', textDecoration: 'underline', fontWeight: 700, cursor: 'pointer', padding: 0, fontSize: 14 }}>主要需求没实现？{m.appeal.windowHours} 小时内申诉</button>
            ) : null}
            {appealOpen && (
              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} className="panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <b style={{ fontSize: 14 }}>哪一项没有实现？（只受理硬性要素清单与“与效果图明显不符”）</b>
                {[...m.checklist, ...(m.engine === 'creative' ? [{ key: 'concept_mismatch', label: '与效果图', value: '主体明显不符' }] : [])].map((c: any) => (
                  <label key={c.key} style={{ display: 'flex', gap: 8, fontSize: 14, alignItems: 'center' }}>
                    <input type="checkbox" checked={pick.includes(c.key)} onChange={(e) => setPick(e.target.checked ? [...pick, c.key] : pick.filter((x) => x !== c.key))} style={{ width: 20, height: 20, accentColor: '#D52B1E' }} />
                    {c.label}：{c.value}
                  </label>
                ))}
                <button className="btn btn-ink btn-sm" disabled={!pick.length} onClick={submitAppeal}>提交申诉</button>
              </motion.div>
            )}
            {aiCad && <Link className="btn btn-sm" to="/cad">描述新的设计需求</Link>}
            {m.turns && <Link to={`/create/${m.turns.sessionId}`} style={{ fontWeight: 700, fontSize: 14 }}>回到对话设计（剩余 {m.turns.limit - m.turns.used}/{m.turns.limit}）</Link>}
            {m.engine === 'cad' && !aiCad && <button className="btn btn-sm" onClick={() => nav(`/cad?from=${m.id}`)}>调整参数重建（不计次）</button>}
          </div>
        </aside>
      </div>
    </main>
  )
}

