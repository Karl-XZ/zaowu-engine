import { Bounds, Center, ContactShadows, Grid, OrbitControls, useGLTF } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Suspense, useEffect, useMemo, useState } from 'react'
import * as THREE from 'three'

export type ViewMode = 'solid' | 'clay' | 'wire' | 'xray'

function Model({ url, mode }: { url: string; mode: ViewMode }) {
  const { scene } = useGLTF(url)
  const obj = useMemo(() => {
    const clone = scene.clone(true)
    clone.traverse((o) => {
      const m = o as THREE.Mesh
      if (!m.isMesh) return
      if (mode !== 'solid') m.material = mode === 'wire'
        ? new THREE.MeshBasicMaterial({ color: '#141210', wireframe: true })
        : mode === 'xray'
          ? new THREE.MeshStandardMaterial({ color: '#D52B1E', transparent: true, opacity: 0.35, roughness: 0.4, side: THREE.DoubleSide })
          : new THREE.MeshStandardMaterial({ color: '#D52B1E', roughness: 0.72, metalness: 0.02 })
      m.castShadow = true
    })
    return clone
  }, [scene, mode])
  useEffect(() => () => {
    if (mode !== 'solid') obj.traverse((o) => {
      const m = o as THREE.Mesh
      if (m.isMesh) (Array.isArray(m.material) ? m.material : [m.material]).forEach((material) => material.dispose())
    })
  }, [obj, mode])
  return <primitive object={obj} />
}

export default function ModelViewer({ url, height = 560 }: { url: string; height?: number | string }) {
  const [mode, setMode] = useState<ViewMode>('solid')
  const [spin, setSpin] = useState(true)
  const [key, setKey] = useState(0)
  const modes: [ViewMode, string][] = [['solid', '实体'], ['clay', '红陶'], ['wire', '线框'], ['xray', '透视']]
  return (
    <div style={{ position: 'relative', height, minHeight: 360 }} className="grid-paper">
      <Canvas key={key} shadows dpr={[1, 2]} camera={{ position: [80, 70, 110], fov: 35, near: 0.5, far: 5000 }} aria-label="三维模型预览，可拖动旋转、滚轮缩放">
        <color attach="background" args={['#EDE5D5']} />
        <hemisphereLight args={['#fffaf0', '#8a8075', 0.9]} />
        <directionalLight position={[60, 120, 80]} intensity={2.2} castShadow />
        <directionalLight position={[-80, 40, -60]} intensity={0.6} color="#ffd9cf" />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.35}>
            <Center top><Model url={url} mode={mode} /></Center>
          </Bounds>
          <ContactShadows position={[0, 0, 0]} opacity={0.35} scale={300} blur={2.4} far={80} />
        </Suspense>
        <Grid args={[400, 400]} cellSize={5} sectionSize={25} cellColor="#cfc5b3" sectionColor="#141210" sectionThickness={1} fadeDistance={420} infiniteGrid />
        <OrbitControls makeDefault autoRotate={spin} autoRotateSpeed={1.4} enableDamping />
      </Canvas>
      <div style={{ position: 'absolute', left: 16, bottom: 16, display: 'flex', flexWrap: 'wrap', border: '3px solid var(--ink)', background: 'var(--paper)' }} role="toolbar" aria-label="视图">
        {modes.map(([m, t], i) => (
          <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
            style={{ minHeight: 44, padding: '0 14px', border: 0, borderLeft: i ? '3px solid var(--ink)' : 0, fontWeight: 700,
              background: mode === m ? 'var(--ink)' : 'transparent', color: mode === m ? 'var(--paper)' : 'var(--ink)', cursor: 'pointer' }}>{t}</button>
        ))}
        <button onClick={() => setSpin(!spin)} aria-pressed={spin} style={{ minHeight: 44, padding: '0 14px', border: 0, borderLeft: '3px solid var(--ink)', fontWeight: 700, background: spin ? 'var(--red)' : 'transparent', color: spin ? 'var(--paper)' : 'var(--ink)', cursor: 'pointer' }}>自转</button>
        <button onClick={() => setKey((k) => k + 1)} style={{ minHeight: 44, padding: '0 14px', border: 0, borderLeft: '3px solid var(--ink)', fontWeight: 700, background: 'transparent', cursor: 'pointer' }}>重置视角</button>
      </div>
    </div>
  )
}
