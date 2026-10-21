#!/usr/bin/env python3
"""生成宣传片所需的静态素材：主视觉人设卡（2x PNG）。

数据全部来自真实午餐菜单 + 真实 calculate-price 返回值，
不使用任何编造的菜品、价格或门店。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from persona_engine import load_menu, load_personas, pick_meal, persona_by_id  # noqa: E402
import card as cardmod  # noqa: E402
import make_card  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(ASSETS, exist_ok=True)

# 真实核价返回（2026-10-21 11:11:21，门店 1400483，到店自取）
CALC_RAW = {
    "success": True,
    "code": 200,
    "message": "请求成功",
    "datetime": "2026-10-21 11:11:21",
    "data": {
        "productOriginalPrice": 2690,
        "productPrice": 2690,
        "originalPrice": 2690,
        "discount": 0,
        "price": 2690,
        "productList": [
            {
                "productCode": "9900016073",
                "productName": "龙焰鸡腿堡三件套",
                "quantity": 1,
                "originalSubtotal": 2690,
                "subtotal": 2690,
            }
        ],
        "takeWayList": [
            {"code": "eat-in", "title": "堂食", "subtitle": "店内用餐"},
            {"code": "locker-in", "title": "外带", "subtitle": "店内取餐柜"},
        ],
    },
}

STORE = {"name": "麦当劳汕头东厦壹佰餐厅", "code": "1400483"}


def build_hero():
    menu = load_menu(os.path.join(ROOT, "tests/fixtures/lunch_menu_raw.json"))
    persona = persona_by_id(load_personas(), "overtime_dog")
    persona = {**persona, "taglines": ["工位到取餐台，是你今天唯一的运动"]}
    sel = pick_meal(menu, persona, text="今天加班，来点狠的", seed=6)
    pick = {
        "mode": "order",
        "persona": {"id": persona["id"], "name": persona["name"], "emoji": persona["emoji"]},
        "tagline": "工位到取餐台，是你今天唯一的运动",
        "selection": sel,
        "tips": ["别选需要剥壳、拆包装的东西，一只手要留给鼠标"],
    }
    c = make_card.build(pick, CALC_RAW, STORE, "午餐", "2026-10-21 11:11", 6)
    c["card_no"] = "SC-20261021-1111"
    return c


def build_grid_card(pid, seed=3):
    """用于片尾人设墙：只取人设本身，不出整卡。"""
    menu = load_menu(os.path.join(ROOT, "tests/fixtures/lunch_menu_raw.json"))
    p = persona_by_id(load_personas(), pid)
    r = pick_meal(menu, p, seed=seed)
    return {"id": p["id"], "name": p["name"], "emoji": p["emoji"], "pick": r["title"], "price": r["menu_price"]}


def main():
    c = build_hero()
    html = cardmod.render_html(c)
    path = os.path.join(ASSETS, "card_hero.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html.replace("width:720px", "width:720px").replace("height:1040px", "height:1040px"))
    with open(os.path.join(ASSETS, "card_hero.txt"), "w", encoding="utf-8") as f:
        f.write(cardmod.render_text(c))

    grid = [
        build_grid_card(pid)
        for pid in [
            "overtime_dog",
            "budget_warrior",
            "calorie_anxiety",
            "happy_looper",
            "indecisive",
            "slack_master",
            "midnight_coder",
            "thrift_actuary",
            "cheat_day",
            "breakfast_soldier",
            "team_lead",
            "random_office",
        ]
    ]
    with open(os.path.join(ASSETS, "grid.json"), "w", encoding="utf-8") as f:
        json.dump(grid, f, ensure_ascii=False, indent=2)
    print(cardmod.render_text(c))
    print("assets written ->", ASSETS)


if __name__ == "__main__":
    main()
