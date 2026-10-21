#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社畜人设卡 · 画廊（离线）

把 12 个人设各出一张卡，拼成一个 HTML 页面，方便一眼验收版式和文案。
用法：
    python3 scripts/gallery.py            # 用 demo 菜单
    python3 scripts/gallery.py --menu tests/fixtures/lunch_menu_raw.json --period 午餐
"""

import argparse
import html
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

import card as cardmod  # noqa: E402
import make_card  # noqa: E402
from persona_engine import load_menu, load_personas, pick_meal, pick_tagline  # noqa: E402

OUT = os.path.join(BASE_DIR, "out")


def one(persona, products, store, period, time_str, seed, source):
    sel = pick_meal(products, persona, seed=seed)
    pick = {
        "mode": "roll",
        "persona": {"id": persona["id"], "name": persona["name"], "emoji": persona.get("emoji", "")},
        "tagline": pick_tagline(persona, seed),
        "selection": sel,
        "tips": persona.get("tips", []),
    }
    c = make_card.build(pick, None, store, period, time_str, seed, "roll")
    c["price"]["source"] = source
    c["price"]["original"] = sel.get("menu_original")
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成人设卡画廊")
    ap.add_argument("--menu", default=os.path.join(BASE_DIR, "data", "demo_menu.json"))
    ap.add_argument("--period", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    personas = load_personas()
    products = load_menu(args.menu)

    raw = json.load(open(args.menu, encoding="utf-8"))
    meta = raw.get("meta", {})
    store = {"name": meta.get("store", "示例餐厅"), "code": meta.get("storeCode", "")}
    period = args.period or meta.get("period", "午餐")
    time_str = meta.get("capturedAt", "2026-10-21 10:59")
    source = "demo" if "demo_menu" in args.menu else "menu"

    cells = []
    for i, p in enumerate(personas):
        c = one(p, products, store, period, time_str, i + 1, source)
        svg = cardmod.render_svg(c).replace('width="720" height="1040"', 'style="width:100%;height:auto"', 1)
        cells.append(f'<figure class="cell">{svg}<figcaption>{html.escape(p["name"])} · {html.escape(c["tagline"])}</figcaption></figure>')

    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>社畜人设卡 · 12 人设画廊</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#EFE9DD;font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",-apple-system,sans-serif;
padding:44px 32px 60px;color:#241C14}}
header{{max-width:1500px;margin:0 auto 30px}}
h1{{font-size:34px;letter-spacing:.04em}}
.sub{{margin-top:10px;font-size:15px;color:#7A6A57;line-height:1.7}}
.tag{{display:inline-block;margin-left:10px;font-size:12px;padding:3px 10px;border-radius:999px;
background:#FFF6E8;border:1px solid #F2DFC2;color:#B4894F;vertical-align:middle}}
.grid{{max-width:1500px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr);gap:26px}}
.cell{{background:transparent}}
.cell svg{{display:block;border-radius:18px;box-shadow:0 12px 30px rgba(64,44,26,.12)}}
figcaption{{margin-top:12px;font-size:13px;color:#7A6A57;line-height:1.55}}
@media (max-width:1200px){{.grid{{grid-template-columns:repeat(3,1fr)}}}}
@media (max-width:860px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head>
<body>
<header>
  <h1>社畜人设卡 · 12 个人设<span class="tag">{html.escape(period)}菜单 · {len(products)} 个餐品</span></h1>
  <div class="sub">同一份菜单，12 种活法。价格标注{'「示例数据 · 非实时」' if source == 'demo' else '「菜单价 · 尚未核价」'}，真实链路会由 calculate-price 覆盖为「已实时核验」。</div>
</header>
<div class="grid">
{''.join(cells)}
</div>
</body></html>
"""
    os.makedirs(OUT, exist_ok=True)
    out = args.out or os.path.join(OUT, "gallery.html")
    open(out, "w", encoding="utf-8").write(page)
    print(f"已生成 {out}（{len(personas)} 张卡）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
