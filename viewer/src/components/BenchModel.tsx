// 3D model of a breadboard bench (a build's starting bench, a step, a commit or the finished build),
// from the GLBs Senna's Build helper code writes (mcp-server/physical_studio/bench/). Each part's
// meshes sit under a node named <id>__mesh. Click a part, or its name below, to see what it is;
// `highlight` marks this step's new parts. Like the Build helper's viewer: reset / top view, an evenly
// lit mode, and the GLB to download. Hardware builds also pass `wires`: clicking a wire marks both of
// its ends in the model and names the part and pin at each one.
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { Bounds, Environment, Html, Lightformer, OrbitControls, useBounds, useGLTF } from '@react-three/drei'
import { EffectComposer, N8AO, ToneMapping } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import { InkEdgesEffect } from './InkEdges'
import type { BenchModel as Model, WireInfo } from '../api'
import './BenchModel.css'

const PICKED = new THREE.Color('#26c6da')
const NEW = new THREE.Color('#0f9fb3')
// "Even light" (the Build helper's default): unlit colours, so dark parts and wires stay readable.
const FLAT_PICKED = new THREE.MeshBasicMaterial({ color: PICKED, side: THREE.DoubleSide })
const FLAT_NEW = new THREE.MeshBasicMaterial({ color: NEW, side: THREE.DoubleSide })
// "Drawing": an assembly-manual line drawing (like IKEA's, and Flatpack's drawing view). White parts, inked by
// InkEdges' screen-space pass, wires in their own colour, this step's new parts in cyan.
const PAPER = new THREE.MeshLambertMaterial({ color: '#ffffff', side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 })
const PAPER_NEW = new THREE.MeshLambertMaterial({ color: '#7fe3f0', side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 })
export type Look = 'studio' | 'even' | 'drawing'
// This step's new parts also show through whatever covers them (a pinion under its cart), faintly, like the
// dashed hidden lines in an IKEA manual: a see-through copy drawn after everything else, ignoring depth.
const GHOST = new THREE.MeshBasicMaterial({ color: NEW, transparent: true, opacity: 0.3, depthTest: false, depthWrite: false })

function ghostOf(mesh: THREE.Mesh): THREE.Mesh {
  let ghost = mesh.userData.ghost as THREE.Mesh | undefined
  if (!ghost) {
    ghost = new THREE.Mesh(mesh.geometry, GHOST)
    ghost.renderOrder = 10
    ghost.raycast = () => {}
    mesh.add(ghost)
    mesh.userData.ghost = ghost
  }
  return ghost
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
  hit.visible = false // still clickable (raycasts ignore visibility), but kept out of the ambient-occlusion depth pass
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
  onBox,
}: {
  model: Model
  picked: string | null
  highlight: string[]
  look: Look
  onPick: (id: string | null) => void
  onBox: (box: THREE.Box3) => void // the studio light sits outside <Bounds>, or its floor would be framed too
}) {
  const gltf = useGLTF(model.glb)
  const ids = useMemo(() => model.labels.map((l) => l.id), [model.labels])
  const wireIds = useMemo(() => model.labels.filter((l) => l.kind === 'wire').map((l) => l.id), [model.labels])
  const invalidate = useThree((s) => s.invalidate)
  const { root, meshes, box } = useMemo(() => {
    const root = gltf.scene.clone(true)
    root.updateMatrixWorld(true)
    const meshes: THREE.Mesh[] = []
    root.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      mesh.castShadow = mesh.receiveShadow = true
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
    return { root, meshes, box: new THREE.Box3().setFromObject(root) }
  }, [gltf, ids, wireIds])

  useEffect(() => {
    for (const mesh of meshes) {
      const id = mesh.userData.part as string | null
      const on = id && id === picked ? PICKED : id && highlight.includes(id) ? NEW : null
      if (on === NEW && !mesh.userData.wire) ghostOf(mesh).visible = true
      else if (mesh.userData.ghost) (mesh.userData.ghost as THREE.Mesh).visible = false
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
    invalidate() // the canvas draws on demand
  }, [meshes, picked, highlight, look, invalidate])
  useEffect(() => onBox(box), [box, onBox])
  // Like Flatpack, each step frames what it adds: the camera eases onto this step's new parts, with enough of
  // the build around them (at least a third of its size) to show where they go. No new parts: the whole build.
  // ...and its new parts drop into place from above (an IKEA manual's arrow, animated). Wires stay put.
  const drop = useRef<{ t0: number; items: { mesh: THREE.Mesh; home: THREE.Vector3; off: THREE.Vector3 }[] } | null>(null)
  const dropping = highlight.join(' ')
  useEffect(() => {
    const ids = dropping ? dropping.split(' ') : []
    const lift = new THREE.Vector3(0, box.getSize(new THREE.Vector3()).length() * 0.18, 0)
    const items = meshes
      .filter((m) => ids.includes(m.userData.part as string) && !m.userData.wire && m.parent)
      .map((mesh) => {
        const home = ((mesh.userData.home as THREE.Vector3 | undefined) ??= mesh.position.clone())
        mesh.position.copy(home)
        const parent = mesh.parent!
        parent.updateWorldMatrix(true, false)
        const at = parent.localToWorld(home.clone())
        const off = parent.worldToLocal(at.clone().add(lift)).sub(home) // world "up" in the parent's frame
        return { mesh, home, off }
      })
    drop.current = items.length ? { t0: performance.now(), items } : null
    invalidate()
  }, [dropping, meshes, box, invalidate])
  useFrame(() => {
    const d = drop.current
    if (!d) return
    const t = Math.min(1, (performance.now() - d.t0) / 900)
    const ease = 1 - (1 - t) ** 3
    for (const { mesh, home, off } of d.items) mesh.position.copy(home).addScaledVector(off, 1 - ease)
    if (t < 1) invalidate()
    else drop.current = null
  })
  const bounds = useBounds()
  const boundsRef = useRef(bounds) // useBounds() is a new object every render: keep it out of the effect's deps
  boundsRef.current = bounds
  const focus = highlight.join(' ')
  useEffect(() => {
    const bounds = boundsRef.current
    const ids = focus ? focus.split(' ') : []
    const target = new THREE.Box3()
    for (const mesh of meshes) if (ids.includes(mesh.userData.part as string)) target.expandByObject(mesh)
    if (target.isEmpty()) {
      bounds.refresh(box).clip().fit()
      return
    }
    const whole = box.getSize(new THREE.Vector3())
    const min = Math.max(whole.x, whole.y, whole.z) / 3
    const c = target.getCenter(new THREE.Vector3())
    const size = target.getSize(new THREE.Vector3()).max(new THREE.Vector3(min, min, min))
    bounds.refresh(new THREE.Box3().setFromCenterAndSize(c, size)).clip().fit()
  }, [focus, meshes, box])

  return (
    <>
      <primitive
        object={root}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation()
          onPick((e.object.userData.part as string | null) ?? null)
        }}
      />
    </>
  )
}

/** Studio look, as Flatpack lights its room: one warm key light casting soft shadows (its shadow camera
 * fitted to this model, so a 7 cm breadboard and a 50 cm pendulum both get crisp ones) onto the parts. No floor:
 * a shadow-catching floor drew a pale arc behind the model. */
function StudioLight({ box }: { box: THREE.Box3 }) {
  const light = useRef<THREE.DirectionalLight>(null)
  const c = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3())
  const r = Math.max(size.x, size.y, size.z) * 0.75 + 0.01
  useEffect(() => {
    const l = light.current
    if (!l) return
    l.target.position.copy(c)
    l.target.updateMatrixWorld()
    l.shadow.camera.updateProjectionMatrix()
  })
  return (
    <>
      <directionalLight
        ref={light}
        castShadow
        position={[c.x + r * 0.9, c.y + r * 2.2, c.z + r * 1.3]}
        intensity={2.6}
        color="#fff4e8"
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-normalBias={r * 0.002}
        shadow-radius={4}
        shadow-camera-left={-r * 1.4}
        shadow-camera-right={r * 1.4}
        shadow-camera-top={r * 1.4}
        shadow-camera-bottom={-r * 1.4}
        shadow-camera-near={r * 0.1}
        shadow-camera-far={r * 6}
      />
    </>
  )
}

// Every step mounts a new canvas, which used to start the camera at the same default pose each time and swoop
// in from there. Like Flatpack, each step's camera now starts where the previous step's left off (per guide) and
// eases onto the new parts, so moving through the steps reads as one continuous shot.
type View = { position: [number, number, number]; rotation: [number, number, number]; target: [number, number, number] }
const lastView = new Map<string, View>()

function RememberView({ guide }: { guide: string }) {
  // Saved on every drawn frame, not on unmount: the next step's canvas reads it while rendering, which React
  // does before the old canvas unmounts.
  useFrame(({ camera, controls }) => {
    const target = (controls as unknown as { target?: THREE.Vector3 } | null)?.target
    if (!target) return
    lastView.set(guide, {
      position: camera.position.toArray(),
      rotation: [camera.rotation.x, camera.rotation.y, camera.rotation.z],
      target: target.toArray(),
    })
  })
  return null
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
  const [bounds, setBounds] = useState<THREE.Box3 | null>(null)
  const ink = useMemo(() => new InkEdgesEffect(), [])
  const guideKey = model.glb.replace(/[^/]*$/, '') // the guide's folder: its steps share one camera
  // Reset view / Top view start from their own pose; otherwise carry on from the last step's camera.
  const [saved] = useState(() => lastView.get(guideKey))
  const start = view.n === 0 ? saved : undefined
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
          camera={
            start
              ? { fov: 35, near: 0.001, far: 50, position: start.position, rotation: start.rotation }
              : { fov: 35, near: 0.001, far: 50, position: view.top ? [0, 0.34, 0.001] : [0.05, 0.22, 0.24] }
          }
          dpr={[1, 2]}
          shadows="soft"
          frameloop="demand" // like Flatpack: draw only when the view or a material changes, not 60 times a second
          onPointerMissed={() => setPicked(null)}
        >
          <color attach="background" args={[look === 'drawing' ? '#ffffff' : look === 'studio' ? '#f7f5f1' : '#ece9e4']} />
          <hemisphereLight args={['#ffffff', '#b9b4ae', look === 'studio' ? 0.6 : 1.7]} />
          {look !== 'studio' && <directionalLight position={[1, 2, 1.5]} intensity={2} />}
          <directionalLight position={[-1.5, 1, -1]} intensity={look === 'studio' ? 0.5 : 0.7} />
          {/* A soft studio for metal parts to reflect (built here, nothing downloaded). */}
          <Environment resolution={128} environmentIntensity={look === 'studio' ? 0.7 : 1}>
            <Lightformer intensity={2} position={[0, 4, 0]} rotation-x={Math.PI / 2} scale={[8, 8, 1]} />
            <Lightformer intensity={1} position={[-4, 1, 2]} rotation-y={Math.PI / 2} scale={[6, 3, 1]} />
            <Lightformer intensity={0.6} position={[4, 1, -2]} rotation-y={-Math.PI / 2} scale={[6, 3, 1]} />
          </Environment>
          <Suspense fallback={null}>
            {/* With no camera to carry on from (a guide's first view, Reset or Top view) the framing snaps into
                place instead of swooping in from the default pose. */}
            <Bounds fit observe margin={1.15} maxDuration={start ? 1 : 0.001}>
              <Scene model={model} picked={picked} highlight={highlight} look={look} onPick={setPicked} onBox={setBounds} />
            </Bounds>
            {look === 'studio' && bounds && <StudioLight box={bounds} />}
            {wire && <WireMarkers wire={wire} />}
          </Suspense>
          {look === 'drawing' && (
            <EffectComposer multisampling={4}>
              <primitive object={ink} />
            </EffectComposer>
          )}
          {look === 'studio' && (
            // ambient occlusion darkens corners and the gaps between parts, so shapes read even in shadow
            <EffectComposer multisampling={4}>
              <N8AO aoRadius={0.012} distanceFalloff={0.6} intensity={2.2} halfRes />
              <ToneMapping mode={ToneMappingMode.NEUTRAL} />
            </EffectComposer>
          )}
          <OrbitControls makeDefault {...(start && { target: start.target })} minDistance={0.01} maxDistance={5} zoomSpeed={0.8} />
          <RememberView guide={guideKey} />
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
