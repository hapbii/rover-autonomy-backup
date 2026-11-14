// RA1: Uno + TB6612 x2, driver 1=right, driver 2=left.
// Camera line following frees A0/A1 for ultrasonic TRIG/ECHO. IR is disconnected.
// LF encoder A/B=D2/D4, RF=D6/D7, LR=A3/A4, RR=A2/A5.
// Right PWM=D3, IN1=D9, IN2=D8; left PWM=D5, IN1=D11, IN2=D12.
// Within a driver, PWMA/PWMB and AIN1/BIN1 and AIN2/BIN2 share their signal.
// Both STBY=D10, preserving the existing driver wiring. D13 is unused.
// D10 is an output: NEVER connect an encoder signal to it.
// No dynamic String/new/malloc. Motion requires HELLO, measured CFG, ARM and fresh V.

#include <Arduino.h>
#include <avr/interrupt.h>
#include <util/atomic.h>
#include <math.h>
#include <stdlib.h>
#include <errno.h>

const uint8_t RIGHT_PWM = 3, LEFT_PWM = 5;
const uint8_t RIGHT_IN1 = 9, RIGHT_IN2 = 8, LEFT_IN1 = 11, LEFT_IN2 = 12, STBY = 10;
const uint8_t TRIG = A0, ECHO = A1;
const uint8_t ENC_A[4] = {2, 6, A3, A2};
const uint8_t ENC_B[4] = {4, 7, A4, A5};
const unsigned long COMMAND_TIMEOUT_MS = 250;
const unsigned long CONTROL_US = 20000;
const unsigned long REPORT_MS = 100;

volatile uint32_t counts[4] = {0, 0, 0, 0};
volatile int8_t encoderSign[4] = {1, 1, 1, 1};
volatile uint8_t previousA[4] = {0, 0, 0, 0};
volatile bool previousEcho = false, waitingEcho = false, rangeValid = false;
volatile uint32_t echoRiseUs = 0, rangeSampleMs = 0;
volatile int16_t rangeMm = -1;

bool identified = false, configured = false, armed = false, fault = false;
uint32_t lastCommandMs = 0, lastControlUs = 0, lastReportMs = 0, lastPingMs = 0, sequence = 0;
uint32_t previousCounts[4] = {0, 0, 0, 0};
float cpr = 0, kp = 0, ki = 0, kd = 0, ff = 0;
int maxPwm = 80;
float targets[2] = {0, 0}, measured[2] = {0, 0}, integrals[2] = {0, 0}, previousError[2] = {0, 0};
int applied[2] = {0, 0};
uint32_t stallSince[2] = {0, 0}, reverseSince[2] = {0, 0};
uint32_t wheelStallSince[4] = {0, 0, 0, 0}, wheelReverseSince[4] = {0, 0, 0, 0};
char input[120];
uint8_t inputUsed = 0;
bool inputOverflow = false;

void output(int right, int left) {
  analogWrite(RIGHT_PWM, 0); analogWrite(LEFT_PWM, 0);
  digitalWrite(STBY, LOW);
  digitalWrite(RIGHT_IN1, right > 0); digitalWrite(RIGHT_IN2, right < 0);
  digitalWrite(LEFT_IN1, left > 0); digitalWrite(LEFT_IN2, left < 0);
  digitalWrite(STBY, (right || left) ? HIGH : LOW);
  analogWrite(RIGHT_PWM, abs(right)); analogWrite(LEFT_PWM, abs(left));
  applied[0] = right; applied[1] = left;
}

void stopMotors() {
  armed = false;
  for (uint8_t side = 0; side < 2; ++side) {
    targets[side] = integrals[side] = previousError[side] = 0;
    stallSince[side] = reverseSince[side] = 0;
  }
  for (uint8_t i = 0; i < 4; ++i) wheelStallSince[i] = wheelReverseSince[i] = 0;
  output(0, 0);
}

void setFault(const __FlashStringHelper *reason) {
  stopMotors(); fault = true;
  Serial.print(F("RA1 FAULT ")); Serial.println(reason);
}

void sampleInterruptPins() {
  // One snapshot per port, no slow digitalRead calls inside high-rate encoder ISRs.
  const uint8_t pd = PIND, pc = PINC;
  const uint8_t a[4] = {uint8_t(bool(pd & _BV(2))), uint8_t(bool(pd & _BV(6))), uint8_t(bool(pc & _BV(3))), uint8_t(bool(pc & _BV(2)))};
  const uint8_t b[4] = {uint8_t(bool(pd & _BV(4))), uint8_t(bool(pd & _BV(7))), uint8_t(bool(pc & _BV(4))), uint8_t(bool(pc & _BV(5)))};
  for (uint8_t i = 0; i < 4; ++i) {
    if (a[i] && !previousA[i]) {
      const int8_t step = (b[i] ? 1 : -1) * encoderSign[i];
      counts[i] += step;  // unsigned wrap is intentional; host decodes modulo 2^32.
    }
    previousA[i] = a[i];
  }
  const bool echo = bool(pc & _BV(1));
  if (waitingEcho && echo && !previousEcho) echoRiseUs = micros();
  if (waitingEcho && !echo && previousEcho) {
    const uint32_t width = micros() - echoRiseUs;
    const uint32_t millimeters = width * 343UL / 2000UL;
    rangeValid = width >= 100 && width <= 24000 && millimeters >= 20 && millimeters <= 4000;
    rangeMm = rangeValid ? int16_t(millimeters) : -1;
    rangeSampleMs = millis(); waitingEcho = false;
  }
  previousEcho = echo;
}

ISR(PCINT1_vect) { sampleInterruptPins(); }
ISR(PCINT2_vect) { sampleInterruptPins(); }

bool number(char *text, float &value) {
  if (!text || !*text) return false;
  char *end;
  errno = 0;
  value = strtod(text, &end);
  return *end == '\0' && errno != ERANGE && isfinite(value);
}

void configure(char **parts, uint8_t count) {
  stopMotors();
  if (!identified || count != 11) { setFault(F("bad_config")); return; }
  float values[10];
  for (uint8_t i = 0; i < 10; ++i) if (!number(parts[i + 1], values[i])) { setFault(F("bad_number")); return; }
  if (values[0] < 1 || values[0] > 100000 || values[0] != floor(values[0]) ||
      values[1] < 0 || values[1] > 20 || values[2] < 0 || values[2] > 20 ||
      values[3] < 0 || values[3] > 5 || values[4] < 0 || values[4] > 5 ||
      values[5] < 1 || values[5] > 100 || values[5] != floor(values[5])) {
    setFault(F("config_bounds")); return;
  }
  for (uint8_t i = 6; i < 10; ++i) if (values[i] != 1 && values[i] != -1) { setFault(F("encoder_sign")); return; }
  cpr = values[0]; kp = values[1]; ki = values[2]; kd = values[3]; ff = values[4]; maxPwm = int(values[5]);
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    for (uint8_t i = 0; i < 4; ++i) { encoderSign[i] = int8_t(values[i + 6]); counts[i] = 0; }
  }
  for (uint8_t i = 0; i < 4; ++i) previousCounts[i] = 0;
  configured = true; fault = false;
  Serial.println(F("RA1 CONFIGURED"));
}

void handle(char *text) {
  char *parts[12], *save = NULL;
  uint8_t count = 0;
  char *token = strtok_r(text, " ", &save);
  while (token && count < 12) { parts[count++] = token; token = strtok_r(NULL, " ", &save); }
  if (!count || token) { setFault(F("command_length")); return; }
  if (!strcmp(parts[0], "HELLO") && count == 1) {
    stopMotors(); identified = true; configured = false;
    Serial.println(F("RA1 READY CAMERA_US 3 5 9 8 11 12 10"));
  } else if (!strcmp(parts[0], "STOP") && count == 1) {
    stopMotors(); Serial.println(F("RA1 STOPPED"));
  } else if (!strcmp(parts[0], "CFG")) {
    configure(parts, count);
  } else if (!strcmp(parts[0], "ARM") && count == 1 && configured && !fault && !armed) {
    stopMotors(); armed = true; lastCommandMs = millis();
    Serial.println(F("RA1 ARMED"));
  } else if (!strcmp(parts[0], "V") && count == 3 && armed && !fault) {
    float right, left;
    if (!number(parts[1], right) || !number(parts[2], left) || abs(right) > 80 || abs(left) > 80) {
      setFault(F("target_bounds")); return;
    }
    targets[0] = right; targets[1] = left; lastCommandMs = millis();
  } else if (!strcmp(parts[0], "PING") && count == 1) {
    Serial.println(F("RA1 PONG"));
  } else {
    setFault(F("bad_command"));
  }
}

void control(uint32_t nowUs, uint32_t nowMs) {
  const float dt = (nowUs - lastControlUs) / 1000000.0f;
  if (dt <= 0 || dt > 0.15f) { if (armed) setFault(F("control_timing")); lastControlUs = nowUs; return; }
  lastControlUs = nowUs;
  uint32_t snapshot[4];
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { for (uint8_t i = 0; i < 4; ++i) snapshot[i] = counts[i]; }
  int32_t delta[4];
  for (uint8_t i = 0; i < 4; ++i) { delta[i] = int32_t(snapshot[i] - previousCounts[i]); previousCounts[i] = snapshot[i]; }
  if (cpr > 0) {
    const float right = (float(delta[1]) + float(delta[3])) * 0.5f * 60.0f / (cpr * dt);
    const float left = (float(delta[0]) + float(delta[2])) * 0.5f * 60.0f / (cpr * dt);
    measured[0] = 0.5f * measured[0] + 0.5f * right;
    measured[1] = 0.5f * measured[1] + 0.5f * left;
  }
  if (!armed) { output(0, 0); return; }
  // Two wheels share one PWM, but a failed or reversed encoder on either wheel
  // must not be hidden by averaging the other wheel's speed.
  for (uint8_t i = 0; i < 4; ++i) {
    const uint8_t side = (i == 1 || i == 3) ? 0 : 1;
    const float rpm = float(delta[i]) * 60.0f / (cpr * dt);
    if (abs(targets[side]) > 8 && abs(applied[side]) > 45 && abs(rpm) < 1) {
      if (!wheelStallSince[i]) wheelStallSince[i] = nowMs;
      if (nowMs - wheelStallSince[i] > 500) { setFault(F("individual_encoder_stall")); return; }
    } else wheelStallSince[i] = 0;
    if (abs(rpm) > 10 && targets[side] * rpm < 0) {
      if (!wheelReverseSince[i]) wheelReverseSince[i] = nowMs;
      if (nowMs - wheelReverseSince[i] > 250) { setFault(F("individual_encoder_direction")); return; }
    } else wheelReverseSince[i] = 0;
  }
  int result[2];
  for (uint8_t side = 0; side < 2; ++side) {
    if (abs(targets[side]) < 0.01f) {
      integrals[side] = previousError[side] = 0; result[side] = 0;
      stallSince[side] = reverseSince[side] = 0; continue;
    }
    const float error = targets[side] - measured[side];
    const float candidateIntegral = constrain(integrals[side] + error * dt, -100.0f, 100.0f);
    const float raw = ff * targets[side] + kp * error + ki * candidateIntegral + kd * (error - previousError[side]) / dt;
    const float limited = constrain(raw, -float(maxPwm), float(maxPwm));
    if (raw == limited || raw * error <= 0) integrals[side] = candidateIntegral;
    previousError[side] = error;
    result[side] = int(round(limited));
    if (abs(targets[side]) > 8 && abs(result[side]) > 45 && abs(measured[side]) < 1) {
      if (!stallSince[side]) stallSince[side] = nowMs;
      if (nowMs - stallSince[side] > 500) { setFault(F("encoder_stall")); return; }
    } else stallSince[side] = 0;
    if (abs(measured[side]) > 10 && measured[side] * targets[side] < 0) {
      if (!reverseSince[side]) reverseSince[side] = nowMs;
      if (nowMs - reverseSince[side] > 250) { setFault(F("encoder_direction")); return; }
    } else reverseSince[side] = 0;
  }
  output(result[0], result[1]);
}

void report(uint32_t nowMs) {
  uint32_t snapshot[4], sampleMs;
  int16_t millimeters;
  bool valid;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    for (uint8_t i = 0; i < 4; ++i) snapshot[i] = counts[i];
    millimeters = rangeMm; valid = rangeValid; sampleMs = rangeSampleMs;
  }
  valid = valid && nowMs - sampleMs < 250;
  const uint8_t flags = (armed ? 1 : 0) | (fault ? 2 : 0) | (valid ? 4 : 0);
  Serial.print(F("T ")); Serial.print(sequence++);
  for (uint8_t i = 0; i < 4; ++i) { Serial.print(' '); Serial.print(snapshot[i]); }
  Serial.print(' '); Serial.print(measured[0], 2); Serial.print(' '); Serial.print(measured[1], 2);
  Serial.print(' '); Serial.print(applied[0]); Serial.print(' '); Serial.print(applied[1]);
  Serial.print(' '); Serial.print(valid ? millimeters : -1); Serial.print(' '); Serial.println(flags);
}

void setup() {
  digitalWrite(STBY, LOW); pinMode(STBY, OUTPUT);
  const uint8_t outputs[] = {RIGHT_PWM, LEFT_PWM, RIGHT_IN1, RIGHT_IN2, LEFT_IN1, LEFT_IN2, TRIG};
  for (uint8_t p : outputs) { digitalWrite(p, LOW); pinMode(p, OUTPUT); }
  stopMotors();
  for (uint8_t i = 0; i < 4; ++i) { pinMode(ENC_A[i], INPUT_PULLUP); pinMode(ENC_B[i], INPUT_PULLUP); }
  pinMode(ECHO, INPUT);
  sampleInterruptPins();
  // Interrupt on A changes only; count rising A edges (x1), read B for direction.
  PCMSK0 = 0;                        // no port-B inputs; D10 is STBY output
  PCMSK1 = _BV(3) | _BV(2) | _BV(1); // A3, A2, ultrasonic A1
  PCMSK2 = _BV(2) | _BV(6);          // D2, D6
  PCIFR = _BV(PCIF0) | _BV(PCIF1) | _BV(PCIF2);
  PCICR = _BV(PCIE1) | _BV(PCIE2);
  Serial.begin(115200); Serial.println(F("RA1 BOOT"));
  lastControlUs = micros();
}

void loop() {
  const uint32_t nowMs = millis(), nowUs = micros();
  if (armed && nowMs - lastCommandMs >= COMMAND_TIMEOUT_MS) {
    stopMotors(); Serial.println(F("RA1 TIMEOUT"));
  }
  uint8_t budget = 64;
  while (budget-- && Serial.available()) {
    const char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (inputOverflow) setFault(F("line_overflow"));
      else if (inputUsed) { input[inputUsed] = '\0'; handle(input); }
      inputUsed = 0; inputOverflow = false;
    } else if (inputUsed < sizeof(input) - 1) input[inputUsed++] = c;
    else { inputOverflow = true; stopMotors(); }
  }
  if (nowUs - lastControlUs >= CONTROL_US) control(nowUs, nowMs);
  if (waitingEcho && nowMs - lastPingMs > 30) {
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { waitingEcho = false; rangeValid = false; rangeMm = -1; rangeSampleMs = nowMs; }
  }
  if (nowMs - lastPingMs >= 60) {
    lastPingMs = nowMs;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { previousEcho = digitalRead(ECHO); waitingEcho = true; }
    digitalWrite(TRIG, HIGH); delayMicroseconds(10); digitalWrite(TRIG, LOW);
  }
  if (identified && nowMs - lastReportMs >= REPORT_MS) { lastReportMs = nowMs; report(nowMs); }
}
