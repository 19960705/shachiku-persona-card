#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社畜人设卡 · 人设匹配与餐品选择引擎

设计原则
--------
1. 人设不写死 SKU，只描述「需求特征」（主食/炸物/甜品/咖啡/饮品/轻食/早餐 权重 +
   价格带 + 搭配策略）。原因：麦当劳菜单按时段下发，09:30 查菜单只有早餐，
   硬编码"板烧鸡腿堡三件套"会推不出东西。特征匹配则在任何时段都有解。
2. 全流程纯标准库、无网络、可复现（支持 --seed）。
3. 输出统一 JSON 到 stdout，方便 Agent 直接消费；人类可读文本由 card.py 渲染。

子命令
------
  list                              列出人设库
  match  --text "今天想省钱"         点餐模式：文本 → 人设
  roll   [--seed 42]                 Roll 模式：按时段加权随机抽人设
  pick   --menu m.json --persona X   从真实菜单挑餐品
         [--text "..."]             用户点了名的餐品会被强制保留
         [--period breakfast]       覆盖时段
"""

import argparse
import json
import os
import random
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSONAS_PATH = os.path.join(BASE_DIR, "data", "personas.json")

# ---------------------------------------------------------------- 特征词典
# 说明：burger 语义上指"能当一餐主食的夹馍/卷类"，含麦满分、营养卷、松饼堡。
# 一个餐品可同时命中多个特征（如"脆薯饼"= fried + breakfast），这是有意的。
LEXICON = {
    "burger": [
        "汉堡", "巨无霸", "麦满分", "营养卷", "松饼", "双蛋堡", "板烧鸡腿",
        "鸡腿堡", "鸡扒", "吉士", "猪柳", "火腿扒", "牛肉", "堡",
    ],
    "fried": ["薯条", "薯饼", "鸡块", "麦乐鸡", "油条", "香肠", "鸡排", "鸡翅", "脆薯"],
    "dessert": [
        "麦旋风", "新地", "冰淇淋", "圆筒", "圣代", "派", "奶昔", "甜",
        "爆爆珠", "星星", "脆脆", "灰焰", "蓝莓", "燕麦黑巧",
    ],
    "coffee": ["咖啡", "拿铁", "美式", "黑巧", "浓缩", "鲜萃"],
    "drink": [
        "可乐", "雪碧", "汁", "牛奶", "纯悦", "红茶", "奶茶", "豆浆",
        "+C", "柠柠", "柠檬", "水",
    ],
    "light": ["沙拉", "玉米杯", "纯悦", "无糖", "零度", "低卡", "蔬菜"],
    # 麦当劳有专门的「500 大卡套餐」分类，比自己按名字猜热量可靠
    "lowcal": ["大卡", "低卡", "轻食", "沙拉"],
    # 杯装甜品（麦旋风/新地/圣代）比圆筒更有"快乐"分量
    "dessert2": ["麦旋风", "新地", "圣代", "奶昔"],
    "breakfast": [
        "麦满分", "早餐", "油条", "豆浆", "营养卷", "松饼", "炒双蛋", "薯饼", "优品",
    ],
    "combo": ["套餐", "组合", "三件套", "二件套"],
    # 三件套/套餐 = 完整一餐；二件套/组合 = 主食+饮料的轻量搭配。
    # 不区分的话「加班狗要三件套」会拿到二件套。
    "combo3": ["三件套", "套餐"],
    "combo2": ["二件套", "组合"],
    "multi": ["双人", "全家", "桶", "分享", "拼盘"],
    "hot": ["辣", "板烧", "双层", "巨无霸", "牛肉", "鸡腿", "脆鸡", "香辣"],
}

# 分类名 → 特征（权重减半，作为弱信号）。
# 注意：不要给"小食甜品"加 fried/dessert —— 麦当劳把冰淇淋、派、油条、玉米杯
# 全放在同一个分类里，按分类挂标签会让"新地"被当成炸物。
CATEGORY_HINTS = {
    "早餐": ["breakfast"],
    "咖啡": ["coffee", "drink"],
    "饮品": ["drink"],
    "大卡": ["lowcal"],
}

FEATURE_LABEL = {
    "burger": "主食扎实",
    "fried": "有炸物",
    "dessert": "有甜品",
    "coffee": "有咖啡",
    "drink": "配饮料",
    "light": "相对轻负担",
    "lowcal": "低卡套餐",
    "dessert2": "杯装甜品",
    "breakfast": "早餐属性",
    "combo": "套餐形态",
    "combo3": "完整三件套",
    "combo2": "轻量二件套",
    "multi": "适合多人",
    "hot": "重口味",
}

BAND_ORDER = {"low": 0, "mid": 1, "high": 2}

# ---------------------------------------------------------------- 时段
PERIODS = [
    ("breakfast", "早餐", 5 * 60, 10 * 60 + 30),
    ("lunch", "午餐", 10 * 60 + 30, 14 * 60),
    ("teatime", "下午茶", 14 * 60, 17 * 60),
    ("dinner", "夜市", 17 * 60, 22 * 60),
]
LATENIGHT = ("latenight", "宵夜")


def period_of(hour, minute=0):
    """返回 (period_key, period_name)。22:00–05:00 为宵夜。"""
    m = hour * 60 + minute
    for key, name, start, end in PERIODS:
        if start <= m < end:
            return key, name
    return LATENIGHT


# ---------------------------------------------------------------- 载入
def load_personas(path=PERSONAS_PATH):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["personas"]


def persona_by_id(personas, pid):
    for p in personas:
        if p["id"] == pid:
            return p
    raise SystemExit(f"[error] 未知人设 id: {pid}（用 `persona_engine.py list` 查看）")


def _features_from_text(text):
    feat = {}
    for key, words in LEXICON.items():
        for w in words:
            if w in text:
                feat[key] = 1
                break
    return feat


def load_menu(path):
    """兼容两种输入：
    1) query-meals 原始响应（含 data.categories / data.meals 映射）
    2) 精简格式 {"meals": [{"code","name","price",...}]} 或直接数组
    返回统一的产品列表。
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    products = []

    # --- 形式 2：数组 / {"meals": [...]}
    if isinstance(raw, list) or (isinstance(raw, dict) and isinstance(raw.get("meals"), list)):
        arr = raw if isinstance(raw, list) else raw["meals"]
        for it in arr:
            name = it.get("name") or ""
            price = it.get("price", it.get("currentPrice"))
            products.append(
                {
                    "code": str(it.get("code") or it.get("productCode")),
                    "name": name,
                    "price": float(price) if price is not None else None,
                    "original_price": _to_float(it.get("originalPrice")),
                    "tags": it.get("tags") or [],
                    "category": it.get("category") or "",
                    "image": it.get("image") or "",
                }
            )
        return _finalize(products)

    # --- 形式 1：MCP 原始响应
    data = raw.get("data", raw)
    meals_map = data.get("meals") or {}
    tag_map, cat_map = {}, {}

    for cat in data.get("categories") or []:
        cname = (cat.get("name") or "").replace("\n", "")
        for m in cat.get("meals") or []:
            code = str(m.get("code"))
            tag_map.setdefault(code, []).extend(m.get("tags") or [])
            if cname and code not in cat_map:
                cat_map[code] = cname

    for code, m in meals_map.items():
        code = str(code)
        name = m.get("name") or ""
        products.append(
            {
                "code": code,
                "name": name,
                "price": _to_float(m.get("currentPrice")),
                "original_price": _to_float(m.get("originalPrice")),
                "tags": tag_map.get(code, []),
                "category": cat_map.get(code, ""),
                "image": m.get("image") or "",
            }
        )

    if not products:
        raise SystemExit(f"[error] 菜单为空或结构无法识别: {path}")
    return _finalize(products)


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _finalize(products):
    """补特征、过滤无价格的、按价格分档。"""
    clean = [p for p in products if p["price"] is not None and p["name"]]
    for p in clean:
        feat = _features_from_text(p["name"])
        for w, keys in CATEGORY_HINTS.items():
            if w in p["category"]:
                for k in keys:
                    feat[k] = 1
        for t in p["tags"]:
            if "早餐" in t:
                feat["breakfast"] = 1
        p["features"] = feat

    prices = sorted(p["price"] for p in clean)
    if prices:
        q1 = prices[len(prices) // 3]
        q2 = prices[(len(prices) * 2) // 3]
        lo, hi = prices[0], prices[-1]
        for p in clean:
            pr = p["price"]
            p["band"] = "low" if pr <= q1 else ("mid" if pr <= q2 else "high")
            # 价格在菜单内的相对位置，0=最便宜 1=最贵。供"省钱/放纵"人设连续打分用。
            p["price_norm"] = round((pr - lo) / (hi - lo), 3) if hi > lo else 0.5
    return clean


# ---------------------------------------------------------------- 打分
def score_item(p, persona):
    """返回 (分数, 命中理由列表)。"""
    feat = p["features"]
    score, reasons = 0.0, []

    for key, weight in persona.get("prefer", {}).items():
        if feat.get(key):
            score += weight
            reasons.append(f"{FEATURE_LABEL.get(key, key)}(+{weight:.1f})")

    band = persona.get("price_band", "any")
    if band != "any":
        diff = BAND_ORDER[band] - BAND_ORDER[p["band"]]
        if diff == 0:
            score += 0.45
            reasons.append("价格带吻合(+0.5)")
        elif abs(diff) == 1:
            score += 0.10
        else:
            score -= 0.55

        # 连续价格偏好：省钱人设偏爱菜单里最便宜的，放纵人设偏爱最贵的
        norm = p.get("price_norm", 0.5)
        if band == "low":
            score += 0.50 * (1 - norm)
        elif band == "high":
            score += 0.50 * norm

    # 静默降权：既没味道也没形态的产品（如纯周边）不该被选中
    if not feat:
        score -= 1.0
    return score, reasons


def rank_items(products, persona):
    scored = []
    for p in products:
        s, r = score_item(p, persona)
        scored.append((s, p, r))
    scored.sort(key=lambda x: (-x[0], x[1]["price"]))
    return scored


# ---------------------------------------------------------------- 点餐模式：文本 → 人设
def match_persona(text, personas, period_key=None):
    text = (text or "").strip()
    scores = {}
    for p in personas:
        if p.get("is_fallback"):
            continue
        s = 0.0
        for kw in p.get("keywords", []):
            if kw in text:
                s += 1.0 + 0.05 * len(kw)  # 长关键词更具体，给一点点加成
        if period_key and period_key in p.get("periods", []):
            s += 0.8
        if s > 0:
            scores[p["id"]] = round(s, 2)

    if not scores:
        fb = next(p for p in personas if p.get("is_fallback"))
        return fb, [], {"reason": "no_signal"}

    best_id = max(scores.items(), key=lambda kv: (kv[1], -_order_of(personas, kv[0])))[0]
    best = persona_by_id(personas, best_id)
    hits = [kw for kw in best.get("keywords", []) if kw in text]
    return best, hits, {"reason": "keyword", "scores": scores}


def _order_of(personas, pid):
    for i, p in enumerate(personas):
        if p["id"] == pid:
            return i
    return 999


# ---------------------------------------------------------------- Roll 模式
def roll_persona(personas, seed=None, period_key=None):
    pool = [p for p in personas]
    weights = []
    for p in pool:
        w = 1.0
        if period_key and period_key in p.get("periods", []):
            w *= 2.5  # 时段契合的人设更容易被抽到
        if p.get("is_fallback"):
            w *= 0.6
        weights.append(w)

    rnd = random.Random(seed)
    total = sum(weights)
    r = rnd.uniform(0, total)
    acc = 0.0
    for p, w in zip(pool, weights):
        acc += w
        if r <= acc:
            return p
    return pool[-1]


def pick_tagline(persona, seed=None):
    tags = persona.get("taglines") or ["今天的你，就是普通社畜"]
    rnd = random.Random(seed)
    return tags[rnd.randrange(len(tags))]


# ---------------------------------------------------------------- 选餐
def find_named_items(products, text, persona=None):
    """在用户原话里找被点名的餐品。

    用户说"麦满分"会同时命中"猪柳蛋麦满分套餐""板烧麦满分套餐"等多个 SKU。
    同一个命中词只保留一个最优 SKU（按人设打分），否则会一口气买四份主食。
    """
    if not text:
        return []
    by_token = {}
    for p in products:
        name = p["name"]
        best = ""
        for i in range(len(name)):
            for j in range(len(name), i + 1, -1):
                sub = name[i:j]
                if len(sub) >= 2 and sub in text and len(sub) > len(best):
                    best = sub
        if not best:
            continue
        score = score_item(p, persona)[0] if persona else 0.0
        cur = by_token.get(best)
        if cur is None or score > cur[0]:
            by_token[best] = (score, p)

    # 长词优先（"麦满分套餐" 比 "麦满分" 更具体）
    ordered = sorted(by_token.items(), key=lambda kv: (-len(kv[0]), -kv[1][0]))
    out, seen = [], set()
    for _, (_, p) in ordered:
        if p["code"] in seen:
            continue
        seen.add(p["code"])
        out.append(p)
        if len(out) >= 2:  # 一餐最多认两个点名餐品，再多就是替用户做决定了
            break
    return out


def is_drink_only(p):
    """只有饮品属性、没有饱腹属性的产品（纯悦、可乐等）。

    用于避免"轻负担"这类 slot 被一瓶水占掉，也避免拼出两份饮料。
    """
    f = p["features"]
    solid = f.get("burger") or f.get("fried") or f.get("dessert") or f.get("breakfast")
    return bool(f.get("drink")) and not solid


def _slot_ok(p, slot):
    if slot == "drink":
        return p["features"].get("drink") and not p["features"].get("coffee")
    if slot == "coffee":
        return p["features"].get("coffee")
    return not is_drink_only(p)


ROLE_PRIORITY = ["combo", "lowcal", "burger", "fried", "dessert", "coffee", "drink", "light"]


def role_of(p):
    """餐品在拼单里的角色。同一套里角色不重复，避免"两份主食""两份饮料"。"""
    f = p["features"]
    for r in ROLE_PRIORITY:
        if f.get(r):
            return r
    return "other"


def _compose(products, persona, must_products, quantity):
    """按 slots 拼一套（单品拼配）。

    规则：
    - 不使用套餐产品占单品位（整套需求走 combo 策略，避免"套餐+套餐"）。
    - 同一角色只出现一次。
    - 已点名的餐品优先占用角色。
    """
    slots = persona.get("slots") or ["burger", "drink"]
    used_codes = {p["code"] for p in must_products}
    chosen = [{"product": p, "role": "用户点名"} for p in must_products]
    used_roles = {role_of(p) for p in must_products}
    missing = []

    # 用户已经点了两样，说明心里有数，不要再替他加东西
    if len(must_products) >= 2:
        slots = []

    for slot in slots:
        if len(chosen) >= 3:
            break
        # 已经有一份饮料/咖啡了，就别再配第二杯
        if slot in ("drink", "coffee") and any(
            c["product"]["features"].get("drink") or c["product"]["features"].get("coffee")
            for c in chosen
        ):
            continue
        # 套餐本身已含饮料，再配一杯就是重复消费
        if slot == "drink" and any(c["product"]["features"].get("combo") for c in chosen):
            continue
        pool = [
            p
            for p in products
            if p["features"].get(slot)
            and p["code"] not in used_codes
            and role_of(p) not in used_roles
            and _slot_ok(p, slot)
        ]
        singles = [p for p in pool if not p["features"].get("combo")]
        if singles:
            pool = singles
        ranked = rank_items(pool, persona)
        if not ranked:
            missing.append(slot)
            continue
        best = ranked[0][1]
        used_codes.add(best["code"])
        used_roles.add(role_of(best))
        chosen.append({"product": best, "role": FEATURE_LABEL.get(slot, slot)})

    if not chosen:
        return None

    total_score = 0.0
    for c in chosen:
        s, _ = score_item(c["product"], persona)
        total_score += s
    reasons = []
    for c in chosen:
        _, r = score_item(c["product"], persona)
        if r:
            reasons.append(f"{c['product']['name']}：{'、'.join(r[:2])}")
    return {
        "strategy": "compose",
        "items": chosen,
        "score": round(total_score / max(len(chosen), 1), 3),
        "reasons": reasons,
        "missing_slots": missing,
        "quantity": quantity,
    }


def pick_meal(products, persona, text=None, period_key=None, seed=None):
    """返回选餐结果 dict。"""
    quantity = int(persona.get("quantity_hint", 1) or 1)

    # 首选槽位在当前菜单完全不存在时（例如早餐时段没有「500大卡套餐」），
    # 退到备选槽位，而不是只推一个孤零零的饮料。
    slots = persona.get("slots") or []
    if slots and persona.get("fallback_slots"):
        if not any(p["features"].get(slots[0]) for p in products):
            persona = {**persona, "slots": persona["fallback_slots"]}

    must = find_named_items(products, text, persona)
    strategy = persona.get("strategy", "auto")

    # 用户在点餐模式下点名了餐品 → 以点名为主，再用 slots 补齐
    if must:
        result = _compose(products, persona, must, 1)
        if result:
            result["strategy"] = "user_named" if len(result["items"]) == len(must) else "user_named_plus"
            result["persona_strategy"] = strategy
            return _signature(result, result["items"][0]["product"], quantity)

    combo_pool = [p for p in products if p["features"].get("combo")]
    plain_pool = [p for p in products if not p["features"].get("combo")]

    if strategy == "auto":
        strategy = "combo" if (persona.get("prefer", {}).get("combo", 0) >= 0.5 and combo_pool) else "compose"

    if strategy == "combo":
        pool = combo_pool or plain_pool
        ranked = rank_items(pool, persona)
        if ranked:
            top = ranked[0]
            return _signature(
                {
                    "strategy": "combo" if combo_pool else "combo_fallback_single",
                    "items": [{"product": top[1], "role": "套餐"}],
                    "score": round(top[0], 3),
                    "reasons": [f"{top[1]['name']}：{'、'.join(top[2][:3])}"] if top[2] else [],
                    "missing_slots": [],
                    "quantity": quantity,
                },
                top[1],
                quantity,
            )

    if strategy == "single":
        ranked = rank_items(plain_pool or products, persona)
        top = ranked[0]
        return _signature(
            {
                "strategy": "single",
                "items": [{"product": top[1], "role": "单品"}],
                "score": round(top[0], 3),
                "reasons": [f"{top[1]['name']}：{'、'.join(top[2][:3])}"] if top[2] else [],
                "missing_slots": [],
                "quantity": quantity,
            },
            top[1],
            quantity,
        )

    if strategy == "random":
        ranked = rank_items(products, persona)[:5]
        rnd = random.Random(seed)
        s, p, r = ranked[rnd.randrange(len(ranked))]
        return _signature(
            {
                "strategy": "random",
                "items": [{"product": p, "role": "手气"}],
                "score": round(s, 3),
                "reasons": [f"{p['name']}：{'、'.join(r[:3])}"] if r else [],
                "missing_slots": [],
                "quantity": quantity,
            },
            p,
            quantity,
        )

    # compose
    result = _compose(products, persona, [], quantity)
    if result is None:
        ranked = rank_items(products, persona)
        top = ranked[0]
        result = {
            "strategy": "fallback_single",
            "items": [{"product": top[1], "role": "单品"}],
            "score": round(top[0], 3),
            "reasons": [],
            "missing_slots": [],
            "quantity": quantity,
        }
    return _signature(result, result["items"][0]["product"], quantity)


def _signature(result, headline, quantity):
    """归一化输出：补齐合计价、展示标题。"""
    items = []
    total = 0.0
    original = 0.0
    for c in result["items"]:
        p = c["product"]
        q = int(c.get("quantity") or quantity)
        items.append(
            {
                "code": p["code"],
                "name": p["name"],
                "price": p["price"],
                "original_price": p.get("original_price"),
                "role": c["role"],
                "quantity": q,
                "image": p.get("image", ""),
            }
        )
        total += p["price"] * q
        original += (p.get("original_price") or p["price"]) * q
    result["items"] = items
    result["menu_price"] = round(total, 2)
    result["menu_original"] = round(original, 2)
    result["title"] = " + ".join(
        it["name"] + (f" ×{it['quantity']}" if it["quantity"] > 1 else "") for it in items
    )
    result["headline"] = headline["name"]
    return result


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="社畜人设卡引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出人设库")

    pcmd = sub.add_parser("period", help="当前时段（优先用 MCP now-time-info 的时间）")
    pcmd.add_argument("--clock", default=None, help='now-time-info 的 formatted/ datetime，如 "2026-10-21 09:32:36"')
    pcmd.add_argument("--hour", type=int, default=None)
    pcmd.add_argument("--minute", type=int, default=0)

    m = sub.add_parser("match", help="点餐模式：文本 → 人设")
    m.add_argument("--text", required=True)
    m.add_argument("--period", default=None)

    r = sub.add_parser("roll", help="Roll 模式")
    r.add_argument("--seed", type=int, default=None)
    r.add_argument("--period", default=None)

    p = sub.add_parser("pick", help="从菜单选餐")
    p.add_argument("--menu", required=True)
    p.add_argument("--persona", required=True)
    p.add_argument("--text", default=None)
    p.add_argument("--period", default=None)
    p.add_argument("--seed", type=int, default=None)

    args = ap.parse_args(argv)
    personas = load_personas()

    if args.cmd == "period":
        from datetime import datetime

        h = m = None
        if args.clock:
            txt = args.clock.replace("T", " ").split(".")[0].strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
                try:
                    dt = datetime.strptime(txt, fmt)
                    h, m = dt.hour, dt.minute
                    break
                except ValueError:
                    continue
        if h is None:
            now = datetime.now()
            h = args.hour if args.hour is not None else now.hour
            m = args.minute if args.hour is not None else now.minute
        key, name = period_of(h, m)
        print(
            json.dumps(
                {"period": key, "name": name, "clock": f"{h:02d}:{m:02d}"},
                ensure_ascii=False,
            )
        )
        return 0

    if args.cmd == "list":
        out = [
            {
                "id": x["id"],
                "name": x["name"],
                "emoji": x["emoji"],
                "tagline": (x.get("taglines") or [""])[0],
                "keywords": x.get("keywords", []),
                "strategy": x.get("strategy"),
                "price_band": x.get("price_band"),
            }
            for x in personas
        ]
        print(json.dumps({"count": len(out), "personas": out}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "match":
        persona, hits, meta = match_persona(args.text, personas, args.period)
        print(
            json.dumps(
                {
                    "mode": "order",
                    "persona": _persona_public(persona),
                    "tagline": pick_tagline(persona, None),
                    "matched_keywords": hits,
                    "meta": meta,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.cmd == "roll":
        persona = roll_persona(personas, args.seed, args.period)
        print(
            json.dumps(
                {
                    "mode": "roll",
                    "persona": _persona_public(persona),
                    "tagline": pick_tagline(persona, args.seed),
                    "seed": args.seed,
                    "meta": {"reason": "weighted_random", "period": args.period},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.cmd == "pick":
        persona = persona_by_id(personas, args.persona)
        products = load_menu(args.menu)
        result = pick_meal(products, persona, args.text, args.period, args.seed)
        bands = {}
        for it in result["items"]:
            for prod in products:
                if prod["code"] == it["code"]:
                    bands[it["code"]] = prod["band"]
        print(
            json.dumps(
                {
                    "persona": _persona_public(persona),
                    "tagline": pick_tagline(persona, args.seed),
                    "selection": result,
                    "price_bands": bands,
                    "menu_stats": {"count": len(products)},
                    "tips": persona.get("tips", []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return 1


def _persona_public(p):
    return {
        "id": p["id"],
        "name": p["name"],
        "emoji": p.get("emoji", ""),
        "taglines": p.get("taglines", []),
        "strategy": p.get("strategy"),
        "price_band": p.get("price_band"),
        "coupon_mode": p.get("coupon_mode", False),
        "closing": p.get("closing", ["要下单吗？"]),
    }


if __name__ == "__main__":
    sys.exit(main())
