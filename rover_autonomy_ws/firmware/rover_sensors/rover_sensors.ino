// RA2 sensor-only Uno firmware. NEVER configures motor/STBY outputs.
// Encoders LF RF LR RR: A=2,6,A3,A2; B=4,7,A4,A5.
// Sonar TRIG=A0 ECHO=A1; IR left->right D8 D9 D10 D11 D12.
#include <Arduino.h>
#include <avr/interrupt.h>
#include <util/atomic.h>
#include <stdlib.h>
#include <string.h>

const uint8_t ENC_A[4] = {2, 6, A3, A2};
const uint8_t ENC_B[4] = {4, 7, A4, A5};
const uint8_t IR_PINS[5] = {8, 9, 10, 11, 12};
const uint8_t TRIG = A0, ECHO = A1;
volatile uint32_t counts[4] = {0, 0, 0, 0};
volatile int8_t signs[4] = {1, 1, 1, 1};
volatile uint8_t previousA[4] = {0, 0, 0, 0};
volatile bool previousEcho = false, waitingEcho = false, rangeValid = false;
volatile uint32_t echoRiseUs = 0, rangeSampleMs = 0;
volatile int16_t rangeMm = -1;
bool identified = false, configured = false, overflow = false;
uint32_t sequence = 0, lastPingMs = 0, lastReportMs = 0;
char input[80];
uint8_t inputUsed = 0;

void sampleInterruptPins() {
  const uint8_t pd = PIND, pc = PINC;
  const uint8_t a[4] = {uint8_t(bool(pd & _BV(2))), uint8_t(bool(pd & _BV(6))),
                       uint8_t(bool(pc & _BV(3))), uint8_t(bool(pc & _BV(2)))};
  const uint8_t b[4] = {uint8_t(bool(pd & _BV(4))), uint8_t(bool(pd & _BV(7))),
                       uint8_t(bool(pc & _BV(4))), uint8_t(bool(pc & _BV(5)))};
  for (uint8_t i = 0; i < 4; ++i) {
    if (a[i] && !previousA[i]) counts[i] += (b[i] ? 1 : -1) * signs[i];
    previousA[i] = a[i];
  }
  const bool echo = bool(pc & _BV(1));
  if (waitingEcho && echo && !previousEcho) echoRiseUs = micros();
  if (waitingEcho && !echo && previousEcho) {
    const uint32_t width = micros() - echoRiseUs;
    const uint32_t mm = width * 343UL / 2000UL;
    rangeValid = width >= 100 && width <= 24000 && mm >= 20 && mm <= 4000;
    rangeMm = rangeValid ? int16_t(mm) : -1;
    rangeSampleMs = millis();
    waitingEcho = false;
  }
  previousEcho = echo;
}

ISR(PCINT1_vect) { sampleInterruptPins(); }
ISR(PCINT2_vect) { sampleInterruptPins(); }

void handle(char *line) {
  if (!strcmp(line, "HELLO")) {
    identified = true; configured = false;
    Serial.println(F("RA2 READY ENC_2_4_6_7_A3_A4_A2_A5 US_A0_A1 IR_8_9_10_11_12"));
  } else if (!strncmp(line, "CFG ", 4) && identified) {
    char *save = NULL;
    char *token = strtok_r(line + 4, " ", &save);
    int8_t candidate[4];
    for (uint8_t i = 0; i < 4; ++i) {
      if (!token || (strcmp(token, "1") && strcmp(token, "-1"))) {
        configured = false; Serial.println(F("RA2 ERROR signs")); return;
      }
      candidate[i] = !strcmp(token, "1") ? 1 : -1;
      token = strtok_r(NULL, " ", &save);
    }
    if (token) { configured = false; Serial.println(F("RA2 ERROR fields")); return; }
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
      for (uint8_t i = 0; i < 4; ++i) { signs[i] = candidate[i]; counts[i] = 0; }
    }
    configured = true;
    Serial.println(F("RA2 CONFIGURED"));
  } else {
    configured = false; Serial.println(F("RA2 ERROR command"));
  }
}

void report(uint32_t nowMs) {
  uint32_t snapshot[4], stamp, sampled;
  int16_t mm;
  bool valid;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    stamp = micros();
    for (uint8_t i = 0; i < 4; ++i) snapshot[i] = counts[i];
    mm = rangeMm; valid = rangeValid; sampled = rangeSampleMs;
  }
  valid = valid && nowMs - sampled < 150;
  uint8_t ir = 0;
  for (uint8_t i = 0; i < 5; ++i) if (digitalRead(IR_PINS[i])) ir |= _BV(i);
  Serial.print(F("S ")); Serial.print(sequence++);
  Serial.print(' '); Serial.print(stamp);
  for (uint8_t i = 0; i < 4; ++i) { Serial.print(' '); Serial.print(snapshot[i]); }
  Serial.print(' '); Serial.print(valid ? mm : -1);
  Serial.print(' '); Serial.print(valid ? 4 : 0);
  Serial.print(' '); Serial.println(ir);
}

void setup() {
  digitalWrite(TRIG, LOW); pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  for (uint8_t i = 0; i < 4; ++i) {
    pinMode(ENC_A[i], INPUT_PULLUP); pinMode(ENC_B[i], INPUT_PULLUP);
  }
  for (uint8_t i = 0; i < 5; ++i) pinMode(IR_PINS[i], INPUT_PULLUP);
  sampleInterruptPins();
  PCMSK0 = 0;
  PCMSK1 = _BV(3) | _BV(2) | _BV(1); // A3/A2 encoder A, A1 echo
  PCMSK2 = _BV(2) | _BV(6);          // D2/D6 encoder A
  PCIFR = _BV(PCIF0) | _BV(PCIF1) | _BV(PCIF2);
  PCICR = _BV(PCIE1) | _BV(PCIE2);
  Serial.begin(115200); Serial.println(F("RA2 BOOT"));
}

void loop() {
  const uint32_t nowMs = millis();
  uint8_t budget = 64;
  while (budget-- && Serial.available()) {
    const char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflow) { configured = false; Serial.println(F("RA2 ERROR overflow")); }
      else if (inputUsed) { input[inputUsed] = '\0'; handle(input); }
      inputUsed = 0; overflow = false;
    } else if (inputUsed < sizeof(input) - 1) input[inputUsed++] = c;
    else { overflow = true; configured = false; }
  }
  if (waitingEcho && nowMs - lastPingMs > 30) {
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
      waitingEcho = false; rangeValid = false; rangeMm = -1; rangeSampleMs = nowMs;
    }
  }
  if (nowMs - lastPingMs >= 60) {
    lastPingMs = nowMs;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { previousEcho = digitalRead(ECHO); waitingEcho = true; }
    digitalWrite(TRIG, HIGH); delayMicroseconds(10); digitalWrite(TRIG, LOW);
  }
  if (configured && nowMs - lastReportMs >= 50) { lastReportMs = nowMs; report(nowMs); }
}
