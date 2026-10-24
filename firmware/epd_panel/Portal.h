/* 配网模块（沿用 epd_calendar 已验证方案：EEPROM 4000 区存账号密码，
 * 无配置时开热点 EPD-Panel-Setup(信道1) + 192.168.1.1 配网页）
 * 注意：不可命名 Webserver.h —— 与 ESP32 库同名会在 Windows 大小写
 * 不敏感文件系统上自包含递归。 */
#ifndef PORTAL_H
#define PORTAL_H

#include <Arduino.h>
#include <DNSServer.h>
#include <EEPROM.h>
#include <WebServer.h>
#include <WiFi.h>

extern const IPAddress apIP;
extern const char apSSID[];
extern boolean settingMode;
extern String ssidList;
extern DNSServer dnsServer;
extern WebServer webServer;

/* 渲染层回调（epd_panel.ino 提供）：配网模式在屏上显示提示文字 */
void portalShowStatus(const String& text);

boolean restoreConfig();
boolean checkConnection();
String makePage(String title, String contents);
String urlDecode(String input);
void startWebServer();
void setupMode();
void wifi_init();

#endif
