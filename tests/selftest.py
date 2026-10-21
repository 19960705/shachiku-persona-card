#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社畜人设卡 · 自测（无网络、无 Token）

    python3 tests/selftest.py

覆盖：人设库完整性、时段判定、MCP 菜单解析、关键词匹配、Roll 可复现性、
选餐策略、点名餐品去重、核价覆盖与价差提示、三种卡片渲染。
"""

import json
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import card as cardmod  # noqa: E402
import make_card  # noqa: E402
from persona_engine import (  # noqa: E402
    find_named_items,
    load_menu,
    load_personas,
    match_persona,
    period_of,
    persona_by_id,
    pick_meal,
    pick_tagline,
    roll_persona,
)

FIX = os.path.join(ROOT, "tests", "fixtures")
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"  <- {detail}"))


def section(t):
    print(f"\n[{t}]")


# ---------------------------------------------------------------- 1 人设库
section("人设库")
personas = load_personas()
check("人设数量为 12", len(personas) == 12, len(personas))
check("id 唯一", len({p["id"] for p in personas}) == 12)
required = {"id", "name", "taglines", "keywords", "prefer", "price_band", "strategy", "slots"}
check("字段完整", all(required <= set(p) for p in personas))
check("有且只有一个兜底人设", sum(1 for p in personas if p.get("is_fallback")) == 1)
check(
    "非兜底人设都有触发关键词",
    all(p.get("keywords") for p in personas if not p.get("is_fallback")),
)
check(
    "price_band 取值合法",
    all(p["price_band"] in ("low", "mid", "high", "any") for p in personas),
)
check(
    "strategy 取值合法",
    all(p["strategy"] in ("combo", "compose", "single", "random", "auto") for p in personas),
)

# ---------------------------------------------------------------- 2 时段
section("时段判定")
cases = [
    ((6, 30), "breakfast"),
    ((10, 29), "breakfast"),
    ((10, 30), "lunch"),
    ((13, 0), "lunch"),
    ((15, 0), "teatime"),
    ((19, 0), "dinner"),
    ((23, 30), "latenight"),
    ((2, 0), "latenight"),
    ((4, 59), "latenight"),
]
check("9 个时段边界", all(period_of(h, m)[0] == k for (h, m), k in cases))

# ---------------------------------------------------------------- 3 菜单解析
section("MCP 菜单解析")
menu = load_menu(os.path.join(FIX, "mcp_menu_raw.json"))
check("解析出 10 个餐品", len(menu) == 10, len(menu))
by_name = {p["name"]: p for p in menu}
check("价格转成浮点", all(isinstance(p["price"], float) for p in menu))
check("名称与原始价保留", by_name["猪柳蛋麦满分套餐"]["original_price"] == 26.5)
check(
    "分类名换行被清理",
    by_name["经典麦旋风"]["category"] == "小食甜品/其他",
    by_name["经典麦旋风"]["category"],
)
check(
    "冰淇淋不会被当成炸物",
    by_name["经典麦旋风"]["features"].get("dessert") == 1
    and not by_name["经典麦旋风"]["features"].get("fried"),
    by_name["经典麦旋风"]["features"],
)
check(
    "脆薯饼 同时是炸物+早餐",
    by_name["脆薯饼"]["features"].get("fried") == 1 and by_name["脆薯饼"]["features"].get("breakfast") == 1,
)
check(
    "套餐 标记 combo + combo3",
    by_name["猪柳蛋麦满分套餐"]["features"].get("combo") == 1
    and by_name["猪柳蛋麦满分套餐"]["features"].get("combo3") == 1,
)
check(
    "组合 标记 combo + combo2（不是 combo3）",
    by_name["原味板烧鸡腿麦满分组合"]["features"].get("combo") == 1
    and by_name["原味板烧鸡腿麦满分组合"]["features"].get("combo2") == 1
    and not by_name["原味板烧鸡腿麦满分组合"]["features"].get("combo3"),
)
check("价格分档覆盖全部餐品", all(p.get("band") in ("low", "mid", "high") for p in menu))
check("价格归一化在 0~1", all(0 <= p.get("price_norm", -1) <= 1 for p in menu))

# ---------------------------------------------------------------- 4 点餐模式
section("点餐模式人设匹配")
match_cases = [
    ("今天想省钱", "budget_warrior"),
    ("优惠券怎么用划算", "budget_warrior"),
    ("有没有低卡的", "calorie_anxiety"),
    ("想吃甜品开心一下", "happy_looper"),
    ("深夜还在写代码", "midnight_coder"),
    ("不知道吃啥都行", "indecisive"),
    ("三个人一起拼单", "team_lead"),
    ("早餐来个麦满分", "breakfast_soldier"),
    ("想吃好的犒劳自己", "cheat_day"),
]
for text, expect in match_cases:
    got, hits, _ = match_persona(text, personas)
    check(f"「{text}」→ {expect}", got["id"] == expect, f"实际 {got['id']}")

fb, _, meta = match_persona("嗯", personas)
check("无信号时落到兜底人设", fb["id"] == "random_office" and meta["reason"] == "no_signal")

# ---------------------------------------------------------------- 5 Roll
section("Roll 模式")
a = roll_persona(personas, seed=42)
b = roll_persona(personas, seed=42)
c = roll_persona(personas, seed=43)
check("同 seed 结果一致（可复现）", a["id"] == b["id"], f"{a['id']} vs {b['id']}")
check("不同 seed 结果不同", a["id"] != c["id"], f"{a['id']} vs {c['id']}")
check("Roll 结果在人设库内", a["id"] in {p["id"] for p in personas})
night = [roll_persona(personas, seed=s, period_key="latenight")["id"] for s in range(60)]
morning = [roll_persona(personas, seed=s, period_key="breakfast")["id"] for s in range(60)]
check(
    "深夜更容易抽到宵夜人设",
    night.count("midnight_coder") > morning.count("midnight_coder"),
    f"夜 {night.count('midnight_coder')} / 早 {morning.count('midnight_coder')}",
)
check(
    "早餐更容易抽到早餐战士",
    morning.count("breakfast_soldier") > night.count("breakfast_soldier"),
    f"早 {morning.count('breakfast_soldier')} / 夜 {night.count('breakfast_soldier')}",
)
check("标语来自该人设", pick_tagline(a, 1) in a["taglines"])

# ---------------------------------------------------------------- 6 选餐
section("选餐策略")
dog = persona_by_id(personas, "overtime_dog")
r_dog = pick_meal(menu, dog, seed=1)
check("加班狗走套餐策略", r_dog["strategy"] == "combo", r_dog["strategy"])
check(
    "加班狗拿到的是套餐类餐品",
    any(it["code"] in ("9900003458", "9900003493") for it in r_dog["items"]),
    [it["name"] for it in r_dog["items"]],
)
check("菜单价 = 各项单价之和", r_dog["menu_price"] == round(sum(it["price"] * it["quantity"] for it in r_dog["items"]), 2))

cal = persona_by_id(personas, "calorie_anxiety")
r_cal = pick_meal(menu, cal, seed=1)
codes = [it["code"] for it in r_cal["items"]]
check("热量焦虑党拼出两样", len(codes) == 2, [it["name"] for it in r_cal["items"]])
check("不出现重复餐品", len(codes) == len(set(codes)))
check(
    "不出现两份饮品",
    sum(1 for it in r_cal["items"] if it["name"] in ("纯悦", "可乐", "鲜萃咖啡")) <= 1,
    [it["name"] for it in r_cal["items"]],
)

team = persona_by_id(personas, "team_lead")
r_team = pick_meal(menu, team, seed=1)
check("团建负责人带份数 3", any(it["quantity"] == 3 for it in r_team["items"]), r_team["items"])
check(
    "份数计入总价",
    r_team["menu_price"] == round(sum(it["price"] * it["quantity"] for it in r_team["items"]), 2),
)

# ---------------------------------------------------------------- 7 点名餐品
section("点名餐品")
must = find_named_items(menu, "我想吃麦满分和薯饼", dog)
check("同一关键词只认一个 SKU", len(must) == 2, [p["name"] for p in must])
r_named = pick_meal(menu, dog, text="我想吃麦满分和薯饼", seed=1)
check("点名两样后不再加购", len(r_named["items"]) == 2, [it["name"] for it in r_named["items"]])
check("点名结果标记为 user_named", r_named["strategy"] == "user_named", r_named["strategy"])
check("点名餐品必须被保留", {"脆薯饼"} <= {it["name"] for it in r_named["items"]})

r_one = pick_meal(menu, dog, text="来杯可乐", seed=1)
check("只点一杯可乐时不会配第二杯饮料",
      sum(1 for it in r_one["items"] if it["name"] in ("可乐", "纯悦", "鲜萃咖啡")) == 1,
      [it["name"] for it in r_one["items"]])

# ---------------------------------------------------------------- 7.5 跨时段适配
section("跨时段适配（午餐菜单）")
lunch = load_menu(os.path.join(FIX, "lunch_menu_raw.json"))
check("午餐菜单解析出 47 个餐品", len(lunch) == 47, len(lunch))
lunch_names = {p["name"] for p in lunch}
check("午餐菜单有汉堡与薯条", "巨无霸" in lunch_names and "薯条" in lunch_names)

cal_lunch = pick_meal(lunch, cal, seed=3)
check(
    "热量焦虑党在午餐时段优先「500大卡套餐」",
    any(p["features"].get("lowcal") for p in lunch if p["name"] == cal_lunch["items"][0]["name"]),
    [it["name"] for it in cal_lunch["items"]],
)
check(
    "早餐时段低卡槽位缺失时回退到轻食槽位",
    len(r_cal["items"]) == 2 and any(it["name"] == "玉米杯" for it in r_cal["items"]),
    [it["name"] for it in r_cal["items"]],
)

happy = persona_by_id(personas, "happy_looper")
r_happy = pick_meal(lunch, happy, seed=3)
check(
    "快乐复读机拿到杯装甜品（不是最便宜的圆筒）",
    r_happy["items"][0]["name"] != "圆筒冰淇淋",
    r_happy["items"][0]["name"],
)

dog_lunch = pick_meal(lunch, dog, seed=3)
check(
    "加班狗在午餐时段拿到三件套",
    dog_lunch["strategy"] == "combo" and len(dog_lunch["items"]) == 1,
    dog_lunch["title"],
)

# ---------------------------------------------------------------- 8 组装 + 核价
section("卡片组装与核价")
mcdog = persona_by_id(personas, "overtime_dog")
# 核价夹具是「单个套餐」的响应，所以这里也构造单品的 selection，
# 否则拿单品实付去比多品菜单价，比的是两个不同的东西。
sel = {
    "strategy": "combo",
    "items": [
        {
            "code": "9900003458",
            "name": "猪柳蛋麦满分套餐",
            "price": 15.9,
            "original_price": 26.5,
            "role": "套餐",
            "quantity": 1,
        }
    ],
    "menu_price": 15.9,
    "menu_original": 26.5,
    "title": "猪柳蛋麦满分套餐",
    "reasons": ["猪柳蛋麦满分套餐：主食扎实(+0.9)、套餐形态(+0.5)"],
    "missing_slots": [],
}
check("单品菜单价 15.90", sel["menu_price"] == 15.9)
pick = {
    "mode": "roll",
    "persona": {"id": mcdog["id"], "name": mcdog["name"], "emoji": mcdog["emoji"]},
    "tagline": mcdog["taglines"][0],
    "selection": sel,
    "tips": mcdog["tips"],
}
calc_raw = json.load(open(os.path.join(FIX, "calc_price_raw.json"), encoding="utf-8"))

c_menu = make_card.build(pick, None, {"name": "测试餐厅"}, "早餐", "2026-10-21 09:40", 1)
check("无核价时价格为菜单价来源", c_menu["price"]["source"] == "menu")

c_calc = make_card.build(pick, calc_raw, {"name": "测试餐厅"}, "早餐", "2026-10-21 09:40", 1)
check("有核价时来源为 calc", c_calc["price"]["source"] == "calc")
check("实付取 calculate-price 的 price/100", c_calc["price"]["total"] == 26.5, c_calc["price"]["total"])
check("原价为 26.50", c_calc["price"]["original"] == 26.5, c_calc["price"]["original"])
check(
    "菜单价与实付不一致时给出解释",
    "15.90" in (c_calc["price"].get("note") or "") and "26.50" in (c_calc["price"].get("note") or ""),
    c_calc["price"].get("note"),
)

# ---------------------------------------------------------------- 9 渲染
section("卡片渲染")
txt = cardmod.render_text(c_calc)
check("文本卡含人设名", "加班狗" in txt)
check("文本卡标注已实时核验", "已实时核验" in txt)
check("文本卡含合计价", "¥26.50" in txt)
check("文本卡含门店", "测试餐厅" in txt)
check("文本卡含行动提示", "要下单吗" in txt)

html = cardmod.render_html(c_calc)
check("HTML 是完整文档", html.lstrip().startswith("<!DOCTYPE html>"))
check("HTML 含人设名", "加班狗" in html)
check("HTML 含核价徽标", "价格已实时核验" in html)
check("HTML 内联样式（单文件可分享）", "<style>" in html and "<link" not in html)

svg = cardmod.render_svg(c_calc)
try:
    root = ET.fromstring(svg)
    ok_svg = root.tag.endswith("svg") and root.get("width") == "720"
except ET.ParseError as e:  # pragma: no cover
    ok_svg, svg = False, str(e)
check("SVG 是合法 XML 且尺寸 720×1040", ok_svg, svg if not ok_svg else "")

txt_demo = cardmod.render_text({**c_menu, "price": {**c_menu["price"], "source": "demo"}})
check("demo 卡明确标注非实时", "示例数据 · 非实时" in txt_demo)
txt_unverified = cardmod.render_text(c_menu)
check("未核价卡标注未核价", "未核价" in txt_unverified)

# ---------------------------------------------------------------- 汇总
print(f"\n{'='*46}")
print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    for f in FAIL:
        print("  ✗ " + f)
    sys.exit(1)
print("全部通过 ✅")
