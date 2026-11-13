import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'

const INK = '#141210', RED = '#D52B1E'

function gridTexture(tone: string) {
  const c = document.createElement('canvas')
  c.width = c.height = 256
  const g = c.getContext('2d')!
  g.fillStyle = tone; g.fillRect(0, 0, 256, 256)
  g.strokeStyle = 'rgba(20,18,16,.22)'; g.lineWidth = 2
  for (let i = 0; i <= 256; i += 32) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, 256); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(256, i); g.stroke() }
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

const scrollP = () => Math.min(1, Math.max(0, window.scrollY / (window.innerHeight * 0.9)))

/** 礼盒：滚动时六个面向外“解构”飞散，丝带骨架保留 —— 从礼物到结构 */
function GiftBox() {
  const group = useRef<THREE.Group>(null!)
  const faces = useRef<THREE.Mesh[]>([])
  const { pointer } = useThree()
  const tex = useMemo(() => [gridTexture('#F1EBDD'), gridTexture('#E6DCC9'), gridTexture('#FBF8F1')], [])
  const faceDefs = useMemo(() => ([
    { n: [0, 0, 1], r: [0, 0, 0], t: 0 }, { n: [0, 0, -1], r: [0, Math.PI, 0], t: 0 },
    { n: [1, 0, 0], r: [0, Math.PI / 2, 0], t: 1 }, { n: [-1, 0, 0], r: [0, -Math.PI / 2, 0], t: 1 },
    { n: [0, 1, 0], r: [-Math.PI / 2, 0, 0], t: 2 }, { n: [0, -1, 0], r: [Math.PI / 2, 0, 0], t: 2 },
  ] as const), [])
  const edges = useMemo(() => {
    const e: { p: [number, number, number]; s: [number, number, number] }[] = []
    for (const a of [-1, 1]) for (const b of [-1, 1]) {
      e.push({ p: [0, a, b], s: [2.06, 0.06, 0.06] }, { p: [a, 0, b], s: [0.06, 2.06, 0.06] }, { p: [a, b, 0], s: [0.06, 0.06, 2.06] })
    }
    return e
  }, [])

  useFrame((state, dt) => {
    const p = scrollP()
    const g = group.current
    g.rotation.y += dt * (0.25 + p * 0.6)
    g.rotation.x = THREE.MathUtils.lerp(g.rotation.x, -0.42 + pointer.y * 0.25, 0.06)
    g.rotation.z = THREE.MathUtils.lerp(g.rotation.z, pointer.x * -0.15, 0.06)
    g.position.y = Math.sin(state.clock.elapsedTime * 0.8) * 0.06
    const ease = p * p * (3 - 2 * p)
    faces.current.forEach((m, i) => {
      const d = faceDefs[i]
      const k = 1.0 + ease * (1.6 + i * 0.25)
      m.position.set(d.n[0] * k, d.n[1] * k, d.n[2] * k)
      m.rotation.set(d.r[0] + ease * (i % 2 ? 0.6 : -0.6), d.r[1] + ease * 0.5, d.r[2] + ease * (i - 2.5) * 0.3)
    })
  })

  return (
    <group ref={group} scale={1.25}>
      {faceDefs.map((d, i) => (
        <mesh key={i} ref={(m) => { if (m) faces.current[i] = m }} position={d.n as any} rotation={d.r as any}>
          <planeGeometry args={[2, 2]} />
          <meshBasicMaterial map={tex[d.t]} side={THREE.DoubleSide} transparent opacity={0.94} />
        </mesh>
      ))}
      {edges.map((e, i) => (
        <mesh key={`e${i}`} position={e.p}><boxGeometry args={e.s} /><meshBasicMaterial color={INK} /></mesh>
      ))}
      {/* 丝带骨架 */}
      <mesh position={[0, 0, 0]}><boxGeometry args={[0.3, 2.12, 0.3]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh position={[0, 1.06, 0]}><boxGeometry args={[0.3, 0.06, 2.12]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh position={[0, 1.06, 0]}><boxGeometry args={[2.12, 0.06, 0.3]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh position={[0, 0, 1.06]}><boxGeometry args={[0.3, 2.12, 0.06]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh position={[0, 0, -1.06]}><boxGeometry args={[0.3, 2.12, 0.06]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh position={[1.06, 0, 0]}><boxGeometry args={[0.06, 2.12, 0.3]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh position={[-1.06, 0, 0]}><boxGeometry args={[0.06, 2.12, 0.3]} /><meshBasicMaterial color={INK} /></mesh>
      {/* 蝴蝶结：两枚红色圆锥 */}
      <mesh position={[0.32, 1.32, 0]} rotation={[0, 0, -Math.PI / 2.6]}><coneGeometry args={[0.26, 0.6, 3]} /><meshBasicMaterial color={RED} /></mesh>
      <mesh position={[-0.32, 1.32, 0]} rotation={[0, 0, Math.PI / 2.6]}><coneGeometry args={[0.26, 0.6, 3]} /><meshBasicMaterial color={RED} /></mesh>
    </group>
  )
}

function Orbit({ r, speed, tilt, dashed = true, color = INK }: { r: number; speed: number; tilt: number; dashed?: boolean; color?: string }) {
  const ref = useRef<THREE.Group>(null!)
  const segs = useMemo(() => Array.from({ length: dashed ? 48 : 1 }, (_, i) => i), [dashed])
  useFrame((_, dt) => { ref.current.rotation.z += dt * speed })
  return (
    <group rotation={[tilt, 0, 0]}>
      <group ref={ref}>
        {dashed ? segs.map((i) => {
          const a = (i / segs.length) * Math.PI * 2
          return (
            <mesh key={i} position={[Math.cos(a) * r, Math.sin(a) * r, 0]} rotation={[0, 0, a + Math.PI / 2]}>
              <boxGeometry args={[0.18, 0.025, 0.025]} /><meshBasicMaterial color={color} />
            </mesh>
          )
        }) : <mesh><torusGeometry args={[r, 0.03, 8, 160]} /><meshBasicMaterial color={color} /></mesh>}
      </group>
    </group>
  )
}

function Satellites() {
  const g = useRef<THREE.Group>(null!)
  useFrame((s) => {
    const t = s.clock.elapsedTime, p = scrollP()
    g.current.children.forEach((c, i) => {
      const a = t * (0.3 + i * 0.07) + i * 1.7
      const r = 3.1 + i * 0.25 + p * 1.5
      c.position.set(Math.cos(a) * r, Math.sin(a * 0.9) * 1.4, Math.sin(a) * r * 0.5)
      c.rotation.set(t * 0.6 + i, t * 0.4, 0)
    })
  })
  return (
    <group ref={g}>
      <mesh><boxGeometry args={[0.5, 0.5, 0.5]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh><torusGeometry args={[0.32, 0.08, 8, 40]} /><meshBasicMaterial color={RED} /></mesh>
      <mesh><coneGeometry args={[0.32, 0.6, 3]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh><boxGeometry args={[0.9, 0.12, 0.12]} /><meshBasicMaterial color={RED} /></mesh>
    </group>
  )
}

function Backdrop() {
  const disc = useRef<THREE.Mesh>(null!)
  const beam = useRef<THREE.Mesh>(null!)
  const { pointer } = useThree()
  useFrame((s) => {
    const p = scrollP()
    disc.current.position.x = THREE.MathUtils.lerp(disc.current.position.x, 0.4 + pointer.x * -0.3, 0.05)
    disc.current.position.y = THREE.MathUtils.lerp(disc.current.position.y, 0.2 + pointer.y * 0.2 - p * 1.2, 0.05)
    disc.current.scale.setScalar(1 + p * 0.35)
    beam.current.rotation.z = -0.49 + Math.sin(s.clock.elapsedTime * 0.25) * 0.03 - p * 0.3
  })
  return (
    <>
      <mesh ref={disc} position={[0.4, 0.2, -3]}><circleGeometry args={[2.9, 96]} /><meshBasicMaterial color={RED} /></mesh>
      <mesh ref={beam} position={[0, -0.9, -2]} rotation={[0, 0, -0.49]}><planeGeometry args={[16, 0.42]} /><meshBasicMaterial color={INK} /></mesh>
      <mesh position={[-2.9, 1.6, -2.5]} rotation={[0, 0, 0.1]}><planeGeometry args={[0.9, 0.9]} /><meshBasicMaterial color={INK} /></mesh>
    </>
  )
}

export default function HeroScene() {
  return (
    <Canvas flat dpr={[1, 2]} camera={{ position: [0, 0.4, 8.4], fov: 42 }} gl={{ antialias: true, alpha: true }}
      style={{ position: 'absolute', inset: 0 }} aria-hidden="true">
      <Backdrop />
      <Orbit r={3.3} speed={0.12} tilt={0.18} />
      <Orbit r={2.55} speed={-0.2} tilt={1.2} dashed={false} color={RED} />
      <GiftBox />
      <Satellites />
    </Canvas>
  )
}
