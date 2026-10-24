#ifndef CONTENT_STORE_H
#define CONTENT_STORE_H
#include "panel_types.h"
#include <WString.h>

uint8_t utf8Len(unsigned char c);
String utf8TrimBytes(String s, unsigned int maxBytes);
unsigned int utf8Chars(const String& s);

bool storeBegin();
String modeRead();
bool modeWrite(const String& mode);
bool storeSaveTimetable(const String& json, String& err);
bool storeLoadTimetable(PanelTimetable& tt);
bool storeReadTimetableRaw(String& out);
bool storeSaveScribe(const String& json, String& err);
bool storeLoadScribe(PanelScribe& sc);
bool storeReadScribeRaw(String& out);

#endif
