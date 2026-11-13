import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errMsg, uid } from '../lib/api'
import { useAuth } from '../lib/auth'

type Plan = {
  planId: string; ready: boolean; summary: string; questions: string[]; assumptions: string[]
  requirements: string[]; dimensionsMm: number[]; expectedBodies: number
}

export default function AiCad() {
  const { user, refresh } = useAuth()
  const nav = useNavigate()
  const [text, setText] = useState('')
  const [plan, setPlan] = useState<Plan | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState<'plan' | 'generate' | null>(null)
  const [error, setError] = useState('')
  const idempotencyKey = useRef(uid())
  const pending = useRef(false)

  const understand = async () => {
    if (!user) return nav('/login?next=/cad')
    if (pending.current || !text.trim() || text.length > 2000) return
    pending.current = true
    setBusy('plan'); setError(''); setConfirmed(false)
    try {
      const next = await api<Plan>('/api/v1/cad/ai/plan', { body: { text: text.trim(), ...(plan ? { previousPlanId: plan.planId } : {}) } })
      setPlan(next); setText(''); idempotencyKey.current = uid()
    } catch (e) { setError(errMsg(e)) } finally { pending.current = false; setBusy(null) }
  }
  const generate = async () => {
    if (pending.current || !plan?.ready || !confirmed || text.trim()) return
    pending.current = true
    setBusy('generate'); setError('')
    try {
      const r = await api<{ taskId: string }>('/api/v1/cad/ai/generate', { body: { planId: plan.planId, idempotencyKey: idempotencyKey.current, confirmAssumptions: true } })
      await refresh()
      nav(`/tasks/${r.taskId}`)
    } catch (e: any) {
      setError(errMsg(e))
      if (e.status === 402) nav('/pay?next=/cad')
    } finally { pending.current = false; setBusy(null) }
  }

  return <section className="wrap" aria-label="描述你想做的物品" style={{ padding: '40px var(--gutter)', maxWidth: 1000 }}>
    <span className="display" style={{ color: 'var(--red)', fontSize: 12, fontWeight: 700, letterSpacing: 3 }}>AI CAD · 从想法到实物</span>
    <h1 style={{ fontSize: 'clamp(32px, 5vw, 64px)', margin: '16px 0' }}>说说你想做什么</h1>
    <p style={{ lineHeight: 1.8 }}>用平常的话描述用途、样子和大小。不确定的地方可以先不填，我们会先整理需求、问清细节，再由你确认建模。</p>
    {plan && <div className="panel" style={{ margin: '24px 0', padding: 24 }} aria-live="polite">
      <h2 style={{ marginTop: 0, fontSize: 24 }}>我理解的需求</h2>
      <p style={{ lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>{plan.summary}</p>
      {plan.requirements.length > 0 && <><h3 style={{ fontSize: 16 }}>需要做到</h3><ul>{plan.requirements.map((r, i) => <li key={i} style={{ margin: '8px 0' }}>{r}</li>)}</ul></>}
      {plan.assumptions.length > 0 && <><h3 style={{ fontSize: 16 }}>还没说明的地方，建议这样做</h3><ul>{plan.assumptions.map((a, i) => <li key={i} style={{ margin: '8px 0' }}>{a}</li>)}</ul></>}
      {plan.dimensionsMm.length > 0 && <p>预计整体大小：{plan.dimensionsMm.map(n => `${n} 毫米`).join(' × ')}；{plan.expectedBodies} 个独立部件。</p>}
      {!plan.ready && <div style={{ borderTop: '2px solid var(--ink)', paddingTop: 16 }}><b>还需要你补充</b><ul>{plan.questions.map((q, i) => <li key={i} style={{ margin: '8px 0' }}>{q}</li>)}</ul><p>在下面直接回答就好，暂时不会开始生成。</p></div>}
    </div>}
    <label htmlFor="cad-description" className="label">{plan ? '补充回答，或说说想改哪里' : '你想做一个什么样的东西？'}</label>
    <textarea id="cad-description" className="textarea" rows={5} maxLength={2000} value={text} disabled={Boolean(busy)} onChange={e => { setText(e.target.value); setConfirmed(false) }} placeholder={plan ? '例如：改成双层，放在桌面上用' : '例如：做一个放在书桌上的双层收纳架，上面放手机，下面放眼镜，大小和一本书差不多。'} />
    <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap', margin: '12px 0 24px' }}>
      <button className="btn btn-ink" disabled={Boolean(busy) || !text.trim()} onClick={understand}>{busy === 'plan' ? '正在理解…' : '理解需求'}</button>
      <span style={{ fontSize: 12 }}>{text.length}/2000 字</span>
      {plan && <button className="btn btn-sm" disabled={Boolean(busy)} onClick={() => { setPlan(null); setText(''); setConfirmed(false); setError('') }}>重新描述一个物品</button>}
    </div>
    {plan?.ready && <div style={{ borderTop: '3px solid var(--ink)', paddingTop: 24 }}>
      <label style={{ display: 'flex', gap: 10, lineHeight: 1.8, alignItems: 'flex-start' }}><input type="checkbox" checked={confirmed} disabled={Boolean(busy) || Boolean(text.trim())} onChange={e => setConfirmed(e.target.checked)} style={{ width: 22, height: 22, accentColor: 'var(--red)' }} />我已确认上面的需求、大小和建议做法，可以开始建模。</label>
      {text.trim() && <p>你有新的补充，请先点「理解需求」更新方案，再确认生成。</p>}
      <button className="btn btn-red btn-lg" style={{ marginTop: 16 }} disabled={Boolean(busy) || !confirmed || Boolean(text.trim())} onClick={generate}>{busy === 'generate' ? '正在提交…' : '确认并生成模型 →'}</button>
      <p style={{ fontSize: 13, lineHeight: 1.8 }}>生成后会检查模型并尝试修复，结果以实际检查为准；复杂或暂不支持的要求可能无法交付。生产前仍需由制造商复核。</p>
    </div>}
    {error && <p role="alert" style={{ color: 'var(--red)', whiteSpace: 'pre-wrap' }}>{error}</p>}
  </section>
}
