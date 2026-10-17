// Traffic light with a crosswalk button for an Arduino Uno. Wiring: docs/traffic-light-wiring.md.
// LEDs through 220 ohm resistors, button pulls D2 to ground (INPUT_PULLUP).
// The light rests on green; pressing the button starts the walk cycle: yellow, then red while
// pedestrians cross, then back to green.

const uint8_t RED_PIN = 11;
const uint8_t YELLOW_PIN = 10;
const uint8_t GREEN_PIN = 9;
const uint8_t BUTTON_PIN = 2;

const unsigned long MIN_GREEN_MS = 5000;  // cars get at least this much green between walks
const unsigned long YELLOW_MS = 3000;
const unsigned long WALK_MS = 8000;       // red: pedestrians cross
const unsigned long CLEAR_MS = 3000;      // red blinks: finish crossing

void setLight(uint8_t pin) {
  digitalWrite(RED_PIN, pin == RED_PIN ? HIGH : LOW);
  digitalWrite(YELLOW_PIN, pin == YELLOW_PIN ? HIGH : LOW);
  digitalWrite(GREEN_PIN, pin == GREEN_PIN ? HIGH : LOW);
}

bool pressed() {
  if (digitalRead(BUTTON_PIN) != LOW) return false;
  delay(20);  // debounce
  return digitalRead(BUTTON_PIN) == LOW;
}

void walkCycle() {
  setLight(YELLOW_PIN);
  delay(YELLOW_MS);
  setLight(RED_PIN);
  delay(WALK_MS);
  for (unsigned long t = 0; t < CLEAR_MS; t += 500) {
    digitalWrite(RED_PIN, (t / 500) % 2 ? HIGH : LOW);
    delay(500);
  }
  setLight(GREEN_PIN);
}

void setup() {
  pinMode(RED_PIN, OUTPUT);
  pinMode(YELLOW_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  // Lamp test so a miswired LED shows up right away.
  setLight(RED_PIN);
  delay(400);
  setLight(YELLOW_PIN);
  delay(400);
  setLight(GREEN_PIN);
}

void loop() {
  unsigned long greenSince = millis();
  while (!pressed()) {}
  // A press during the minimum green is remembered and served once it runs out.
  while (millis() - greenSince < MIN_GREEN_MS) {}
  walkCycle();
}
