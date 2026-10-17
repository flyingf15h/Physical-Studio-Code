import { useEffect, useMemo, useRef } from 'react'
import { createPortal, useFrame } from '@react-three/fiber'
import { Html, Line, useBounds, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { addedAt, motions, type StepsDoc, type Vec3 } from './steps'

const DURATION = 1.4 // seconds for a part to fly in
const HIGHLIGHT = new THREE.Color('#26c6da')
const DEG = Math.PI / 180

interface Node {
  obj: THREE.Object3D
  basePos: THREE.Vector3
  baseQuat: THREE.Quaternion
  center: THREE.Vector3 // bounding-box centre in the node's local frame (mm)
  materials: THREE.MeshStandardMaterial[]
  pulses: boolean // wires keep their colour readable instead of pulsing cyan
}

const ease = (t: number) => 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3)

interface Props {
  glbUrl: string
  doc: StepsDoc
  step: number // 0-based
  exploded: boolean
}

export function Assembly({ glbUrl, doc, step, exploded }: Props) {
  const gltf = useGLTF(glbUrl)
  const added = useMemo(() => addedAt(doc), [doc])
  const motionOf = useMemo(() => motions(doc), [doc])

  // Each placement is a direct child of the "design" node, named by its id (docs/steps-format.md).
  const { root, design, nodes } = useMemo(() => {
    const kinds = new Map(doc.placements.map((p) => [p.id, p.kind]))
    const root = gltf.scene.clone(true)
    const design = root.getObjectByName('design') ?? root
    const nodes = new Map<string, Node>()
    for (const obj of design.children) {
      const materials: THREE.MeshStandardMaterial[] = []
      const box = new THREE.Box3()
      obj.traverse((o) => {
        const mesh = o as THREE.Mesh
        if (!mesh.isMesh) return
        mesh.material = (mesh.material as THREE.MeshStandardMaterial).clone()
        materials.push(mesh.material as THREE.MeshStandardMaterial)
        mesh.geometry.computeBoundingBox()
        box.union(mesh.geometry.boundingBox!)
      })
      nodes.set(obj.name, {
        obj,
        basePos: obj.position.clone(),
        baseQuat: obj.quaternion.clone(),
        center: box.getCenter(new THREE.Vector3()),
        materials,
        pulses: kinds.get(obj.name) !== 'wire',
      })
    }
    return { root, design, nodes }
  }, [gltf, doc])

  // Refit the camera when the exploded view changes how much space the design takes.
  const bounds = useBounds()
  useEffect(() => {
    const t = setTimeout(() => bounds.refresh().clip().fit(), 60)
    return () => clearTimeout(t)
  }, [exploded, bounds])

  const stepStart = useRef({ step: -1, time: 0 })
  const euler = useMemo(() => new THREE.Euler(), [])
  const spin = useMemo(() => new THREE.Quaternion(), [])

  useFrame(({ clock }) => {
    const now = clock.getElapsedTime()
    if (stepStart.current.step !== step) stepStart.current = { step, time: now }
    const progress = ease((now - stepStart.current.time) / DURATION)
    const pulse = 0.35 + 0.25 * Math.sin(now * 4)

    for (const [id, node] of nodes) {
      const at = added.get(id) ?? 0
      node.obj.visible = at <= step
      if (!node.obj.visible) continue
      const current = at === step
      const m = motionOf.get(id)
      const f = exploded ? 1 : current ? 1 - progress : 0
      const offset = m?.from_offset ?? [0, 0, 0]
      node.obj.position.set(
        node.basePos.x + offset[0] * f,
        node.basePos.y + offset[1] * f,
        node.basePos.z + offset[2] * f,
      )
      const r = m?.from_rotation ?? [0, 0, 0]
      euler.set(r[0] * DEG * f, r[1] * DEG * f, r[2] * DEG * f, 'XYZ')
      node.obj.quaternion.copy(node.baseQuat).multiply(spin.setFromEuler(euler))
      const highlight = current && !exploded && node.pulses
      for (const mat of node.materials) {
        if (highlight) mat.emissive.copy(HIGHLIGHT)
        else mat.emissive.setRGB(0, 0, 0)
        mat.emissiveIntensity = highlight ? pulse : 0
      }
    }
  })

  const current = doc.steps[step]

  // Turns a point in a placement's local frame into the design frame, using its final transform.
  const toDesign = (target: string, at?: Vec3): Vec3 | null => {
    const node = nodes.get(target)
    if (!node) return null
    const p = at ? new THREE.Vector3(...at) : node.center.clone()
    p.applyQuaternion(node.baseQuat).add(node.basePos)
    return [p.x, p.y, p.z]
  }

  return (
    <>
      <primitive object={root} />
      {!exploded &&
        current &&
        createPortal(
          <>
            {(current.callouts ?? []).map((c, i) => {
              const p = toDesign(c.target, c.at)
              return (
                p && (
                  <Html key={`c${step}-${i}`} position={p} center zIndexRange={[20, 0]}>
                    <div className="callout">{c.text}</div>
                  </Html>
                )
              )
            })}
            {(current.dimensions ?? []).map((d, i) => {
              const mid: Vec3 = [(d.from[0] + d.to[0]) / 2, (d.from[1] + d.to[1]) / 2, (d.from[2] + d.to[2]) / 2 + 2]
              return (
                <group key={`d${step}-${i}`}>
                  <Line points={[d.from, d.to]} color="#ff7a45" lineWidth={2} depthTest={false} renderOrder={10} />
                  <Html position={mid} center zIndexRange={[20, 0]}>
                    <div className="dimension">{d.label}</div>
                  </Html>
                </group>
              )
            })}
          </>,
          design,
        )}
    </>
  )
}
