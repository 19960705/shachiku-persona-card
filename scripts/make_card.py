#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社畜人设卡 · 组装 card.json

把三份数据合成一张卡：
  1. persona_engine.py pick 的输出（人设 + 选中的餐品）
  2. calculate-price 的原始响应（可选；有它才能标"已实时核验"）
  3. 门店 / 时段 / 时间（由 Agent 从 query-nearby-stores、now-time-info 取得）

为什么必须分开：菜单里的 currentPrice 可能是「随单购早餐卡价」，需要额外买卡
才成立。实测 9900003458 菜单价 ¥15.90，calculate-price 实付 ¥26.50。
所以卡面区分三种价格来源：calc（已核验）/ menu（菜单价未核价）/ demo（示例）。
"""

import argparse
import json
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

from card import gen_card_no  # noqa: E402


def fen2yuan(v):
    try:
        return round(int(v) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_calc(raw):
    """兼容 {data:{...}} 与已解包的 {...}。返回 (total, original, discount)。"""
    if not raw:
        return None
    d = raw.get("data", raw) if isinstance(raw, dict) else None
    if not isinstance(d, dict) or "price" not in d:
        return None
    return fen2yuan(d.get("price")), fen2yuan(d.get("originalPrice")), fen2yuan(d.get("discount"))


def _apply_calc_items(selection, calc_raw):
    """把 calculate-price 的分项小计写回卡片，保证单项价与合计自洽。"""
    d = calc_raw.get("data") if isinstance(calc_raw, dict) else None
    if not isinstance(d, dict):
        return
    plist = d.get("productList") or []
    for it in selection.get("items", []):
        for pl in plist:
            if str(pl.get("productCode")) != str(it.get("code")):
                continue
            sub = fen2yuan(pl.get("subtotal"))
            qty = int(it.get("quantity") or 1)
            if sub is not None and qty > 0:
                it.setdefault("menu_price", it.get("price"))
                it["price"] = round(sub / qty, 2)
            break


def build(pick, calc_raw=None, store=None, period=None, time_str=None, seed=None, mode=None):
    persona = pick["persona"]
    selection = pick["selection"]
    menu_price = selection.get("menu_price")
    menu_original = selection.get("menu_original")

    price = {"source": "menu", "total": menu_price, "original": menu_original, "menu_price": menu_price}
    extracted = extract_calc(calc_raw)
    if extracted:
        total, original, discount = extracted
        price.update(
            {
                "source": "calc",
                "total": total,
                "original": original if original else menu_original,
                "discount": discount,
            }
        )
        # 用核价返回的分项实付覆盖展示价，否则会出现"单项 ¥15.90、合计 ¥26.50"
        _apply_calc_items(selection, calc_raw)
        # 菜单价与实付不一致时，必须解释，别让用户以为被坑
        if menu_price is not None and total is not None and abs(float(menu_price) - float(total)) > 0.01:
            if float(total) > float(menu_price):
                price["note"] = (
                    f"菜单显示 ¥{menu_price:.2f} 属随单购/会员专享价，实付 ¥{total:.2f}，以核价为准"
                )
            else:
                price["note"] = f"核价后比菜单更低，已享优惠 ¥{float(menu_price) - float(total):.2f}"
            price["coupon_note"] = price["note"]

    card = {
        "mode": mode or pick.get("mode", "roll"),
        "persona": {"name": persona.get("name"), "emoji": persona.get("emoji"), "id": persona.get("id")},
        "tagline": pick.get("tagline", ""),
        "selection": selection,
        "price": price,
        "store": store or {},
        "period": period or "",
        "time": time_str or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "card_no": gen_card_no(seed),
        "menu_note": "",
        "tips": pick.get("tips", []),
        "seed": seed,
    }

    # 现场菜单没有该人设偏好的品类时，说明降级原因（例如深夜人设撞上早餐菜单）
    missing = selection.get("missing_slots") or []
    if missing:
        from persona_engine import FEATURE_LABEL

        names = "、".join(FEATURE_LABEL.get(m, m) for m in missing)
        card["menu_note"] = f"当前时段菜单没有「{names}」，已用现有可售餐品替代"

    return card


def main(argv=None):
    ap = argparse.ArgumentParser(description="组装 card.json")
    ap.add_argument("--pick", required=True, help="persona_engine.py pick 输出")
    ap.add_argument("--calc", default=None, help="calculate-price 原始响应")
    ap.add_argument("--store-name", default="")
    ap.add_argument("--store-code", default="")
    ap.add_argument("--period", default="")
    ap.add_argument("--time", default=None)
    ap.add_argument("--mode", default=None, choices=["roll", "order"])
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    pick = read_json(args.pick)
    calc_raw = read_json(args.calc) if args.calc else None
    store = {"name": args.store_name, "code": args.store_code} if args.store_name else {}
    card = build(pick, calc_raw, store, args.period, args.time, args.seed, args.mode)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2)
    print(json.dumps(card, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
