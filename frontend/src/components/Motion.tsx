import { motion, useInView, useMotionValue, useSpring, useTransform, animate, type MotionValue } from 'framer-motion'
import { useEffect, useRef, useState, type ReactNode } from 'react'

const EASE = [0.2, 0.8, 0.2, 1] as const

/** 逐字揭示：每个字从不同的几何方向“砸”进来（构成主义的不对称节奏）。 */
export function SplitReveal({ text, className, style, delay = 0, as = 'span', mode = 'drop' }: {
  text: string; className?: string; style?: React.CSSProperties; delay?: number; as?: 'span' | 'h1' | 'h2'; mode?: 'drop' | 'mask'
}) {
  const ref = useRef<HTMLElement>(null)
  const inView = useInView(ref, { once: true, margin: '-10% 0px' })
  const chars = Array.from(text)
  const Tag: any = motion[as]
  return (
    <Tag ref={ref} className={className} style={{ display: 'block', ...style }} aria-label={text}>
      {chars.map((c, i) => {
        const dir = i % 3
        const from = mode === 'mask'
          ? { y: '110%' }
          : dir === 0 ? { y: '-120%', rotate: -18 } : dir === 1 ? { x: '-60%', rotate: 24 } : { y: '120%', rotate: 10 }
        return (
          <span key={i} aria-hidden="true" style={{ display: 'inline-block', overflow: mode === 'mask' ? 'hidden' : 'visible', verticalAlign: 'top' }}>
            <motion.span style={{ display: 'inline-block', whiteSpace: 'pre', transformOrigin: '50% 80%' }}
              initial={{ opacity: mode === 'mask' ? 1 : 0, ...from }}
              animate={inView ? { opacity: 1, x: 0, y: 0, rotate: 0 } : undefined}
              transition={{ delay: delay + i * 0.055, duration: 0.8, ease: EASE }}>
              {c}
            </motion.span>
          </span>
        )
      })}
    </Tag>
  )
}

/** 区块入场：从斜角滑入 */
export function Rise({ children, delay = 0, x = 0, y = 60, rotate = 0, className, style }: {
  children: ReactNode; delay?: number; x?: number; y?: number; rotate?: number; className?: string; style?: React.CSSProperties
}) {
  return (
    <motion.div className={className} style={style}
      initial={{ opacity: 0, x, y, rotate }} whileInView={{ opacity: 1, x: 0, y: 0, rotate: 0 }}
      viewport={{ once: true, margin: '-8% 0px' }} transition={{ duration: 0.9, delay, ease: EASE }}>
      {children}
    </motion.div>
  )
}

/** 数字滚动 */
export function CountUp({ to, duration = 1.4, className, style }: { to: number; duration?: number; className?: string; style?: React.CSSProperties }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const [v, setV] = useState(0)
  useEffect(() => {
    if (!inView) return
    const c = animate(0, to, { duration, ease: EASE, onUpdate: (x) => setV(Math.round(x)) })
    return () => c.stop()
  }, [inView, to, duration])
  return <span ref={ref} className={className} style={style}>{v}</span>
}

/** 印章：旋转砸下 + 冲击波 */
export function Stamp({ children, rotate = -12, delay = 0.2, style, className }: {
  children: ReactNode; rotate?: number; delay?: number; style?: React.CSSProperties; className?: string
}) {
  return (
    <motion.div className={className} style={{ position: 'absolute', ...style }}
      initial={{ scale: 3.2, rotate: rotate - 24, opacity: 0 }}
      whileInView={{ scale: 1, rotate, opacity: 1 }} viewport={{ once: true }}
      transition={{ type: 'spring', stiffness: 520, damping: 18, delay }}>
      {children}
    </motion.div>
  )
}

/** 鼠标视差（-1..1） */
export function usePointer(): [MotionValue<number>, MotionValue<number>] {
  const x = useMotionValue(0), y = useMotionValue(0)
  useEffect(() => {
    const f = (e: PointerEvent) => { x.set((e.clientX / window.innerWidth) * 2 - 1); y.set((e.clientY / window.innerHeight) * 2 - 1) }
    window.addEventListener('pointermove', f)
    return () => window.removeEventListener('pointermove', f)
  }, [x, y])
  return [useSpring(x, { stiffness: 60, damping: 18 }), useSpring(y, { stiffness: 60, damping: 18 })]
}

export function Parallax({ px, py, depth, children, style }: { px: MotionValue<number>; py: MotionValue<number>; depth: number; children?: ReactNode; style?: React.CSSProperties }) {
  const tx = useTransform(px, (v) => v * depth)
  const ty = useTransform(py, (v) => v * depth)
  return <motion.div aria-hidden="true" style={{ position: 'absolute', x: tx, y: ty, ...style }}>{children}</motion.div>
}

/** 无限跑马灯 */
export function Ticker({ items, rotate = -2.5, speed = 36 }: { items: string[]; rotate?: number; speed?: number }) {
  const row = [...items, ...items]
  return (
    <div aria-hidden="true" style={{ position: 'relative', height: 120, overflow: 'hidden' }}>
      <div style={{ position: 'absolute', left: '-5%', right: '-5%', top: 30, background: 'var(--ink)', transform: `rotate(${rotate}deg)`,
        borderTop: '3px solid var(--red)', borderBottom: '3px solid var(--red)', overflow: 'hidden' }}>
        <div className="marquee" style={{ gap: 40, padding: '16px 0', color: 'var(--paper)', fontSize: 26, fontWeight: 900, whiteSpace: 'nowrap', animationDuration: `${speed}s` }}>
          {row.map((t, i) => (
            <span key={i} style={{ display: 'inline-flex', gap: 40 }}>{t}<span style={{ color: 'var(--red)' }}>■</span></span>
          ))}
        </div>
      </div>
    </div>
  )
}
