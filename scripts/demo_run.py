#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社畜人设卡 · 离线 demo（无需 Token / 无需 MCP）

跑通与线上完全相同的链路：人设 → 选餐 → 组装卡片 → 渲染。
唯一区别是菜单来自 data/demo_menu.json，价格标注为「示例数据 · 非实时」。

用法：
  python3 scripts/demo_run.py                          # Roll 一个
  python3 scripts/demo_run.py --seed 7                 # 可复现
  python3 scripts/demo_run.py --mode order --text "今天想省钱"
  python3 scripts/demo_run.py --persona calorie_anxiety
  python3 scripts/demo_run.py --all                    # 12 个人设各出一张，方便验收
"""

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

import card as cardmod  # noqa: E402
import make_card  # noqa: E402
from persona_engine import (  # noqa: E402
    load_menu,
    load_personas,
    match_persona,
    persona_by_id,
    pick_meal,
    pick_tagline,
    roll_persona,
)

DEMO_MENU = os.path.join(BASE_DIR, "data", "demo_menu.json")
OUT_DIR = os.path.join(BASE_DIR, "out")


def run(persona, products, mode, text, seed, store, period, time_str, tag="card"):
    selection = pick_meal(products, persona, text=text, period_key="breakfast", seed=seed)
    pick = {
        "mode": mode,
        "persona": {
            "id": persona["id"],
            "name": persona["name"],
            "emoji": persona.get("emoji", ""),
        },
        "tagline": pick_tagline(persona, seed),
        "selection": selection,
        "tips": persona.get("tips", []),
    }
    c = make_card.build(pick, None, store, period, time_str, seed, mode)
    c["price"]["source"] = "demo"
    c["price"]["original"] = selection.get("menu_original")

    cardmod_text = cardmod.render_text(c)
    os.makedirs(OUT_DIR, exist_ok=True)
    for fmt, content in (
        ("txt", cardmod_text + "\n"),
        ("html", cardmod.render_html(c)),
        ("svg", cardmod.render_svg(c)),
    ):
        with open(os.path.join(OUT_DIR, f"{tag}.{fmt}"), "w", encoding="utf-8") as f:
            f.write(content)
    with open(os.path.join(OUT_DIR, f"{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    return cardmod_text


def main(argv=None):
    ap = argparse.ArgumentParser(description="社畜人设卡离线 demo")
    ap.add_argument("--mode", default="roll", choices=["roll", "order"])
    ap.add_argument("--text", default="")
    ap.add_argument("--persona", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--all", action="store_true", help="12 个人设各出一张卡")
    args = ap.parse_args(argv)

    personas = load_personas()
    products = load_menu(DEMO_MENU)
    with open(DEMO_MENU, "r", encoding="utf-8") as f:
        meta = json.load(f).get("meta", {})
    store = {"name": meta.get("store", ""), "code": meta.get("storeCode", "")}
    period, time_str = meta.get("period", "早餐"), meta.get("capturedAt", "")

    if args.all:
        print(f"离线 demo：{len(personas)} 个人设 · 菜单 {len(products)} 个餐品\n")
        for i, p in enumerate(personas):
            print("=" * 62)
            print(run(p, products, "roll", "", i + 1, store, period, time_str, tag=p["id"]))
        print("=" * 62)
        print(f"卡片已输出到 {OUT_DIR}/（每个人设 .txt/.html/.svg/.json）")
        return 0

    if args.persona:
        persona = persona_by_id(personas, args.persona)
        mode = "order" if args.text else args.mode
    elif args.mode == "order" and args.text:
        persona, hits, _ = match_persona(args.text, personas, "breakfast")
        mode = "order"
        if hits:
            print(f"[匹配关键词] {'、'.join(hits)}")
    else:
        persona = roll_persona(personas, args.seed, "breakfast")
        mode = "roll"

    print(run(persona, products, mode, args.text, args.seed, store, period, time_str))
    print(f"\n（卡片已输出到 {OUT_DIR}/card.txt · card.html · card.svg · card.json）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
