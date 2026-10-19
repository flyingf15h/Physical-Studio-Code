// Projects on screen 1: the ready-made guides that ship with the viewer (public/<folder>), and the
// designs this browser has opened a guide for ("Your projects"), plus the guides the visitor's own
// AI exported with their key (GET /api/my-projects). The opened ones and the key live in
// localStorage: per browser, and the page still works when storage is blocked.

import { forgetSaved, saveProject } from './api'
import { authToken } from './auth'
import { withParams } from './router'

export interface Project {
  design: string // ?design= value: a public/ folder or "out/<job id>"; "build/<id>" for a breadboard build
  title: string
  prompt?: string
  steps?: number
  openedAt?: number // ms; your projects only
  thumb?: string // a picture of the project for its card, instead of thumbnail()
  level?: Level // ready-made guides: how hard it is
  minutes?: number // ready-made guides: about how long it takes to build
}

export const LEVELS = ['Beginner', 'Intermediate', 'Advanced'] as const
export type Level = (typeof LEVELS)[number]

// The ready-made guides are finished breadboard builds shipped with the server
// (mcp-server/physical_studio/bench/ready/<name>/), opened at /build/<name>.
const PENDULUM_STEPS = 33
export const READY_MADE: Project[] = [
  {
    design: 'build/traffic-light',
    level: 'Beginner',
    minutes: 30,
    title: 'Traffic light',
    prompt: 'Arduino Uno with red, yellow and green LEDs on D11, D10 and D9 and a crosswalk button on D2.',
    steps: 18,
  },
  {
    design: 'build/blink',
    level: 'Beginner',
    minutes: 10,
    title: 'Blink',
    prompt: 'Arduino Uno with a red LED on D13 that turns on and off every second.',
    steps: 6,
  },
  {
    design: 'build/button-led',
    level: 'Beginner',
    minutes: 15,
    title: 'Button and LED',
    prompt: 'A push button on D2 toggles a green LED on D13 on and off.',
    steps: 9,
  },
  {
    design: 'build/led-dimmer',
    level: 'Beginner',
    minutes: 15,
    title: 'LED dimmer',
    prompt: 'A 10k potentiometer on A0 sets the brightness of a yellow LED on PWM pin D9.',
    steps: 9,
  },
  {
    design: 'build/night-light',
    level: 'Beginner',
    minutes: 20,
    title: 'Night light',
    prompt: 'A photoresistor on A0 turns an LED on D9 on when the room gets dark.',
    steps: 10,
  },
  {
    design: 'build/buzzer-melody',
    level: 'Beginner',
    minutes: 15,
    title: 'Buzzer melody',
    prompt: 'Press the button on D2 and a piezo buzzer on D8 plays a short tune.',
    steps: 9,
  },
  {
    design: 'build/rgb-led',
    level: 'Beginner',
    minutes: 20,
    title: 'RGB colour mixer',
    prompt: 'A common-cathode RGB LED on D9, D10 and D11 fades through the rainbow.',
    steps: 9,
  },
  {
    design: 'build/distance-alarm',
    level: 'Intermediate',
    minutes: 30,
    title: 'Distance alarm',
    prompt: 'An HC-SR04 ultrasonic sensor and a buzzer that beeps faster as something gets closer.',
    steps: 15,
  },
  {
    design: 'build/double-pendulum',
    level: 'Advanced',
    minutes: 480,
    title: 'Double inverted pendulum',
    prompt: 'Teensy 4.1, DRV8874 motor driver, two AS5600 encoders and two VL53L0X distance sensors on a breadboard.',
    steps: PENDULUM_STEPS,
    thumb: '/double-pendulum/design.png', // the CAD render (cart, rail and two arms), not the breadboard
  },
]

const KEY = 'physical-studio:projects'
const CONNECT_KEY = 'physical-studio:key' // the personal MCP key from POST /api/connect

export function savedKey(): string | null {
  try {
    return localStorage.getItem(CONNECT_KEY)
  } catch {
    return null
  }
}

export function saveKey(key: string) {
  try {
    localStorage.setItem(CONNECT_KEY, key)
  } catch {
    // storage blocked: the key is shown once, so the visitor can copy it
  }
}

const MAX = 30

// Every export writes design.png (render.py's quick software render). The two ready-made guides'
// thumbnails are screenshots of the guide instead, which look closer to the real thing; rerunning
// their example scripts replaces them with the software render.
/** A build's thumbnail is its last step's picture (the whole circuit) when the step count is known. */
export const thumbnail = (design: string, steps?: number) =>
  design.startsWith('build/') ? `/out/build-${design.slice(6)}/step-${steps || 1}.svg` : `/${design}/design.png`

/** Where a project opens: a build's own page, or the guide. */
export const projectHref = (design: string, code: string | null) =>
  design.startsWith('build/') ? withParams(`/${design}`, { code }) : withParams('/guide', { design, code })

export function yourProjects(): Project[] {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) ?? '[]') as Project[]
    return Array.isArray(list) ? list.filter((p) => p && typeof p.design === 'string') : []
  } catch {
    return []
  }
}

function save(list: Project[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)))
  } catch {
    // storage blocked (private window): the list just isn't kept
  }
}

/** Records a guide you opened, newest first. Ready-made guides and the bundled sample are skipped. */
export function rememberProject(p: Project) {
  if (p.design === 'sample' || READY_MADE.some((r) => r.design === p.design)) return
  save([{ ...p, openedAt: Date.now() }, ...yourProjects().filter((q) => q.design !== p.design)])
  // Logged in: keep it with the account too, so it follows you to other browsers.
  if (authToken())
    void saveProject({ design: p.design, title: p.title, prompt: p.prompt, steps: p.steps }).catch(() => {})
}

export function forgetProject(design: string) {
  save(yourProjects().filter((p) => p.design !== design))
  if (authToken()) void forgetSaved(design).catch(() => {})
}
