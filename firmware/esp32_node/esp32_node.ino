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

// ----------- Chân điều khiển (downlink) — ví dụ relay/LED -----------
#define ACTUATOR_PIN 2        // GPIO2: LED onboard / chân điều khiển relay

WiFiClient   espClient;
PubSubClient mqtt(espClient);
char topic[64];        // uplink:   iot/nodes/<NODE_ID>
char cmdTopic[64];     // downlink: iot/cmd/<NODE_ID>
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

// Xử lý lệnh downlink nhận từ gateway. Ví dụ payload: {"cmd":"relay","state":1}
void onCommand(char* t, byte* payload, unsigned int len) {
  StaticJsonDocument<128> doc;
  if (deserializeJson(doc, payload, len)) {
    Serial.println("Lenh khong phai JSON hop le");
    return;
  }
  const char* cmd = doc["cmd"] | "";
  Serial.printf("[%s] nhan lenh: cmd=%s\n", NODE_ID, cmd);

  if (strcmp(cmd, "relay") == 0) {
    int state = doc["state"] | 0;
    digitalWrite(ACTUATOR_PIN, state ? HIGH : LOW);
    Serial.printf("  -> dat ACTUATOR = %d\n", state);
  }
  // Thêm các lệnh khác tại đây, ví dụ đổi chu kỳ gửi, reboot, hiệu chỉnh...
}

void connectMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
  while (!mqtt.connected()) {
    Serial.print("Ket noi MQTT... ");
    bool ok = (strlen(MQTT_USER) > 0)
      ? mqtt.connect(NODE_ID, MQTT_USER, MQTT_PASS)
      : mqtt.connect(NODE_ID);
    if (ok) {
      Serial.println("OK");
      mqtt.subscribe(cmdTopic, 1);   // đăng ký nhận lệnh downlink
      Serial.printf("Da subscribe lenh: %s\n", cmdTopic);
    } else {
      Serial.printf("that bai rc=%d, thu lai sau 3s\n", mqtt.state());
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  pinMode(ACTUATOR_PIN, OUTPUT);
  digitalWrite(ACTUATOR_PIN, LOW);
  snprintf(topic, sizeof(topic), "iot/nodes/%s", NODE_ID);
  snprintf(cmdTopic, sizeof(cmdTopic), "iot/cmd/%s", NODE_ID);
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
