/* 局域网投喂 API 与手机主页
 * 协议版本: v1（/api/status 报告 api:"v1"；破坏性升级时递增并保持老接口兼容）
 *   POST /api/timetable  body=课程表JSON            成功: {"ok":true}
 *   GET  /api/timetable  读回当前课程表JSON          成功: {"ok":true,"data":{...}}
 *   POST /api/scribe     body=誊抄JSON              成功: {"ok":true,"pages":N}
 *   POST /api/display    text/plain 公告             成功: {"ok":true}
 *   POST /api/mode       text/plain timetable|scribe|notice|refresh|next|prev
 *   GET  /api/status     诊断JSON
 *   GET  /               手机投喂主页
 *   GET  /tt             课程表录入页（主页二级页面）
 */
#include "api_panel.h"
#include <ArduinoJson.h>

extern PanelState g_panel;
extern String g_last_error;

/* ---------- 主页（手机浏览器） ---------- */

static const char HOME_HTML[] PROGMEM = R"rawl(
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>墨水屏投喂</title>
<style>
body{font-family:-apple-system,sans-serif;margin:12px;background:#f5f6f8;color:#222}
.card{background:#fff;border-radius:12px;padding:14px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
h2{font-size:17px;margin:0 0 8px}
textarea{width:100%;box-sizing:border-box;font-size:16px;padding:8px;border:1px solid #ccc;border-radius:8px}
input,select{font-size:16px;padding:6px;border:1px solid #ccc;border-radius:8px;width:100%;box-sizing:border-box}
button{font-size:17px;padding:10px 16px;border:0;border-radius:8px;background:#1a73e8;color:#fff;margin:6px 6px 0 0}
button.sec{background:#888}
label{display:block;margin:8px 0 2px;font-size:14px;color:#555}
#msg{font-size:15px;margin-top:8px;min-height:20px}
.entry{display:block;text-align:center;background:#1a73e8;color:#fff;padding:11px;border-radius:8px;text-decoration:none;font-size:17px;margin:8px 0 2px}
.hint{font-size:13px;color:#666;margin:4px 0 0}
</style></head><body>
<div class="card"><h2>当前状态</h2><div id="status">读取中…</div></div>
<div class="card"><h2>课程表</h2>
<div id="ttinfo" class="hint">未配置</div>
<a class="entry" href="/tt">课程表录入 / 修改 ›</a>
<button class="sec" onclick="postMode('timetable')">切到课程表</button>
<button class="sec" onclick="postMode('next')">下一页 ›</button>
<button class="sec" onclick="postMode('prev')">‹ 上一页</button>
</div>
<div class="card"><h2>推送作文（誊抄模式）</h2>
<label>标题（可空）</label><input id="stitle" placeholder="《我的妈妈》">
<label>正文字数：<span id="cnt">0</span>（26px 约470字/页，自动分页）</label>
<textarea id="stext" rows="8" placeholder="粘贴作文草稿…"></textarea>
<label>字号档（誊抄正文·标题·页脚同尺寸）</label>
<select id="sfont"><option value="small">小（26px·默认·约470字/页）</option><option value="mid">中（28px·约400字/页）</option><option value="big">大（34px·约280字/页）</option></select>
<button onclick="pushScribe()">推送到屏幕</button>
<button class="sec" onclick="postMode('next')">下一页 ›</button>
<button class="sec" onclick="postMode('prev')">‹ 上一页</button>
</div>
<div class="card"><h2>临时公告</h2>
<input id="ntext" placeholder="如：21:30 该睡觉了">
<button onclick="pushNotice()">显示公告</button>
</div>
<div class="card"><h2>模式</h2>
<button class="sec" onclick="postMode('timetable')">回课程表</button>
<button class="sec" onclick="postMode('scribe')">进誊抄</button>
<button class="sec" onclick="postMode('notice')">显示公告</button>
<button class="sec" onclick="postMode('refresh')">整屏刷新</button>
</div>
<div id="msg"></div>
<script>
function show(m,c){var e=document.getElementById('msg');e.textContent=m;e.style.color=c||'#188038';}
function esc(s){return s.replace(/[&<>"]/g,function(x){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[x]})}
function loadStatus(){fetch('/api/status').then(r=>r.json()).then(j=>{
 document.getElementById('status').innerHTML=
 '模式: <b>'+esc(j.mode)+'</b><br>课程表: '+(j.timetable?('第'+j.tt_page+'/'+j.tt_pages+'页'):'未配置')+
 '<br>作文: '+(j.scribe?('第'+j.scribe_page+'/'+j.scribe_pages+'页 · '+j.scribe_font+'档'):'无')+
 (j.notice?('<br>公告: '+esc(j.notice)):'');
 document.getElementById('ttinfo').textContent=j.timetable?('已配置 · 第'+j.tt_page+'/'+j.tt_pages+'页'):'未配置，点上面进入录入';
}).catch(e=>show('读取失败:'+e,'#d93025'));}
function post(url,body,ct){return fetch(url,{method:'POST',headers:{'Content-Type':ct||'text/plain;charset=utf-8'},body:body}).then(r=>r.json());}
function postMode(m){post('/api/mode',m).then(j=>{show(j.ok?('已切换: '+m):('失败:'+j.error));setTimeout(loadStatus,1200);}).catch(e=>show('失败:'+e,'#d93025'));}
function pushScribe(){var t=document.getElementById('stext').value.trim();
 if(!t){show('请先输入正文','#d93025');return;}
 var body=JSON.stringify({title:document.getElementById('stitle').value.trim(),text:t,font:document.getElementById('sfont').value});
 post('/api/scribe',body,'application/json').then(j=>{show(j.ok?('已推送，共'+j.pages+'页'):('失败:'+j.error));postMode('scribe');setTimeout(loadStatus,1500);}).catch(e=>show('失败:'+e,'#d93025'));}
function pushNotice(){var t=document.getElementById('ntext').value.trim();
 if(!t){show('请先输入公告','#d93025');return;}
 post('/api/display',t).then(j=>{show(j.ok?'公告已显示':('失败:'+j.error));setTimeout(loadStatus,1200);}).catch(e=>show('失败:'+e,'#d93025'));}
document.getElementById('stext').addEventListener('input',function(){document.getElementById('cnt').textContent=this.value.length;});
loadStatus();setInterval(loadStatus,10000);
</script></body></html>
)rawl";

/* ---------- 课程表录入页（主页的二级页面） ----------
 * 分天录入：周一~周日 × 上午/下午，提交 {title, days:[{name,am,pm}]}。
 * 进入时自动读回当前课程表，改完直接推送（不用每次从零手敲）。 */

static const char TT_HTML[] PROGMEM = R"rawl(
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>课程表录入</title>
<style>
body{font-family:-apple-system,sans-serif;margin:12px;background:#f5f6f8;color:#222}
.card{background:#fff;border-radius:12px;padding:14px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
h2{font-size:17px;margin:0 0 8px}
input{font-size:16px;padding:8px;border:1px solid #ccc;border-radius:8px;width:100%;box-sizing:border-box}
button{font-size:17px;padding:10px 16px;border:0;border-radius:8px;background:#1a73e8;color:#fff;margin:6px 6px 0 0}
button.sec{background:#888}
label{display:block;margin:8px 0 2px;font-size:14px;color:#555}
#msg{font-size:15px;margin-top:8px;min-height:20px}
.day{border:1px solid #e2e5e9;border-radius:10px;padding:6px 10px 10px;margin-bottom:10px}
.day h3{margin:6px 0 0;font-size:15px}
.day h3 input{border:0;padding:2px 0;font-size:16px;font-weight:600;color:#1a73e8;background:transparent}
.back{display:inline-block;color:#1a73e8;text-decoration:none;font-size:15px;margin-bottom:8px}
.hint{font-size:13px;color:#666;margin:4px 0 0}
</style></head><body>
<div class="card">
<a class="back" href="/">‹ 返回主页</a>
<h2>课程表录入</h2>
<label>表头标题</label>
<input id="title" placeholder="四 1 班课程表（游泳周）">
<p class="hint">每天分上午 / 下午两栏，课程之间用「、」分隔。留空表示这一栏没有课。</p>
</div>
<div id="days"></div>
<div class="card">
<button onclick="submitTT()">推送到屏幕</button>
<button class="sec" onclick="addDay()">＋ 增加一天</button>
</div>
<div id="msg"></div>
<script>
var DN=['周一','周二','周三','周四','周五','周六','周日'];
var nDays=5;
function esc(s){return String(s).replace(/[&<>"]/g,function(x){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[x]})}
function show(m,c){var e=document.getElementById('msg');e.textContent=m;e.style.color=c||'#188038';}
function buildDay(i){
 var d=document.createElement('div');d.className='day';
 d.innerHTML='<h3><input id="dn'+i+'" value="'+esc(DN[i])+'"></h3>'+
  '<label>上午</label><input id="am'+i+'" placeholder="语文、语文、数学、英语">'+
  '<label>下午</label><input id="pm'+i+'" placeholder="阅读、体育与健康、音乐、信息技术">';
 return d;
}
function renderDays(){var b=document.getElementById('days');b.innerHTML='';for(var i=0;i<nDays;i++)b.appendChild(buildDay(i));}
function addDay(){if(nDays>=7){show('最多 7 天','#d93025');return;}nDays++;renderDays();}
function collect(){
 var days=[];
 for(var i=0;i<nDays;i++){
  var nm=(document.getElementById('dn'+i).value||'').trim();
  var am=(document.getElementById('am'+i).value||'').trim();
  var pm=(document.getElementById('pm'+i).value||'').trim();
  if(!am&&!pm)continue;
  days.push({name:nm||DN[i],am:am,pm:pm});
 }
 return days;
}
function submitTT(){
 var days=collect();
 if(!days.length){show('请至少填写一天','#d93025');return;}
 var title=(document.getElementById('title').value||'').trim()||'课程表';
 fetch('/api/timetable',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({title:title,days:days})})
  .then(function(r){return r.json()})
  .then(function(j){
   if(j.ok){show('课程表已更新，正在显示…');
    fetch('/api/mode',{method:'POST',headers:{'Content-Type':'text/plain'},body:'timetable'})
     .then(function(){setTimeout(function(){show('已推送到屏幕');},900);});
   }else show('失败：'+j.error,'#d93025');
  }).catch(function(e){show('失败：'+e,'#d93025')});
}
function load(){
 fetch('/api/timetable').then(function(r){return r.json()}).then(function(j){
  if(!j.ok){renderDays();return;}
  var d=j.data||{},days=d.days||[];
  if(d.title)document.getElementById('title').value=d.title;
  nDays=Math.max(5,days.length);renderDays();
  for(var i=0;i<days.length;i++){
   document.getElementById('dn'+i).value=days[i].name||DN[i];
   document.getElementById('am'+i).value=days[i].am||'';
   document.getElementById('pm'+i).value=days[i].pm||'';
  }
  show(days.length?('已载入当前课程表，改完直接推送'):'');
 }).catch(function(){renderDays();});
}
renderDays();load();
</script></body></html>
)rawl";

static void sendOk(bool ok, const String& extra = "") {
  String s = String("{\"ok\":") + (ok ? "true" : "false");
  if (extra.length()) s += "," + extra;
  s += "}";
  webServer.send(200, "application/json; charset=utf-8", s);
}

static void sendErr(const String& err) {
  String e = err;
  e.replace("\\", "\\\\");
  e.replace("\"", "\\\"");
  webServer.send(200, "application/json; charset=utf-8", "{\"ok\":false,\"error\":\"" + e + "\"}");
}

/* ---------- 刷新调度（主 loop 执行实际刷屏） ---------- */

volatile bool g_render_dirty = false;   // 需要全量重绘
volatile bool g_hard_refresh = false;   // 本次要求整屏刷新（清残影）

/* ★ 刷新策略（2026-10-29 快刷方案，替代 10-28 的"一律整刷"）：
 *  - 上电首刷 / 手动 refresh / 定期消残影 → g_hard_refresh=true →
 *    _Update_Full 整刷（~27s），同时把 old/new 两份屏 RAM 都写成当前帧，
 *    建立干净的差分基准（见 epd_panel.ino renderCurrent）。
 *  - 其余内容变化 → g_hard_refresh=false → displayWindowBW 黑白差分
 *    快刷（UC8179 官方 OTP 差分波形，标称 ~1.3s）。
 * 注意区分两条"局刷"路径：
 *  1) GxEPD2 三色局刷 display(true)（_Update_Part）——物理 ~18s 不快，
 *     且只把"当前软件页"写回屏 RAM（GxEPD2_BW.h:361），整屏重绘模式下
 *     会把旧页残影留在屏上（2026-10-28 实机 bug）。已弃用。
 *  2) 黑白差分 displayWindowBW → refresh_bw：自己 writeImagePartToCurrent
 *     整窗写入 + 刷完回写 previous RAM 更新基准，协议完整。本方案用它。
 * 前提：画面全部黑字（红色无法参与差分），render_panel.cpp 已去掉红色。
 * 残影对策：连续快刷 FAST_EVERY 次在本文件强制插一次整刷。 */
/* 残影计数器：文件级而不是函数内 static，供 fastRefreshCount() 查询
 * （/api/status 上报"距下次整刷还有几次"，投喂页可见）。 */
static uint8_t g_fast_count = 0;

unsigned int fastRefreshCount() { return g_fast_count; }

void requestRender() {
  g_render_dirty = false;   // 先清再置：重复置位不构成变化，loop 不会触发
  if (++g_fast_count >= FAST_EVERY) {  // 定期整刷清残影（含上电后第 N 次）
    g_fast_count = 0;
    g_hard_refresh = true;
  } else {
    g_hard_refresh = false;
  }
  g_render_dirty = true;
}

/* 强制整刷（手动 refresh / 切换模板模式）：整刷会把屏 RAM 的
 * old/new 两份都重置为当前帧，差分基准随之重建。 */
void requestFullRender() {
  g_render_dirty = false;
  g_fast_count = 0;         // 手动整刷同时重置残影计数器
  g_hard_refresh = true;
  g_render_dirty = true;
}

/* ---------- 路由 ---------- */

void handleHome() {
  webServer.send(200, "text/html; charset=utf-8", FPSTR(HOME_HTML));
}

/* 课程表录入页（主页二级页面） */
void handleTimetablePage() {
  webServer.send(200, "text/html; charset=utf-8", FPSTR(TT_HTML));
}

/* 读回当前课程表（供录入页回填表单） */
void handleApiTimetableGet() {
  String raw;
  if (!storeReadTimetableRaw(raw)) { sendErr("尚未配置课程表"); return; }
  webServer.send(200, "application/json; charset=utf-8",
                 String("{\"ok\":true,\"data\":") + raw + "}");
}

void handleApiTimetable() {
  String body = webServer.arg("plain");
  String err;
  if (!storeSaveTimetable(body, err)) { sendErr(err); return; }
  if (!storeLoadTimetable(g_panel.tt)) { sendErr("存储后校验失败"); return; }
  g_panel.tt_page = 0;
  g_panel.mode = "timetable";
  modeWrite(g_panel.mode);
  requestRender();
  sendOk(true, "\"mode\":\"timetable\"");
  Serial.println("[API] 课程表已更新");
}

/* 读回当前誊抄内容（调试用：可核对正文里的换行/空格） */
void handleApiScribeGet() {
  String raw;
  if (!storeReadScribeRaw(raw)) { sendErr("尚未配置誊抄内容"); return; }
  webServer.send(200, "application/json; charset=utf-8",
                 String("{\"ok\":true,\"data\":") + raw + "}");
}

void handleApiScribe() {
  String body = webServer.arg("plain");
  String err;
  if (!storeSaveScribe(body, err)) { sendErr(err); return; }
  if (!storeLoadScribe(g_panel.sc)) { sendErr("存储后校验失败"); return; }
  g_panel.scribe_page = 0;
  g_panel.mode = "scribe";
  modeWrite(g_panel.mode);
  requestRender();
  sendOk(true, "\"pages\":" + String(scribeTotalPages(g_panel.sc)));
  Serial.println("[API] 誊抄内容已更新");
}

void handleApiDisplay() {
  String body = webServer.arg("plain");
  body.trim();
  if (body.length() == 0) { sendErr("公告文本为空"); return; }
  if (utf8Chars(body) > 120) { sendErr("公告过长（上限120字）"); return; }
  g_panel.notice = body;
  g_panel.mode = "notice";
  modeWrite(g_panel.mode);
  requestRender();
  sendOk(true);
  Serial.println("[API] 公告已显示");
}

void handleApiMode() {
  String body = webServer.arg("plain");
  body.trim();
  if (body == "timetable") {
    if (!g_panel.tt.valid) { sendErr("课程表未配置"); return; }
    g_panel.mode = "timetable";
  } else if (body == "scribe") {
    if (!g_panel.sc.valid) { sendErr("誊抄内容未推送"); return; }
    g_panel.mode = "scribe";
  } else if (body == "notice") {
    if (g_panel.notice.length() == 0) { sendErr("暂无公告，请先通过 /api/display 或主页发布"); return; }
    g_panel.mode = "notice";
  } else if (body == "refresh") {
    // 强制整刷：交给 loop 执行（不能在现场渲染——整刷 20+ 秒会把 HTTP
    // 响应堵死，客户端必然读超时，2026-10-28 实机发现）。
    requestFullRender();
    sendOk(true);
    return;
  } else if (body == "next" || body == "prev") {
    if (g_panel.mode == "timetable") {
      // 课程表也可能分页（天块不跨页）
      if (body == "next") { if (g_panel.tt_page + 1 < g_panel.tt_pages) g_panel.tt_page++; }
      else { if (g_panel.tt_page > 0) g_panel.tt_page--; }
      requestRender();
      sendOk(true, "\"page\":" + String(g_panel.tt_page + 1));
      return;
    }
    if (g_panel.mode != "scribe" || !g_panel.sc.valid) { sendErr("当前不在可翻页模式"); return; }
    unsigned int pages = scribeTotalPages(g_panel.sc);
    if (body == "next") { if (g_panel.scribe_page + 1 < pages) g_panel.scribe_page++; }
    else { if (g_panel.scribe_page > 0) g_panel.scribe_page--; }
    requestRender();
    sendOk(true, "\"page\":" + String(g_panel.scribe_page + 1));
    return;
  } else {
    sendErr("mode 无效: timetable|scribe|notice|refresh|next|prev");
    return;
  }
  modeWrite(g_panel.mode);
  requestRender();       // 切模板与翻页同理：整屏差异由差分波形逐像素驱动，
                         // 残影交给 FAST_EVERY 定期整刷压（2026-10-29 实机取向）
  sendOk(true, "\"mode\":\"" + g_panel.mode + "\"");
}

void handleApiStatus() {
  String s = "{";
  s += "\"api\":\"v1\"";
  s += ",\"mode\":\"" + g_panel.mode + "\"";
  s += ",\"timetable\":" + String(g_panel.tt.valid ? "true" : "false");
  s += ",\"scribe\":" + String(g_panel.sc.valid ? "true" : "false");
  s += ",\"scribe_page\":" + String(g_panel.scribe_page + 1);
  s += ",\"scribe_pages\":" + String(g_panel.sc.valid ? scribeTotalPages(g_panel.sc) : 0);
  s += ",\"scribe_font\":\"" + (g_panel.sc.valid ? g_panel.sc.font : String("")) + "\"";
  s += ",\"tt_page\":" + String(g_panel.tt_page + 1);
  s += ",\"tt_pages\":" + String(g_panel.tt_pages);
  s += ",\"notice\":\"";
  { // 转义公告文本
    unsigned int pos = 0;
    while (pos < g_panel.notice.length()) {
      char c = g_panel.notice[pos];
      if (c == '"' || c == '\\') { s += '\\'; s += c; }
      else if ((unsigned char)c >= 0x80) { s += c; } // UTF-8 原样
      else if (c == '\n') s += "\\n";
      else s += c;
      pos++;
    }
  }
  s += "\"";
  s += ",\"ip\":\"" + WiFi.localIP().toString() + "\"";
  s += ",\"free_heap\":" + String(ESP.getFreeHeap());
  // 刷新调度透明度：距下一次自动整刷（清残影）还需几次快刷
  s += ",\"fast_count\":" + String(g_fast_count);
  s += ",\"full_in\":" + String(FAST_EVERY > g_fast_count ? FAST_EVERY - g_fast_count : 0);
  s += "}";
  webServer.send(200, "application/json; charset=utf-8", s);
}

void registerPanelRoutes() {
  webServer.on("/", HTTP_GET, handleHome);
  webServer.on("/tt", HTTP_GET, handleTimetablePage);
  webServer.on("/api/timetable", HTTP_POST, handleApiTimetable);
  webServer.on("/api/timetable", HTTP_GET, handleApiTimetableGet);
  webServer.on("/api/scribe", HTTP_POST, handleApiScribe);
  webServer.on("/api/scribe", HTTP_GET, handleApiScribeGet);
  webServer.on("/api/display", HTTP_POST, handleApiDisplay);
  webServer.on("/api/mode", HTTP_POST, handleApiMode);
  webServer.on("/api/status", HTTP_GET, handleApiStatus);
}
