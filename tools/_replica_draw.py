# -*- coding: utf-8 -*-
"""逐字复刻 drawScribeImpl（2026-11-15 终版）：渲染坐标 -> 屏幕画布，与照片对账
校验三件事：① 字符守恒（不吞字）② 无越界（不出屏）③ 行边界合理（不切单词）"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

d = json.load(open('tools/_dbg2.json', encoding='utf-8'))['data']
text, font = d['text'], d.get('font','mid')
px = {'small':26,'mid':28,'big':34}[font]
PANEL_W, PANEL_H = 480, 800
availW, availH = PANEL_W-24, PANEL_H-22-44
cell = px                        # 列几何唯一权威=px（与固件同步）
cols = max(1, availW//cell)
lineH = px + 4                   # 行距=px+4（墨迹带零交叠最小值）
rows = max(1, availH//lineH)
gx = (PANEL_W - cols*cell)//2; gy = 22
assert gx >= 0, "gx 为负 = 越界回归"
# 墨迹带校验：基线=by+px/2，前行底缘=基线+4，后行顶缘=下一基线-22
prev_bot = gy + px//2 + 4
next_top = gy + lineH + px//2 - (px-6)
assert prev_bot < next_top, f"墨迹交叠! {prev_bot} >= {next_top}"
print(f"px={px} cols={cols} cell={cell} lineH={lineH} rows/pg={rows} gx={gx} gy={gy} 墨迹带[{gy+px//2-22},{prev_bot}) vs 后行起{next_top} 零交叠OK")

NO_START={0x3001,0x3002,0xFF0C,0xFF01,0xFF1F,0xFF1B,0xFF1A,0x201D,0x2019,
 0x300B,0x300D,0xFF09,0x3011,0x2026,0x002C,0x002E,0xFF0E}
def isalnum(c): return c.isdigit() or c.isascii() and c.isalpha()

cps=list(text)
total=len(cps)
# --- scribeBuildRows 复刻（终版：禁则挪标点 + 单词防切退到空格） ---
srow=[0]; row=0; ci=0; col=0
while ci<total and row<339:
    cp=cps[ci]
    if cp in '\n\r':
        ci+=1; row+=1; srow.append(ci); col=0; continue
    if col>=cols:
        if col>0 and ci>0 and cp in NO_START:
            row+=1; srow.append(ci); col=0; continue      # 禁则：标点挪新行行首
        if col>0 and ci>0 and (cp==' ' or isalnum(cp)):
            cut=ci; has=False
            while cut>srow[row]+1:
                if cps[cut-1]==' ':
                    if any(cps[b] in NO_START for b in range(cut,ci)):
                        break                # 新行将以禁则标点开头，放弃防切
                    has=True; break
                cut-=1
            if has:
                row+=1; srow.append(cut); col=0; continue
        row+=1; srow.append(ci); col=0
    ci+=1; col+=1
srow.append(total); nrow=row+1
# 文末换行收缩（与固件同步）
if srow[nrow-1]==total and total>0 and cps[total-1] in '\n\r':
    srow[nrow-1]=total-1

# --- 守恒校验 ---
covered=[]
for r in range(nrow): covered.extend(range(srow[r], srow[r+1]))
missing=sorted(set(range(total))-set(covered)); dup=len(covered)-len(set(covered))
print("守恒:", "OK 全部%d字符" % total if not missing and not dup else f"!!丢失{missing} 重复{dup}")

title=d.get('title',''); author=d.get('author','')
hl=0
if title:
    n=len(title)+(len(author)+1 if author else 0)
    hl=(n+cols-1)//cols
first = rows-hl if (title and hl<rows) else rows
pages = 1 if nrow<=first else 1+(nrow-first+rows-1)//rows
print(f"headerLines={hl} firstPageRows={first} pages={pages}")

for page in range(pages):
    r0 = 0 if page==0 else first+(page-1)*rows
    r1 = min(nrow, (first if page==0 else r0+rows))
    print(f"\n--- 页 {page+1}/{pages} ---")
    for r in range(r0, r1):
        gridrow=(r-r0)+(hl if page==0 else 0)
        by=gy+gridrow*lineH
        frm,to=srow[r],srow[r+1]
        seg=''.join(c for c in cps[frm:to] if c not in '\n\r')
        # 最右字符右缘像素 = gx + (n-1)*cell + (cell-px)/2 + 墨迹宽(px)
        n=max(1,to-frm)
        right = gx + (n-1)*cell + (cell-px)//2 + px
        warn = '!!越界' if right > PANEL_W else ''
        print(f"r{r:2d} y={by:3d} 宽{to-frm:2d}{warn:6s} |{seg}|")
