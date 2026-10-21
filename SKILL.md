---
name: shachiku-persona-card
description: 麦当劳「社畜人设卡」。Roll 一个人设，或按用户想吃的餐品/需求（省钱、低卡、深夜、甜品、多人拼单）匹配人设，调用麦当劳 MCP 取真实门店与菜单、用 calculate-price 实时核价，输出一张可截图分享的人设卡（文本卡 + HTML + SVG）。触发词：roll 一个人设、抽个人设、今日人设卡、社畜人设、想吃麦当劳但不知道吃啥、帮我配一份麦当劳。
dependency:
  python: []
  system: []
---

# 社畜人设卡

把人设梗和真实点餐接在一起：**先定人设，再在当场可售的菜单里挑餐品，最后核价出卡。**

| 模式 | 触发 | 做什么 |
|------|------|--------|
| **A · Roll** | 「roll 一个人设」「抽一个」「今日人设」「随便来个人设」 | 按时段加权随机抽人设 → 推荐对应餐品 |
| **B · 点餐** | 提到具体餐品或需求：「我想吃麦满分和薯条」「今天想省钱」「有没有低卡的」「三个人拼单」 | 关键词匹配人设 → 优先保留用户点名的餐品 → 补齐搭配 |

---

## 0. 准备

所有命令都在**本 SKILL.md 所在目录**执行。脚本纯标准库，不需要 pip 安装。

```bash
mkdir -p /tmp/shachiku
PY=python3     # 3.9+ 均可
```

---

## 1. 两条硬前置（A / B 都要先做）

### 1.1 取时间 → 判断时段

```
now-time-info  →  拿到服务器时间（用返回的 data.formatted）
```

```bash
$PY scripts/persona_engine.py period --clock "2026-10-21 09:32:36"
# {"period": "breakfast", "name": "早餐", "clock": "09:32"}
```

**必须用 MCP 返回的时间，不要用本机时钟**——本机时区/时钟可能和服务器不一致，时段判错会直接推不出餐品。

时段划分：早餐 05:00–10:30 / 午餐 10:30–14:00 / 下午茶 14:00–17:00 / 夜市 17:00–22:00 / 宵夜 22:00–05:00。

### 1.2 取门店 + 菜单

```
query-nearby-stores  beType=1, searchType=1        # 先看收藏门店
```

- 有结果 → 取第一个，记下 `storeName` / `storeCode`
- 返回空或不是用户所在城市 → 问用户「在哪个城市 / 附近什么地标」，再用 `searchType=2, city=..., keyword=...` 重查
- 多个门店 → 默认取第一个，**在卡面上写明门店名**，让用户自己确认

```
query-meals  storeCode=<storeCode>, orderType=1, beType=1
```

把返回的 JSON **原样**存到 `/tmp/shachiku/menu.json`（用写文件工具，不要手动裁剪、不要改字段名）。

> ⚠️ **菜单按时段下发。** 09:32 查到的菜单只有早餐类（麦满分、油条、咖啡），没有巨无霸和薯条——这不是接口出错，是正常的。所以人设推荐必须落在「当场可售」的餐品上，不能照抄固定 SKU。

---

## 2. 模式 A · Roll

```bash
$PY scripts/persona_engine.py roll --seed <随机整数> --period <period>
```

返回：

```json
{
  "mode": "roll",
  "persona": {"id": "overtime_dog", "name": "加班狗", "emoji": "🌙", ...},
  "tagline": "今天的你只想快点填饱肚子",
  "seed": 42
}
```

- `--seed` 传一个随机整数（比如当前时间戳后四位），**同一个 seed 后面选餐也要用**，否则人设和餐品会对不上。
- 时段契合的人设权重 ×2.5（早餐时段更容易抽到「早餐战士」，深夜更容易抽到「深夜程序员」）。

---

## 3. 模式 B · 点餐

```bash
$PY scripts/persona_engine.py match --text "<用户原话>" --period <period>
```

返回 `persona` + `matched_keywords` + `meta`。

- `meta.reason == "no_signal"` 且拿到的是 `random_office`：说明没识别出意图，**追问一句**（"今天是想吃甜的还是想省钱？"），别硬出卡。
- `matched_keywords` 可以写进卡面理由里，让用户知道你为什么这么判断。

---

## 4. 选餐

```bash
$PY scripts/persona_engine.py pick \
  --menu /tmp/shachiku/menu.json \
  --persona <persona.id> \
  --text "<用户原话，Roll 模式留空>" \
  --period <period> --seed <同一个 seed>
```

输出里最关键的是 `selection`：

| 字段 | 含义 |
|------|------|
| `items[]` | 选中餐品，含 `code`（= productCode）、`name`、`quantity`、`price` |
| `strategy` | `combo` 整套 / `compose` 单品拼配 / `single` 单品 / `random` 手气 / `user_named` 用户点名 |
| `menu_price` | 菜单价合计（**还没核价**） |
| `reasons` | 为什么选它，可直接写进卡面 |
| `missing_slots` | 当前菜单缺的品类，需在卡上说明 |

把整份 JSON 存到 `/tmp/shachiku/pick.json`。

> 选餐规则（已内置，不用你判断）：一餐最多 3 件；不出现两份主食/两份饮料；套餐不再配饮料；用户点名 2 样后不再加购；同一关键词只认一个 SKU（说"麦满分"不会买 4 个套餐）。

---

## 5. 核价（必做）

```
calculate-price  storeCode, orderType=1, beType=1,
                 items=[{"productCode": <items[].code>, "quantity": <items[].quantity>}, ...]
```

- 价格单位是**分**，脚本会自动转元，你不用自己算。
- 原样存到 `/tmp/shachiku/calc.json`。
- 核价失败（报错/超时）→ **不核价也能出卡**，但价格来源必须降级为「菜单价 · 未核价」，并在回复里说明一句。绝不允许把菜单价说成核验价。

> 实测：菜单显示 ¥15.90 的套餐，`calculate-price` 返回 ¥26.50。菜单价是「随单购早餐卡」价，需要额外买卡才成立。脚本会自动在卡上标注差额说明——这是这张卡最容易被投诉的地方，必须保留。

---

## 6. 组装 + 渲染

```bash
$PY scripts/make_card.py \
  --pick /tmp/shachiku/pick.json \
  --calc /tmp/shachiku/calc.json \
  --store-name "麦当劳汕头东厦壹佰餐厅" --store-code "1400483" \
  --period "早餐" --mode roll --seed 42 \
  --out /tmp/shachiku/card.json

$PY scripts/card.py --input /tmp/shachiku/card.json \
  --outdir /tmp/shachiku --format all
```

`card.py` 会把**文本卡打印到 stdout**（直接贴给用户），同时生成：

- `/tmp/shachiku/card.txt` — 文本卡
- `/tmp/shachiku/card.html` — 720×1040 竖版，浏览器打开即可截图
- `/tmp/shachiku/card.svg` — 矢量版，任意尺寸不糊

回复用户时：先给文本卡，再把 `card.html` / `card.svg` 通过文件展示工具给用户。

---

## 7. 下单（可选，用户明确要求才做）

只有用户说「下单」「就这个」「买了」才进入这一步。

1. 从 `calculate-price` 返回的 `takeWayList` 里选取餐方式（`eat-in` 堂食 / `locker-in` 外带），默认堂食。
2. 调 `create-order`：`storeCode`、`orderType=1`、`beType=1`、`takeWayCode`、`items`（同核价时的 items）。
3. 把返回的支付链接给用户，提示「支付完成后回复我」。

**不得自动下单，不得替用户换门店，不得替用户加量。**

---

## 8. 没有 MCP / 没有 Token 时

```bash
$PY scripts/demo_run.py                    # Roll 一个
$PY scripts/demo_run.py --persona cheat_day
$PY scripts/demo_run.py --mode order --text "今天想省钱"
$PY scripts/demo_run.py --all              # 12 个人设各出一张，验收用
$PY scripts/gallery.py                     # 一页看完 12 张卡（推荐先看这个）
$PY scripts/gallery.py --menu tests/fixtures/lunch_menu_raw.json --period 午餐
```

走的是完全相同的链路，只是菜单来自 `data/demo_menu.json`（真实菜单快照）。卡面会标「示例数据 · 非实时」，回复时也要说明这是 demo 数据。

---

## 9. 输出模板（文本卡，固定格式）

```
🎴 今日人设卡  No.SC-20261021-0931
──────────────────────────────
今日人设：加班狗 🌙
「今天的你只想快点填饱肚子」

推荐：猪柳蛋麦满分套餐
价格：¥26.50（已实时核验）
　　　菜单显示 ¥15.90 属随单购/会员专享价，实付 ¥26.50，以核价为准
门店：麦当劳汕头东厦壹佰餐厅
时段：早餐 · 2026-10-21 09:41

为什么是它：
  · 猪柳蛋麦满分套餐：主食扎实(+0.9)、套餐形态(+0.5)、完整三件套(+0.4)

要下单吗？还是再 Roll 一次？
──────────────────────────────
```

多件时「推荐」改为分行列出，每行「· 名称 ×份数　¥价格」。

---

## 10. 硬性规则

1. **价格三种标注，不许含糊**：`已实时核验`（calculate-price 成功）/ `菜单价 · 未核价` / `示例数据 · 非实时`。
2. **菜单价可能是随单购价**，与实付不一致时必须解释差额，不许只显示便宜的那个。
3. **不许编造**门店、餐品、价格。MCP 没返回的东西就不存在。
4. **人设是玩梗，不是评价用户**。不要对真实收入、体重、加班时长下判断；文案只描述"今天的你"，不对人。
5. **一餐最多 3 件**，不主动加第 4 件。
6. **不代替用户下单**，不替用户选门店、不替用户加量。
7. 用户所在地不明、门店查不到时**先问**，不要猜城市。

---

## 11. 常见问题处置

| 现象 | 处置 |
|------|------|
| 收藏门店为空 | 问城市+地标，`searchType=2` 重查；不要默认用上次的门店 |
| 收藏门店在别的城市 | 同上，重新问 |
| 菜单只有早餐 | 正常。人设照推，但卡面注明「当前时段仅早餐菜单」 |
| 人设需要的品类没有 | `missing_slots` 非空时，`make_card` 会自动写备注，照实说 |
| 核价金额异常（比菜单贵很多） | 大概率是随单购/会员价差异，保留核价结果 + 差额说明 |
| 用户要的餐品不在菜单 | 明确说「这家店当前没有 XX」，再给替代项，不要装作有 |

---

## 文件结构

```
shachiku-persona-card/
├── SKILL.md                  # 本文件
├── README.md                 # 项目说明
├── MCP_INTEGRATION.md        # MCP 工具用法与实测坑位
├── CONTEST_DECLARATION.md    # 参赛声明（须替换为官方原件）
├── workbuddy.md              # 用 WorkBuddy 的开发记录
├── data/
│   ├── personas.json         # 12 个人设：关键词/权重/价格带/策略
│   └── demo_menu.json        # 离线 demo 菜单（真实快照）
├── scripts/
│   ├── persona_engine.py     # 人设匹配 + 选餐（纯逻辑，可单独跑）
│   ├── make_card.py          # 组装 card.json（含核价覆盖）
│   ├── card.py               # 渲染 text / html / svg
│   ├── demo_run.py           # 离线端到端
│   └── gallery.py            # 12 人设一页画廊
└── tests/
    ├── selftest.py           # 71 项自测，无网络
    └── fixtures/             # MCP 真实响应切片（早餐 / 午餐 / 核价）
```
