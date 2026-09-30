/*
 * Radar acústico MVP — v6.1 (chirp + correlación + continuo)
 *
 * Según la teoría del curso (Partes 2–3 / Adelanto):
 *   - Señal TX = chirp lineal (barrido de frecuencia)
 *   - Retardo del eco = pico de correlación cruzada
 *   - Distancia monostática: d = (vs * tau) / 2
 *
 * Modo continuo (por defecto): mide en bucle y suaviza con EMA
 * para una lectura estable en Serial Monitor / Serial Plotter.
 *
 * Comandos Serial (9600):
 *   C  — modo continuo ON (default al arrancar)
 *   X  — modo continuo OFF
 *   M  — una medición detallada (pausa el continuo un ciclo)
 *   L  — diagnóstico mic
 *   T  — tono continuo ON
 *   S  — apaga tono + detiene continuo
 *   D  — dump CSV de la última captura
 */

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static const uint8_t  PIN_SPEAKER = 9;
static const uint8_t  PIN_MIC     = A0;

static const float    FS_HZ          = 16000.0f;
static const uint16_t SAMPLE_US      = 62;
static const uint16_t FS_HZ_INT      = 16000;
static const uint16_t N_SAMPLES      = 320;

static const uint16_t F_START_HZ     = 2000;
static const uint16_t F_END_HZ       = 7000;
static const uint16_t CHIRP_MS       = 10;
static const uint16_t CHIRP_SAMPLES  = 160;

static const float    VS_MPS         = 343.0f;
static const uint16_t MIN_LAG        = 24;
static const uint32_t PHASE_K        = 268435UL;

static const float    CAL_OFFSET_CM  = 0.0f;
static const float    CAL_SCALE      = 1.0f;

/*
 * Continuo / PRI (pulse repetition interval):
 *   Ventana RX ≈ N_SAMPLES/FS ≈ 20 ms → ToF máx. ~3.4 m.
 *   Si el siguiente chirp sale antes de que muera el eco/reverberación
 *   del anterior, la correlación ve ecos “fantasma” (ambigüedad de rango).
 *   CONT_GAP_MS es silencio EXTRA tras cada medida (parlante ya apagado
 *   durante la correlación). 250–400 ms es razonable en habitación.
 */
static const uint16_t CONT_GAP_MS    = 300;
static const float    EMA_ALPHA      = 0.35f; // 0..1 (más alto = más reactivo)
static const float    OUTLIER_CM     = 25.0f; // ignora saltos bruscos aislados

static int16_t samples[N_SAMPLES];
static int8_t  chirp_ref[CHIRP_SAMPLES];
static bool    has_capture = false;

static bool    continuousMode = true;
static bool    emaInit = false;
static float   emaCm = 0.0f;
static uint8_t outlierStreak = 0;

static void speedUpAdc() {
  ADCSRA = (ADCSRA & 0xF8) | 0x04;
}

static int16_t abs16(int16_t v) {
  return (v < 0) ? (int16_t)(-v) : v;
}

static void buildChirpReference() {
  const float T = (float)CHIRP_SAMPLES / FS_HZ;
  const float k = (float)(F_END_HZ - F_START_HZ) / T;
  for (uint16_t i = 0; i < CHIRP_SAMPLES; i++) {
    float t = (float)i / FS_HZ;
    float phase = 2.0f * (float)M_PI * ((float)F_START_HZ * t + 0.5f * k * t * t);
    chirp_ref[i] = (int8_t)(127.0f * sin(phase));
  }
}

static void removeDc() {
  long sum = 0;
  for (uint16_t i = 0; i < N_SAMPLES; i++) sum += samples[i];
  int16_t mean = (int16_t)(sum / (long)N_SAMPLES);
  for (uint16_t i = 0; i < N_SAMPLES; i++) {
    samples[i] = (int16_t)(samples[i] - mean);
  }
}

static void transmitChirpAndAcquire() {
  unsigned long t0 = micros();
  uint32_t phase = 0;

  for (uint16_t i = 0; i < N_SAMPLES; i++) {
    unsigned long due = t0 + (unsigned long)i * SAMPLE_US;
    while ((long)(micros() - due) < 0) {}

    if (i < CHIRP_SAMPLES) {
      uint32_t f = (uint32_t)F_START_HZ
                 + ((uint32_t)(F_END_HZ - F_START_HZ) * (uint32_t)i) / (uint32_t)CHIRP_SAMPLES;
      phase += f * PHASE_K;
      digitalWrite(PIN_SPEAKER, (phase & 0x80000000UL) ? HIGH : LOW);
    } else {
      digitalWrite(PIN_SPEAKER, LOW);
    }

    samples[i] = (int16_t)analogRead(PIN_MIC);
  }

  digitalWrite(PIN_SPEAKER, LOW);
  has_capture = true;
}

static bool correlateDirectPeak(uint16_t &lagOut, long &peakOut) {
  const uint16_t maxLag = (uint16_t)(N_SAMPLES - CHIRP_SAMPLES);
  if (MIN_LAG > maxLag) return false;

  long best = 0;
  uint16_t bestLag = MIN_LAG;
  bool found = false;

  for (uint16_t lag = MIN_LAG; lag <= maxLag; lag++) {
    long acc = 0;
    for (uint16_t n = 0; n < CHIRP_SAMPLES; n++) {
      acc += (long)samples[lag + n] * (long)chirp_ref[n];
    }
    long a = (acc < 0) ? -acc : acc;
    long b = (best < 0) ? -best : best;
    if (!found || a > b) {
      best = acc;
      bestLag = lag;
      found = true;
    }
  }

  if (!found) return false;
  lagOut = bestLag;
  peakOut = best;
  return true;
}

/*
 * Una toma ToF. Devuelve true si hay distancia válida en distCmOut.
 */
static bool measureDistanceCm(float &distCmOut, uint16_t &lagOut, long &peakOut) {
  transmitChirpAndAcquire();
  removeDc();

  long eTx = 0;
  for (uint16_t i = 0; i < CHIRP_SAMPLES; i++) {
    eTx += (long)abs16(samples[i]);
  }
  if (eTx < (long)CHIRP_SAMPLES * 8L) return false;

  uint16_t lag = 0;
  long peak = 0;
  if (!correlateDirectPeak(lag, peak)) return false;

  long peakAbs = (peak < 0) ? -peak : peak;
  if (peakAbs < 50L) return false;

  float tau_s = (float)lag / FS_HZ;
  float dist_raw_cm = (VS_MPS * tau_s) / 2.0f * 100.0f;
  distCmOut = CAL_SCALE * dist_raw_cm + CAL_OFFSET_CM;
  lagOut = lag;
  peakOut = peak;
  return true;
}

static float updateEma(float rawCm) {
  if (!emaInit) {
    emaCm = rawCm;
    emaInit = true;
    outlierStreak = 0;
    return emaCm;
  }

  float delta = rawCm - emaCm;
  if (delta < 0) delta = -delta;

  // Rechaza un salto aislado; acepta si se confirma 2 veces
  if (delta > OUTLIER_CM && outlierStreak < 1) {
    outlierStreak++;
    return emaCm;
  }
  outlierStreak = 0;
  emaCm = EMA_ALPHA * rawCm + (1.0f - EMA_ALPHA) * emaCm;
  return emaCm;
}

static void printContinuousLine(bool ok, float rawCm, float filtCm, uint16_t lag, long peak) {
  // Formato amigable con Serial Plotter (etiquetas:valor)
  if (ok) {
    Serial.print(F("raw_cm:"));
    Serial.print(rawCm, 1);
    Serial.print(F(",filt_cm:"));
    Serial.print(filtCm, 1);
    Serial.print(F(",lag:"));
    Serial.print(lag);
    Serial.print(F(",peak:"));
    Serial.println(peak);
  } else {
    Serial.print(F("raw_cm:nan,filt_cm:"));
    if (emaInit) Serial.print(emaCm, 1);
    else Serial.print(F("nan"));
    Serial.println(F(",lag:0,peak:0"));
  }
}

static void runContinuousTick() {
  float rawCm = 0.0f;
  uint16_t lag = 0;
  long peak = 0;
  bool ok = measureDistanceCm(rawCm, lag, peak);
  float filt = emaInit ? emaCm : rawCm;
  if (ok) filt = updateEma(rawCm);
  printContinuousLine(ok, ok ? rawCm : 0.0f, filt, lag, peak);

  // Silencio acústico: deja regresar/amortiguar el eco antes del próximo TX.
  digitalWrite(PIN_SPEAKER, LOW);
  noTone(PIN_SPEAKER);
  delay(CONT_GAP_MS);
}

static void runMeasurementDetailed() {
  Serial.println(F("--- Medicion (chirp + correlacion) ---"));
  float distCm = 0.0f;
  uint16_t lag = 0;
  long peak = 0;
  if (!measureDistanceCm(distCm, lag, peak)) {
    Serial.println(F("NO_ECHO"));
    Serial.println(F("OK"));
    return;
  }

  float filt = updateEma(distCm);
  float tau_ms = (float)lag / FS_HZ * 1000.0f;

  Serial.print(F("lag_samples="));
  Serial.println(lag);
  Serial.print(F("corr_peak="));
  Serial.println(peak);
  Serial.print(F("tau_ms="));
  Serial.println(tau_ms, 3);
  Serial.print(F("distancia_cm_raw="));
  Serial.println(distCm, 1);
  Serial.print(F("distancia_cm="));
  Serial.println(filt, 1);
  Serial.print(F("distancia_m="));
  Serial.println(filt / 100.0f, 3);
  Serial.println(F("OK"));
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
  bool wasCont = continuousMode;
  continuousMode = false;
  Serial.println(F("--- Diagnostico L ---"));
  digitalWrite(PIN_SPEAKER, LOW);
  delay(30);
  int quiet = measureDelta(600);
  tone(PIN_SPEAKER, (unsigned)((F_START_HZ + F_END_HZ) / 2));
  delay(80);
  int loud = measureDelta(800);
  noTone(PIN_SPEAKER);
  digitalWrite(PIN_SPEAKER, LOW);
  Serial.print(F("silencio delta="));
  Serial.println(quiet);
  Serial.print(F("con_tono delta="));
  Serial.println(loud);
  continuousMode = wasCont;
}

static void dumpCsv() {
  if (!has_capture) {
    Serial.println(F("ERR: captura primero (C o M)"));
    return;
  }
  Serial.println(F("BEGIN_SAMPLES"));
  Serial.print(F("FS="));
  Serial.println((int)FS_HZ_INT);
  Serial.print(F("F_START="));
  Serial.println(F_START_HZ);
  Serial.print(F("F_END="));
  Serial.println(F_END_HZ);
  Serial.print(F("CHIRP_MS="));
  Serial.println(CHIRP_MS);
  Serial.print(F("CHIRP_SAMPLES="));
  Serial.println(CHIRP_SAMPLES);
  Serial.print(F("MIN_LAG="));
  Serial.println(MIN_LAG);
  Serial.print(F("N_SAMPLES="));
  Serial.println(N_SAMPLES);
  for (uint16_t i = 0; i < N_SAMPLES; i++) Serial.println(samples[i]);
  Serial.println(F("END_SAMPLES"));
}

static void handleCommand(char c) {
  if (c == 'C' || c == 'c') {
    continuousMode = true;
    Serial.println(F("CONTINUO ON"));
  } else if (c == 'X' || c == 'x') {
    continuousMode = false;
    Serial.println(F("CONTINUO OFF"));
  } else if (c == 'M' || c == 'm') {
    bool was = continuousMode;
    continuousMode = false;
    runMeasurementDetailed();
    continuousMode = was;
  } else if (c == 'L' || c == 'l') {
    listenDiag();
  } else if (c == 'T' || c == 't') {
    continuousMode = false;
    tone(PIN_SPEAKER, (unsigned)((F_START_HZ + F_END_HZ) / 2));
    Serial.println(F("Tono ON (continuo OFF)"));
  } else if (c == 'S' || c == 's') {
    continuousMode = false;
    noTone(PIN_SPEAKER);
    digitalWrite(PIN_SPEAKER, LOW);
    Serial.println(F("OFF"));
  } else if (c == 'D' || c == 'd') {
    dumpCsv();
  }
}

void setup() {
  pinMode(PIN_SPEAKER, OUTPUT);
  digitalWrite(PIN_SPEAKER, LOW);
  speedUpAdc();
  buildChirpReference();
  Serial.begin(9600);
  Serial.println(F("Radar MVP v6.1 continuo"));
  Serial.println(F("C=continuo X=parar M=detalle | Plotter: raw_cm,filt_cm"));
  tone(PIN_SPEAKER, (unsigned)((F_START_HZ + F_END_HZ) / 2));
  delay(150);
  noTone(PIN_SPEAKER);
  delay(100);
  continuousMode = true;
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r' || c == ' ') continue;
    handleCommand(c);
    while (Serial.available() > 0) {
      char d = (char)Serial.read();
      if (d == '\n') break;
    }
  }

  if (continuousMode) {
    runContinuousTick();
  }
}
