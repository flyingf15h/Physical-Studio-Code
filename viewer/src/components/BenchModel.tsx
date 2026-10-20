// 3D model of a breadboard bench (a build's starting bench, a step, a commit or the finished build),
// from the GLBs Senna's Build helper code writes (mcp-server/physical_studio/bench/). Each part's
// meshes sit under a node named <id>__mesh. Click a part, or its name below, to see what it is;
// `highlight` marks this step's new parts. Like the Build helper's viewer: reset / top view, an evenly
// lit mode, and the GLB to download. Hardware builds also pass `wires`: clicking a wire marks both of
// its ends in the model and names the part and pin at each one.
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Canvas, type ThreeEvent } from '@react-three/fiber'
import { Bounds, ContactShadows, Environment, Html, Lightformer, OrbitControls, useGLTF } from '@react-three/drei'
import type { BenchModel as Model, WireInfo } from '../api'
import './BenchModel.css'

const PICKED = new THREE.Color('#26c6da')
const NEW = new THREE.Color('#0f9fb3')
// "Even light" (the Build helper's default): unlit colours, so dark parts and wires stay readable.
const FLAT_PICKED = new THREE.MeshBasicMaterial({ color: PICKED, side: THREE.DoubleSide })
const FLAT_NEW = new THREE.MeshBasicMaterial({ color: NEW, side: THREE.DoubleSide })
// "Drawing": an assembly-manual line drawing (like IKEA's, and Flatpack's drawing view). White parts with black
// edges where faces meet at more than 25°, wires in their own colour, this step's new parts in cyan.
const INK = new THREE.LineBasicMaterial({ color: '#1d1d1f' })
const PAPER = new THREE.MeshLambertMaterial({ color: '#ffffff', side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 })
const PAPER_NEW = new THREE.MeshLambertMaterial({ color: '#7fe3f0', side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 })
export type Look = 'studio' | 'even' | 'drawing'

/** The mesh's ink lines, made the first time the drawing view needs them. */
function inkOf(mesh: THREE.Mesh): THREE.LineSegments {
  let ink = mesh.userData.ink as THREE.LineSegments | undefined
  if (!ink) {
    ink = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 25), INK)
    ink.raycast = () => {} // clicks go to the part, not its outline
    mesh.add(ink)
    mesh.userData.ink = ink
  }
  return ink
}

// Wires are under a millimetre thick, so clicks on them used to miss: each wire gets an invisible copy
// pushed out along its normals, about 3 mm across, that catches the click.
const HIT = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false })
const HIT_MARGIN_M = 0.0012

function hitZone(mesh: THREE.Mesh): THREE.Mesh {
  const g = mesh.geometry.clone()
  const pos = g.attributes.position as THREE.BufferAttribute
  const nor = g.attributes.normal as THREE.BufferAttribute
  const d = HIT_MARGIN_M / mesh.matrixWorld.getMaxScaleOnAxis() // in the mesh's own units
  for (let i = 0; i < pos.count; i++) {
    pos.setXYZ(i, pos.getX(i) + nor.getX(i) * d, pos.getY(i) + nor.getY(i) * d, pos.getZ(i) + nor.getZ(i) * d)
  }
  g.computeBoundingSphere()
  const hit = new THREE.Mesh(g, HIT)
  hit.name = `${mesh.userData.part}__hit`
  hit.userData.part = mesh.userData.part
  return hit
}

function partOf(obj: THREE.Object3D, ids: string[]): string | null {
  for (let o: THREE.Object3D | null = obj; o; o = o.parent) {
    const id = ids.find((i) => o!.name.startsWith(`${i}__`))
    if (id) return id
  }
  return null
}

/** "From Teensy 4.1 pin D2 to A4988 STEP, about 120 mm": the two ends of a clicked wire. */
export function WireEnds({ wire }: { wire: WireInfo }) {
  return (
    <span className="wire-ends">
      <span className="wire-swatch" style={{ background: wire.color }} />
      <span className="wire-end">
        <span className="wire-tag">A</span> {wire.from.part} <code>{wire.from.pin}</code>
      </span>
      <span aria-hidden="true">→</span>
      <span className="wire-end">
        <span className="wire-tag">B</span> {wire.to.part} <code>{wire.to.pin}</code>
      </span>
      {wire.inline && <span className="muted">through a {wire.inline}</span>}
      {wire.length_mm ? <span className="muted">· about {wire.length_mm} mm</span> : null}
    </span>
  )
}

function WireMarkers({ wire }: { wire: WireInfo }) {
  if (!wire.ends) return null
  return (
    <>
      {wire.ends.map((p, i) => {
        const end = i === 0 ? wire.from : wire.to
        return (
          <group key={i} position={p}>
            <mesh renderOrder={10}>
              <sphereGeometry args={[0.0028, 16, 12]} />
              <meshBasicMaterial color={PICKED} depthTest={false} transparent opacity={0.95} />
            </mesh>
            <Html center={false} zIndexRange={[20, 10]} style={{ pointerEvents: 'none' }}>
              <div className="wire-label">
                <span className="wire-tag">{i === 0 ? 'A' : 'B'}</span>
                {end.part} · <strong>{end.pin}</strong>
              </div>
            </Html>
          </group>
        )
      })}
    </>
  )
}

function Scene({
  model,
  picked,
  highlight,
  look,
  onPick,
}: {
  model: Model
  picked: string | null
  highlight: string[]
  look: Look
  onPick: (id: string | null) => void
}) {
  const gltf = useGLTF(model.glb)
  const ids = useMemo(() => model.labels.map((l) => l.id), [model.labels])
  const wireIds = useMemo(() => model.labels.filter((l) => l.kind === 'wire').map((l) => l.id), [model.labels])
  const { root, meshes, box } = useMemo(() => {
    const root = gltf.scene.clone(true)
    root.updateMatrixWorld(true)
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
      // CAD guides carry each part's real finish (bare steel, PCB solder mask); the breadboard GLBs have
      // vertex colours and no finish, so they stay matte.
      const real = !look.vertexColors && old.isMeshStandardMaterial
      mesh.userData.lit = new THREE.MeshStandardMaterial({
        ...look,
        roughness: real ? old.roughness : 0.8,
        metalness: real ? old.metalness : 0,
      })
      mesh.userData.flat = new THREE.MeshBasicMaterial(look)
      mesh.userData.part = partOf(mesh, ids)
      meshes.push(mesh)
    })
    for (const mesh of meshes) {
      mesh.userData.wire = wireIds.includes(mesh.userData.part as string)
      if (mesh.userData.wire) mesh.add(hitZone(mesh))
    }
    const box = new THREE.Box3().setFromObject(root)
    return { root, meshes, box }
  }, [gltf, ids, wireIds])

  useEffect(() => {
    for (const mesh of meshes) {
      const id = mesh.userData.part as string | null
      const on = id && id === picked ? PICKED : id && highlight.includes(id) ? NEW : null
      const ink = look === 'drawing' && !mesh.userData.wire ? inkOf(mesh) : (mesh.userData.ink as THREE.LineSegments | undefined)
      if (ink) ink.visible = look === 'drawing' && !mesh.userData.wire
      if (look === 'drawing') {
        mesh.material = on === PICKED ? FLAT_PICKED : on === NEW ? PAPER_NEW : mesh.userData.wire ? (mesh.userData.flat as THREE.Material) : PAPER
      } else if (look === 'even') {
        mesh.material = on === PICKED ? FLAT_PICKED : on === NEW ? FLAT_NEW : (mesh.userData.flat as THREE.Material)
      } else {
        const mat = mesh.userData.lit as THREE.MeshStandardMaterial
        mat.emissive.copy(on ?? new THREE.Color('black'))
        mat.emissiveIntensity = on ? 0.55 : 0
        mesh.material = mat
      }
    }
  }, [meshes, picked, highlight, look])

  const size = box.getSize(new THREE.Vector3())
  const centre = box.getCenter(new THREE.Vector3())
  return (
    <>
      <primitive
        object={root}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation()
          onPick((e.object.userData.part as string | null) ?? null)
        }}
      />
      {/* A soft shadow on the table under the model, so it sits on something instead of floating. */}
      {look === 'studio' && (
        <ContactShadows
          position={[centre.x, box.min.y - 0.0004, centre.z]}
          scale={Math.max(size.x, size.z) * 1.6}
          far={Math.max(size.y, 0.02) * 1.5}
          blur={2.4}
          opacity={0.42}
          resolution={512}
        />
      )}
    </>
  )
}

interface Props {
  model: Model
  guide?: Record<string, string> // part id -> "what it is" note
  wires?: Record<string, WireInfo> // hardware builds: wire id -> its two ends
  highlight?: string[]
  height?: number
}

export function BenchModel({ model, guide = {}, wires = {}, highlight = [], height = 420 }: Props) {
  const [picked, setPicked] = useState<string | null>(null)
  const [view, setView] = useState({ n: 0, top: false }) // a new n remounts the canvas at that view
  const [look, setLook] = useState<Look>('studio')
  const label = model.labels.find((l) => l.id === picked)
  const wire = picked ? wires[picked] : undefined
  const parts = model.labels.filter((l) => l.kind !== 'wire')
  const wireLabels = model.labels.filter((l) => l.kind === 'wire')
  // Scroll over the model zooms it, not the page: React's wheel handlers are passive, so stop the
  // page scroll with a native listener (the orbit controls still get the event).
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const stop = (e: WheelEvent) => e.preventDefault()
    el.addEventListener('wheel', stop, { passive: false })
    return () => el.removeEventListener('wheel', stop)
  }, [])

  return (
    <div className="bench-model">
      <div className="bench-canvas" style={{ height }} ref={box}>
        <Canvas
          key={view.n}
          camera={{ fov: 35, near: 0.001, far: 50, position: view.top ? [0, 0.34, 0.001] : [0.05, 0.22, 0.24] }}
          dpr={[1, 2]}
          onPointerMissed={() => setPicked(null)}
        >
          <color attach="background" args={[look === 'drawing' ? '#ffffff' : '#ece9e4']} />
          <hemisphereLight args={['#ffffff', '#b9b4ae', 1.7]} />
          <directionalLight position={[1, 2, 1.5]} intensity={2} />
          <directionalLight position={[-1.5, 1, -1]} intensity={0.7} />
          {/* A soft studio for metal parts to reflect (built here, nothing downloaded). */}
          <Environment resolution={128}>
            <Lightformer intensity={2} position={[0, 4, 0]} rotation-x={Math.PI / 2} scale={[8, 8, 1]} />
            <Lightformer intensity={1} position={[-4, 1, 2]} rotation-y={Math.PI / 2} scale={[6, 3, 1]} />
            <Lightformer intensity={0.6} position={[4, 1, -2]} rotation-y={-Math.PI / 2} scale={[6, 3, 1]} />
          </Environment>
          <Suspense fallback={null}>
            <Bounds fit observe margin={1.15}>
              <Scene model={model} picked={picked} highlight={highlight} look={look} onPick={setPicked} />
            </Bounds>
            {wire && <WireMarkers wire={wire} />}
          </Suspense>
          <OrbitControls makeDefault minDistance={0.01} maxDistance={5} zoomSpeed={0.8} />
        </Canvas>
        <div className="bench-tools">
          <span>Drag to rotate · scroll to zoom · click a part or wire</span>
          <button type="button" onClick={() => setView((v) => ({ n: v.n + 1, top: false }))}>
            Reset view
          </button>
          <button type="button" onClick={() => setView((v) => ({ n: v.n + 1, top: true }))}>
            Top view
          </button>
          <span className="bench-looks" role="group" aria-label="How the model is drawn">
            {(
              [
                ['studio', 'Studio', 'Studio lighting with shadows'],
                ['even', 'Even light', 'Light every part evenly: dark parts are easier to see'],
                ['drawing', 'Drawing', 'Black-and-white line drawing, like an assembly manual; new parts in cyan'],
              ] as const
            ).map(([id, name, title]) => (
              <button key={id} type="button" aria-pressed={look === id} title={title} onClick={() => setLook(id)}>
                {name}
              </button>
            ))}
          </span>
          <a href={model.glb} download title="Download this 3D model (GLB)">
            Download
          </a>
        </div>
      </div>
      <p className="bench-info" aria-live="polite">
        {wire ? (
          <WireEnds wire={wire} />
        ) : label ? (
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
      {wireLabels.length > 0 && (
        <div className="bench-parts bench-wires" aria-label="Wires">
          {wireLabels.map((l) => (
            <button
              key={l.id}
              type="button"
              className={[l.id === picked ? 'picked' : '', highlight.includes(l.id) ? 'new' : ''].join(' ')}
              onClick={() => setPicked(l.id === picked ? null : l.id)}
            >
              {wires[l.id] ? (
                <>
                  <span className="wire-swatch" style={{ background: wires[l.id].color }} />
                  {wires[l.id].from.pin} → {wires[l.id].to.pin}
                </>
              ) : (
                l.name
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
