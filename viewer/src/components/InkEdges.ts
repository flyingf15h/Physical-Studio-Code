// "Drawing" look's ink: a screen-space edge pass like Flatpack's manual view. It reads the depth buffer and
// draws a line where depth jumps (outlines) or its slope changes (creases between faces), so a part gets the
// lines a manual illustrator would draw instead of one line per mesh edge (which got busy on detailed parts).
import * as THREE from 'three'
import { BlendFunction, Effect, EffectAttribute } from 'postprocessing'

const fragment = /* glsl */ `
uniform vec3 ink;
uniform float thickness;
uniform float crease;

float dist(vec2 p) { return -getViewZ(readDepth(p)); }

void mainImage(const in vec4 inputColor, const in vec2 uv, const in float depth, out vec4 outputColor) {
  vec2 t = texelSize * thickness;
  float d = dist(uv);
  float l = dist(uv - vec2(t.x, 0.0)), r = dist(uv + vec2(t.x, 0.0));
  float b = dist(uv - vec2(0.0, t.y)), u = dist(uv + vec2(0.0, t.y));
  float jump = max(max(abs(l - d), abs(r - d)), max(abs(b - d), abs(u - d))) / d;  // outline: depth jumps
  float bend = (abs(l + r - 2.0 * d) + abs(b + u - 2.0 * d)) / d;                 // crease: slope changes
  float edge = max(smoothstep(0.012, 0.03, jump), smoothstep(crease, crease * 2.5, bend));
  outputColor = vec4(mix(inputColor.rgb, ink, edge), inputColor.a);
}
`

export class InkEdgesEffect extends Effect {
  constructor({ ink = '#1d1d1f', thickness = 1.2, crease = 0.0025 } = {}) {
    super('InkEdgesEffect', fragment, {
      blendFunction: BlendFunction.NORMAL,
      attributes: EffectAttribute.DEPTH,
      uniforms: new Map<string, THREE.Uniform>([
        ['ink', new THREE.Uniform(new THREE.Color(ink))],
        ['thickness', new THREE.Uniform(thickness)],
        ['crease', new THREE.Uniform(crease)],
      ]),
    })
  }
}
