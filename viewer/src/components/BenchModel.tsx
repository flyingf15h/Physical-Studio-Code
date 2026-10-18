// 3D model of a breadboard bench (a build's starting bench, a step, a commit or the finished build),
// from the GLBs Senna's Build helper code writes (mcp-server/physical_studio/bench/). Each part's
// meshes sit under a node named <id>__mesh. Click a part, or its name below, to see what it is;
// `highlight` marks this step's new parts. Like the Build helper's viewer: reset / top view, an evenly
// lit mode, and the GLB to download.
import { Suspense, useEffect, useMemo, useState } from 'react'
import * as THREE from 'three'
import { Canvas, type ThreeEvent } from '@react-three/fiber'
import { Bounds, OrbitControls, useGLTF } from '@react-three/drei'
import type { BenchModel as Model } from '../api'
import './BenchModel.css'

const PICKED = new THREE.Color('#26c6da')
const NEW = new THREE.Color('#0f9fb3')
// "Even light" (the Build helper's default): unlit colours, so dark parts and wires stay readable.
const FLAT_PICKED = new THREE.MeshBasicMaterial({ color: PICKED, side: THREE.DoubleSide })
const FLAT_NEW = new THREE.MeshBasicMaterial({ color: NEW, side: THREE.DoubleSide })

function partOf(obj: THREE.Object3D, ids: string[]): string | null {
  for (let o: THREE.Object3D | null = obj; o; o = o.parent) {
    const id = ids.find((i) => o!.name.startsWith(`${i}__`))
    if (id) return id
  }
  return null
}

function Scene({
  model,
  picked,
  highlight,
  flat,
  onPick,
}: {
  model: Model
  picked: string | null
  highlight: string[]
  flat: boolean
  onPick: (id: string | null) => void
}) {
  const gltf = useGLTF(model.glb)
  const ids = useMemo(() => model.labels.map((l) => l.id), [model.labels])
  const { root, meshes } = useMemo(() => {
    const root = gltf.scene.clone(true)
    const meshes: THREE.Mesh[] = []
    root.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      // The bench GLBs carry positions and vertex colours only; lighting needs normals.
      if (!mesh.geometry.attributes.normal) mesh.geometry.computeVertexNormals()
      // trimesh writes sRGB vertex colours; three.js expects linear ones (else everything looks washed out).
      const colors = mesh.geometry.attributes.color as THREE.BufferAttribute | undefined
      if (colors && !mesh.geometry.userData.linearColors) {
        const c = new THREE.Color()
        for (let i = 0; i < colors.count; i++) {
          c.setRGB(colors.getX(i), colors.getY(i), colors.getZ(i), THREE.SRGBColorSpace)
          colors.setXYZ(i, c.r, c.g, c.b)
        }
        colors.needsUpdate = true
        mesh.geometry.userData.linearColors = true // geometry is shared between clones: convert once
      }
      const old = mesh.material as THREE.MeshStandardMaterial
      const look = {
        color: old.color?.clone() ?? new THREE.Color('white'),
        map: old.map ?? null, // CAD guides: photo of a board's top
        vertexColors: !!mesh.geometry.attributes.color,
        side: THREE.DoubleSide,
      }
      mesh.userData.lit = new THREE.MeshStandardMaterial({ ...look, roughness: 0.8, metalness: 0 })
      mesh.userData.flat = new THREE.MeshBasicMaterial(look)
      mesh.userData.part = partOf(mesh, ids)
      meshes.push(mesh)
    })
    return { root, meshes }
  }, [gltf, ids])

  useEffect(() => {
    for (const mesh of meshes) {
      const id = mesh.userData.part as string | null
      const on = id && id === picked ? PICKED : id && highlight.includes(id) ? NEW : null
      if (flat) {
        mesh.material = on === PICKED ? FLAT_PICKED : on === NEW ? FLAT_NEW : (mesh.userData.flat as THREE.Material)
      } else {
        const mat = mesh.userData.lit as THREE.MeshStandardMaterial
        mat.emissive.copy(on ?? new THREE.Color('black'))
        mat.emissiveIntensity = on ? 0.55 : 0
        mesh.material = mat
      }
    }
  }, [meshes, picked, highlight, flat])

  return (
    <primitive
      object={root}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation()
        onPick((e.object.userData.part as string | null) ?? null)
      }}
    />
  )
}

interface Props {
  model: Model
  guide?: Record<string, string> // part id -> "what it is" note
  highlight?: string[]
  height?: number
}

export function BenchModel({ model, guide = {}, highlight = [], height = 420 }: Props) {
  const [picked, setPicked] = useState<string | null>(null)
  const [view, setView] = useState({ n: 0, top: false }) // a new n remounts the canvas at that view
  const [flat, setFlat] = useState(false)
  const label = model.labels.find((l) => l.id === picked)
  const parts = model.labels.filter((l) => l.kind !== 'wire')

  return (
    <div className="bench-model">
      <div className="bench-canvas" style={{ height }}>
        <Canvas
          key={view.n}
          camera={{ fov: 35, near: 0.001, far: 50, position: view.top ? [0, 0.34, 0.001] : [0.05, 0.22, 0.24] }}
          dpr={[1, 2]}
          onPointerMissed={() => setPicked(null)}
        >
          <color attach="background" args={['#ece9e4']} />
          <hemisphereLight args={['#ffffff', '#b9b4ae', 1.7]} />
          <directionalLight position={[1, 2, 1.5]} intensity={2} />
          <directionalLight position={[-1.5, 1, -1]} intensity={0.7} />
          <Suspense fallback={null}>
            <Bounds fit clip observe margin={1.15}>
              <Scene model={model} picked={picked} highlight={highlight} flat={flat} onPick={setPicked} />
            </Bounds>
          </Suspense>
          <OrbitControls makeDefault />
        </Canvas>
        <div className="bench-tools">
          <span>Drag to rotate · scroll to zoom · click a part</span>
          <button type="button" onClick={() => setView((v) => ({ n: v.n + 1, top: false }))}>
            Reset view
          </button>
          <button type="button" onClick={() => setView((v) => ({ n: v.n + 1, top: true }))}>
            Top view
          </button>
          <button
            type="button"
            aria-pressed={flat}
            title={flat ? 'Back to studio lighting' : 'Light every part evenly: dark parts are easier to see'}
            onClick={() => setFlat(!flat)}
          >
            {flat ? 'Studio light' : 'Even light'}
          </button>
          <a href={model.glb} download title="Download this 3D model (GLB)">
            Download
          </a>
        </div>
      </div>
      <p className="bench-info" aria-live="polite">
        {label ? (
          <>
            <strong>{label.name}</strong>
            {guide[label.id] ? ` · ${guide[label.id]}` : ''}
          </>
        ) : (
          'Click any part to see what it is and how to spot it on your bench.'
        )}
      </p>
      {parts.length > 0 && (
        <div className="bench-parts">
          {parts.map((l) => (
            <button
              key={l.id}
              type="button"
              className={[l.id === picked ? 'picked' : '', highlight.includes(l.id) ? 'new' : ''].join(' ')}
              onClick={() => setPicked(l.id === picked ? null : l.id)}
            >
              {l.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
