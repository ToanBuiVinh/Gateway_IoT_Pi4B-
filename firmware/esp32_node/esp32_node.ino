/* =====================================================================
 * NODE ESP32 MẪU  ->  publish MQTT tới Gateway (Raspberry Pi 4B)
 * ---------------------------------------------------------------------
 * - Kết nối WiFi
 * - Publish JSON vào topic: iot/nodes/<NODE_ID>
 * - Đổi NODE_ID cho từng node (node-01 ... node-10)
 *
 * Thư viện cần cài (Arduino IDE -> Library Manager):
 *   - PubSubClient (Nick O'Leary)
 *   - ArduinoJson (Benoit Blanchon)
 *   - DHT sensor library (Adafruit)  // nếu dùng DHT22
 * ===================================================================== */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "DHT.h"

// ----------- CẤU HÌNH (đổi theo node của bạn) -----------
const char* WIFI_SSID     = "TEN_WIFI";
const char* WIFI_PASS     = "MAT_KHAU_WIFI";

const char* MQTT_HOST     = "192.168.1.10";   // IP của Raspberry Pi 4B
const int   MQTT_PORT     = 1883;
const char* MQTT_USER     = "";               // để trống nếu anonymous
const char* MQTT_PASS     = "";

const char* NODE_ID       = "node-01";        // <-- ĐỔI cho từng node
const unsigned long PUBLISH_INTERVAL_MS = 10000;  // 10 giây/lần

// ----------- Cảm biến DHT22 -----------
#define DHTPIN  4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

WiFiClient   espClient;
PubSubClient mqtt(espClient);
char topic[64];
unsigned long lastPublish = 0;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Ket noi WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi OK. IP: %s\n", WiFi.localIP().toString().c_str());
}

void connectMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  while (!mqtt.connected()) {
    Serial.print("Ket noi MQTT... ");
    bool ok = (strlen(MQTT_USER) > 0)
      ? mqtt.connect(NODE_ID, MQTT_USER, MQTT_PASS)
      : mqtt.connect(NODE_ID);
    if (ok) {
      Serial.println("OK");
    } else {
      Serial.printf("that bai rc=%d, thu lai sau 3s\n", mqtt.state());
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  snprintf(topic, sizeof(topic), "iot/nodes/%s", NODE_ID);
  connectWiFi();
  connectMQTT();
}

void loop() {
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();

  unsigned long now = millis();
  if (now - lastPublish < PUBLISH_INTERVAL_MS) return;
  lastPublish = now;

  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    Serial.println("Doc DHT loi, bo qua lan nay");
    return;
  }

  // Tạo JSON: {"temperature":25.4,"humidity":60.1}
  StaticJsonDocument<128> doc;
  doc["temperature"] = t;
  doc["humidity"]    = h;

  char buf[128];
  size_t n = serializeJson(doc, buf);
  bool ok = mqtt.publish(topic, buf, n);
  Serial.printf("[%s] publish %s -> %s\n", NODE_ID, buf, ok ? "OK" : "FAIL");
}
