# MCP 集成说明

本文记录「社畜人设卡」实际调用了哪些麦当劳 MCP 工具、参数怎么传、以及开发过程中实测到的坑。

---

## 1. 工具清单

| MCP 工具 | 用在哪 | 必要性 | 说明 |
|---------|--------|--------|------|
| `now-time-info` | 前置 | **必需** | 取服务器时间判断时段。菜单按时段下发，时间错了整个推荐就错了 |
| `query-nearby-stores` | 前置 | **必需** | 取门店 `storeCode`。`searchType=1` 先查收藏，空则 `searchType=2` 按城市+地标搜 |
| `query-meals` | 前置 | **必需** | 取当场可售菜单。选餐打分的唯一数据来源 |
| `calculate-price` | 核价 | **必需** | 卡面标「已实时核验」的唯一依据；同时拿到下单要用的 `takeWayList` |
| `create-order` | 下单 | 可选 | 仅在用户明确说「下单」时调用 |
| `query-meal-detail` | — | 本期未用 | 套餐组成的细节展示，v1 用 `query-meals` 的标签够了 |
| `query-store-coupons` | — | 计划中 | 「省钱精算师」的"最优券组合"要它，v1 只做了提示 |
| `query-my-coupons` | — | 本期未用 | 用户卡包券，用于券推荐场景 |

---

## 2. 调用链

```
① now-time-info
   ↓  data.formatted = "2026-10-21 09:32:36"
   ↓  persona_engine.py period --clock "..."  →  {period: breakfast, name: 早餐}

② query-nearby-stores  { beType:1, searchType:1 }
   ↓  取第一条 → storeCode=1400483, storeName=麦当劳汕头东厦壹佰餐厅
   ↓  (空 / 跨城 → 追问城市+地标，改 searchType:2, city, keyword)

③ query-meals  { storeCode, orderType:1, beType:1 }
   ↓  原样存 /tmp/shachiku/menu.json

④ 选人设
   Roll   : persona_engine.py roll  --seed N --period breakfast
   点餐   : persona_engine.py match --text "<用户原话>" --period breakfast

⑤ 选餐
   persona_engine.py pick --menu menu.json --persona <id> --text "..." --period ... --seed N
   ↓  selection.items[].code / quantity

⑥ calculate-price  { storeCode, orderType:1, beType:1, items:[{productCode, quantity}] }
   ↓  原样存 /tmp/shachiku/calc.json        ← 单位是「分」

⑦ make_card.py  --pick --calc --store-name --period → card.json
⑧ card.py       --input card.json --format all → text / html / svg
```

---

## 3. 参数映射规则（麦当劳 MCP 的坑）

### 3.1 `beType` / `orderType` / `beCode` 三者联动

这是麦当劳 MCP 最容易传错的地方：

| 场景 | beType | orderType | beCode |
|------|--------|-----------|--------|
| 到店自取 | `1` | `1` | **不传**（传了会报错） |
| 得来速车道 | `5` | `1` | **必传**（来自 `query-nearby-stores`） |
| 麦乐送 | `2` | `2` | **必传**（来自 `delivery-query-stores`） |
| 企业团餐 | `6` | `2` | **必传**（来自 `delivery-query-stores`） |

本 Skill v1 **只做到店自取**（`beType=1, orderType=1, 不传 beCode`），因为人设卡是"下楼取餐"的场景，链路最短、坑最少。

### 3.2 `query-nearby-stores` 的两个实测现象

1. **`distance` 恒为 0**。收藏门店返回 5 条，`distance` 全是 `0`、经纬度也是 `0.0`，没法真正按"最近"排序。所以选门店只能取第一条 + 在卡面写明门店名让用户确认。
2. **收藏门店可能跨城市**。实测返回里同时有汕头 4 家、厦门 1 家。**不能默认第一条就在用户身边**——卡面必须写门店名，必要时先问用户。

门店还返回 `reservationTimeOptions`（可预约时段），本 Skill 未使用，但下单时如果要预约需要用 `reservationDate`（格式 `yyyy-MM-dd HH:mm`）。

### 3.3 `query-meals` 返回的是「当前时段菜单」

09:32 调用返回的分类是：人气热卖 / 超值早餐 / 6折起早餐卡专区 / 厚松饼堡系列 / 麦满分系列 / 麦咖啡™ / 炒双蛋堡系列 / 早安营养卷 / 小食甜品·其他 / 饮品。

**没有巨无霸、没有薯条、没有麦乐鸡。** 这是正常行为，不是接口缺数据。

这直接决定了人设推荐的设计：不能写死 SKU，只能按特征打分（详见 README「设计决策 1」）。

返回结构：

```json
{ "data": {
    "categories": [{ "name": "麦满分系列", "meals": [{ "code": "9900003458", "tags": ["三件套"] }] }],
    "meals": { "9900003458": { "name": "猪柳蛋麦满分套餐", "currentPrice": "15.9", "originalPrice": "26.5" } }
} }
```

解析要点（`persona_engine.load_menu` 已处理）：
- 菜品详情在 `data.meals`（以 code 为 key 的映射），分类只是索引
- 分类名带换行（`"小食甜品\n/其他"`），要清掉
- `currentPrice` 是**字符串**，要转浮点
- 标签（`三件套`/`二件套`/`冰淇淋`）在 `categories[].meals[].tags`，需要按 code 合并回来

### 3.4 `calculate-price` 返回单位是「分」

```json
{ "data": {
    "price": 2650, "originalPrice": 2650, "discount": 0,
    "productList": [{ "productCode": "9900003458", "quantity": 1, "subtotal": 2650 }],
    "takeWayList": [{ "code": "eat-in", "title": "堂食" }, { "code": "locker-in", "title": "外带" }]
} }
```

- `price` / `originalPrice` / `discount` / `productList[].subtotal` 全部是**分**，脚本统一 `/100`。
- `productList[].subtotal` 是**分项实付小计**。卡片用它覆盖展示价，保证"单项价 × 份数 = 合计"自洽。
- `takeWayList` 是下单必填的 `takeWayCode` 来源（`eat-in` 堂食 / `locker-in` 外带）。

### 3.5 ⚠️ 菜单价 ≠ 实付价（最重要的一条）

实测同一个商品：

| 来源 | 金额 | 说明 |
|------|------|------|
| `query-meals.currentPrice` | **¥15.90** | 「随单购早餐卡优惠」价，需额外买早餐卡才成立 |
| `calculate-price.price` | **¥26.50** | 不买卡的实际结算价 |

`query-meals` 里该商品的 `discountType` 字段是 `"随单购早餐卡优惠"`，`canWithOrder: true`——这就是线索。

所以本项目定了一条硬规则：**卡面上的「已实时核验」只能来自 `calculate-price`**。菜单价只能标「未核价」，且两者不一致时必须解释差额，不能让用户以为 15.90 能买到。

### 3.6 `create-order` 的额外参数

| 参数 | 说明 |
|------|------|
| `takeWayCode` | `orderType=1` 时必传，来自 `calculate-price` 的 `takeWayList[].code` |
| `items` | 和核价时完全一致（productCode + quantity） |
| `addressId` | 仅外送场景，本 Skill 不用 |
| `reservationDate` | 仅预约场景 |

---

## 4. 失败处理

| 失败点 | 表现 | 处置 |
|--------|------|------|
| `now-time-info` 失败 | 无返回 | 用本机时间兜底，并说明"时段可能不准" |
| 收藏门店为空 | `data: []` | 追问城市 + 地标，`searchType=2` 重查；不许猜 |
| 门店跨城市 | 返回多地门店 | 卡面写门店名；明显不在用户城市就问 |
| `query-meals` 空 | 菜单为空 | 该门店当前不可点，建议换门店 |
| `calculate-price` 失败 | 报错/超时 | **仍可出卡**，价格来源降级为 `menu`（标「未核价」），明确告知用户 |
| 人设需要的品类缺失 | `missing_slots` 非空 | `make_card` 自动写备注「当前时段菜单没有XX，已用现有餐品替代」，照实说 |
| 用户点名的餐品不在菜单 | 餐品没匹配上 | 明确说"这家店当前没有 XX"，给替代项，不许装 |

---

## 5. 为什么不让 LLM 直接调完所有工具

试过让模型自己决定"推荐哪个餐品"，三个问题：

1. **不稳定**：同一句话两次运行给出不同套餐，用户会觉得随机。
2. **算错价**：分 → 元、套餐价 vs 单品价、份数乘算，模型偶尔会错，而价格错是硬伤。
3. **不可解释**：说不出"为什么选它"，卡面的"为什么是它"就写不实。

所以现在的分工是：**MCP 调用和语言表达交给 Agent，人设匹配、打分、算价、渲染交给 Python**。Python 侧 71 项自测全绿，价格标注不会出错。

---

## 6. 复现验证

MCP 真实响应切片放在 `tests/fixtures/`：

- `mcp_menu_raw.json` — `query-meals` 结构切片（10 个餐品，含 `小食甜品\n/其他` 这种带换行的分类名）
- `calc_price_raw.json` — `calculate-price` 真实响应（¥26.50 那条）

```bash
python3 tests/selftest.py
# [MCP 菜单解析] 9 项全绿
# [卡片组装与核价] 4 项全绿
```

---

## 7. 接入配置

真实 Token 不入库，仓库里只有脱敏示例 [`mcp-config.example.json`](mcp-config.example.json)：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer ${MCD_MCP_TOKEN}" }
    }
  }
}
```

把 `${MCD_MCP_TOKEN}` 替换为你在麦当劳 MCP 控制台领到的 Token，配到连接器里即可。本仓库所有
脚本都不读取 Token，也不直接发网络请求——**MCP 调用全部由 Agent 侧完成**，脚本只吃 JSON。

