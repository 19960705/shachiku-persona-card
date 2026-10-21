#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社畜人设卡 · 卡片渲染器

输入一份 card.json，输出：
  - 文本卡（终端 / 聊天窗口直接看，也可截图）
  - card.html（720×1040 竖版，浏览器打开即可截图分享）
  - card.svg （矢量，任意尺寸无损）

card.json 结构见 README.md「卡片数据契约」。所有渲染只读这份 JSON，
不做任何网络请求，因此 demo 模式与真实模式走同一条渲染链路。
"""

import argparse
import html
import json
import os
import random
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PRICE_LABEL = {
    "calc": "已实时核验",
    "menu": "菜单价 · 未核价",
    "demo": "示例数据 · 非实时",
}
# 卡面徽标用整句，避免"价格示例数据"这种拼接读起来别扭
BADGE_TEXT = {
    "calc": "价格已实时核验",
    "menu": "菜单价 · 尚未核价",
    "demo": "示例数据 · 非实时",
}
PRICE_BADGE = {"calc": "✓", "menu": "!", "demo": "○"}


# ------------------------------------------------------------------ 工具
def money(v):
    if v is None:
        return "—"
    return f"¥{float(v):.2f}"


def gen_card_no(seed=None, when=None):
    rnd = random.Random(seed)
    when = when or datetime.now()
    return f"SC-{when.strftime('%Y%m%d')}-{rnd.randint(1000, 9999)}"


def _wrap(text, width):
    """按显示宽度折行（中日韩字符算 2，ASCII 算 1）。"""
    out, line, w = [], "", 0
    for ch in text:
        cw = 2 if ord(ch) > 0x2E80 else 1
        if w + cw > width * 2 and line:
            out.append(line)
            line, w = "", 0
        line += ch
        w += cw
    if line:
        out.append(line)
    return out or [""]


# ------------------------------------------------------------------ 文本卡
def render_text(card):
    p = card["persona"]
    sel = card.get("selection", {})
    price = card.get("price", {})
    store = card.get("store", {})
    items = sel.get("items", [])
    src = price.get("source", "menu")
    rule = "─" * 30

    L = []
    L.append(f"🎴 今日人设卡  No.{card.get('card_no', '—')}")
    L.append(rule)
    L.append(f"今日人设：{p.get('name', '社畜')} {p.get('emoji', '')}".rstrip())
    L.append(f"「{card.get('tagline', '')}」")
    L.append("")

    if len(items) == 1:
        it = items[0]
        qty = f" ×{it['quantity']}" if it.get("quantity", 1) > 1 else ""
        L.append(f"推荐：{it['name']}{qty}")
    else:
        L.append("推荐：")
        for it in items:
            qty = f" ×{it['quantity']}" if it.get("quantity", 1) > 1 else ""
            L.append(f"  · {it['name']}{qty}　{money(it.get('price'))}")

    total = price.get("total")
    line = f"价格：{money(total)}（{PRICE_LABEL.get(src, '未核价')}）"
    L.append(line)

    original = price.get("original")
    if src == "calc" and original and total and float(original) > float(total) + 0.01:
        L.append(f"　　　原价 {money(original)}，省 {money(float(original) - float(total))}")
    if price.get("coupon_note"):
        L.append(f"　　　{price['coupon_note']}")

    if store.get("name"):
        L.append(f"门店：{store['name']}")
    if card.get("period") or card.get("time"):
        L.append(f"时段：{card.get('period', '')} · {card.get('time', '')}".strip(" ·"))

    reasons = sel.get("reasons") or []
    if reasons:
        L.append("")
        L.append("为什么是它：")
        for r in reasons[:3]:
            L.append(f"  · {r}")

    if card.get("menu_note"):
        L.append("")
        L.append(f"注：{card['menu_note']}")

    L.append("")
    L.append("要下单吗？还是再 Roll 一次？")
    L.append(rule)
    return "\n".join(L)


# ------------------------------------------------------------------ 公共布局数据
def _layout(card):
    p = card["persona"]
    sel = card.get("selection", {})
    price = card.get("price", {})
    store = card.get("store", {})
    items = sel.get("items", [])
    src = price.get("source", "menu")
    total = price.get("total")
    original = price.get("original")
    saved = None
    if src == "calc" and original and total and float(original) > float(total) + 0.01:
        saved = float(original) - float(total)

    return {
        "name": p.get("name", "社畜"),
        "emoji": p.get("emoji", "🍔"),
        "tagline": card.get("tagline", ""),
        "items": items,
        "total": money(total),
        "saved": money(saved) if saved else None,
        "src_label": PRICE_LABEL.get(src, "未核价"),
        "badge_text": BADGE_TEXT.get(src, "价格未核价"),
        "src_badge": PRICE_BADGE.get(src, ""),
        "verified": src == "calc",
        "tips": (card.get("tips") or [])[:2],
        "price_note": price.get("note", ""),
        "store": store.get("name", ""),
        "store_code": store.get("code", ""),
        "period": card.get("period", ""),
        "time": card.get("time", ""),
        "card_no": card.get("card_no", "—"),
        "mode": card.get("mode", "roll"),
        "menu_note": card.get("menu_note", ""),
        "reasons": (sel.get("reasons") or [])[:3],
    }


# ------------------------------------------------------------------ HTML 卡
def render_html(card, standalone=True):
    d = _layout(card)
    e = html.escape

    item_rows = ""
    for it in d["items"]:
        qty = f'<span class="qty">×{it["quantity"]}</span>' if it.get("quantity", 1) > 1 else ""
        item_rows += (
            f'<div class="item"><span class="iname">{e(it["name"])}{qty}</span>'
            f'<span class="iprice">{money(it.get("price"))}</span></div>'
        )

    reasons = ""
    if d["reasons"]:
        lis = "".join(f"<li>{e(r)}</li>" for r in d["reasons"])
        reasons = f'<div class="why"><div class="why-t">为什么是它</div><ul>{lis}</ul></div>'

    note = f'<div class="note">{e(d["menu_note"])}</div>' if d["menu_note"] else ""
    saved = f'<div class="saved">原价 {money(card.get("price", {}).get("original"))} · 省 {d["saved"]}</div>' if d["saved"] else ""
    tips = ""
    if d["tips"]:
        lis = "".join(f"<li>{e(t)}</li>" for t in d["tips"])
        tips = f'<div class="why tips"><div class="why-t">小贴士</div><ul>{lis}</ul></div>'
    pnote = f'<div class="pnote">{e(d["price_note"])}</div>' if d["price_note"] else ""
    mode_label = "ROLL 模式" if d["mode"] == "roll" else "点餐模式"

    body = f"""
<section class="card">
  <div class="topbar"></div>
  <header class="hd">
    <div class="hd-left">
      <div class="kicker">今日人设卡</div>
      <div class="mode">{mode_label}</div>
    </div>
    <div class="hd-right">No.{e(d['card_no'])}</div>
  </header>

  <div class="persona">
    <div class="avatar">{e(d['emoji'])}</div>
    <h1>{e(d['name'])}</h1>
    <p class="tagline">「{e(d['tagline'])}」</p>
  </div>

  <div class="rec">
    <div class="rec-t">今日推荐</div>
    {item_rows}
    <div class="total">
      <span class="tl">合计</span>
      <span class="tv">{d['total']}</span>
    </div>
    {saved}
    <div class="badge {'ok' if d['verified'] else 'warn'}">
      {d['src_badge']} {d['badge_text']}
    </div>
    {pnote}
  </div>

  {reasons}
  {tips}

  <div class="meta">
    <div><span>门店</span>{e(d['store']) or '—'}</div>
    <div><span>时段</span>{e(d['period'])} · {e(d['time'])}</div>
  </div>

  {note}

  <footer class="ft">
    <span>要下单吗？</span>
    <span class="dot">·</span>
    <span>还是再 Roll 一次？</span>
  </footer>
</section>"""

    css = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#EFE9DD;display:flex;align-items:center;justify-content:center;
 min-height:100vh;font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",-apple-system,sans-serif;
 padding:24px}
.card{width:720px;min-height:1040px;background:#FFFDF8;border-radius:28px;overflow:hidden;
 position:relative;box-shadow:0 24px 60px rgba(64,44,26,.16);
 display:flex;flex-direction:column;padding:0 56px 44px}
.topbar{height:14px;background:linear-gradient(90deg,#DA291C 0%,#DA291C 62%,#FFC72C 62%,#FFC72C 100%);
 margin:0 -56px 0}
.hd{display:flex;justify-content:space-between;align-items:flex-end;padding:34px 0 0}
.kicker{font-size:15px;letter-spacing:.32em;color:#B4894F;font-weight:600}
.mode{font-size:12px;color:#9A8F80;letter-spacing:.18em;margin-top:8px}
.hd-right{font-size:13px;color:#A99C8B;font-variant-numeric:tabular-nums;letter-spacing:.06em}
.persona{text-align:center;padding:22px 0 18px}
.avatar{width:114px;height:114px;margin:0 auto 16px;border-radius:50%;
 background:radial-gradient(circle at 34% 30%,#FFF6E3,#FFE0A8 62%,#FFD07A);
 display:flex;align-items:center;justify-content:center;font-size:56px;
 box-shadow:inset 0 -6px 18px rgba(255,160,40,.22),0 10px 26px rgba(218,41,28,.10)}
h1{font-size:54px;font-weight:800;letter-spacing:.04em;color:#241C14;line-height:1.12}
.tagline{margin-top:12px;font-size:22px;color:#7A6A57;letter-spacing:.02em;line-height:1.5}
.rec{margin-top:6px;background:#FFF6E8;border:1.5px solid #F2DFC2;border-radius:20px;padding:22px 26px}
.rec-t{font-size:13px;color:#B4894F;letter-spacing:.26em;font-weight:600;margin-bottom:16px}
.item{display:flex;justify-content:space-between;align-items:baseline;padding:8px 0;
 border-bottom:1px dashed #EBD9BE;font-size:22px;color:#2E2519}
.item:last-of-type{border-bottom:none}
.qty{font-size:15px;color:#B4894F;margin-left:8px}
.iprice{font-size:19px;color:#6E6152;font-variant-numeric:tabular-nums}
.total{display:flex;justify-content:space-between;align-items:baseline;
 margin-top:14px;padding-top:16px;border-top:2px solid #E4CFAE}
.tl{font-size:16px;color:#8A7A66;letter-spacing:.14em}
.tv{font-size:42px;font-weight:800;color:#DA291C;font-variant-numeric:tabular-nums}
.saved{font-size:14px;color:#12805C;margin-top:6px;text-align:right}
.badge{margin-top:18px;display:inline-block;font-size:14px;padding:8px 16px;border-radius:999px;font-weight:600}
.badge.ok{background:#E6F6EE;color:#0E7A55;border:1px solid #BFE7D4}
.badge.warn{background:#FFF4DF;color:#9A6A17;border:1px solid #F0DCAF}
.pnote{margin-top:10px;font-size:13px;line-height:1.6;color:#9A6A17}
.why{margin-top:18px;padding:0 4px}
.why-t{font-size:13px;color:#B4894F;letter-spacing:.26em;font-weight:600;margin-bottom:10px}
.why ul{list-style:none}
.why li{font-size:16px;color:#6E6152;line-height:1.7;padding-left:18px;position:relative}
.why li::before{content:"·";position:absolute;left:6px;color:#D2A25F;font-weight:800}
.tips{margin-top:14px}
.tips li::before{content:"›";color:#C9A87A}
.meta{margin-top:auto;padding-top:20px;border-top:1.5px solid #EFE3CF;font-size:15px;color:#6E6152;line-height:2}
.meta span{display:inline-block;width:56px;color:#B4894F;letter-spacing:.1em}
.note{font-size:13px;color:#9A8F80;margin-top:10px;line-height:1.7}
.ft{margin-top:16px;text-align:center;font-size:19px;color:#241C14;letter-spacing:.06em}
.dot{margin:0 10px;color:#D2A25F}
@media print{body{background:#fff}}
"""
    if not standalone:
        return f"<style>{css}</style>\n{body}"
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=760,initial-scale=1\">\n"
        f"<title>今日人设卡 · {html.escape(d['name'])}</title>\n<style>{css}</style>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )


# ------------------------------------------------------------------ SVG 卡
def _svg_escape(t):
    return html.escape(str(t), quote=True)


def render_svg(card):
    d = _layout(card)
    W, H = 720, 1040
    out = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    add("<defs>")
    add('<linearGradient id="bar" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="62%" stop-color="#DA291C"/><stop offset="62%" stop-color="#FFC72C"/></linearGradient>')
    add('<radialGradient id="av" cx="34%" cy="30%" r="72%">'
        '<stop offset="0%" stop-color="#FFF6E3"/><stop offset="62%" stop-color="#FFE0A8"/>'
        '<stop offset="100%" stop-color="#FFD07A"/></radialGradient>')
    add("</defs>")
    add(f'<rect width="{W}" height="{H}" rx="0" fill="#EFE9DD"/>')
    add(f'<rect x="24" y="18" width="{W-48}" height="{H-36}" rx="28" fill="#FFFDF8"/>')
    add(f'<path d="M24 46 A28 28 0 0 1 52 18 H{W-24} V32 H24 Z" fill="url(#bar)"/>')
    add(f'<rect x="24" y="18" width="{W-48}" height="14" fill="url(#bar)"/>')

    font = 'font-family="PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif"'
    add(f'<text x="80" y="78" font-size="15" letter-spacing="6" fill="#B4894F" font-weight="600" {font}>今日人设卡</text>')
    add(f'<text x="80" y="100" font-size="12" letter-spacing="3" fill="#9A8F80" {font}>'
        f'{"ROLL 模式" if d["mode"] == "roll" else "点餐模式"}</text>')
    add(f'<text x="{W-80}" y="84" font-size="13" fill="#A99C8B" text-anchor="end" {font}>No.{_svg_escape(d["card_no"])}</text>')

    add(f'<circle cx="{W/2}" cy="200" r="66" fill="url(#av)"/>')
    add(f'<text x="{W/2}" y="228" font-size="66" text-anchor="middle">{_svg_escape(d["emoji"])}</text>')

    add(f'<text x="{W/2}" y="330" font-size="58" font-weight="800" fill="#241C14" '
        f'text-anchor="middle" letter-spacing="2" {font}>{_svg_escape(d["name"])}</text>')

    y = 372
    for ln in _wrap("「" + d["tagline"] + "」", 26):
        add(f'<text x="{W/2}" y="{y}" font-size="22" fill="#7A6A57" text-anchor="middle" {font}>'
            f'{_svg_escape(ln)}</text>')
        y += 34

    # 推荐区
    box_y = y + 14
    items = d["items"]
    box_h = 144 + 40 * max(len(items), 1)
    add(f'<rect x="80" y="{box_y}" width="{W-160}" height="{box_h}" rx="20" fill="#FFF6E8" stroke="#F2DFC2" stroke-width="1.5"/>')
    add(f'<text x="108" y="{box_y+38}" font-size="13" letter-spacing="5" fill="#B4894F" font-weight="600" {font}>今日推荐</text>')

    iy = box_y + 78
    for it in items:
        qty = f' ×{it["quantity"]}' if it.get("quantity", 1) > 1 else ""
        add(f'<text x="108" y="{iy}" font-size="21" fill="#2E2519" {font}>{_svg_escape(it["name"] + qty)}</text>')
        add(f'<text x="{W-108}" y="{iy}" font-size="18" fill="#6E6152" text-anchor="end" {font}>'
            f'{money(it.get("price"))}</text>')
        add(f'<line x1="108" y1="{iy+12}" x2="{W-108}" y2="{iy+12}" stroke="#EBD9BE" stroke-width="1" stroke-dasharray="4 4"/>')
        iy += 40

    ty = box_y + box_h - 34
    add(f'<text x="108" y="{ty}" font-size="15" letter-spacing="3" fill="#8A7A66" {font}>合计</text>')
    add(f'<text x="{W-108}" y="{ty+6}" font-size="40" font-weight="800" fill="#DA291C" text-anchor="end" '
        f'font-family="PingFang SC, sans-serif">{d["total"]}</text>')
    add(f'<line x1="108" y1="{ty-32}" x2="{W-108}" y2="{ty-32}" stroke="#E4CFAE" stroke-width="2"/>')

    # 核价徽标
    by = box_y + box_h + 22
    badge_w = 260
    add(f'<rect x="80" y="{by}" width="{badge_w}" height="36" rx="18" '
        f'fill="{"#E6F6EE" if d["verified"] else "#FFF4DF"}" '
        f'stroke="{"#BFE7D4" if d["verified"] else "#F0DCAF"}" stroke-width="1"/>')
    add(f'<text x="{80+badge_w/2}" y="{by+24}" font-size="14" font-weight="600" text-anchor="middle" '
        f'fill="{"#0E7A55" if d["verified"] else "#9A6A17"}" {font}>'
        f'{d["src_badge"]} {_svg_escape(d["badge_text"])}</text>')

    # 理由
    ry = by + 62
    if d["price_note"]:
        for ln in _wrap(d["price_note"], 40):
            add(f'<text x="84" y="{ry}" font-size="13" fill="#9A6A17" {font}>{_svg_escape(ln)}</text>')
            ry += 20
        ry += 10
    if d["reasons"]:
        add(f'<text x="84" y="{ry}" font-size="13" letter-spacing="5" fill="#B4894F" font-weight="600" {font}>为什么是它</text>')
        ry += 28
        for r in d["reasons"]:
            for ln in _wrap("· " + r, 34):
                add(f'<text x="84" y="{ry}" font-size="15" fill="#6E6152" {font}>{_svg_escape(ln)}</text>')
                ry += 24

    # 小贴士（空间够才画，避免和底部信息重叠）
    if d["tips"] and ry < H - 300:
        ry += 16
        add(f'<text x="84" y="{ry}" font-size="13" letter-spacing="5" fill="#B4894F" font-weight="600" {font}>小贴士</text>')
        ry += 26
        for t in d["tips"]:
            for ln in _wrap("› " + t, 34):
                add(f'<text x="84" y="{ry}" font-size="15" fill="#6E6152" {font}>{_svg_escape(ln)}</text>')
                ry += 24

    # 门店
    my = H - 190
    add(f'<line x1="80" y1="{my-24}" x2="{W-80}" y2="{my-24}" stroke="#EFE3CF" stroke-width="1.5"/>')
    store_txt = d["store"] or "—"
    add(f'<text x="80" y="{my}" font-size="15" fill="#B4894F" letter-spacing="2" {font}>门店</text>')
    add(f'<text x="136" y="{my}" font-size="15" fill="#6E6152" {font}>{_svg_escape(store_txt[:26])}</text>')
    add(f'<text x="80" y="{my+32}" font-size="15" fill="#B4894F" letter-spacing="2" {font}>时段</text>')
    add(f'<text x="136" y="{my+32}" font-size="15" fill="#6E6152" {font}>'
        f'{_svg_escape(d["period"])} · {_svg_escape(d["time"])}</text>')

    add(f'<text x="{W/2}" y="{H-92}" font-size="19" fill="#241C14" text-anchor="middle" letter-spacing="1" {font}>'
        f'要下单吗？  ·  还是再 Roll 一次？</text>')
    add(f'<text x="{W/2}" y="{H-62}" font-size="11" fill="#B9AE9E" text-anchor="middle" letter-spacing="2" {font}>'
        f'SHACHIKU PERSONA CARD</text>')
    add("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="渲染今日人设卡")
    ap.add_argument("--input", required=True, help="card.json 路径")
    ap.add_argument("--outdir", default=None, help="输出目录（默认与输入同目录）")
    ap.add_argument("--format", default="all", choices=["text", "html", "svg", "all"])
    ap.add_argument("--name", default="card", help="输出文件名前缀")
    args = ap.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as f:
        card = json.load(f)
    card.setdefault("time", datetime.now().strftime("%Y-%m-%d %H:%M"))
    card.setdefault("card_no", gen_card_no(card.get("seed")))

    outdir = args.outdir or os.path.dirname(os.path.abspath(args.input))
    os.makedirs(outdir, exist_ok=True)
    written = []

    if args.format in ("text", "all"):
        txt = render_text(card)
        p = os.path.join(outdir, f"{args.name}.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
        written.append(p)
        print(txt)
        print()

    if args.format in ("html", "all"):
        p = os.path.join(outdir, f"{args.name}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(render_html(card))
        written.append(p)

    if args.format in ("svg", "all"):
        p = os.path.join(outdir, f"{args.name}.svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(render_svg(card))
        written.append(p)

    if args.format != "text":
        print("已生成：" + "、".join(os.path.basename(x) for x in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
