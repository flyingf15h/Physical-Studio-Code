// Parts search as you type: "le" -> LED 5 mm first, "but" -> the 6 mm push button, "pot" -> the 10k
// potentiometer. Each word you type must start a word of the part's name, id or one of its everyday
// names (ALIASES); among matches, parts people use most (COMMON) come first. Used by "Parts I have" on
// the Dashboard and the parts library panel.
import type { PartSummary } from './api'

// Most used first: the part a beginner most likely means when several match.
const COMMON = [
  'led-5mm', 'resistor-220', 'push-button-6mm', 'arduino-uno', 'breadboard-half', 'servo-sg90',
  'potentiometer-10k', 'buzzer-active-12mm', 'resistor-10k', 'hc-sr04', 'esp32-devkit-v1', 'arduino-nano',
  'led-rgb-5mm', 'oled-ssd1306-128x64', 'lcd-1602-i2c', 'dht11', 'pir-hc-sr501', 'photoresistor-ldr',
  'raspberry-pi-pico', 'breadboard-full', 'resistor-1k', 'led-3mm', 'piezo-buzzer', 'tt-gearmotor',
  'l298n-driver', 'relay-module-1ch', 'battery-9v', 'battery-holder-4xaa', 'neopixel-ring-12',
  'stepper-28byj48', 'uln2003-driver', 'mpu6050-gy521', 'joystick-ky023', 'rotary-encoder-ky040',
  'slide-switch-spdt', 'transistor-2n2222', 'diode-1n4007', 'capacitor-ceramic-100nf',
  'capacitor-electrolytic-100uf', 'ds18b20', 'dht22', 'servo-mg996r', 'nema17-stepper-40', 'a4988-driver',
  'raspberry-pi-4', 'resistor-330', 'resistor-4k7', 'arduino-mega-2560', 'battery-18650', 'tp4056-charger',
  'speaker-28mm', 'max7219-matrix', 'xiao-esp32c3', 'toggle-switch-mts102', 'barrel-jack-dc005', 'led-10mm',
  'm3-screw-10mm', 'm3-screw-6mm',
]

// Everyday names for parts whose library name doesn't say them.
const ALIASES: Record<string, string> = {
  'led-5mm': 'light diode lamp red green',
  'led-3mm': 'light diode lamp',
  'led-rgb-5mm': 'light colour color',
  'push-button-6mm': 'button switch tactile tact pushbutton',
  'tactile-button-12mm': 'button switch tactile pushbutton',
  'potentiometer-10k': 'pot knob dial variable resistor',
  'trimpot-10k': 'pot trimmer variable resistor',
  'buzzer-active-12mm': 'beeper sound speaker alarm',
  'piezo-buzzer': 'beeper sound speaker',
  'hc-sr04': 'ultrasonic distance sonar range',
  'vl53l0x-board': 'distance laser tof time of flight range',
  'servo-sg90': 'motor micro servo',
  'servo-mg996r': 'motor servo metal gear',
  'tt-gearmotor': 'motor dc yellow gear robot',
  'dc-motor-130': 'motor dc hobby',
  'stepper-28byj48': 'motor stepper',
  'nema17-stepper-40': 'motor stepper 3d printer',
  'oled-ssd1306-128x64': 'screen display',
  'lcd-1602-i2c': 'screen display 16x2 character',
  'tm1637-4digit': 'display clock seven segment 7',
  'seven-segment-1digit': 'display 7 segment digit',
  'dht11': 'temperature humidity sensor',
  'dht22': 'temperature humidity sensor',
  'ds18b20': 'temperature sensor waterproof',
  'thermistor-ntc-10k': 'temperature',
  'photoresistor-ldr': 'light sensor photocell',
  'pir-hc-sr501': 'motion sensor infrared',
  'mpu6050-gy521': 'gyro accelerometer imu tilt motion',
  'relay-module-1ch': 'switch mains',
  'l298n-driver': 'motor driver h bridge',
  'a4988-driver': 'stepper driver',
  'drv8825-driver': 'stepper driver',
  'uln2003-driver': 'stepper driver',
  'esp32-devkit-v1': 'wifi bluetooth microcontroller board',
  'esp8266-nodemcu': 'wifi microcontroller board',
  'arduino-uno': 'microcontroller board',
  'arduino-nano': 'microcontroller board',
  'raspberry-pi-pico': 'microcontroller board rp2040',
  'teensy-41': 'microcontroller board',
  'battery-9v': 'power',
  'battery-holder-4xaa': 'power aa batteries',
  'psu-12v-2a': 'power supply adapter wall',
  'regulator-7805': 'voltage power 5v',
  'buck-12v-3v3': 'voltage regulator power step down',
  'neopixel-ring-12': 'led ring addressable ws2812 rgb',
  'joystick-ky023': 'thumbstick analog',
  'rotary-encoder-ky040': 'knob dial',
  'keypad-4x4': 'buttons keys membrane',
  'rfid-rc522': 'nfc card reader',
  'ir-receiver-vs1838b': 'infrared remote',
  'hc-05-bluetooth': 'wireless serial',
  'microsd-module': 'sd card storage',
  'soil-moisture-sensor': 'plant water',
  'sound-sensor-ky038': 'microphone mic noise',
  'touch-sensor-ttp223': 'capacitive button',
  'transistor-2n2222': 'npn',
  'mosfet-irlz44n': 'transistor switch',
  'diode-1n4007': 'rectifier',
  'capacitor-ceramic-100nf': 'cap decoupling',
  'capacitor-electrolytic-100uf': 'cap',
  'breadboard-half': 'protoboard solderless',
  'breadboard-full': 'protoboard solderless',
  'slide-switch-spdt': 'on off power switch',
  'limit-switch-kw12': 'endstop micro switch',
  'led-10mm': 'light diode lamp big',
  'arduino-mega-2560': 'microcontroller board',
  'xiao-esp32c3': 'wifi bluetooth microcontroller board tiny',
  'battery-18650': 'lithium lipo li-ion cell power rechargeable',
  'tp4056-charger': 'lithium battery charger usb',
  'speaker-28mm': 'sound audio',
  'vibration-motor-1027': 'buzz haptic rumble motor',
  'toggle-switch-mts102': 'on off switch lever',
  'barrel-jack-dc005': 'power socket dc jack adapter',
  'bmp280-module': 'barometer altitude air pressure temperature sensor',
  'max7219-matrix': 'led matrix display dot',
  'mq2-gas-sensor': 'smoke gas air quality sensor',
}

const rank = new Map(COMMON.map((id, i) => [id, i]))

function words(p: PartSummary): string[] {
  return `${p.name} ${p.id} ${ALIASES[p.id] ?? ''}`
    .toLowerCase()
    .split(/[^a-z0-9.]+/)
    .filter(Boolean)
}

/** "3 le" -> { count: "3", text: "le" }: a quantity typed before the part. */
export function splitCount(text: string): { count: string; text: string } {
  const m = text.trim().match(/^(\d{1,3})\s*(?:x|×)?\s+(.*)$/i)
  return m ? { count: m[1], text: m[2] } : { count: '', text: text.trim() }
}

/** Library parts matching what's typed so far, best first. */
export function searchParts(library: PartSummary[], typed: string, limit = 6): PartSummary[] {
  const terms = splitCount(typed)
    .text.toLowerCase()
    .split(/[^a-z0-9.]+/)
    .filter(Boolean)
  if (!terms.length) return []
  const scored: { p: PartSummary; s: number }[] = []
  for (const p of library) {
    const ws = words(p)
    const name = p.name.toLowerCase()
    let s = 0
    let ok = true
    for (const t of terms) {
      if (ws.includes(t)) s += 3 // a whole word
      else if (ws.some((w) => w.startsWith(t))) s += name.startsWith(t) ? 2.5 : 2 // the start of a word
      else if (t.length >= 4 && name.includes(t)) s += 1 // inside a word ("8266")
      else {
        ok = false
        break
      }
    }
    if (!ok) continue
    s += p.mine ? 2 : 0 // the signed-in user's own BOM
    s += rank.has(p.id) ? 2 - rank.get(p.id)! / COMMON.length : 0 // common parts first
    scored.push({ p, s })
  }
  return scored
    .sort((a, b) => b.s - a.s || a.p.name.localeCompare(b.p.name))
    .slice(0, limit)
    .map(({ p }) => p)
}
