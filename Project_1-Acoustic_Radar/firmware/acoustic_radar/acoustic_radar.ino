/*
 * Radar acústico MVP — v7.1 (chirp + FFT onboard, RAM-safe Uno)
 *
 * r = IFFT( conj(FFT(ref)) * FFT(rx) )   // teoría del curso
 * d = (vs * tau) / 2
 *
 * FFT radix-2 en int16 + twiddles en PROGMEM (~1.2 KB SRAM globales).
 *
 * Comandos (9600): C continuo | X parar | M detalle | L | T | S | D
 * Arranca en CONTINUO OFF (estable). Enviar C para modo continuo.
 */

#include <avr/pgmspace.h>
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static const uint8_t  PIN_SPEAKER = 9;
static const uint8_t  PIN_MIC     = A0;

static const float    FS_HZ          = 8000.0f;
static const uint16_t SAMPLE_US      = 125;
static const uint16_t FS_HZ_INT      = 8000;
static const uint16_t N_SAMPLES      = 88;
static const uint16_t CHIRP_SAMPLES  = 40;
static const uint16_t CHIRP_MS       = 5;
static const uint16_t FFT_N          = 128;

static const uint16_t F_START_HZ     = 2000;
static const uint16_t F_END_HZ       = 3500;

static const float    VS_MPS         = 343.0f;
static const uint16_t MIN_LAG        = 10;
static const uint32_t PHASE_K        = 536871UL;

static const float    CAL_OFFSET_CM  = 0.0f;
static const float    CAL_SCALE      = 1.0f;

static const uint16_t CONT_GAP_MS    = 300;
static const float    EMA_ALPHA      = 0.35f;
static const float    OUTLIER_CM     = 25.0f;

static int16_t samples[N_SAMPLES];
static int16_t fftRe[FFT_N];
static int16_t fftIm[FFT_N];
static int16_t refRe[FFT_N];
static int16_t refIm[FFT_N];

static bool    has_capture = false;
static bool    continuousMode = false;
static bool    emaInit = false;
static float   emaCm = 0.0f;
static uint8_t outlierStreak = 0;

/* cos/sin(2*pi*k/128) Q15, k=0..63 (flash) */
static const int16_t TWIDDLE_COS[] PROGMEM = {
  32767, 32728, 32609, 32412, 32137, 31785, 31356, 30852,
  30273, 29621, 28898, 28105, 27245, 26319, 25329, 24279,
  23169, 22005, 20787, 19519, 18204, 16845, 15446, 14009,
  12539, 11038, 9511, 7961, 6392, 4807, 3211, 1607,
  0, -1607, -3211, -4807, -6392, -7961, -9511, -11038,
  -12539, -14009, -15446, -16845, -18204, -19519, -20787, -22005,
  -23169, -24279, -25329, -26319, -27245, -28105, -28898, -29621,
  -30273, -30852, -31356, -31785, -32137, -32412, -32609, -32728
};
static const int16_t TWIDDLE_SIN[] PROGMEM = {
  0, 1607, 3211, 4807, 6392, 7961, 9511, 11038,
  12539, 14009, 15446, 16845, 18204, 19519, 20787, 22005,
  23169, 24279, 25329, 26319, 27245, 28105, 28898, 29621,
  30273, 30852, 31356, 31785, 32137, 32412, 32609, 32728,
  32767, 32728, 32609, 32412, 32137, 31785, 31356, 30852,
  30273, 29621, 28898, 28105, 27245, 26319, 25329, 24279,
  23169, 22005, 20787, 19519, 18204, 16845, 15446, 14009,
  12539, 11038, 9511, 7961, 6392, 4807, 3211, 1607
};

static void speedUpAdc() {
  ADCSRA = (ADCSRA & 0xF8) | 0x04;
}

static int16_t abs16(int16_t v) {
  return (v < 0) ? (int16_t)(-v) : v;
}

static int16_t sat16(int32_t x) {
  if (x > 32767L) return 32767;
  if (x < -32768L) return -32768;
  return (int16_t)x;
}

static void twiddle(uint16_t tIdx, bool inverse, int16_t &wr, int16_t &wi) {
  /* tIdx = 0..127 correspondiente a 2*pi*tIdx/128 */
  tIdx = (uint16_t)(tIdx & 127);
  if (tIdx < 64) {
    wr = (int16_t)pgm_read_word(&TWIDDLE_COS[tIdx]);
    wi = (int16_t)pgm_read_word(&TWIDDLE_SIN[tIdx]);
  } else if (tIdx == 64) {
    wr = -32767;
    wi = 0;
  } else {
    uint16_t t2 = (uint16_t)(128 - tIdx);
    wr = (int16_t)pgm_read_word(&TWIDDLE_COS[t2]);
    wi = (int16_t)(-((int16_t)pgm_read_word(&TWIDDLE_SIN[t2])));
  }
  /* Forward FFT usa e^(-jθ) → wi = -sin; IFFT usa e^(+jθ) → wi = +sin */
  if (!inverse) wi = (int16_t)(-wi);
}

static void bitReverseInt16(int16_t *re, int16_t *im, uint16_t n) {
  uint16_t j = 0;
  for (uint16_t i = 1; i < n; i++) {
    uint16_t bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      int16_t tr = re[i]; re[i] = re[j]; re[j] = tr;
      int16_t ti = im[i]; im[i] = im[j]; im[j] = ti;
    }
  }
}

static void fftInt16(int16_t *re, int16_t *im, bool inverse) {
  const uint16_t n = FFT_N;
  bitReverseInt16(re, im, n);

  for (uint16_t len = 2; len <= n; len <<= 1) {
    uint16_t half = len >> 1;
    uint16_t tableStep = (uint16_t)(n / len);
    for (uint16_t i = 0; i < n; i += len) {
      for (uint16_t j = 0; j < half; j++) {
        int16_t wr, wi;
        twiddle((uint16_t)(j * tableStep), inverse, wr, wi);

        uint16_t u = i + j;
        uint16_t v = u + half;
        int16_t tr = sat16(((int32_t)wr * re[v] - (int32_t)wi * im[v]) >> 15);
        int16_t ti = sat16(((int32_t)wr * im[v] + (int32_t)wi * re[v]) >> 15);

        int16_t ur = re[u];
        int16_t ui = im[u];
        /* Solo atenuar en FFT directa (anti-overflow). En IFFT no,
           o el pico de correlación se va a 0 y siempre da NO_ECHO. */
        if (!inverse) {
          re[v] = (int16_t)((ur - tr) >> 1);
          im[v] = (int16_t)((ui - ti) >> 1);
          re[u] = (int16_t)((ur + tr) >> 1);
          im[u] = (int16_t)((ui + ti) >> 1);
        } else {
          re[v] = sat16((int32_t)ur - tr);
          im[v] = sat16((int32_t)ui - ti);
          re[u] = sat16((int32_t)ur + tr);
          im[u] = sat16((int32_t)ui + ti);
        }
      }
    }
  }
}

static bool correlateFftPeak(uint16_t &lagOut, int32_t &peakOut, int32_t &bestAbsOut) {
  /* Sin >>2: en Uno la señal ya es pequeña; no matar energía */
  for (uint16_t i = 0; i < FFT_N; i++) {
    fftRe[i] = (i < N_SAMPLES) ? samples[i] : 0;
    fftIm[i] = 0;
  }
  fftInt16(fftRe, fftIm, false);

  for (uint16_t k = 0; k < FFT_N; k++) {
    int32_t yr = fftRe[k];
    int32_t yi = fftIm[k];
    int32_t xr = refRe[k];
    int32_t xi = refIm[k];
    /* Menos shift → pico usable para argmax */
    fftRe[k] = sat16((xr * yr - xi * yi) >> 10);
    fftIm[k] = sat16((xr * yi + xi * yr) >> 10);
  }

  fftInt16(fftRe, fftIm, true);

  const uint16_t maxLag = (uint16_t)(N_SAMPLES - 1);
  if (MIN_LAG > maxLag) {
    bestAbsOut = 0;
    return false;
  }

  int32_t best = 0;
  uint16_t bestLag = MIN_LAG;
  bool found = false;
  for (uint16_t lag = MIN_LAG; lag <= maxLag; lag++) {
    int32_t a = fftRe[lag];
    if (a < 0) a = -a;
    if (!found || a > best) {
      best = a;
      bestLag = lag;
      peakOut = fftRe[lag];
      found = true;
    }
  }
  bestAbsOut = best;
  /* Umbral muy bajo: con señal real el pico debe destacar; 0 = fallo total */
  if (!found || best < 1) return false;
  lagOut = bestLag;
  return true;
}

static void buildRefSpectrum() {
  const float T = (float)CHIRP_SAMPLES / FS_HZ;
  const float kSlope = (float)(F_END_HZ - F_START_HZ) / T;

  for (uint16_t i = 0; i < FFT_N; i++) {
    if (i < CHIRP_SAMPLES) {
      float t = (float)i / FS_HZ;
      float phase = 2.0f * (float)M_PI *
                    ((float)F_START_HZ * t + 0.5f * kSlope * t * t);
      fftRe[i] = (int16_t)(sin(phase) * 16000.0f);
    } else {
      fftRe[i] = 0;
    }
    fftIm[i] = 0;
  }

  fftInt16(fftRe, fftIm, false);

  for (uint16_t k = 0; k < FFT_N; k++) {
    refRe[k] = fftRe[k];
    refIm[k] = (int16_t)(-fftIm[k]);
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
                 + ((uint32_t)(F_END_HZ - F_START_HZ) * (uint32_t)i)
                       / (uint32_t)CHIRP_SAMPLES;
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

static bool measureDistanceCm(float &distCmOut, uint16_t &lagOut, int32_t &peakOut,
                              long &eTxOut, int32_t &bestAbsOut, uint8_t &failCode) {
  /* failCode: 0=ok 1=TX_WEAK 2=NO_PEAK */
  failCode = 0;
  transmitChirpAndAcquire();
  removeDc();

  long eTx = 0;
  for (uint16_t i = 0; i < CHIRP_SAMPLES; i++) eTx += (long)abs16(samples[i]);
  eTxOut = eTx;
  /* Umbral bajo: solo detecta mic “muerto” */
  if (eTx < (long)CHIRP_SAMPLES * 3L) {
    failCode = 1;
    bestAbsOut = 0;
    return false;
  }

  uint16_t lag = 0;
  int32_t peak = 0;
  int32_t bestAbs = 0;
  if (!correlateFftPeak(lag, peak, bestAbs)) {
    failCode = 2;
    bestAbsOut = bestAbs;
    return false;
  }

  bestAbsOut = bestAbs;
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
  if (delta > OUTLIER_CM && outlierStreak < 1) {
    outlierStreak++;
    return emaCm;
  }
  outlierStreak = 0;
  emaCm = EMA_ALPHA * rawCm + (1.0f - EMA_ALPHA) * emaCm;
  return emaCm;
}

static void printContinuousLine(bool ok, float rawCm, float filtCm, uint16_t lag, int32_t peak) {
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
  int32_t peak = 0;
  long eTx = 0;
  int32_t bestAbs = 0;
  uint8_t fail = 0;
  bool ok = measureDistanceCm(rawCm, lag, peak, eTx, bestAbs, fail);
  float filt = emaInit ? emaCm : rawCm;
  if (ok) filt = updateEma(rawCm);
  printContinuousLine(ok, ok ? rawCm : 0.0f, filt, lag, peak);
  digitalWrite(PIN_SPEAKER, LOW);
  noTone(PIN_SPEAKER);
  delay(CONT_GAP_MS);
}

static void runMeasurementDetailed() {
  Serial.println(F("--- Medicion FFT (Arduino) ---"));
  float distCm = 0.0f;
  uint16_t lag = 0;
  int32_t peak = 0;
  long eTx = 0;
  int32_t bestAbs = 0;
  uint8_t fail = 0;
  if (!measureDistanceCm(distCm, lag, peak, eTx, bestAbs, fail)) {
    Serial.print(F("eTx="));
    Serial.println(eTx);
    Serial.print(F("corr_best="));
    Serial.println(bestAbs);
    if (fail == 1) {
      Serial.println(F("NO_ECHO: TX_WEAK (mic no oye el chirp)"));
      Serial.println(F("Revisa cableado mic/parlante, pot y GND comun"));
    } else {
      Serial.println(F("NO_ECHO: NO_PEAK (sin eco claro)"));
      Serial.println(F("Acerca objeto ~50cm, sube pot, prueba L"));
    }
    Serial.println(F("OK"));
    return;
  }
  float filt = updateEma(distCm);
  float tau_ms = (float)lag / FS_HZ * 1000.0f;
  Serial.println(F("method=FFT_corr"));
  Serial.print(F("eTx="));
  Serial.println(eTx);
  Serial.print(F("fft_n="));
  Serial.println(FFT_N);
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
  Serial.print(F("FFT_N="));
  Serial.println(FFT_N);
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
    Serial.println(F("Tono ON"));
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
  Serial.begin(9600);
  buildRefSpectrum();
  Serial.println(F("Radar MVP v7.1 FFT int16"));
  Serial.println(F("Listo. M=medir  C=continuo"));
  tone(PIN_SPEAKER, (unsigned)((F_START_HZ + F_END_HZ) / 2));
  delay(120);
  noTone(PIN_SPEAKER);
  continuousMode = false;
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
  if (continuousMode) runContinuousTick();
}
