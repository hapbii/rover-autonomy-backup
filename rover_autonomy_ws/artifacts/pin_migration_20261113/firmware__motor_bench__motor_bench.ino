// Uno + TB6612, verified user wiring. Open-loop PWM test; no encoder input.
// Serial: HELLO / ARM / M <signed PWM A> <signed PWM B> / STOP
// Motors remain off until a HELLO and ARM exchange. Lost commands stop in 250 ms.
#include <Arduino.h>
#include <stdlib.h>
#include <errno.h>

const uint8_t PWMA = 3, PWMB = 5;
const uint8_t AIN1 = 9, AIN2 = 8, BIN1 = 11, BIN2 = 12, STBY = 10;
const int MAX_PWM = 80;
const unsigned long WATCHDOG_MS = 250, SESSION_MS = 8000;
int outputA = 0, outputB = 0;
bool identified = false, armed = false;
unsigned long lastCommand = 0, armedAt = 0, lastReport = 0;
char line[48];
uint8_t used = 0;
bool overflowed = false;

void output(int a, int b) {
  // PWM off before changing direction. A stopped channel uses PWM=0.
  analogWrite(PWMA, 0); analogWrite(PWMB, 0);
  digitalWrite(STBY, LOW);
  digitalWrite(AIN1, a > 0); digitalWrite(AIN2, a < 0);
  digitalWrite(BIN1, b > 0); digitalWrite(BIN2, b < 0);
  digitalWrite(STBY, (a != 0 || b != 0) ? HIGH : LOW);
  analogWrite(PWMA, abs(a)); analogWrite(PWMB, abs(b));
  outputA = a; outputB = b;
}

void stopMotors() { output(0, 0); armed = false; }

void report() {
  Serial.print(F("T ")); Serial.print(outputA);
  Serial.print(' '); Serial.println(outputB);
}

bool parsePwm(char *text, int &a, int &b) {
  char *end;
  errno = 0;
  long first = strtol(text, &end, 10);
  if (end == text || errno == ERANGE || first < -MAX_PWM || first > MAX_PWM || *end != ' ') return false;
  text = end;
  errno = 0;
  long second = strtol(text, &end, 10);
  if (end == text || errno == ERANGE || second < -MAX_PWM || second > MAX_PWM || *end != '\0') return false;
  a = (int)first; b = (int)second;
  return true;
}

void handle(char *text) {
  if (!strcmp(text, "HELLO")) {
    stopMotors(); identified = true;
    Serial.println(F("EM2 READY 3 5 9 8 11 12 10"));
  } else if (!strcmp(text, "STOP")) {
    stopMotors(); Serial.println(F("EM2 STOPPED")); report();
  } else if (!strcmp(text, "ARM") && identified && !armed) {
    output(0, 0); armed = true; lastCommand = armedAt = millis();
    Serial.println(F("EM2 ARMED")); report();
  } else if (text[0] == 'M' && text[1] == ' ' && armed) {
    int a, b;
    if (!parsePwm(text + 2, a, b)) {
      stopMotors(); Serial.println(F("EM2 ERROR bad_pwm")); return;
    }
    output(a, b); lastCommand = millis(); report();
  } else {
    stopMotors(); Serial.println(F("EM2 ERROR bad_command"));
  }
}

void setup() {
  digitalWrite(STBY, LOW); pinMode(STBY, OUTPUT);
  const uint8_t pins[] = {PWMA, PWMB, AIN1, AIN2, BIN1, BIN2};
  for (uint8_t p : pins) { digitalWrite(p, LOW); pinMode(p, OUTPUT); }
  stopMotors();
  Serial.begin(115200);
  Serial.println(F("EM2 BOOT"));
}

void loop() {
  unsigned long now = millis();
  if (armed && ((unsigned long)(now - lastCommand) >= WATCHDOG_MS ||
                (unsigned long)(now - armedAt) >= SESSION_MS)) {
    stopMotors(); Serial.println(F("EM2 TIMEOUT")); report();
  }
  // Bounded work per loop so malformed input cannot starve the watchdog.
  uint8_t budget = 64;
  while (budget-- && Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflowed) { stopMotors(); Serial.println(F("EM2 ERROR line_too_long")); }
      else if (used) { line[used] = '\0'; handle(line); }
      used = 0; overflowed = false;
    } else if (used < sizeof(line) - 1) line[used++] = c;
    else { overflowed = true; stopMotors(); }
  }
  if (identified && (unsigned long)(now - lastReport) >= 50) {
    lastReport = now; report();
  }
}
