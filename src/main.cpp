#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>

// ---------- Sensor & I/O pins ----------
const int MPU_ADDR   = 0x68;
const int FSR_PIN    = 34;
const int LDR_PIN    = 35;

const int BUZZER_PIN = 25;   // buzzer pin
const int LED_PIN    = 18;   // status LED

// PWM channel for buzzer (ESP32)
const int BUZZER_CH  = 0;

// FSR threshold for "sitting"
const int FSR_SEATED_THRESH = 2000;

// Posture threshold
const float PITCH_THRESH = 5.0f;   // degrees

// Sitting duration threshold (demo = 30 seconds)
const unsigned long BREAK_MS = 30000UL;

// ---------- WiFi + Cloud ----------
const char* WIFI_SSID = "XXXXXXXX";
const char* WIFI_PASS = "XXXXXXXXXXX";


const char* SERVER_URL = "http://XX.XX.XXX.XXX:5000/api/data";

unsigned long seatedStartMs = 0;   // when we first detected "sitting"

// --------- Buzzer helpers ----------
void buzzerOff() {
  ledcWriteTone(BUZZER_CH, 0);  // stop tone
}

void buzzerTone(uint32_t freq) {
  ledcWriteTone(BUZZER_CH, freq);
}

// --------- Cloud send helper ----------
void sendToServer(float pitch,
                  int fsr_raw,
                  int ldr_raw,
                  bool isSeated,
                  unsigned long seatedSeconds,
                  const String& stateStr) {
  if (WiFi.status() != WL_CONNECTED) {
    // Not connected, skip sending
    return;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  String json = "{";
  json += "\"pitch\":" + String(pitch, 2) + ",";
  json += "\"fsr\":" + String(fsr_raw) + ",";
  json += "\"ldr\":" + String(ldr_raw) + ",";
  json += "\"isSeated\":" + String(isSeated ? 1 : 0) + ",";
  json += "\"seatedTime\":" + String(seatedSeconds) + ",";
  json += "\"state\":\"" + stateStr + "\"";
  json += "}";

  int code = http.POST(json);

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  // -------- WiFi connect --------
  Serial.println("Connecting to WiFi...");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  // -------- IMU init --------
  Wire.begin(21, 22); // SDA, SCL
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);   // PWR_MGMT_1
  Wire.write(0);      // wake up
  Wire.endTransmission();

  analogReadResolution(12);

  // LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  ledcSetup(BUZZER_CH, 2000, 8);
  ledcAttachPin(BUZZER_PIN, BUZZER_CH);
  buzzerOff();

  Serial.println("IMU + Seat FSR + LDR with seat + posture + 30s timer alerts + AWS cloud");
}

void loop() {
  unsigned long now = millis();

  // ---------- IMU: read accel ----------
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);              
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, 6, true);

  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();

  // accel in g
  float ax_f = ax / 16384.0f;
  float ay_f = ay / 16384.0f;
  float az_f = az / 16384.0f;

  // rough pitch from accel (deg)
  float pitch_acc = atan2(-ax_f, sqrt(ay_f*ay_f + az_f*az_f)) * 180.0 / PI;

  // ---------- FSR: raw (seat sensor) ----------
  int fsr_raw = analogRead(FSR_PIN);

  // ---------- LDR: raw (context only) ----------
  int ldr_raw = analogRead(LDR_PIN);

  // ---------- Sitting detection ----------
  bool isSeated = (fsr_raw > FSR_SEATED_THRESH);

  if (!isSeated) {
    // if not seated, reset timer
    seatedStartMs = 0;
  } else if (seatedStartMs == 0) {
    // just started sitting
    seatedStartMs = now;
  }

  unsigned long seatedDurationMs = 0;
  if (seatedStartMs != 0) {
    seatedDurationMs = now - seatedStartMs;
  }
  unsigned long seatedSeconds = seatedDurationMs / 1000;

  // ---------- Posture & long-sit conditions ----------
  bool badPosture   = (pitch_acc > PITCH_THRESH);
  bool longSitting  = (seatedDurationMs >= BREAK_MS);

  // ---------- Buzzer + LED logic ----------
  if (!isSeated) {
    // Not sitting -> no sound, LED off
    buzzerOff();
    digitalWrite(LED_PIN, LOW);

  } else {
    // Sitting
    if (badPosture) {
      buzzerTone(3000);
      bool led_on = ((now / 300) % 2 == 0);  // blink ~ every 300ms
      digitalWrite(LED_PIN, led_on ? HIGH : LOW);

    } else if (longSitting) {
      buzzerTone(2000);
      digitalWrite(LED_PIN, HIGH);

    } else {
      buzzerOff();
      digitalWrite(LED_PIN, LOW);
    }
  }


  String stateStr;
  if (!isSeated) {
    stateStr = "NOT SEATED";
  } else {
    if (badPosture) {
      stateStr = "BAD POSTURE";
    } else if (longSitting) {
      stateStr = "LONG SITTING";
    } else {
      stateStr = "SEATED OK";
    }
  }


  Serial.print("Pitch = ");
  Serial.print(pitch_acc, 1);
  Serial.print(" deg | FSR raw = ");
  Serial.print(fsr_raw);
  Serial.print(" | LDR raw = ");
  Serial.print(ldr_raw);
  Serial.print(" | isSeated=");
  Serial.print(isSeated ? "1" : "0");
  Serial.print(" | seatedTime(s)=");
  Serial.print(seatedSeconds);
  Serial.print(" | state=");
  Serial.println(stateStr);


  static unsigned long lastSend = 0;
  if (now - lastSend >= 1000) {   // every 1 second
    sendToServer(pitch_acc, fsr_raw, ldr_raw, isSeated, seatedSeconds, stateStr);
    lastSend = now;
  }

  delay(200);
}
