# Demo clip: Gemini catches a backwards LED

A 30 to 45 second clip for the pitch and Devpost. It needs a person, a phone and the breadboard; an agent can't record it.

## Setup

- Traffic-light build on the breadboard, wired per `docs/traffic-light-wiring.md` up to the step that places the red LED.
- Open the Build helper on physicalstudio.work, traffic-light card, and go to the red LED step.
- Screen recorder on the laptop (or a second phone filming the screen), and good, even light on the bench. Glare on the LED rim hides the flat side.

## Shots

1. **Step on screen (5 s).** The step picture shows the red LED, long leg (anode) toward the resistor.
2. **Make the mistake (5 s).** Push the red LED in with the legs swapped: short leg (cathode, flat side) toward the resistor. Hold it so the camera sees the leg lengths.
3. **Photo check (10 s).** Take the step photo. Keep the LED and both holes in frame, close enough to read the leg lengths and the flat side of the rim.
4. **Verdict (10 s).** Gemini answers with status `problem` and a specific fix, for example "The LED is in backwards". Hold on the screen long enough to read it (the schema is in `viewer/server/stepCheck.js`).
5. **Fix and pass (10 s).** Flip the LED, take the photo again, and get the pass. Optional: power up and show the lamp test (red, yellow, green).

## Tips

- Do a dry run first. If Gemini misses the swap, move closer and bend the long leg so the difference is obvious.
- Free-tier keys are rate limited; don't burn calls on retakes right before recording.
- Copy the real verdict text into the TODO in `docs/devpost.md` ("paste a real verdict from the demo here").
