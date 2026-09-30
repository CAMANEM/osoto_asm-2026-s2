/*
 * Radar acústico MVP — v4 (pulso corto)
 *
 * Con TPA3110 el TX es fuerte y “ensucia” muchos ms.
 * Un pulso largo (8 ms) solapa el eco a <1 m → distancias falsas.
 *
 * v4: pulso ~1.5 ms, busca eco DESPUÉS del TX + guardia.
 * Prueba válida: PARED/caja a 50 cm y luego 80 cm (no 5 cm).
 *
 * Comandos: M medir | L diag | T tono | S off | D dump
 */

static const uint8_t  PIN_SPEAKER = 9;
static const uint8_t  PIN_MIC     = A0;

static const float    FS_HZ         = 8000.0f;
static const uint16_t SAMPLE_US     = 125;
static const uint16_t N_SAMPLES     = 200;   // 25 ms
static const unsigned F0_HZ         = 1000;
static const uint16_t PULSE_SAMPLES = 10;    // 1.25 ms
static const uint16_t RING_GUARD    = 4;     // 0.5 ms
static const float    VS_MPS        = 343.0f;

// ~30 cm .. 100 cm  (lag 14 → 0.30 m; lag 47 → 1.00 m)
static const uint16_t ECHO_LO = 14;
static const uint16_t ECHO_HI = 48;

static int16_t samples[N_SAMPLES];
static bool has_capture = false;

static void speedUpAdc() {
  ADCSRA = (ADCSRA & 0xF8) | 0x04;
}

static int16_t maxAbsRange(uint16_t a, uint16_t b) {
  if (b >= N_SAMPLES) b = N_SAMPLES - 1;
  if (a > b) return 0;
  int16_t m = 0;
  for (uint16_t i = a; i <= b; i++) {
    int16_t v = samples[i];
    if (v < 0) v = (int16_t)(-v);
    if (v > m) m = v;
  }
  return m;
}

static uint16_t argmaxAbsRange(uint16_t a, uint16_t b) {
  if (b >= N_SAMPLES) b = N_SAMPLES - 1;
  int16_t best = -1;
  uint16_t idx = a;
  for (uint16_t i = a; i <= b; i++) {
    int16_t v = samples[i];
    if (v < 0) v = (int16_t)(-v);
    if (v > best) {
      best = v;
      idx = i;
    }
  }
  return idx;
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
  if (loud < 80) Serial.println(F("TX debil: sube un poco el pot del amp"));
  else Serial.println(F("OK acustico. Prueba pared a 50cm y 80cm."));
}

static void runMeasurement() {
  Serial.println(F("--- Medicion ---"));
  transmitAndAcquire();
  removeDc();

  uint16_t searchLo = (uint16_t)(PULSE_SAMPLES + RING_GUARD);
  if (searchLo < ECHO_LO) searchLo = ECHO_LO;
  uint16_t searchHi = ECHO_HI;

  int16_t amp_tx   = maxAbsRange(0, PULSE_SAMPLES);
  int16_t amp_echo = maxAbsRange(searchLo, searchHi);
  int16_t amp_tail = maxAbsRange((uint16_t)(searchHi + 1), N_SAMPLES - 1);

  long sum = 0;
  uint16_t n = 0;
  for (uint16_t i = searchLo; i <= searchHi; i++) {
    int16_t v = samples[i];
    if (v < 0) v = (int16_t)(-v);
    sum += v;
    n++;
  }
  int16_t meanEcho = (n > 0) ? (int16_t)(sum / n) : 1;
  if (meanEcho < 1) meanEcho = 1;

  uint16_t peakIdx = argmaxAbsRange(searchLo, searchHi);
  int16_t peakAmp = samples[peakIdx];
  if (peakAmp < 0) peakAmp = (int16_t)(-peakAmp);
  float snr = (float)peakAmp / (float)meanEcho;

  Serial.print(F("amp_tx="));
  Serial.println(amp_tx);
  Serial.print(F("amp_echo="));
  Serial.println(amp_echo);
  Serial.print(F("amp_tail="));
  Serial.println(amp_tail);
  Serial.print(F("mean_echo="));
  Serial.println(meanEcho);
  Serial.print(F("snr="));
  Serial.println(snr, 2);
  Serial.print(F("search="));
  Serial.print(searchLo);
  Serial.print(F(".."));
  Serial.println(searchHi);

  if (amp_tx < 40) {
    Serial.println(F("NO_ECHO: TX debil"));
    Serial.println(F("OK"));
    return;
  }

  if (snr < 1.6f || peakAmp < 25) {
    Serial.println(F("NO_ECHO: sin eco claro."));
    Serial.println(F("Pared grande a 50-70cm, perpendicular; pot medio."));
    Serial.println(F("OK"));
    return;
  }

  float tau_s = (float)peakIdx / FS_HZ;
  float dist_m = (VS_MPS * tau_s) / 2.0f;

  Serial.print(F("peak_sample="));
  Serial.println(peakIdx);
  Serial.print(F("tau_ms="));
  Serial.println(tau_s * 1000.0f, 3);
  Serial.print(F("distancia_cm="));
  Serial.println(dist_m * 100.0f, 1);
  Serial.print(F("distancia_m="));
  Serial.println(dist_m, 3);
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
  Serial.println(F("Radar MVP v4.2 rango 30-100cm"));
  Serial.println(F("M|L|T|S|D — objeto a 30cm debe dar ~25-40cm"));
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
