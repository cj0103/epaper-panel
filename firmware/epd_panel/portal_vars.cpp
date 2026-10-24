/* 配网全局变量定义（WiFi 配置存 EEPROM 4000 区，机制沿用已验证的旧版） */
#include "Portal.h"

const IPAddress apIP(192, 168, 1, 1);
const char apSSID[] = "EPD-Panel-Setup";   // ASCII: 保证 softAP 以 2.4G 广播；固定信道1
boolean settingMode = false;
String ssidList = "";
DNSServer dnsServer;
WebServer webServer(80);
