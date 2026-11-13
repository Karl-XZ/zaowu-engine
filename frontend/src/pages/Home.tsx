import { motion, useScroll, useTransform, type MotionValue } from 'framer-motion'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Footer } from '../components/Chrome'
import { CountUp, Parallax, Rise, SplitReveal, Stamp, Ticker, usePointer } from '../components/Motion'
import { useAuth } from '../lib/auth'

const HeroScene = lazy(() => import('../components/HeroScene'))

function useIsWide(bp = 960) {
  const [w, setW] = useState(() => typeof window !== 'undefined' && window.innerWidth >= bp)
  useEffect(() => {
    const f = () => setW(window.innerWidth >= bp)
    window.addEventListener('resize', f)
    return () => window.removeEventListener('resize', f)
  }, [bp])
  return w
}

function Hero() {
  const [px, py] = usePointer()
  const { scrollY } = useScroll()
  const textY = useTransform(scrollY, [0, 700], [0, -140])
  const textOpacity = useTransform(scrollY, [0, 600], [1, 0.2])
  const { user } = useAuth()
  return (
    <section style={{ position: 'relative', minHeight: 'calc(100vh - 72px)', borderBottom: '3px solid var(--ink)', overflow: 'hidden' }}>
      <div className="hide-sm" style={{ position: 'absolute', left: 14, top: 120, transform: 'rotate(-90deg)', transformOrigin: 'left top', fontSize: 11, fontWeight: 700, letterSpacing: 6, whiteSpace: 'nowrap' }}>
        <span className="display">TEXT → CONCEPT → MODEL → PRINT → GIFT</span>
      </div>
      <div style={{ position: 'absolute', inset: 0, left: '44%' }} className="hero-canvas">
        <Suspense fallback={null}><HeroScene /></Suspense>
      </div>
      <Parallax px={px} py={py} depth={-18} style={{ right: '6%', top: '12%' }}>
        <span className="mono" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 700 }}><span style={{ width: 60, height: 2, background: 'var(--ink)' }} />60.0 mm</span>
      </Parallax>
      <Parallax px={px} py={py} depth={26} style={{ left: '46%', top: '52%' }}>
        <span className="mono hide-sm" style={{ fontSize: 12, fontWeight: 700, background: 'var(--paper)', border: '2px solid var(--ink)', padding: '6px 10px' }}>壁厚 ≥ 2.0 mm ✓</span>
      </Parallax>
      <Parallax px={px} py={py} depth={-30} style={{ right: '5%', bottom: '10%' }}>
        <span className="mono hide-sm" style={{ fontSize: 12, fontWeight: 700, background: 'var(--ink)', color: 'var(--paper)', padding: '6px 10px' }}>WATERTIGHT · MANIFOLD ✓</span>
      </Parallax>
      <Parallax px={px} py={py} depth={14} style={{ right: '2%', bottom: '22%' }}>
        <span className="display outline-text hide-sm" style={{ fontWeight: 900, fontSize: 'clamp(80px, 9vw, 150px)', lineHeight: 0.8 }}>3D</span>
      </Parallax>

      <motion.div className="wrap" style={{ position: 'relative', zIndex: 3, y: textY, opacity: textOpacity, paddingTop: 'clamp(40px, 7vh, 96px)', paddingBottom: 80, pointerEvents: 'none' }}>
        <div style={{ maxWidth: 720, display: 'flex', flexDirection: 'column', gap: 28, pointerEvents: 'auto' }}>
          <motion.div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }} initial={{ opacity: 0, x: -40 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.6 }}>
            <span className="chip chip-ink">AI × 3D 打印</span><span className="chip">送礼定制</span><span className="chip chip-red">嘉立创制造</span>
          </motion.div>
          <h1 style={{ margin: 0, fontWeight: 900, lineHeight: 0.92, letterSpacing: -2, fontSize: 'clamp(64px, 9.6vw, 168px)' }}>
            <SplitReveal text="心意，" delay={0.7} style={{ whiteSpace: 'nowrap' }} />
            <SplitReveal text="要有形状。" delay={0.95} style={{ color: 'var(--red)', whiteSpace: 'nowrap' }} />
          </h1>
          <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.5, duration: 0.8 }}
            style={{ margin: 0, maxWidth: 540, fontSize: 'clamp(17px, 1.5vw, 20px)', lineHeight: 1.75, fontWeight: 500, background: 'rgba(241,235,221,.75)' }}>
            说一句话，AI 先画出效果图；聊几句改到满意（最多 10 次），再一键转成<b>能真正打印出来</b>的 3D 模型 —— 修复、预检、切片后交给嘉立创做成实物。
          </motion.p>
          <motion.div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }} initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.7, type: 'spring', stiffness: 200, damping: 20 }}>
            <Link to="/create" className="btn btn-red" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 14, minWidth: 250, padding: '18px 22px', minHeight: 0 }}>
              <span className="display" style={{ fontSize: 11, letterSpacing: 3 }}>ENGINE A · LUX3D</span>
              <span style={{ display: 'flex', justifyContent: 'space-between', fontSize: 28 }}>创意 3D <span aria-hidden>→</span></span>
              <span style={{ fontSize: 13, fontWeight: 500 }}>效果图 → 对话调整 → 3D</span>
            </Link>
            <Link to="/cad" className="btn btn-ink" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 14, minWidth: 250, padding: '18px 22px', minHeight: 0 }}>
              <span className="display" style={{ fontSize: 11, letterSpacing: 3 }}>ENGINE B · CAD</span>
              <span style={{ display: 'flex', justifyContent: 'space-between', fontSize: 28 }}>精确 CAD <span aria-hidden>→</span></span>
              <span style={{ fontSize: 13, fontWeight: 500 }}>铭牌 · 钥匙扣 · 底座 · 盒子</span>
            </Link>
          </motion.div>
          <motion.p className="mono" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2 }} style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>
            每天 3 个合格模型免费 ／ 之后 ¥5 一个 ／ <span style={{ background: 'var(--ink)', color: 'var(--paper)', padding: '2px 6px' }}>不合格，不收钱</span>
            {!user && <> ／ <Link to="/login">注册即领</Link></>}
          </motion.p>
        </div>
      </motion.div>
      <motion.div aria-hidden="true" className="mono" animate={{ y: [0, 10, 0] }} transition={{ repeat: Infinity, duration: 1.8 }}
        style={{ position: 'absolute', left: '50%', bottom: 18, fontSize: 11, fontWeight: 700, letterSpacing: 3 }}>SCROLL ↓ 解构</motion.div>
      <style>{`@media (max-width: 960px){.hero-canvas{left:0 !important;opacity:.28}}`}</style>
    </section>
  )
}

function Manifesto() {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 80%', 'end 40%'] })
  const words = ['别的 AI', '给你', '一张图。', '造物引擎', '给你', '一件', '能拿在手里的', '礼物。']
  return (
    <section ref={ref} className="wrap" style={{ padding: 'clamp(64px, 10vw, 160px) var(--gutter)' }}>
      <p style={{ margin: 0, fontSize: 'clamp(40px, 6.4vw, 110px)', fontWeight: 900, lineHeight: 1.08, letterSpacing: -1 }}>
        {words.map((w, i) => <Word key={i} p={scrollYProgress} i={i} n={words.length} red={i === 3 || i === 7}>{w}</Word>)}
      </p>
    </section>
  )
}
function Word({ p, i, n, red, children }: { p: MotionValue<number>; i: number; n: number; red?: boolean; children: string }) {
  const o = useTransform(p, [i / n, (i + 1) / n], [0.12, 1])
  const y = useTransform(p, [i / n, (i + 1) / n], [30, 0])
  return <motion.span style={{ opacity: o, y, display: 'inline-block', marginRight: '0.25em', color: red ? 'var(--red)' : 'var(--ink)' }}>{children}</motion.span>
}

const STEPS = [
  { n: '01', t: '说一句话', d: '先选材料和尺寸，再说出你想送的礼物。AI 立刻画出第一张效果图。', tag: 'DESIGN SPEC' },
  { n: '02', t: '聊着改', d: '“耳朵圆一点”“换黏土风”“改成暖粉色”——造型、风格、颜色随口调，最多 10 次，每一版都保留。', tag: '≤ 10 TURNS' },
  { n: '03', t: '转 3D · 预检', d: 'Lux3D 把确认的效果图转成 3D，再修复、测壁厚、真实切片。过不了关，就不算交付、不扣次。', tag: 'VERIFIED_DELIVERABLE', red: true },
  { n: '04', t: '打印送达', d: '锁定生产文件哈希，带着材料和尺寸去嘉立创报价、打印、发货。制造费按嘉立创实际报价。', tag: 'SHA-256 LOCKED' },
]

function StepCard({ s, wide }: { s: typeof STEPS[0]; wide: boolean }) {
  return (
    <div style={{ flex: wide ? '0 0 min(520px, 70vw)' : '1 1 auto', minHeight: wide ? 520 : 0, border: '3px solid var(--ink)', padding: 32, display: 'flex', flexDirection: 'column', gap: 18,
      background: s.red ? 'var(--red)' : 'var(--paper)', color: s.red ? 'var(--paper)' : 'var(--ink)', boxShadow: '12px 12px 0 var(--ink)' }}>
      <span className="display" style={{ fontWeight: 900, fontSize: wide ? 180 : 110, lineHeight: 0.8, color: 'transparent', WebkitTextStroke: `2px ${s.red ? 'var(--paper)' : 'var(--ink)'}` }}>{s.n}</span>
      <h3 style={{ margin: 0, fontSize: 40, fontWeight: 900 }}>{s.t}</h3>
      <p style={{ margin: 0, fontSize: 17, lineHeight: 1.75, maxWidth: 420 }}>{s.d}</p>
      <span className="mono" style={{ marginTop: 'auto', alignSelf: 'flex-start', fontSize: 12, fontWeight: 700, background: 'var(--ink)', color: 'var(--paper)', padding: '6px 10px' }}>{s.tag}</span>
    </div>
  )
}

function Steps() {
  const wide = useIsWide()
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] })
  const x = useTransform(scrollYProgress, [0, 1], ['0%', '-62%'])
  const beam = useTransform(scrollYProgress, [0, 1], [-30, 20])
  const stepLabel = useTransform(scrollYProgress, (v) => `STEP ${String(Math.min(4, Math.floor(v * 4) + 1)).padStart(2, '0')} / 04`)
  const head = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, flex: wide ? '0 0 440px' : undefined }}>
      <span className="display" style={{ fontSize: 13, fontWeight: 700, letterSpacing: 4, color: 'var(--red)' }}>HOW IT WORKS</span>
      <h2 style={{ margin: 0, fontSize: 'clamp(48px, 6vw, 96px)', fontWeight: 900, lineHeight: 1 }}>四步，<br />从一句话<br /><span style={{ color: 'var(--red)' }}>到实物</span></h2>
      <p style={{ margin: 0, fontSize: 16, lineHeight: 1.7, maxWidth: 360 }}>别的 AI 只给你一张好看的图。造物引擎给你的，是一份<b>工厂能直接接单</b>的文件。</p>
    </div>
  )
  if (!wide) {
    return (
      <section className="wrap" style={{ padding: '72px var(--gutter)', display: 'flex', flexDirection: 'column', gap: 28 }}>
        {head}{STEPS.map((s) => <Rise key={s.n}><StepCard s={s} wide={false} /></Rise>)}
      </section>
    )
  }
  return (
    <section ref={ref} style={{ height: '320vh', position: 'relative', borderTop: '3px solid var(--ink)' }}>
      <div style={{ position: 'sticky', top: 72, height: 'calc(100vh - 72px)', overflow: 'hidden', display: 'flex', alignItems: 'center' }} className="grid-paper">
        <motion.div aria-hidden style={{ position: 'absolute', left: '-10%', top: '74%', width: '130%', height: 34, background: 'var(--ink)', rotate: beam }} />
        <motion.div style={{ x, display: 'flex', alignItems: 'center', gap: 56, paddingLeft: 'var(--gutter)', paddingRight: '20vw' }}>
          {head}
          {STEPS.map((s) => <StepCard key={s.n} s={s} wide />)}
        </motion.div>
        <motion.div aria-hidden className="mono" style={{ position: 'absolute', right: 'var(--gutter)', bottom: 28, fontSize: 12, fontWeight: 700 }}>
          <motion.span>{stepLabel}</motion.span>
        </motion.div>
      </div>
    </section>
  )
}

/** 对话调整演示：自动播放的聊天 + 10 格次数条 */
function ChatDemo() {
  const lines = [
    { u: '一个站在月亮上的 Q 版小熊，送给闺蜜', a: 'v0 · 已生成，月亮做成一体底座', color: '#D52B1E', ear: 0 },
    { u: '耳朵再圆一点，身体胖一些', a: 'v1 · 造型已调整', color: '#D52B1E', ear: 1 },
    { u: '让一颗星星飘在它头顶', a: '飘浮的星星打印不出来 → 改成抱在手里？本次不计次', color: '#D52B1E', ear: 1, block: true },
    { u: '就这么改，颜色换成暖粉色', a: 'v2 · 抱星星、暖粉色', color: '#EE968B', ear: 1, star: true },
  ]
  const [step, setStep] = useState(0)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    let timer: any
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) timer = setInterval(() => setStep((s) => (s + 1) % (lines.length + 2)), 1800)
      else clearInterval(timer)
    }, { threshold: 0.4 })
    io.observe(el)
    return () => { io.disconnect(); clearInterval(timer) }
  }, [lines.length])
  const shown = lines.slice(0, Math.min(step, lines.length))
  const cur = shown[shown.length - 1] || lines[0]
  const used = shown.filter((l) => !l.block).length - (shown.length ? 1 : 0)
  return (
    <section ref={ref} style={{ background: 'var(--ink)', color: 'var(--paper)', borderTop: '3px solid var(--ink)', overflow: 'hidden', position: 'relative' }}>
      <div className="wrap" style={{ padding: 'clamp(56px, 8vw, 120px) var(--gutter)', display: 'flex', flexWrap: 'wrap', gap: 48, alignItems: 'center' }}>
        <div style={{ flex: '1 1 420px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <span className="display" style={{ fontSize: 13, fontWeight: 700, letterSpacing: 4, color: 'var(--red)' }}>TALK · TWEAK · CONFIRM</span>
          <h2 style={{ margin: 0, fontSize: 'clamp(44px, 5.6vw, 88px)', fontWeight: 900, lineHeight: 1.02 }}>不会建模？<br /><span style={{ color: 'var(--red)' }}>会聊天就行。</span></h2>
          <p style={{ margin: 0, fontSize: 16, lineHeight: 1.8, color: 'var(--rule-2)', maxWidth: 460 }}>每次设计包含首张效果图和最多 10 次对话调整。打印不出来的要求会被提前拦下并给出替代方案 —— 被拦下的那次不计次。</p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div aria-hidden style={{ display: 'flex', gap: 5 }}>
              {Array.from({ length: 10 }, (_, i) => (
                <motion.span key={i} animate={{ background: i < used ? '#D52B1E' : 'rgba(0,0,0,0)', scale: i === used - 1 ? [1, 1.4, 1] : 1 }}
                  style={{ width: 20, height: 26, border: '2px solid var(--paper)', display: 'block' }} />
              ))}
            </div>
            <span className="display" style={{ fontSize: 30, fontWeight: 900 }}>{10 - Math.max(0, used)}<span style={{ fontSize: 14, color: 'var(--rule-2)' }}>/10</span></span>
          </div>
          <Link to="/create" className="btn btn-red" style={{ alignSelf: 'flex-start', '--sh': 'var(--paper)' } as any}>开始对话设计 →</Link>
        </div>
        <div style={{ flex: '1 1 520px', display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 260px', display: 'flex', flexDirection: 'column', gap: 10, minHeight: 380 }} aria-live="polite">
            {shown.map((l, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <motion.div initial={{ x: 60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} style={{ alignSelf: 'flex-end', background: 'var(--paper)', color: 'var(--ink)', padding: '10px 14px', fontSize: 14, fontWeight: 700, maxWidth: '90%' }}>{l.u}</motion.div>
                <motion.div initial={{ x: -60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ delay: 0.35 }}
                  style={{ alignSelf: 'flex-start', background: l.block ? 'var(--red)' : 'transparent', border: '2px solid var(--paper)', padding: '8px 12px', fontSize: 13, maxWidth: '92%' }}>{l.a}</motion.div>
              </div>
            ))}
          </div>
          <div style={{ flex: '0 0 240px', height: 300, position: 'relative', background: 'radial-gradient(ellipse at 50% 40%, #FBF7EE, #DCD2BF)', border: '3px solid var(--paper)', alignSelf: 'center' }} aria-hidden>
            <Bear color={cur.color} round={cur.ear === 1} star={!!(cur as any).star} />
            <span className="display" style={{ position: 'absolute', left: 10, top: 8, color: 'var(--red)', fontWeight: 900, fontSize: 30 }}>v{Math.max(0, used)}</span>
          </div>
        </div>
      </div>
    </section>
  )
}

function Bear({ color, round, star }: { color: string; round: boolean; star: boolean }) {
  const t = { type: 'spring', stiffness: 200, damping: 16 } as const
  const ball = (s: React.CSSProperties) => <motion.div animate={{ background: `radial-gradient(circle at 38% 30%, #fff6, transparent 50%), ${color}` }} transition={t} style={{ position: 'absolute', borderRadius: '50%', ...s }} />
  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <div style={{ position: 'absolute', left: 30, bottom: 20, width: 180, height: 60, borderRadius: '0 0 90px 90px', background: 'linear-gradient(#F3E3B5,#D9BE7E)' }} />
      {ball({ left: 70, bottom: 64, width: 100, height: 96, borderRadius: '50px 50px 34px 34px' })}
      {ball({ left: 60, top: 46, width: 120, height: 108 })}
      <motion.div animate={{ scale: round ? 1.2 : 1 }} style={{ position: 'absolute', left: 52, top: 36, width: 40, height: 40 }}>{ball({ inset: 0 })}</motion.div>
      <motion.div animate={{ scale: round ? 1.2 : 1 }} style={{ position: 'absolute', left: 148, top: 36, width: 40, height: 40 }}>{ball({ inset: 0 })}</motion.div>
      <div style={{ position: 'absolute', left: 96, top: 92, width: 10, height: 12, borderRadius: '50%', background: '#2A1F1C' }} />
      <div style={{ position: 'absolute', left: 134, top: 92, width: 10, height: 12, borderRadius: '50%', background: '#2A1F1C' }} />
      <div style={{ position: 'absolute', left: 106, top: 112, width: 28, height: 20, borderRadius: '50%', background: '#FCE9E2' }} />
      <motion.div initial={false} animate={{ scale: star ? 1 : 0, rotate: star ? 0 : -180 }} transition={t}
        style={{ position: 'absolute', left: 96, top: 168, width: 48, height: 48, background: '#F2C94C', clipPath: 'polygon(50% 0%,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%)' }} />
    </div>
  )
}

function Engines() {
  return (
    <section style={{ display: 'flex', flexWrap: 'wrap', background: 'var(--ink)', borderTop: '3px solid var(--ink)', borderBottom: '3px solid var(--ink)', overflow: 'hidden' }}>
      <motion.div initial={{ x: '-30%', opacity: 0 }} whileInView={{ x: 0, opacity: 1 }} viewport={{ once: true }} transition={{ duration: 1, ease: [0.2, 0.8, 0.2, 1] }}
        className="split-l" style={{ flex: '1 1 520px', background: 'var(--red)', color: 'var(--paper)', padding: 'clamp(40px,6vw,96px) clamp(16px,6vw,112px) clamp(40px,6vw,96px) var(--gutter)', display: 'flex', flexDirection: 'column', gap: 22, position: 'relative' }}>
        <div aria-hidden className="spin-slow" style={{ position: 'absolute', right: '12%', bottom: -90, width: 300, height: 300, borderRadius: '50%', border: '40px dashed rgba(20,18,16,.2)' }} />
        <span className="display" style={{ fontSize: 13, fontWeight: 700, letterSpacing: 4 }}>ENGINE A</span>
        <h2 style={{ margin: 0, fontSize: 'clamp(48px, 6vw, 92px)', fontWeight: 900, lineHeight: 1 }}>创意 3D</h2>
        <p style={{ margin: 0, fontWeight: 700 }}>AI 效果图 + 对话调整 · Aholo Lux3D 图生 3D</p>
        <blockquote style={{ margin: '8px 0', padding: '20px 24px', background: 'var(--paper)', color: 'var(--ink)', fontSize: 20, fontWeight: 700, boxShadow: '8px 8px 0 var(--ink)' }}>“送朋友一个 Q 版小熊摆件，底座写生日快乐”</blockquote>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10, lineHeight: 1.6 }}>
          <li>■ AI 先出效果图，对话调整造型、风格、颜色，最多 10 次</li>
          <li>■ 确认后 Lux3D 图生 3D；构图自带一体底座、不留悬空碎片</li>
          <li>■ 适合：公仔、宠物、人物纪念、装饰摆件</li>
        </ul>
        <Link to="/create" className="btn btn-ink" style={{ alignSelf: 'flex-start' }}>开始创意生成 →</Link>
      </motion.div>
      <motion.div initial={{ x: '30%', opacity: 0 }} whileInView={{ x: 0, opacity: 1 }} viewport={{ once: true }} transition={{ duration: 1, delay: 0.1, ease: [0.2, 0.8, 0.2, 1] }}
        className="split-r grid-paper" style={{ flex: '1 1 520px', background: 'var(--paper)', padding: 'clamp(40px,6vw,96px) var(--gutter) clamp(40px,6vw,96px) clamp(16px,7vw,128px)', display: 'flex', flexDirection: 'column', gap: 22 }}>
        <span className="display" style={{ fontSize: 13, fontWeight: 700, letterSpacing: 4 }}>ENGINE B</span>
        <h2 style={{ margin: 0, fontSize: 'clamp(48px, 6vw, 92px)', fontWeight: 900, lineHeight: 1 }}>精确 CAD</h2>
        <p style={{ margin: 0, fontWeight: 700 }}>本地参数化模板 + 几何内核实测 · 单位 mm</p>
        <DrawingMini />
        <blockquote style={{ margin: 0, padding: '20px 24px', background: 'var(--ink)', color: 'var(--paper)', fontSize: 20, fontWeight: 700, boxShadow: '8px 8px 0 var(--red)' }}>“长 70 mm、宽 35 mm，带直径 5 mm 孔的钥匙扣”</blockquote>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10, lineHeight: 1.6 }}>
          <li>■ 输出 STL / 3MF / GLB，尺寸由几何内核实测</li>
          <li>■ 改长宽厚只重算参数 —— <b>不计次</b></li>
          <li>■ 适合：铭牌、钥匙扣、底座、收纳盒</li>
        </ul>
        <Link to="/cad" className="btn btn-red" style={{ alignSelf: 'flex-start' }}>开始精确建模 →</Link>
      </motion.div>
      <style>{`.split-l{clip-path:polygon(0 0,100% 0,90% 100%,0 100%)}.split-r{clip-path:polygon(10% 0,100% 0,100% 100%,0 100%)}@media(max-width:820px){.split-l,.split-r{clip-path:none}}`}</style>
    </section>
  )
}

function DrawingMini() {
  const draw = { initial: { pathLength: 0 }, whileInView: { pathLength: 1 }, viewport: { once: true }, transition: { duration: 1.4, ease: 'easeInOut' } } as const
  return (
    <svg viewBox="0 0 450 170" style={{ width: '100%', maxWidth: 440 }} role="img" aria-label="钥匙扣工程图：70 × 35 毫米，直径 5 毫米挂孔">
      <motion.path d="M30 30 H350 Q364 30 364 44 V106 Q364 120 350 120 H30 Q16 120 16 106 V44 Q16 30 30 30 Z" fill="none" stroke="#141210" strokeWidth="4" {...draw} />
      <motion.circle cx="44" cy="75" r="12" fill="none" stroke="#D52B1E" strokeWidth="4" {...draw} />
      <motion.path d="M16 12 H364 M16 6 V18 M364 6 V18" stroke="#141210" strokeWidth="2" {...draw} />
      <motion.path d="M384 30 V120 M378 30 H390 M378 120 H390" stroke="#141210" strokeWidth="2" {...draw} />
      <rect x="156" y="2" width="76" height="20" fill="#F1EBDD" /><text x="194" y="17" textAnchor="middle" fontFamily="JetBrains Mono" fontSize="13" fontWeight="700" fill="#141210">70.0 mm</text>
      <text x="394" y="80" fontFamily="JetBrains Mono" fontSize="13" fontWeight="700" fill="#141210">35.0</text>
      <text x="22" y="150" fontFamily="JetBrains Mono" fontSize="13" fontWeight="700" fill="#D52B1E">⌀ 5.0 mm 挂孔</text>
      <text x="110" y="83" fontFamily="Noto Sans SC" fontSize="24" fontWeight="900" fill="#141210">TO：阿杰</text>
    </svg>
  )
}

function Price() {
  return (
    <section id="price" className="wrap" style={{ padding: 'clamp(64px, 8vw, 128px) var(--gutter)' }}>
      <h2 style={{ margin: '0 0 40px', fontSize: 'clamp(44px, 6vw, 96px)', fontWeight: 900, lineHeight: 1 }}>价格，<span style={{ color: 'var(--red)' }}>一句话说完。</span></h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', border: '3px solid var(--ink)', position: 'relative' }}>
        <div style={{ flex: '1 1 380px', padding: 36, borderRight: '3px solid var(--ink)', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <CountUp to={3} className="display" style={{ fontWeight: 900, fontSize: 'clamp(180px, 20vw, 300px)', lineHeight: 0.78, color: 'var(--red)', letterSpacing: -8 }} />
          <span style={{ fontSize: 28, fontWeight: 900 }}>每天免费 3 个</span>
          <span style={{ fontSize: 15, lineHeight: 1.6 }}>创意与 CAD 共用，北京时间 00:00 重置。只计「通过制造预检」的合格模型；一次设计含首图 + 最多 10 次调整。</span>
        </div>
        <div style={{ flex: '1 1 380px', padding: 36, background: 'var(--ink)', color: 'var(--paper)', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <span className="display" style={{ fontWeight: 900, fontSize: 'clamp(150px, 16vw, 250px)', lineHeight: 0.82, letterSpacing: -6 }}><span style={{ fontSize: '.45em', verticalAlign: 'top' }}>¥</span><CountUp to={5} /></span>
          <span style={{ fontSize: 28, fontWeight: 900 }}>之后每个 5 元</span>
          <span style={{ fontSize: 15, lineHeight: 1.6 }}>付款先冻结权益，模型合格才核销；失败自动恢复，可原路退款。</span>
        </div>
        <Stamp style={{ right: 'clamp(12px, 3vw, 48px)', top: 'clamp(40px, 8vw, 110px)', zIndex: 2 }}>
          <div style={{ background: 'var(--paper)', border: '4px solid var(--red)', color: 'var(--red)', padding: '14px 24px', fontSize: 'clamp(22px, 2.6vw, 38px)', fontWeight: 900, letterSpacing: 4, whiteSpace: 'nowrap', boxShadow: '0 0 0 8px var(--paper)' }}>不合格 · 不收钱</div>
        </Stamp>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', border: '3px solid var(--ink)', borderTop: 0 }}>
        {[['永久免费', '旋转预览、历史作品、同一版本文件下载。'], ['修复不扣次', '平台模型缺陷导致的修复和重试，不再收费。'], ['CAD 改尺寸免费', '同一模板的纯参数调整，只在本地重算。'], ['制造费直付工厂', '打印与物流由嘉立创报价收费，平台不赚差价。']].map(([t, d], i) => (
          <Rise key={t} delay={i * 0.08} y={30}><div style={{ padding: '24px 28px', borderRight: '3px solid var(--ink)', height: '100%' }}><b style={{ fontSize: 18 }}>{t}</b><p style={{ margin: '8px 0 0', fontSize: 14, lineHeight: 1.6 }}>{d}</p></div></Rise>
        ))}
      </div>
    </section>
  )
}

function FinalCTA() {
  const [v, setV] = useState('')
  const nav = useNavigate()
  return (
    <section style={{ position: 'relative', overflow: 'hidden', borderTop: '3px solid var(--ink)' }}>
      <motion.div aria-hidden initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }} transition={{ type: 'spring', stiffness: 90, damping: 14 }}
        style={{ position: 'absolute', right: -120, top: -160, width: 520, height: 520, borderRadius: '50%', background: 'var(--red)' }} />
      <motion.div aria-hidden initial={{ x: '-100%' }} whileInView={{ x: 0 }} viewport={{ once: true }} transition={{ duration: 1, ease: [0.7, 0, 0.2, 1] }}
        style={{ position: 'absolute', left: '-10%', bottom: 40, width: '70%', height: 28, background: 'var(--ink)', rotate: -6 }} />
      <div className="wrap" style={{ position: 'relative', padding: 'clamp(64px, 8vw, 128px) var(--gutter) clamp(96px, 10vw, 160px)', display: 'flex', flexDirection: 'column', gap: 32 }}>
        <h2 style={{ margin: 0, fontSize: 'clamp(56px, 9vw, 150px)', fontWeight: 900, lineHeight: 0.95, letterSpacing: -2 }}>
          <SplitReveal text="现在，" mode="mask" /><SplitReveal text="说出你的礼物。" mode="mask" delay={0.2} />
        </h2>
        <form onSubmit={(e) => { e.preventDefault(); nav(`/create?prompt=${encodeURIComponent(v)}`) }}
          style={{ display: 'flex', flexWrap: 'wrap', maxWidth: 920, border: '3px solid var(--ink)', background: 'var(--paper)', boxShadow: '10px 10px 0 var(--ink)' }}>
          <label htmlFor="cta" className="sr-only">描述你的礼物</label>
          <input id="cta" value={v} onChange={(e) => setV(e.target.value)} placeholder="一只抱着星星的小熊，6 厘米高，送给闺蜜…"
            style={{ flex: '1 1 320px', minWidth: 0, minHeight: 68, border: 0, padding: '0 24px', fontSize: 18, background: 'transparent', fontFamily: 'inherit' }} />
          <button className="btn btn-red" style={{ minHeight: 68, border: 0, borderLeft: '3px solid var(--ink)', fontSize: 20 }}>免费生成 →</button>
        </form>
      </div>
    </section>
  )
}

export default function Home() {
  return (
    <main>
      <Hero />
      <Ticker items={['说一句话', 'AI 效果图', '对话调整', '转成 3D', '预检 · 切片', '嘉立创打印', '送到 TA 手里']} />
      <Manifesto />
      <Steps />
      <ChatDemo />
      <Engines />
      <Price />
      <FinalCTA />
      <Footer />
    </main>
  )
}
