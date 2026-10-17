// The finished design as a 3D model you can rotate (screen 2), at the guide's last step.
import { Suspense, useEffect, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { Bounds, OrbitControls } from '@react-three/drei'
import { Assembly } from '../Assembly'
import { loadSteps, type StepsDoc } from '../steps'

export function DesignModel({ design }: { design: string }) {
  const [doc, setDoc] = useState<StepsDoc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState(0)

  useEffect(() => {
    let stop = false
    loadSteps(`/${design}/design.steps.json`).then(
      (d) => !stop && setDoc(d),
      (e) => !stop && setError(e instanceof Error ? e.message : String(e)),
    )
    return () => {
      stop = true
    }
  }, [design])

  if (error) return <p className="muted">Couldn't load the 3D model: {error}</p>
  if (!doc) return <p className="muted">Loading the 3D model…</p>
  return (
    <div className="design-model">
      <Canvas camera={{ fov: 35, near: 0.001, far: 50, position: [0.15, 0.15, 0.2] }} dpr={[1, 2]}>
        <color attach="background" args={['#ece9e4']} />
        <hemisphereLight args={['#ffffff', '#b9b4ae', 1.6]} />
        <directionalLight position={[1, 2, 1.5]} intensity={2.2} />
        <directionalLight position={[-1.5, 1, -1]} intensity={0.8} />
        <Suspense fallback={null}>
          <Bounds fit clip margin={1.3}>
            <Assembly glbUrl={`/${design}/${doc.model}`} doc={doc} step={doc.steps.length - 1} exploded={false} view={view} still />
          </Bounds>
        </Suspense>
        <OrbitControls makeDefault />
      </Canvas>
      <div className="design-model-tools">
        <span>Drag to rotate · scroll to zoom</span>
        <button onClick={() => setView((v) => v + 1)}>Reset view</button>
      </div>
    </div>
  )
}
