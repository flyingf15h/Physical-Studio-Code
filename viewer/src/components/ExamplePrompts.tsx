import './ExamplePrompts.css'

/** The demo prompt; same text as mcp-server/examples/traffic_light.py and schemas/examples/traffic-light.steps.json. */
export const DEMO_PROMPT =
  'Traffic light for an Arduino Uno: red, yellow and green LEDs in a column on the lid, a crosswalk button, USB accessible on the side.'

interface Example {
  title: string
  prompt: string
  uses: string
}

// Only parts from parts/*.json, so every example can actually be built.
const EXAMPLES: Example[] = [
  {
    title: 'Traffic light',
    prompt: DEMO_PROMPT,
    uses: 'Arduino Uno, 3 LEDs (red, yellow, green), 1 button',
  },
  {
    title: 'Reaction timer',
    prompt:
      'Two-player reaction timer for an Arduino Uno in an enclosure: one button and one LED per player on the lid, a buzzer that starts each round, USB accessible on the side.',
    uses: 'Arduino Uno, 2 buttons, 2 LEDs, piezo buzzer',
  },
  {
    title: 'Night-light',
    prompt:
      'Night-light for an Arduino Uno: a row of 6 LEDs on top of the enclosure and one button to cycle brightness, USB accessible on the side for power.',
    uses: 'Arduino Uno, 6 LEDs, 1 button',
  },
  {
    title: 'Kitchen timer',
    prompt:
      'Kitchen timer for an Arduino Uno in an enclosure: 2 buttons to add a minute and start, 3 LEDs showing time left, a buzzer when it ends, USB accessible on the side.',
    uses: 'Arduino Uno, 2 buttons, 3 LEDs, piezo buzzer',
  },
]

/** Clickable starter prompts for the Describe screen; the first is the demo. */
export function ExamplePrompts({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <ul className="examples-list" aria-label="Example prompts">
      {EXAMPLES.map((ex, i) => (
        <li key={ex.title}>
          <button
            type="button"
            className={i === 0 ? 'examples-card examples-demo' : 'examples-card'}
            onClick={() => onPick(ex.prompt)}
          >
            <span className="examples-title">
              {ex.title}
              {i === 0 && <span className="examples-badge">Demo</span>}
            </span>
            <span className="examples-prompt">{ex.prompt}</span>
            <span className="examples-uses">uses: {ex.uses}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
