// Simon memory game for an Arduino Uno. Wiring: docs/simon-wiring.md.
// Buttons pull to ground (INPUT_PULLUP), LEDs through 220 ohm resistors, piezo on D12.

const uint8_t BUTTON_PINS[4] = {2, 3, 4, 5};    // red, green, blue, yellow
const uint8_t LED_PINS[4] = {8, 9, 10, 11};
const uint16_t TONES[4] = {310, 415, 209, 252};  // the original Simon notes, in Hz
const uint8_t BUZZER_PIN = 12;
const uint8_t MAX_ROUNDS = 32;
const unsigned long INPUT_TIMEOUT_MS = 3000;

uint8_t sequence[MAX_ROUNDS];
uint8_t rounds = 0;

void show(uint8_t color, unsigned int ms) {
  digitalWrite(LED_PINS[color], HIGH);
  tone(BUZZER_PIN, TONES[color], ms);
  delay(ms);
  digitalWrite(LED_PINS[color], LOW);
  noTone(BUZZER_PIN);
}

void allLeds(bool on) {
  for (uint8_t i = 0; i < 4; i++) digitalWrite(LED_PINS[i], on ? HIGH : LOW);
}

// Waits for a press and its release; returns the color, or -1 on timeout.
int8_t readButton(unsigned long timeoutMs) {
  unsigned long start = millis();
  while (millis() - start < timeoutMs) {
    for (uint8_t i = 0; i < 4; i++) {
      if (digitalRead(BUTTON_PINS[i]) == LOW) {
        delay(20);  // debounce
        digitalWrite(LED_PINS[i], HIGH);
        tone(BUZZER_PIN, TONES[i]);
        while (digitalRead(BUTTON_PINS[i]) == LOW) {}
        noTone(BUZZER_PIN);
        digitalWrite(LED_PINS[i], LOW);
        delay(20);
        return i;
      }
    }
  }
  return -1;
}

// LED chase until any button is pressed, so the game starts on a press.
void attract() {
  uint8_t i = 0;
  while (true) {
    digitalWrite(LED_PINS[i], HIGH);
    for (uint8_t t = 0; t < 15; t++) {
      for (uint8_t b = 0; b < 4; b++) {
        if (digitalRead(BUTTON_PINS[b]) == LOW) {
          allLeds(false);
          while (digitalRead(BUTTON_PINS[b]) == LOW) {}
          delay(400);
          return;
        }
      }
      delay(10);
    }
    digitalWrite(LED_PINS[i], LOW);
    i = (i + 1) % 4;
  }
}

void gameOver() {
  tone(BUZZER_PIN, 42, 1000);
  for (uint8_t i = 0; i < 3; i++) {
    allLeds(true);
    delay(250);
    allLeds(false);
    delay(250);
  }
  delay(500);
}

void win() {
  for (uint8_t n = 0; n < 3; n++) {
    for (uint8_t i = 0; i < 4; i++) show(i, 80);
  }
  delay(500);
}

void setup() {
  for (uint8_t i = 0; i < 4; i++) {
    pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    pinMode(LED_PINS[i], OUTPUT);
  }
  pinMode(BUZZER_PIN, OUTPUT);
  randomSeed(analogRead(A0));  // A0 is left floating, which gives a different game each time
}

void loop() {
  attract();
  rounds = 0;
  while (true) {
    sequence[rounds++] = random(4);
    unsigned int speed = rounds < 6 ? 420 : rounds < 14 ? 320 : 220;
    for (uint8_t i = 0; i < rounds; i++) {
      show(sequence[i], speed);
      delay(speed / 3);
    }
    for (uint8_t i = 0; i < rounds; i++) {
      if (readButton(INPUT_TIMEOUT_MS) != sequence[i]) {
        gameOver();
        return;
      }
    }
    if (rounds == MAX_ROUNDS) {
      win();
      return;
    }
    delay(600);
  }
}
