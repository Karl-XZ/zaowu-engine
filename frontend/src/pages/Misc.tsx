import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { SplitReveal } from '../components/Motion'
import { api, errMsg, fen } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useToast } from '../lib/toast'

/* ---------------- 登录 / 注册 ---------------- */
export function Login() {
  const { login, register } = useAuth()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const toast = useToast()
  const [mode, setMode] = useState<'login' | 'register'>('register')
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [nick, setNick] = useState('')
  const [agree, setAgree] = useState(false)
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      if (mode === 'login') await login(email, pw)
      else await register(email, pw, nick)
      toast(mode === 'login' ? '欢迎回来' : '注册成功，今日 3 次免费额度已到账')
      nav(sp.get('next') || '/create')
    } catch (err) { toast(errMsg(err), true) } finally { setBusy(false) }
  }
  return (
    <main style={{ minHeight: 'calc(100vh - 72px)', display: 'flex', flexWrap: 'wrap', overflow: 'hidden' }}>
      <section style={{ flex: '1 1 480px', background: 'var(--red)', color: 'var(--paper)', position: 'relative', overflow: 'hidden', padding: 'clamp(40px,6vw,96px) var(--gutter)', minHeight: 420 }}>
        <motion.div aria-hidden initial={{ rotate: -40, x: -200 }} animate={{ rotate: -28, x: 0 }} transition={{ duration: 1.1, ease: [0.2, 0.8, 0.2, 1] }}
          style={{ position: 'absolute', left: '-20%', top: '62%', width: '150%', height: 46, background: 'var(--ink)' }} />
        <motion.div aria-hidden initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 120, damping: 14, delay: 0.2 }}
          style={{ position: 'absolute', right: '10%', top: '18%', width: 220, height: 220, borderRadius: '50%', border: '30px solid var(--paper)' }} />
        <h1 style={{ position: 'relative', margin: 0, fontSize: 'clamp(56px, 8vw, 132px)', fontWeight: 900, lineHeight: 0.95 }}>
          <SplitReveal text="每天" /><SplitReveal text="3 个" delay={0.2} /><SplitReveal text="免费。" delay={0.4} />
        </h1>
        <p style={{ position: 'relative', fontSize: 17, lineHeight: 1.8, maxWidth: 380, marginTop: 24 }}>注册即领今日额度。合格交付才计次，失败不扣、放弃退回。</p>
      </section>
      <section style={{ flex: '1 1 420px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
        <form onSubmit={submit} className="panel" style={{ width: '100%', maxWidth: 440, boxShadow: '14px 14px 0 var(--ink)' }}>
          <div role="tablist" style={{ display: 'flex' }}>
            {(['register', 'login'] as const).map((m) => (
              <button type="button" role="tab" aria-selected={mode === m} key={m} onClick={() => setMode(m)}
                style={{ flex: 1, minHeight: 56, border: 0, borderBottom: '3px solid var(--ink)', fontWeight: 900, fontSize: 17, cursor: 'pointer',
                  background: mode === m ? 'var(--ink)' : 'transparent', color: mode === m ? 'var(--paper)' : 'var(--ink)' }}>{m === 'register' ? '注册' : '登录'}</button>
            ))}
          </div>
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <label><span className="label">邮箱</span><input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            {mode === 'register' && <label><span className="label">昵称（可选）</span><input className="input" value={nick} maxLength={32} onChange={(e) => setNick(e.target.value)} /></label>}
            <label><span className="label">密码（至少 6 位）</span><input className="input" type="password" required minLength={6} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={pw} onChange={(e) => setPw(e.target.value)} /></label>
            {mode === 'register' && (
              <label style={{ display: 'flex', gap: 10, fontSize: 13, lineHeight: 1.6, alignItems: 'flex-start' }}>
                <input type="checkbox" required checked={agree} onChange={(e) => setAgree(e.target.checked)} style={{ width: 20, height: 20, accentColor: '#D52B1E', flex: '0 0 auto' }} />
                <span>我已阅读 <Link to="/rules#privacy">隐私与照片授权说明</Link> 与 <Link to="/rules">计次与退款规则</Link>。上传的照片默认私有，仅用于本次生成。</span>
              </label>
            )}
            <button className="btn btn-red btn-lg" disabled={busy}>{busy ? '请稍候…' : mode === 'register' ? '注册并领取额度' : '登录'}</button>
          </div>
        </form>
      </section>
    </main>
  )
}

/* ---------------- 付费 ---------------- */
export function Pay() {
  const { user, ready, refresh } = useAuth()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const toast = useToast()
  const [order, setOrder] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (ready && !user) nav('/login?next=/pay') }, [user, ready]) // eslint-disable-line
  useEffect(() => {
    if (!order || order.state !== 'WAITING_PAY') return
    const t = setInterval(async () => {
      const o = await api(`/api/v1/pay/orders/${order.id}`).catch(() => null)
      if (o && o.state !== 'WAITING_PAY') { setOrder(o); await refresh(); toast('支付成功，已到账 1 次付费生成'); clearInterval(t) }
    }, 2000)
    return () => clearInterval(t)
  }, [order]) // eslint-disable-line
  if (!user) return null
  const q = user.quota
  const create = async () => {
    setBusy(true)
    try {
      const o = await api('/api/v1/pay/orders', { body: {} })
      setOrder(o)
      if (o.mock) nav(`/pay/mock?trade=${o.outTradeNo}&oid=${o.id}&next=${encodeURIComponent(sp.get('next') || '/create')}`)
      else window.location.href = o.payUrl
    } catch (e) { toast(errMsg(e), true) } finally { setBusy(false) }
  }
  const refundUnused = async () => {
    if (!window.confirm('对所有未使用的付费次数申请原路退款？')) return
    const r = await api('/api/v1/pay/refund-unused', { body: {} }).catch((e) => toast(errMsg(e), true))
    if (r) { toast(`已退款 ${r.refunded} 笔`); refresh() }
  }
  return (
    <main style={{ position: 'relative', overflow: 'hidden', minHeight: 'calc(100vh - 72px)' }}>
      <motion.div aria-hidden initial={{ scale: 0.4, x: -200 }} animate={{ scale: 1, x: 0 }} transition={{ type: 'spring', stiffness: 70, damping: 16 }}
        style={{ position: 'absolute', left: -200, top: 60, width: 780, height: 780, borderRadius: '50%', background: 'var(--red)' }} />
      <motion.div aria-hidden initial={{ x: '-100%' }} animate={{ x: 0 }} transition={{ duration: 1, delay: 0.3, ease: [0.7, 0, 0.2, 1] }}
        style={{ position: 'absolute', left: '-10%', bottom: 40, width: '70%', height: 40, background: 'var(--ink)', rotate: -14 }} />
      <div className="wrap" style={{ position: 'relative', padding: 'clamp(40px, 6vw, 80px) var(--gutter)', display: 'flex', flexWrap: 'wrap', gap: 40, alignItems: 'center' }}>
        <div style={{ flex: '1 1 460px', color: 'var(--paper)', paddingLeft: 'clamp(0px, 3vw, 40px)' }}>
          <span className="display" style={{ fontSize: 13, fontWeight: 700, letterSpacing: 4 }}>{q.freeRemaining > 0 ? `今日免费还剩 ${q.freeRemaining} 次` : '今日免费额度已用完'}</span>
          <div className="display" style={{ fontWeight: 900, fontSize: 'clamp(160px, 20vw, 300px)', lineHeight: 0.8, letterSpacing: -8 }}><span style={{ fontSize: '.4em', verticalAlign: 'top' }}>¥</span>5</div>
          <div style={{ fontSize: 'clamp(24px, 2.4vw, 34px)', fontWeight: 900, marginTop: 12 }}>生成下一个合格模型</div>
          <div className="mono" style={{ fontSize: 13, fontWeight: 700, marginTop: 8 }}>或者等到 {new Date(q.resetAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}（北京时间）恢复 3 次免费</div>
        </div>
        <section className="panel" style={{ flex: '1 1 440px', maxWidth: 560, boxShadow: '14px 14px 0 var(--ink)' }}>
          <div className="panel-head" style={{ padding: '18px 24px' }}><h1 style={{ margin: 0, fontSize: 20 }}>购买 1 次生成</h1><span className="mono" style={{ fontSize: 12 }}>{order ? `#${order.outTradeNo}` : ''}</span></div>
          <div style={{ padding: 24, borderBottom: '3px solid var(--ink)', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>当前付费次数</span><b>{q.paidCredits}</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}><span>应付</span><b className="display" style={{ fontSize: 30 }}>{fen(q.priceFen)}</b></div>
          </div>
          <ol style={{ margin: 0, padding: 24, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 14, borderBottom: '3px solid var(--ink)' }}>
            {[['付款后先冻结', '钱不会马上被核销'], ['通过制造预检', '才算交付、才正式扣款'], ['失败自动恢复', '为生成权益，随时可申请原路退款']].map(([b, t], i) => (
              <li key={b} style={{ display: 'flex', gap: 14, alignItems: 'center', fontSize: 14 }}>
                <span className="display" style={{ flex: '0 0 32px', height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, background: i === 0 ? 'var(--red)' : i === 1 ? 'var(--ink)' : 'transparent', color: i < 2 ? 'var(--paper)' : 'var(--ink)', border: '3px solid ' + (i === 0 ? 'var(--red)' : 'var(--ink)') }}>{i + 1}</span>
                <span><b>{b}</b>，{t}</span>
              </li>
            ))}
          </ol>
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <button className="btn btn-red btn-lg" disabled={busy} onClick={create}>支付宝付款 {fen(q.priceFen)}</button>
            {q.paidCredits > 0 && <button className="btn btn-sm" onClick={refundUnused}>未使用的付费次数原路退款</button>}
            <Link to={sp.get('next') || '/create'} style={{ textAlign: 'center', fontWeight: 700, fontSize: 14 }}>先不付，返回</Link>
            <p style={{ margin: 0, fontSize: 12, lineHeight: 1.6, color: 'var(--muted)' }}>单纯不喜欢外观不退款；硬性要素未实现或 3D 与确认的效果图明显不符，可在交付后 24 小时内申诉。<Link to="/rules">完整规则</Link></p>
          </div>
        </section>
      </div>
    </main>
  )
}

/** 模拟收银台（未配置支付宝密钥时使用，走与真实通知相同的入账逻辑） */
export function PayMock() {
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const toast = useToast()
  const { refresh } = useAuth()
  const [busy, setBusy] = useState(false)
  const pay = async () => {
    setBusy(true)
    try {
      await api('/api/v1/pay/mock/confirm', { body: { outTradeNo: sp.get('trade') } })
      await refresh()
      toast('支付成功（模拟），已到账 1 次付费生成')
      nav(sp.get('next') || '/create')
    } catch (e) { toast(errMsg(e), true) } finally { setBusy(false) }
  }
  return (
    <main className="wrap" style={{ padding: '80px var(--gutter)', display: 'flex', justifyContent: 'center' }}>
      <div className="panel" style={{ maxWidth: 460, width: '100%', boxShadow: '14px 14px 0 var(--red)' }}>
        <div className="panel-head" style={{ padding: '16px 20px' }}><b>模拟收银台</b><span className="mono" style={{ fontSize: 11 }}>ALIPAY MOCK</span></div>
        <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.7 }}>当前未配置支付宝密钥，系统处于模拟支付模式。填写 <code>.env</code> 中的 <code>ALIPAY_*</code> 后将跳转真实收银台。</p>
          <div className="mono" style={{ fontSize: 13 }}>订单号 {sp.get('trade')}</div>
          <div className="display" style={{ fontSize: 56, fontWeight: 900 }}>¥5.00</div>
          <button className="btn btn-red btn-lg" disabled={busy} onClick={pay}>确认支付（模拟）</button>
          <Link to="/pay" style={{ textAlign: 'center', fontSize: 14, fontWeight: 700 }}>取消</Link>
        </div>
      </div>
    </main>
  )
}

/* ---------------- 我的作品 ---------------- */
export function Me() {
  const { user, ready } = useAuth()
  const nav = useNavigate()
  const [data, setData] = useState<any>(null)
  const [sessions, setSessions] = useState<any[]>([])
  useEffect(() => {
    if (!ready) return
    if (!user) { nav('/login?next=/me'); return }
    api('/api/v1/models').then(setData).catch(() => {})
    api('/api/v1/design-sessions').then(setSessions).catch(() => {})
  }, [user, ready]) // eslint-disable-line
  if (!data) return <div className="loading-stripes" style={{ height: 8 }} />
  const open = sessions.filter((s) => ['concept_ready', 'adjusting'].includes(s.state))
  return (
    <main className="wrap" style={{ padding: 'clamp(32px, 5vw, 72px) var(--gutter)' }}>
      <h1 style={{ margin: '0 0 32px', fontSize: 'clamp(48px, 7vw, 120px)', fontWeight: 900, lineHeight: 0.95 }}>我的<span style={{ color: 'var(--red)' }}>作品</span></h1>
      {open.length > 0 && (
        <section style={{ marginBottom: 40 }}>
          <h2 style={{ fontSize: 22, fontWeight: 900 }}>进行中的设计</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {open.map((s) => <Link key={s.id} to={`/create/${s.id}`} className="btn btn-sm">{s.title} · 已调整 {s.turnsUsed}/10 →</Link>)}
          </div>
        </section>
      )}
      {data.tasks.filter((t: any) => t.state !== 'FAILED_REFUND').length > 0 && (
        <section style={{ marginBottom: 40 }}>
          <h2 style={{ fontSize: 22, fontWeight: 900 }}>生成中</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {data.tasks.filter((t: any) => t.state !== 'FAILED_REFUND').map((t: any) => <Link key={t.id} to={`/tasks/${t.id}`} className="btn btn-sm btn-ink">{t.engine === 'cad' ? 'CAD' : '创意'} · {t.state} →</Link>)}
          </div>
        </section>
      )}
      {data.models.length === 0 ? (
        <div className="panel" style={{ padding: 40, textAlign: 'center' }}>
          <p style={{ fontSize: 18 }}>还没有作品。</p>
          <Link to="/create" className="btn btn-red">做第一个礼物 →</Link>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 24 }}>
          {data.models.map((m: any, i: number) => (
            <motion.div key={m.id} initial={{ y: 40, opacity: 0, rotate: i % 2 ? 2 : -2 }} animate={{ y: 0, opacity: 1, rotate: 0 }} transition={{ delay: i * 0.05 }}>
              <Link to={`/models/${m.id}`} className="panel" style={{ display: 'block', textDecoration: 'none', boxShadow: '8px 8px 0 var(--ink)' }}>
                <div style={{ aspectRatio: '1', background: m.thumb ? '#EFE7D7' : 'var(--ink)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                  {m.thumb ? <img src={m.thumb} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    : <span className="display" style={{ color: 'var(--paper)', fontSize: 40, fontWeight: 900 }}>CAD</span>}
                </div>
                <div style={{ padding: 14, borderTop: '3px solid var(--ink)' }}>
                  <b style={{ display: 'block', fontSize: 16 }}>{m.title}</b>
                  <span className="mono" style={{ fontSize: 11 }}>{m.material} · {m.dimensionMm.map((x: number) => x.toFixed(0)).join('×')} mm · {new Date(m.createdAt).toLocaleDateString('zh-CN')}</span>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </main>
  )
}

/* ---------------- 管理后台 ---------------- */
export function Admin() {
  const [d, setD] = useState<any>(null)
  const toast = useToast()
  useEffect(() => { api('/api/v1/admin/overview').then(setD).catch((e) => toast(errMsg(e), true)) }, []) // eslint-disable-line
  if (!d) return <div className="loading-stripes" style={{ height: 8 }} />
  const tiles = [['用户', d.users], ['设计会话', d.sessions], ['合格交付', d.delivered], ['今日成本', fen(d.costTodayFen)],
    ['今日免费成本', `${fen(d.freeCostTodayFen)} / ${fen(d.platformFreeBudgetFen)}`], ['累计收入', fen(d.revenueFen)],
    ['每件合格交付成本', d.costPerDeliveredFen != null ? fen(d.costPerDeliveredFen) : '-'], ['待复核申诉', d.claimsPending]]
  return (
    <main className="wrap" style={{ padding: '40px var(--gutter)' }}>
      <h1 style={{ margin: '0 0 24px', fontSize: 56, fontWeight: 900 }}>运营<span style={{ color: 'var(--red)' }}>后台</span></h1>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 24 }}>
        {Object.entries(d.mock).map(([k, v]) => <span key={k} className={`chip ${v ? 'chip-red' : 'chip-ink'}`}>{k}：{v ? '模拟模式' : '已接入'}</span>)}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', border: '3px solid var(--ink)' }}>
        {tiles.map(([t, v], i) => (
          <div key={t as string} style={{ padding: 20, borderRight: '3px solid var(--ink)', borderBottom: '3px solid var(--ink)', background: i === 3 ? 'var(--red)' : 'transparent', color: i === 3 ? 'var(--paper)' : 'var(--ink)' }}>
            <div style={{ fontSize: 13, fontWeight: 700 }}>{t}</div>
            <div className="display" style={{ fontSize: 30, fontWeight: 900, marginTop: 6 }}>{v as any}</div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, marginTop: 32 }}>
        <section className="panel" style={{ flex: '1 1 380px' }}>
          <div className="panel-head">任务状态</div>
          <ul className="row-list" style={{ padding: '0 16px' }}>{Object.entries(d.taskStates).map(([k, v]) => <li key={k}><span className="mono">{k}</span><b>{v as any}</b></li>)}</ul>
        </section>
        <section className="panel" style={{ flex: '2 1 520px', overflowX: 'auto' }}>
          <div className="panel-head">供应商成本账本（最近 30 笔）</div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead><tr>{['#', '供应商', '接口', '预估', '实际', '免费档', '结果'].map((h) => <th key={h} style={{ textAlign: 'left', padding: 8, borderBottom: '2px solid var(--ink)' }}>{h}</th>)}</tr></thead>
            <tbody>{d.ledger.map((r: any) => (
              <tr key={r.id}><td style={{ padding: 8 }} className="mono">{r.id}</td><td>{r.provider}</td><td>{r.endpoint}</td><td className="mono">{fen(r.estimated)}</td><td className="mono">{r.actual != null ? fen(r.actual) : '-'}</td><td>{r.free ? '是' : '否'}</td><td>{r.outcome}</td></tr>
            ))}</tbody>
          </table>
        </section>
      </div>
      {d.recentFailures.length > 0 && (
        <section className="panel" style={{ marginTop: 24 }}>
          <div className="panel-head">最近失败（成本仍计入账本）</div>
          <ul className="row-list" style={{ padding: '0 16px' }}>{d.recentFailures.map((f: any) => <li key={f.id}><span>{f.engine} · {f.error}</span><b>{fen(f.cost)}</b></li>)}</ul>
        </section>
      )}
    </main>
  )
}

/* ---------------- 规则 ---------------- */
export function Rules() {
  const S = ({ id, t, children }: any) => (
    <section id={id} style={{ borderTop: '3px solid var(--ink)', padding: '32px 0', display: 'flex', flexWrap: 'wrap', gap: 24 }}>
      <h2 style={{ flex: '0 0 280px', margin: 0, fontSize: 32, fontWeight: 900 }}>{t}</h2>
      <div style={{ flex: '1 1 420px', fontSize: 15, lineHeight: 1.9 }}>{children}</div>
    </section>
  )
  return (
    <main className="wrap" style={{ padding: 'clamp(32px, 5vw, 72px) var(--gutter)' }}>
      <h1 style={{ margin: '0 0 40px', fontSize: 'clamp(48px, 7vw, 110px)', fontWeight: 900, lineHeight: 0.95 }}>规则，<span style={{ color: 'var(--red)' }}>写清楚。</span></h1>
      <S t="计次"><ul>
        <li>每个账户每天 3 次免费合格模型，创意与 CAD 共用，北京时间 00:00 重置；之后每个 ¥5。</li>
        <li>一次创意设计 = 首张效果图 + 最多 10 次对话调整 + 1 次转 3D，合格交付后只计 1 次。</li>
        <li>被预检拦下的修改、平台为可打印性发起的修正、平台缺陷的修复重试，都不计次。</li>
        <li>高级模板模式下，同一模板的纯参数调整不计次（每天最多 30 次重建）；AI CAD 按新生成任务计次。</li>
        <li>为防止滥用：每天未交付的生成尝试最多 5 次、放弃的设计最多 3 个。</li>
      </ul></S>
      <S id="refund" t="退款与申诉"><ul>
        <li>付费后先冻结；未通过制造预检自动恢复为付费次数，可随时申请原路退款。</li>
        <li>交付后 24 小时内、且未下载正式生产文件前，可就硬性要素清单或“与确认的效果图明显不符”申诉。</li>
        <li>单纯不喜欢外观（风格、表情、颜色偏好等清单外的意见）不属于平台责任。</li>
        <li>交付后 30 天内，若嘉立创因平台文件缺陷拒收（文件哈希、材料、尺寸未变），平台免费修复，仍失败则恢复额度或退款。</li>
        <li>制造费、加工质量与物流由嘉立创按其订单条款处理。</li>
      </ul></S>
      <S id="privacy" t="隐私与照片授权"><ul>
        <li>上传的照片与描述默认私有，仅用于你的本次生成，不会公开展示或跨用户复用。</li>
        <li>请确认你对参考素材拥有使用权；受版权保护的角色无法制作。</li>
        <li>收货信息只在你确认生产订单时提供给嘉立创。</li>
        <li>单色材料打印件为材料本色，效果图中的颜色不会印到成品上。</li>
      </ul></S>
    </main>
  )
}

export function NotFound() {
  return (
    <main className="wrap" style={{ padding: '80px var(--gutter)', minHeight: '60vh' }}>
      <div className="display outline-text" style={{ fontSize: 'clamp(120px, 24vw, 360px)', fontWeight: 900, lineHeight: 0.8 }}>404</div>
      <p style={{ fontSize: 22, fontWeight: 900 }}>这个页面还没有被构造出来。</p>
      <Link to="/" className="btn btn-red">回到首页</Link>
    </main>
  )
}

