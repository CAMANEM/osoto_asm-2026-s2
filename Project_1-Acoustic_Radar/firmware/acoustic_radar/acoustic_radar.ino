/*
 * Radar acústico MVP — v5.1 (onset + calibración)
 *
 * Usa el PRIMER cruce de umbral tras el ringing (flanco), no el máximo
 * absoluto (que llega tarde y “alarga” la distancia).
 *
 * Calibración rápida:
 *   1) Pon objeto a 50 cm medidos con cinta
 *   2) Anota distancia_cm_raw
 *   3) Ajusta CAL_OFFSET_CM = 50 - distancia_cm_raw
 *      (ej: si lee 70 → CAL_OFFSET_CM = -20)
 *
 * Comandos: M | L | T | S | D
 */

static const uint8_t  PIN_SPEAKER = 9;
static const uint8_t  PIN_MIC     = A0;

static const float    FS_HZ         = 8000.0f;
static const uint16_t SAMPLE_US     = 125;
static const uint16_t N_SAMPLES     = 200;
static const unsigned F0_HZ         = 1000;
static const uint16_t PULSE_SAMPLES = 10;
static const float    VS_MPS        = 343.0f;
static const uint16_t MAX_ECHO      = 56;   // ~120 cm

// >>> CALIBRACIÓN: edita esto tras una medida a 50 cm conocidos <<<
static const float    CAL_OFFSET_CM = 0.0f;   // ej. -20.0 si siempre lee ~20 cm de más
static const float    CAL_SCALE     = 1.0f;   // normalmente 1.0

static int16_t samples[N_SAMPLES];
static bool has_capture = false;

static void speedUpAdc() {
  ADCSRA = (ADCSRA & 0xF8) | 0x04;
}

static int16_t abs16(int16_t v) {
  return (v < 0) ? (int16_t)(-v) : v;
}

static int16_t maxAbsRange(uint16_t a, uint16_t b) {
  if (b >= N_SAMPLES) b = N_SAMPLES - 1;
  if (a > b) return 0;
  int16_t m = 0;
  for (uint16_t i = a; i <= b; i++) {
    int16_t v = abs16(samples[i]);
    if (v > m) m = v;
  }
  return m;
}

static void removeDc() {
  long sum = 0;
  for (uint16_t i = 0; i < N_SAMPLES; i++) sum += samples[i];
  int16_t mean = (int16_t)(sum / (long)N_SAMPLES);
  for (uint16_t i = 0; i < N_SAMPLES; i++) {
    samples[i] = (int16_t)(samples[i] - mean);
  }
}

static void transmitAndAcquire() {
  unsigned long t0 = micros();
  tone(PIN_SPEAKER, F0_HZ);
  for (uint16_t i = 0; i < N_SAMPLES; i++) {
    unsigned long due = t0 + (unsigned long)i * SAMPLE_US;
    while ((long)(micros() - due) < 0) {}
    samples[i] = (int16_t)analogRead(PIN_MIC);
    if (i + 1 == PULSE_SAMPLES) {
      noTone(PIN_SPEAKER);
      digitalWrite(PIN_SPEAKER, LOW);
    }
  }
  noTone(PIN_SPEAKER);
  digitalWrite(PIN_SPEAKER, LOW);
  has_capture = true;
}

static int measureDelta(int reads) {
  int mn = 1024, mx = 0;
  for (int i = 0; i < reads; i++) {
    int v = analogRead(PIN_MIC);
    if (v < mn) mn = v;
    if (v > mx) mx = v;
  }
  return mx - mn;
}

static void listenDiag() {
  Serial.println(F("--- Diagnostico L ---"));
  noTone(PIN_SPEAKER);
  digitalWrite(PIN_SPEAKER, LOW);
  delay(30);
  int quiet = measureDelta(600);
  tone(PIN_SPEAKER, F0_HZ);
  delay(80);
  int loud = measureDelta(800);
  noTone(PIN_SPEAKER);
  digitalWrite(PIN_SPEAKER, LOW);
  Serial.print(F("silencio delta="));
  Serial.println(quiet);
  Serial.print(F("con_tono delta="));
  Serial.println(loud);
}

static uint16_t findQuietStart(int16_t ampTx) {
  int16_t thr = (int16_t)(ampTx / 5);
  if (thr < 15) thr = 15;
  uint8_t ok = 0;
  for (uint16_t i = PULSE_SAMPLES; i < MAX_ECHO; i++) {
    if (abs16(samples[i]) < thr) {
      ok++;
      if (ok >= 3) return (uint16_t)(i + 1);
    } else {
      ok = 0;
    }
  }
  return (uint16_t)(PULSE_SAMPLES + 12);
}

// Primer flanco tras silencio (mejor ToF que el máximo)
static bool findOnset(uint16_t from, uint16_t to, int16_t thr, uint16_t &onsetOut) {
  if (from >= to) return false;
  for (uint16_t i = from; i <= to; i++) {
    if (abs16(samples[i]) >= thr) {
      onsetOut = i;
      return true;
    }
  }
  return false;
}

static void runMeasurement() {
  Serial.println(F("--- Medicion ---"));
  transmitAndAcquire();
  removeDc();

  int16_t amp_tx = maxAbsRange(0, PULSE_SAMPLES);
  if (amp_tx < 40) {
    Serial.println(F("NO_ECHO: TX debil"));
    Serial.println(F("OK"));
    return;
  }

  uint16_t quietAt = findQuietStart(amp_tx);
  if (quietAt >= MAX_ECHO - 2) {
    Serial.println(F("NO_ECHO: ringing largo — baja pot"));
    Serial.println(F("OK"));
    return;
  }

  // Umbral de eco: entre cola y una fracción del TX
  int16_t amp_tail = maxAbsRange((uint16_t)(MAX_ECHO + 1), N_SAMPLES - 1);
  int16_t thr = (int16_t)(amp_tail + 12);
  int16_t thr2 = (int16_t)(amp_tx / 8);
  if (thr2 > thr) thr = thr2;
  if (thr < 22) thr = 22;

  uint16_t onset = 0;
  if (!findOnset((uint16_t)(quietAt + 1), MAX_ECHO, thr, onset)) {
    Serial.print(F("quiet_at="));
    Serial.println(quietAt);
    Serial.print(F("thr="));
    Serial.println(thr);
    Serial.println(F("NO_ECHO: sin flanco. Acerca pared / sube poco pot."));
    Serial.println(F("OK"));
    return;
  }

  float tau_s = (float)onset / FS_HZ;
  float dist_raw_cm = (VS_MPS * tau_s) / 2.0f * 100.0f;
  float dist_cm = CAL_SCALE * dist_raw_cm + CAL_OFFSET_CM;

  Serial.print(F("amp_tx="));
  Serial.println(amp_tx);
  Serial.print(F("quiet_at="));
  Serial.println(quietAt);
  Serial.print(F("thr="));
  Serial.println(thr);
  Serial.print(F("onset_sample="));
  Serial.println(onset);
  Serial.print(F("tau_ms="));
  Serial.println(tau_s * 1000.0f, 3);
  Serial.print(F("distancia_cm_raw="));
  Serial.println(dist_raw_cm, 1);
  Serial.print(F("distancia_cm="));
  Serial.println(dist_cm, 1);
  Serial.print(F("distancia_m="));
  Serial.println(dist_cm / 100.0f, 3);
  Serial.println(F("OK"));
}

static void dumpCsv() {
  if (!has_capture) {
    Serial.println(F("ERR: M primero"));
    return;
  }
  Serial.println(F("BEGIN_SAMPLES"));
  for (uint16_t i = 0; i < N_SAMPLES; i++) Serial.println(samples[i]);
  Serial.println(F("END_SAMPLES"));
}

void setup() {
  pinMode(PIN_SPEAKER, OUTPUT);
  digitalWrite(PIN_SPEAKER, LOW);
  speedUpAdc();
  Serial.begin(9600);
  Serial.println(F("Radar MVP v5.1 onset+cal"));
  Serial.println(F("1) Mide a 50cm cinta  2) Ajusta CAL_OFFSET_CM"));
  tone(PIN_SPEAKER, F0_HZ);
  delay(300);
  noTone(PIN_SPEAKER);
}

void loop() {
  if (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == 'M' || c == 'm') runMeasurement();
    else if (c == 'L' || c == 'l') listenDiag();
    else if (c == 'T' || c == 't') {
      tone(PIN_SPEAKER, F0_HZ);
      Serial.println(F("Tono ON"));
    } else if (c == 'S' || c == 's') {
      noTone(PIN_SPEAKER);
      digitalWrite(PIN_SPEAKER, LOW);
      Serial.println(F("OFF"));
    } else if (c == 'D' || c == 'd') dumpCsv();
    while (Serial.available() > 0) {
      if ((char)Serial.read() == '\n') break;
    }
  }
}
