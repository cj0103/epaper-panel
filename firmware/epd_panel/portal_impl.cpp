/* 配网实现（机制与 epd_calendar 一致，已实测可用） */
#include "Portal.h"

boolean restoreConfig() {
  Serial.println("读取 EEPROM 配网信息...");
  String ssid = "";
  String pass = "";
  if (EEPROM.read(4000) != 0) {
    // 按 '\0' 截断读取，保留中文SSID/特殊字符密码的 UTF-8 字节
    for (int i = 4000; i < 4032; ++i) {
      char ch = EEPROM.read(i);
      if (ch == 0) break;
      ssid += ch;
    }
    Serial.print("WiFi: ");
    Serial.println(ssid);
    for (int i = 4032; i < 4064; ++i) {
      char ch = EEPROM.read(i);
      if (ch == 0) break;
      pass += ch;
    }
    Serial.println("Connecting...");
    WiFi.begin(ssid.c_str(), pass.c_str());
    return true;
  }
  Serial.println("无保存配置。");
  return false;
}

boolean checkConnection() {
  int count = 0;
  Serial.print("等待连接");
  while (count < 30) {
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\n连接成功！");
      return true;
    }
    delay(500);
    Serial.print(".");
    count++;
  }
  Serial.println("\n连接超时。");
  return false;
}

String makePage(String title, String contents) {
  String s = "<!DOCTYPE html><html><head>";
  s += "<meta charset=\"utf-8\">";
  s += "<meta name=\"viewport\" content=\"width=device-width,user-scalable=0\">";
  s += "<title>";
  s += title;
  s += "</title></head><body>";
  s += contents;
  s += "</body></html>";
  return s;
}

String urlDecode(String input) {
  String s = input;
  s.replace("%20", " ");
  s.replace("+", " ");
  s.replace("%21", "!");
  s.replace("%22", "\"");
  s.replace("%23", "#");
  s.replace("%24", "$");
  s.replace("%25", "%");
  s.replace("%26", "&");
  s.replace("%27", "\'");
  s.replace("%28", "(");
  s.replace("%29", ")");
  s.replace("%2A", "*");
  s.replace("%2B", "+");
  s.replace("%2C", ",");
  s.replace("%2E", ".");
  s.replace("%2F", "/");
  s.replace("%3A", ":");
  s.replace("%3B", ";");
  s.replace("%3C", "<");
  s.replace("%3D", "=");
  s.replace("%3E", ">");
  s.replace("%3F", "?");
  s.replace("%40", "@");
  s.replace("%5B", "[");
  s.replace("%5C", "\\");
  s.replace("%5D", "]");
  s.replace("%5E", "^");
  s.replace("%5F", "_");
  s.replace("%60", "`");
  return s;
}

/* 配网页：手机浏览器打开 */
static void handleSettings() {
  String s = "<h1>墨水屏配网</h1><p>选择 WiFi 并输入密码：</p>";
  s += "<form method=\"get\" action=\"setap\" style=\"font-size:18px;line-height:2.2\">";
  s += "<label>网络:</label><select name=\"ssid\" style=\"font-size:16px\">";
  s += ssidList;
  s += "</select><br>密码: <input name=\"pass\" length=64 type=\"password\" style=\"font-size:16px\"><br>";
  s += "<input type=\"submit\" value=\"保存并提交\" style=\"font-size:18px;padding:6px 18px\"></form>";
  webServer.send(200, "text/html; charset=utf-8", makePage("配网", s));
}

static void handleSetap() {
  for (int i = 4000; i < 4096; ++i) {
    EEPROM.write(i, 0);
  }
  EEPROM.commit();
  String ssid = urlDecode(webServer.arg("ssid"));
  String pass = urlDecode(webServer.arg("pass"));
  Serial.print("保存 WiFi: ");
  Serial.println(ssid);
  for (unsigned int i = 0; i < ssid.length(); ++i) EEPROM.write(4000 + i, ssid[i]);
  for (unsigned int i = 0; i < pass.length(); ++i) EEPROM.write(4032 + i, pass[i]);
  EEPROM.commit();
  String s = "<h1>设置完成！</h1><p>设备即将重启并接入 \"";
  s += ssid;
  s += "\"，请将手机重新连回原网络。</p>";
  webServer.send(200, "text/html; charset=utf-8", makePage("配网", s));
  delay(2000); // 等响应送达再重启
  ESP.restart();
}

void startWebServer() {
  if (settingMode) {
    Serial.print("配网 Web 服务: http://");
    Serial.println(WiFi.softAPIP());
    webServer.on("/settings", handleSettings);
    webServer.on("/setap", handleSetap);
    webServer.onNotFound([]() {
      String s = "<h1>配网模式</h1><p><a href=\"/settings\">点击配网</a></p>";
      webServer.send(200, "text/html; charset=utf-8", makePage("配网模式", s));
    });
  } else {
    // 联网模式下的配网逃生入口（投喂主页 / 由主程序注册）
    webServer.on("/reset", []() {
      for (int i = 4000; i < 4096; ++i) EEPROM.write(i, 0);
      EEPROM.commit();
      String s = "<h1>WiFi 配置已清除</h1><p>请重启设备进入配网模式。</p>";
      webServer.send(200, "text/html; charset=utf-8", makePage("重置", s));
    });
  }
  webServer.begin();
}

void setupMode() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  int n = WiFi.scanNetworks();
  delay(100);
  // 去重（同名多信道热点会重复出现）
  for (int i = 0; i < n; ++i) {
    String name = WiFi.SSID(i);
    bool dup = false;
    for (int j = 0; j < i; ++j)
      if (WiFi.SSID(j) == name) { dup = true; break; }
    if (dup || name.length() == 0) continue;
    ssidList += "<option value=\"";
    ssidList += name;
    ssidList += "\">";
    ssidList += name;
    ssidList += "</option>";
  }
  delay(100);
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0));
  WiFi.softAP(apSSID, nullptr, 1);   // 开放热点，固定信道 1
  dnsServer.start(53, "*", apIP);
  portalShowStatus("配网模式\n请连接热点\n" + String(apSSID) + "\n浏览器打开\n192.168.1.1");
  startWebServer();
  Serial.print("热点: ");
  Serial.println(apSSID);
}

void wifi_init() {
  delay(10);
  if (restoreConfig()) {
    if (checkConnection()) {
      settingMode = false;
      startWebServer();
      return;
    }
  }
  settingMode = true;
  setupMode();
}
