import { AnimatePresence, motion, useMotionValue, useSpring } from 'framer-motion'
import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'

export function GenerationMode() {
  const [config, setConfig] = useState<{ mock: { image: boolean; aholo: boolean; slicer: boolean } } | null>(null)
  useEffect(() => { api('/api/v1/config').then(setConfig).catch(() => {}) }, [])
  return <div role="status" style={{ padding: '8px var(--gutter)', background: 'var(--paper-2)', borderBottom: '2px solid var(--ink)', fontSize: 12 }}>
    {config ? `效果图：${config.mock.image ? '本地模拟示意图' : '已配置图像服务'} · 3D：${config.mock.aholo ? '本地模拟模型，不代表输入造型' : '已配置模型服务'} · CAD：AI 理解需求后建模 · 固定模板在高级模式 · 切片：${config.mock.slicer ? '几何估算' : '已配置切片器'}` : '正在读取生成服务配置…'}
    {' · 几何预检不保证可制造性，生产前请由制造商复核。'}
  </div>
}

export function Logo({ size = 44, sub = true }: { size?: number; sub?: boolean }) {
  return (
    <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none', color: 'var(--ink)' }} aria-label="造物引擎 首页">
      <motion.span whileHover={{ rotate: -90 }} transition={{ type: 'spring', stiffness: 300, damping: 14 }}
        style={{ display: 'inline-flex', width: size, height: size, background: 'var(--red)', position: 'relative', alignItems: 'center', justifyContent: 'center', flex: '0 0 auto' }}>
        <span style={{ width: size * 0.4, height: size * 0.4, borderRadius: '50%', background: 'var(--paper)' }} />
        <span style={{ position: 'absolute', width: size * 1.27, height: Math.max(4, size * 0.13), background: 'var(--ink)', transform: 'rotate(-35deg)' }} />
      </motion.span>
      <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1 }}>
        <span style={{ fontSize: size * 0.52, fontWeight: 900, letterSpacing: 2 }}>造物引擎</span>
        {sub && <span className="display" style={{ fontSize: 10, fontWeight: 700, letterSpacing: 3, marginTop: 4 }}>ZAOWU ENGINE</span>}
      </span>
    </Link>
  )
}

export function QuotaBadge() {
  const { user } = useAuth()
  if (!user) return null
  const q = user.quota
  const zero = q.freeRemaining === 0
  return (
    <Link to="/pay" className="mono" title="今日免费额度（北京时间 00:00 重置）"
      style={{ fontSize: 13, fontWeight: 700, border: '2px solid var(--ink)', padding: '8px 12px', textDecoration: 'none',
        background: zero ? 'var(--ink)' : 'transparent', color: zero ? 'var(--paper)' : 'var(--ink)', whiteSpace: 'nowrap' }}>
      今日免费 <span style={{ color: 'var(--red)' }}>{q.freeRemaining}</span>/{q.freeTotal}
      {q.paidCredits > 0 && <> · 付费 {q.paidCredits}</>}
      {q.freeReserved > 0 && <> · 预留 {q.freeReserved}</>}
    </Link>
  )
}

export function Nav({ compact = false }: { compact?: boolean }) {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const link = ({ isActive }: { isActive: boolean }) => ({ textDecoration: 'none', color: isActive ? 'var(--red)' : 'var(--ink)', fontWeight: 700 })
  return (
    <header style={{ position: 'sticky', top: 0, zIndex: 50, borderBottom: '3px solid var(--ink)', background: 'rgba(241,235,221,.94)', backdropFilter: 'blur(6px)' }}>
      <div className="wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, minHeight: compact ? 64 : 72 }}>
        <Logo size={compact ? 36 : 44} sub={!compact} />
        <nav aria-label="主导航" className="hide-sm" style={{ display: 'flex', gap: 'clamp(14px, 2.4vw, 34px)', fontSize: 15 }}>
          <NavLink to="/create" style={link}>创意 3D</NavLink>
          <NavLink to="/cad" style={link}>实用物品 CAD</NavLink>
          <Link to="/#price" style={{ textDecoration: 'none', fontWeight: 700 }}>价格</Link>
          <NavLink to="/me" style={link}>我的作品</NavLink>
          {user?.isAdmin && <NavLink to="/admin" style={link}>后台</NavLink>}
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <QuotaBadge />
          {user ? (
            <button className="btn btn-sm hide-sm" onClick={() => { logout(); nav('/') }}>退出</button>
          ) : (
            <Link to="/login" className="btn btn-ink btn-sm" style={{ minHeight: 44 }}>登录</Link>
          )}
          <button className="btn btn-ink btn-sm" aria-label="菜单" aria-expanded={open} onClick={() => setOpen(!open)}
            style={{ display: 'none', width: 44, minHeight: 44, padding: 0 }} data-mobile-menu>≡</button>
        </div>
      </div>
      <style>{`@media (max-width: 820px){[data-mobile-menu]{display:inline-flex !important}}`}</style>
      <AnimatePresence>
        {open && (
          <motion.nav aria-label="移动导航" initial={{ clipPath: 'polygon(0 0,100% 0,100% 0,0 0)' }}
            animate={{ clipPath: 'polygon(0 0,100% 0,100% 100%,0 100%)' }} exit={{ clipPath: 'polygon(0 0,100% 0,100% 0,0 0)' }}
            style={{ background: 'var(--ink)', color: 'var(--paper)', display: 'flex', flexDirection: 'column', padding: 16, gap: 4 }}
            onClick={() => setOpen(false)}>
            {[['/create', '创意 3D'], ['/cad', '实用物品 CAD'], ['/me', '我的作品'], ['/pay', '额度与付费']].map(([to, t]) => (
              <Link key={to} to={to} style={{ color: 'var(--paper)', textDecoration: 'none', fontSize: 28, fontWeight: 900, padding: '8px 0' }}>{t}</Link>
            ))}
            {user && <button className="btn btn-sm" style={{ alignSelf: 'flex-start', marginTop: 8 }} onClick={() => { logout(); nav('/') }}>退出登录</button>}
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  )
}

/** 页面转场：红、黑两块斜切面板扫过（构成主义擦除） */
export function PageWipe() {
  const loc = useLocation()
  return (
    <AnimatePresence mode="wait">
      <motion.div key={loc.pathname} aria-hidden="true" style={{ position: 'fixed', inset: 0, zIndex: 9000, pointerEvents: 'none', overflow: 'hidden' }}>
        <motion.div style={{ position: 'absolute', inset: '-20%', background: 'var(--red)', transform: 'skewX(-14deg)' }}
          initial={{ x: '0%' }} animate={{ x: '130%' }} transition={{ duration: 0.75, ease: [0.7, 0, 0.2, 1] }} />
        <motion.div style={{ position: 'absolute', inset: '-20%', background: 'var(--ink)', transform: 'skewX(-14deg)' }}
          initial={{ x: '0%' }} animate={{ x: '130%' }} transition={{ duration: 0.75, delay: 0.08, ease: [0.7, 0, 0.2, 1] }} />
      </motion.div>
    </AnimatePresence>
  )
}

/** 十字准星光标 + 实时坐标（工程制图感） */
export function Crosshair() {
  const x = useMotionValue(-100), y = useMotionValue(-100)
  const sx = useSpring(x, { stiffness: 900, damping: 50 }), sy = useSpring(y, { stiffness: 900, damping: 50 })
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [hot, setHot] = useState(false)
  const [enabled, setEnabled] = useState(false)
  useEffect(() => {
    const fine = window.matchMedia('(pointer: fine)').matches && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    setEnabled(fine)
    if (!fine) return
    document.body.classList.add('has-cursor')
    const mv = (e: PointerEvent) => {
      x.set(e.clientX); y.set(e.clientY); setPos({ x: e.clientX, y: e.clientY })
      setHot(!!(e.target as HTMLElement)?.closest?.('a,button,[role=tab],label'))
    }
    window.addEventListener('pointermove', mv)
    return () => { window.removeEventListener('pointermove', mv); document.body.classList.remove('has-cursor') }
  }, [x, y])
  if (!enabled) return null
  return (
    <motion.div aria-hidden="true" style={{ position: 'fixed', left: 0, top: 0, x: sx, y: sy, zIndex: 9999, pointerEvents: 'none' }}>
      <motion.div animate={{ scale: hot ? 1.8 : 1, rotate: hot ? 45 : 0 }} transition={{ type: 'spring', stiffness: 400, damping: 22 }}
        style={{ position: 'absolute', left: -14, top: -14, width: 28, height: 28 }}>
        <span style={{ position: 'absolute', left: 13, top: 0, width: 2, height: 28, background: hot ? 'var(--red)' : 'var(--ink)' }} />
        <span style={{ position: 'absolute', top: 13, left: 0, height: 2, width: 28, background: hot ? 'var(--red)' : 'var(--ink)' }} />
        <span style={{ position: 'absolute', left: 9, top: 9, width: 10, height: 10, border: '2px solid var(--red)', borderRadius: hot ? 0 : '50%' }} />
      </motion.div>
      <span className="mono" style={{ position: 'absolute', left: 18, top: 14, fontSize: 10, fontWeight: 700, whiteSpace: 'nowrap', color: 'var(--ink)', background: 'rgba(241,235,221,.8)', padding: '1px 4px' }}>
        X {String(Math.round(pos.x * 0.264)).padStart(3, '0')} · Y {String(Math.round(pos.y * 0.264)).padStart(3, '0')} mm
      </span>
    </motion.div>
  )
}

export function Footer() {
  return (
    <footer style={{ background: 'var(--ink)', color: 'var(--rule-2)', borderTop: '6px solid var(--red)' }}>
      <div className="wrap" style={{ padding: '40px var(--gutter)', display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 24, fontSize: 13, lineHeight: 1.9 }}>
        <div><div style={{ fontSize: 28, fontWeight: 900, color: 'var(--paper)' }}>造物引擎</div><div className="display" style={{ fontSize: 11, letterSpacing: 3 }}>ZAOWU ENGINE</div></div>
        <div style={{ display: 'flex', flexDirection: 'column' }}><b style={{ color: 'var(--paper)' }}>服务</b><Link to="/create" style={{ color: 'inherit' }}>创意 3D</Link><Link to="/cad" style={{ color: 'inherit' }}>实用物品 CAD</Link><Link to="/rules" style={{ color: 'inherit' }}>价格与计次规则</Link></div>
        <div style={{ display: 'flex', flexDirection: 'column' }}><b style={{ color: 'var(--paper)' }}>保障</b><Link to="/rules#refund" style={{ color: 'inherit' }}>退款与申诉</Link><Link to="/rules#privacy" style={{ color: 'inherit' }}>隐私与照片授权</Link></div>
        <div style={{ maxWidth: 340 }}><b style={{ color: 'var(--paper)' }}>说明</b><div>效果图与 3D 生成由第三方模型服务与本地 CAD 内核提供；实体制造、物流与售后由嘉立创按其订单条款履约。</div></div>
      </div>
    </footer>
  )
}
