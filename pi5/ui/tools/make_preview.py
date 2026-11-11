"""Convert native LVGL snapshots into an offline layout-review gallery."""
import argparse
import html
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SCREENS = {
    "home": ("主菜单", "新游戏、真实 SQLite 玩家库、已保存对局和实时诊断。"),
    "setup": ("新游戏设置", "选择双人、人机或本地 Stockfish 指导；选择真实玩家、执棋方和时间。"),
    "profiles": ("玩家库", "SQLite 玩家列表初始为空；创建、重命名、选择和删除均永久保存。"),
    "player-editor": ("创建玩家", "输入名称并保存到数据库，支持屏幕键盘、实体键盘及粘贴。"),
    "board-setup": ("摆棋和检查", "图中为目标初始布局；只有真实占用匹配且手动确认棋子类型和方向后才能开始。"),
    "game": ("实时对局", "显示后台提供的双方时钟、回合、走法和提示。离线截图没有虚构的对局数据。"),
    "move-editor": ("确认特殊走法", "无法从占用唯一识别的走法可手动输入 UCI，仍需通过合法性和实体占用检查。"),
    "history": ("历史记录", "从 SQLite 读取真实对局，包括未完成的局和实际结果。"),
    "review": ("真实棋谱回放", "读取保存的每步局面；没有记录时不会生成示例棋谱，也不会移动实体棋子。"),
    "diagnostics": ("实时棋盘诊断", "选择串口，按固件坐标查看真实占用、扫描时间和 MUX 输入信息。"),
}

TEMPLATE = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCB · Pi 5 Touch UI</title><style>
*{box-sizing:border-box}body{margin:0;background:#eeece6;color:#20231f;font-family:system-ui,-apple-system,sans-serif}
header{max-width:1220px;margin:auto;padding:32px 28px 22px}header small{letter-spacing:.16em;font-size:11px;color:#64685e}h1{font-size:30px;margin:9px 0 10px;font-weight:650}header p{margin:0;color:#62675d;font-size:14px;line-height:1.8}
main{max-width:1220px;margin:auto;padding:0 28px 40px;display:grid;grid-template-columns:254px minmax(280px,1fr) 234px;gap:28px;align-items:start}
aside{padding-top:12px}nav{display:grid;gap:6px}button{font:inherit;cursor:pointer}nav button{border:0;background:transparent;color:#555d50;text-align:left;padding:12px 15px;border-radius:10px;font-size:14px}nav button[aria-current=true]{background:#252b22;color:#fff}nav button:hover:not([aria-current=true]){background:#e1dccf}button:focus-visible{outline:3px solid #9d7d40;outline-offset:3px}
.device{width:100%;max-width:424px;justify-self:center;background:#171b16;padding:9px;border-radius:22px;box-shadow:0 18px 50px #18201420}.viewport{position:relative;aspect-ratio:720/1280;overflow:hidden;border-radius:14px;background:#f8f7f3}.viewport img{display:block;width:100%;height:auto}.touch{position:absolute;background:transparent;border:0;border-radius:7px;padding:0}.touch:hover{background:#ceb88828;outline:2px solid #a68b51}.touch[disabled]{cursor:not-allowed}.touch[disabled]:hover{background:transparent;outline:none}
.details{font-size:14px;line-height:1.8}.details h2{font-size:20px;line-height:1.4;margin:0 0 12px}.details p{color:#62675d;margin:0 0 20px}.details dl{border-top:1px solid #d3d2c9;padding-top:18px}.details dt{font-size:11px;color:#777c70;text-transform:uppercase;letter-spacing:.08em;margin-top:14px}.details dd{margin:4px 0 0}.tag{display:inline-block;background:#e4dcc9;padding:5px 9px;border-radius:5px;font-size:12px}.note{font-size:12px!important;margin-top:18px!important}.pager{display:flex;justify-content:center;gap:10px;margin-top:15px}.pager button{border:1px solid #67715f;background:transparent;border-radius:8px;padding:9px 14px;color:#f0f2e9}.pager span{align-self:center;font-size:12px;color:#c0c8b7}
@media(max-width:980px){main{grid-template-columns:210px 1fr}.details{grid-column:1/-1;max-width:650px}.details dl{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}.details dd{margin-bottom:8px}}
@media(max-width:620px){header{padding:24px 18px}main{display:flex;flex-direction:column;padding:0 18px 28px;gap:18px}aside{width:100%;padding:0}nav{display:flex;overflow-x:auto;gap:5px;padding-bottom:5px}nav button{white-space:nowrap;padding:10px 12px}.device{max-width:400px;align-self:center}.details{width:100%}h1{font-size:25px}}
</style></head><body><header><small>SMART CHESS BOARD / TEAM 24</small><h1>Pi 5 触摸界面设计</h1><p>5-inch Touch Display 2 · 720 × 1280 竖屏 · 原生 LVGL 渲染<br>点击屏幕按钮或左侧页面名称查看流程；这是离线布局预览；真实走棋、保存和诊断请使用 Pi 上的原生程序。</p></header>
<main><aside><nav aria-label="界面页面">__NAV__</nav></aside>
<section class="device" aria-label="原生触摸界面预览"><div class="viewport"><img id="screen" alt=""><div id="touches"></div></div><div class="pager"><button id="prev" aria-label="上一页">←</button><span id="count"></span><button id="next" aria-label="下一页">→</button></div></section>
<section class="details"><span class="tag">Native UI + board service</span><h2 id="name" style="margin-top:16px" aria-live="polite"></h2><p id="description"></p><dl><div><dt>运行平台</dt><dd>Raspberry Pi 5</dd></div><div><dt>显示与触摸</dt><dd>DSI · GPIO 供电</dd></div><div><dt>原生画布</dt><dd>720 × 1280</dd></div><div><dt>界面程序</dt><dd>C / LVGL 9.3.0</dd></div></dl><p class="note">图像由同目录 C 程序使用空的临时数据库渲染。网页只展示版式；真实玩家和棋谱读写 SQLite，数据不会写在 HTML 中。原生程序通过本机服务接收真实棋盘状态。离线预览不启动服务、不生成对局。</p></section></main>
<script>
const screens=__SCREENS__,maps=__MAPS__,names=Object.keys(screens);let current='home';
function show(key){if(!screens[key])key='home';current=key;document.getElementById('screen').src=key+'.png';document.getElementById('screen').alt=screens[key][0];document.getElementById('name').textContent=screens[key][0];document.getElementById('description').textContent=screens[key][1];document.getElementById('count').textContent=(names.indexOf(key)+1)+' / '+names.length;document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-current',String(b.dataset.screen===key)));const layer=document.getElementById('touches');layer.replaceChildren();for(const h of maps.screens[key]||[]){const b=document.createElement('button');b.className='touch';b.disabled=h.disabled;b.setAttribute('aria-label',h.id.replaceAll('-',' '));Object.assign(b.style,{left:(h.x/maps.width*100)+'%',top:(h.y/maps.height*100)+'%',width:(h.w/maps.width*100)+'%',height:(h.h/maps.height*100)+'%'});b.onclick=()=>show(h.target);layer.appendChild(b)}history.replaceState(null,'','#'+key)}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>show(b.dataset.screen));document.getElementById('prev').onclick=()=>show(names[(names.indexOf(current)+names.length-1)%names.length]);document.getElementById('next').onclick=()=>show(names[(names.indexOf(current)+1)%names.length]);show(location.hash.slice(1)||'home');
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    maps = json.loads((args.rendered / "hotspots.json").read_text())
    for key in SCREENS:
        with Image.open(args.rendered / f"{key}.ppm") as im:
            if im.size != (720, 1280):
                raise ValueError(f"Unexpected canvas: {key}: {im.size}")
            im.save(args.destination / f"{key}.png")
    nav = "".join(f'<button data-screen="{key}" aria-current="false">{html.escape(value[0])}</button>'
                  for key, value in SCREENS.items())
    page = TEMPLATE.replace("__NAV__", nav).replace("__SCREENS__", json.dumps(SCREENS, ensure_ascii=False))
    page = page.replace("__MAPS__", json.dumps(maps))
    (args.destination / "index.html").write_text(page)
    (args.destination / "hotspots.json").write_text(json.dumps(maps, indent=2) + "\n")
    names = ["home", "profiles", "player-editor", "setup", "history", "diagnostics"]
    sheet = Image.new("RGB", (1080, 1368), "#eeece6")
    draw = ImageDraw.Draw(sheet)
    try:
        heading = ImageFont.truetype("DejaVuSans.ttf", 21)
    except OSError:
        heading = ImageFont.load_default(size=21)
    for i, name in enumerate(names):
        x, y = (i % 3) * 360, (i // 3) * 684
        draw.text((x + 12, y + 12), name, font=heading, fill="#20231f")
        with Image.open(args.destination / f"{name}.png") as im:
            sheet.paste(im.resize((350, 622)), (x + 5, y + 48))
    sheet.save(args.destination / "overview.png")
    print(f"Created {len(SCREENS)} LVGL screen previews in {args.destination}")


if __name__ == "__main__":
    main()
