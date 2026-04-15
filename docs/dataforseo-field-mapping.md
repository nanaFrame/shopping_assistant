# DataForSEO 字段映射规范

## 1. 文档目标

本文档定义 `DataForSEO Merchant Google Shopping` 相关端点与项目内部领域模型之间的字段映射规则。

它要解决的问题是：

- 外部端点到底返回哪些关键字段
- 这些字段如何映射到内部 `product_card`、`seller_summary`、`review_summary`
- 哪些字段是候选阶段即可得到的，哪些必须等补全阶段
- `product_ref` 应如何生成，才能在会话、缓存和流式事件中保持稳定

本文件是以下模块开始编码前的直接输入：

- `integrations.dataforseo`
- `storage.cache`
- `storage.session`
- `domain.models`
- `application.stream_service`

## 2. 与现有文档的关系

- [docs/project-architecture.md](docs/project-architecture.md)：定义系统级分层和模块边界
- [docs/shopping-agent-architecture.md](docs/shopping-agent-architecture.md)：定义 15 个运行时节点和推荐流程
- [docs/streaming-event-contract.md](docs/streaming-event-contract.md)：定义前后端流式事件协议

本文件不重新定义 Agent 流程，只定义外部数据如何进入内部模型。

## 3. 端点角色边界

项目当前使用 4 个 Google Shopping 端点：

| 端点 | 角色 | 何时使用 |
| --- | --- | --- |
| `Products` | 搜索候选商品和获取基础卡片 | 用户发起模糊探索、条件细化、重新搜索时 |
| `Product Info` | 获取商品详情、图片、规格、特性、变体 | Top 3 已选出，需要补齐商品细节时 |
| `Sellers` | 获取卖家列表、价格、运费和购买细节 | 需要比较价格、平台和卖家差异时 |
| `Reviews` | 获取评论摘要、评分分布、关键词和评论项 | 需要补充口碑依据和用户反馈时 |

关键边界：

- `Products` 负责候选发现，不负责完整详情
- `Product Info` 负责商品细节
- `Sellers` 负责价格和卖家对比
- `Reviews` 负责评论和口碑依据

## 4. 标识符策略

## 4.1 外部标识符

DataForSEO 相关端点涉及 3 个核心商品标识：

| 标识符 | 含义 | 常见来源 | 备注 |
| --- | --- | --- | --- |
| `product_id` | Google Shopping 动态商品 ID | `Products` 返回 | 最常用，适合 `Product Info` 和 `Sellers` |
| `data_docid` | SERP 数据元素 ID | `Products` 返回，`Product Info` 也可能回传 | 辅助标识，适合补强稳定性 |
| `gid` | Google Shopping 全局商品 ID | `Products` 返回，`Product Info` 也可能回传 | `Reviews` 端点依赖它 |

输入依赖关系：

- `Products`：按 `keyword + location + language` 搜索，不需要商品标识符
- `Product Info`：`product_id / data_docid / gid` 三选一即可，推荐尽量保留三者
- `Sellers`：`product_id / data_docid / gid` 三选一即可
- `Reviews`：必须有 `gid`

因此，`Products` 搜索阶段的一个关键任务，是尽可能把 `product_id`、`data_docid`、`gid` 收集齐。

## 4.2 内部标识模型

建议内部统一保存一个标识符包：

```json
{
  "product_ref": "dfs:gshopping:pid:3805205938126402128",
  "provider": "dataforseo",
  "channel": "google_shopping",
  "product_id": "3805205938126402128",
  "gid": "4702526954592161872",
  "data_docid": "9874368152810998595"
}
```

### 4.3 `product_ref` 生成规则

`product_ref` 是系统内部稳定引用，不直接展示给用户。

生成优先级建议如下：

1. 若有 `product_id`，使用：
   `dfs:gshopping:pid:{product_id}`
2. 否则若有 `gid`，使用：
   `dfs:gshopping:gid:{gid}`
3. 否则若有 `data_docid`，使用：
   `dfs:gshopping:doc:{data_docid}`
4. 若三者都没有，使用弱引用兜底：
   `dfs:gshopping:fallback:{hash(normalized_title|seller|url)}`

### 4.4 为什么优先 `product_id`

原因：

- `Products` 返回中通常就有 `product_id`
- `Product Info` 和 `Sellers` 都支持 `product_id`
- 对于缓存命中和流式事件定位都比较直观

但必须注意：

- `Reviews` 端点要求 `gid`
- 所以只保存 `product_id` 不够，必须保留 `gid`

### 4.5 标识符落盘原则

建议：

- 会话状态中保留 `product_ref`
- 商品缓存中保留完整 `identifier_bundle`
- 流式事件中只用 `product_ref`
- 当后续端点返回新的 `gid / data_docid` 时，应补写回缓存

## 5. 内部领域模型建议

## 5.1 `product_card`

建议把内部商品卡片拆成两层：

- 基础字段：搜索和首屏展示阶段需要
- 补充字段：细节补全后用于增强卡片、对比表格和推荐理由

### 基础字段

```json
{
  "product_ref": "dfs:gshopping:pid:3805205938126402128",
  "title": "Apple iPhone 12 - 128 GB - Black - Unlocked",
  "brand": null,
  "description_excerpt": "5G to download movies on the fly...",
  "image_url": "https://...",
  "product_url": "https://...",
  "platform": "Google Shopping",
  "domain": "backmarket.com",
  "seller_name": "Back Market",
  "price_current": 1099.99,
  "price_old": null,
  "currency": "USD",
  "rank_absolute": 2,
  "reviews_count": 9134,
  "product_rating_value": 4.6,
  "product_rating_max": 5,
  "source_stage": "products"
}
```

这里需要明确区分：

- `platform` 表示导购渠道或结果承载渠道，在当前 `MVP` 中固定为 `Google Shopping`
- `domain` 表示卖家网站域名，例如 `backmarket.com`
- `seller_name` 表示卖家名称，例如 `Back Market`

在后续多渠道扩展时：

- `platform` 可以扩展为 `Google Shopping`、`Amazon`、`JD` 等渠道名
- `domain` 仍然只表示具体卖家或落地站点域名

### 补充字段

```json
{
  "feature_bullets": [],
  "spec_highlights": {},
  "images": [],
  "variations": [],
  "price_range": null,
  "seller_count": null,
  "seller_summary": [],
  "review_keywords": [],
  "review_summary": null,
  "review_items": []
}
```

## 5.2 `price_snapshot`

```json
{
  "source": "products|sellers|product_info",
  "current": 1099.99,
  "old": null,
  "base_price": null,
  "shipping_price": null,
  "total_price": null,
  "currency": "USD",
  "displayed_price": "$1099.99",
  "is_price_range": false
}
```

## 5.3 `seller_summary`

```json
{
  "seller_name": "Back Market",
  "domain": "backmarket.com",
  "url": "https://...",
  "base_price": 129.0,
  "shipping_price": 1.99,
  "total_price": 144.21,
  "currency": "USD",
  "rating_value": 4.7,
  "rating_max": 5,
  "details": null,
  "annotation": null
}
```

## 5.4 `review_summary`

```json
{
  "total_reviews": 20051,
  "average_rating": 4.6,
  "rating_max": 5,
  "rating_groups": [],
  "top_keywords": [],
  "sample_reviews": []
}
```

## 6. 端点输入映射

## 6.1 `Products`

主要输入：

| 外部字段 | 内部用途 |
| --- | --- |
| `keyword` | 搜索关键词 |
| `location_code` / `location_name` | 搜索地区 |
| `language_code` / `language_name` | 搜索语言 |
| `depth` | 搜索结果数量 |
| `price_min` / `price_max` | 价格筛选 |
| `sort_by` | 排序规则 |
| `search_param` | 高级筛选参数 |

内部建议封装为：

```json
{
  "query_text": "iphone",
  "locale": {
    "location_code": 2840,
    "language_code": "en"
  },
  "filters": {
    "depth": 40,
    "price_min": 5,
    "price_max": 100,
    "sort_by": "price_low_to_high",
    "search_param": null
  }
}
```

## 6.2 `Product Info`

输入标识：

- `product_id`
- `data_docid`
- `gid`

内部规则：

- 默认优先用 `product_id`
- 若 `product_id` 缺失，再退到 `gid`
- 若仍缺失，再退到 `data_docid`

## 6.3 `Sellers`

输入标识：

- `product_id`
- `data_docid`
- `gid`
- 可选 `additional_specifications`

建议：

- 优先使用 `product_id`
- 如 `Products` 已返回 `additional_specifications`，应一并保存，供 `Sellers` 任务使用

## 6.4 `Reviews`

输入标识：

- `gid`

内部规则：

- 没有 `gid` 就不能安全发起 `Reviews`
- 若 `gid` 缺失，应在能力层标记：
  `reviews_supported = false`

## 7. 字段映射：`Products`

`Products` 是候选阶段的主数据源。

### 7.1 关键字段映射

| DataForSEO 字段 | 内部字段 | 用途 | 备注 |
| --- | --- | --- | --- |
| `title` | `product_card.title` | 候选卡片标题 | 基础字段 |
| `description` | `product_card.description_excerpt` | 首屏摘要 | 基础字段 |
| `url` | `product_card.product_url` | 点击跳转 | 基础字段 |
| 常量 `Google Shopping` 或 `channel=google_shopping` 映射 | `product_card.platform` | 渠道展示 | `MVP` 阶段固定值 |
| `domain` | `product_card.domain` | 卖家站点域名展示 | 基础字段 |
| `seller` | `product_card.seller_name` | 首屏商家名 | 基础字段 |
| `price` | `product_card.price_current` | 首屏价格 | 基础字段 |
| `old_price` | `product_card.price_old` | 价格对比 | 可空 |
| `currency` | `product_card.currency` | 价格币种 | 基础字段 |
| `product_images[0]` | `product_card.image_url` | 候选卡片图片 | 若存在 |
| `product_id` | `identifier_bundle.product_id` | 稳定标识 | 关键字段 |
| `data_docid` | `identifier_bundle.data_docid` | 稳定标识 | 关键字段 |
| `gid` | `identifier_bundle.gid` | Reviews 输入 | 关键字段 |
| `rank_absolute` | `product_card.rank_absolute` | 排名信息 | 基础字段 |
| `reviews_count` | `product_card.reviews_count` | 评论数 | 候选展示 |
| `product_rating.value` | `product_card.product_rating_value` | 平均评分 | 候选展示 |
| `product_rating.rating_max` | `product_card.product_rating_max` | 评分上限 | 候选展示 |
| `shop_ad_aclk` | `ad_ref.shop_ad_aclk` | 广告落地扩展 | 可选 |
| `delivery_message` | `shipping_summary.delivery_message` | 配送信息 | 可选 |
| `delivery_price.*` | `shipping_summary.*` | 配送价格 | 可选 |
| `additional_specifications` | `identifier_bundle.additional_specifications` | 后续 `Sellers` 任务可用 | 应缓存 |

### 7.2 通过 `Products` 可以立即得到的内容

适合在候选卡片阶段直接使用：

- 标题
- 摘要
- 图片
- 当前价格
- 商家名
- 平台/来源域名
- 评论数
- 产品评分
- 排名
- 标识符包

### 7.3 `Products` 不应负责的内容

不要指望 `Products` 提供完整：

- 完整规格
- 完整卖家列表
- 价格区间
- 评论关键词
- 评论正文
- 详细变体信息

这些应交给其他端点补齐。

## 8. 字段映射：`Product Info`

`Product Info` 是商品详情的主要数据源。

### 8.1 关键字段映射

| DataForSEO 字段 | 内部字段 | 用途 | 备注 |
| --- | --- | --- | --- |
| `title` | `product_card.title` | 标题补全/修正 | 如比 `Products` 更完整，可覆盖 |
| `description` | `product_card.description_full` | 详情描述 | 补充字段 |
| `url` | `product_card.product_url` | Google Shopping 商品页 | 可回填 |
| `images` | `product_card.images` | 图片列表 | 补充字段 |
| `images[0]` | `product_card.image_url` | 主图 | 如首屏图缺失，可覆盖 |
| `features[]` | `product_card.feature_bullets` | 核心卖点 | 推荐解释使用 |
| `rating.value` | `review_summary.average_rating` | 产品总体评分 | 可作补充来源 |
| `rating.rating_max` | `review_summary.rating_max` | 评分上限 | 可作补充来源 |
| `seller_reviews_count` | `seller_summary.primary_seller_reviews_count` | 卖家评价量 | 可选 |
| `data_docid` | `identifier_bundle.data_docid` | 标识补齐 | 可回写 |
| `gid` | `identifier_bundle.gid` | 标识补齐 | 关键 |
| `specifications[]` | `product_card.spec_highlights` | 规格字段 | 详情和对比表使用 |
| `sellers[]` | `seller_summary.preview_items` | 预览级卖家数据 | 非权威价格源 |
| `variations[]` | `product_card.variations` | 变体信息 | 补充字段 |

### 8.2 品牌字段规则

`brand` 在外部字段中未必直接给出。

建议按以下顺序推导：

1. 在 `specifications[]` 中查找 `Brand` / `Manufacturer`
2. 若无，再从 `title` 做保守提取
3. 仍无则保持 `null`

### 8.3 `Product Info` 的权威范围

以下字段建议以 `Product Info` 为主：

- 图片列表
- 完整描述
- 规格
- 特性
- 变体

但以下字段不应只依赖 `Product Info`：

- 卖家价格对比
- 最终价格区间
- 评论关键词和评论正文

## 9. 字段映射：`Sellers`

`Sellers` 是价格与平台对比的权威数据源。

### 9.1 关键字段映射

| DataForSEO 字段 | 内部字段 | 用途 | 备注 |
| --- | --- | --- | --- |
| `title` | `product_card.title` | 标题补齐 | 可回填 |
| `url` | `product_card.product_url` | Google Shopping 商品页 | 可回填 |
| `image_url` | `product_card.image_url` | 主图补齐 | 可回填 |
| `rating.value` | `product_card.product_rating_value` | 顶层产品评分 | 可补齐 |
| `items[].domain` | `seller_summary.domain` | 卖家站点域名 | 关键 |
| `items[].title` | `seller_summary.offer_title` | 卖家商品标题 | 可选 |
| `items[].url` | `seller_summary.url` | 卖家商品 URL | 关键 |
| `items[].details` | `seller_summary.details` | 卖家说明/活动 | 可选 |
| `items[].base_price` | `seller_summary.base_price` | 不含税运价格 | 关键 |
| `items[].shipping_price` | `seller_summary.shipping_price` | 运费 | 关键 |
| `items[].total_price` | `seller_summary.total_price` | 总价 | 关键 |
| `items[].currency` | `seller_summary.currency` | 币种 | 关键 |
| `items[].displayed_payment_breakdown` | `seller_summary.payment_breakdown` | 分期文案 | 可选 |
| `items[].seller_name` | `seller_summary.seller_name` | 卖家名 | 关键 |
| `items[].rating.value` | `seller_summary.rating_value` | 店铺评分 | 可选 |
| `items[].shop_ad_aclk` | `seller_summary.shop_ad_aclk` | 广告落地标识 | 可选 |
| `items[].product_annotation` | `seller_summary.annotation` | 价格标签/优惠标签 | 可选 |

### 9.2 `Sellers` 的权威范围

以下信息应以 `Sellers` 为权威：

- 卖家数量
- 卖家列表
- 卖家站点域名
- 总价、运费、价格区间
- 当前最低价与最高价

### 9.3 价格区间计算规则

建议：

- `price_range.min` = `items[].total_price` 的最小值
- `price_range.max` = `items[].total_price` 的最大值
- 若 `total_price` 缺失，则回退到 `base_price`

## 10. 字段映射：`Reviews`

`Reviews` 是评论和口碑的权威数据源。

### 10.1 关键字段映射

| DataForSEO 字段 | 内部字段 | 用途 | 备注 |
| --- | --- | --- | --- |
| `title` | `product_card.title` | 标题补齐 | 可回填 |
| `image_url` | `product_card.image_url` | 主图补齐 | 可回填 |
| `rating.value` | `review_summary.average_rating` | 平均评分 | 权威 |
| `rating.rating_max` | `review_summary.rating_max` | 评分上限 | 权威 |
| `rating_groups[]` | `review_summary.rating_groups` | 评分分布 | 权威 |
| `top_keywords[]` | `review_summary.top_keywords` | 评论关键词 | 权威 |
| `reviews_count` | `review_summary.total_reviews` | 评论总量 | 权威 |
| `items[]` | `review_summary.sample_reviews` | 评论样本 | 权威 |
| `items[].title` | `review_item.title` | 评论标题 | 可空 |
| `items[].review_text` | `review_item.text` | 评论正文 | 关键 |
| `items[].provided_by` | `review_item.provided_by` | 评论来源站点 | 关键 |
| `items[].author` | `review_item.author` | 评论作者 | 可选 |
| `items[].publication_date` | `review_item.publication_date` | 评论时间 | 可选 |
| `items[].rating.value` | `review_item.rating_value` | 单条评论评分 | 可选 |
| `items[].images[]` | `review_item.images` | 评论附图 | 可选 |

### 10.2 `Reviews` 的权威范围

以下内容建议只信任 `Reviews`：

- 评论关键词
- 评分分布
- 评论样本
- 评论总量
- 评论来源域名

## 11. 字段来源矩阵

下面是内部核心字段的推荐来源：

| 内部字段 | 首选来源 | 次选来源 | 备注 |
| --- | --- | --- | --- |
| `title` | `Products` | `Product Info` / `Sellers` / `Reviews` | 搜索阶段先用 `Products`，缺失时补齐 |
| `description_excerpt` | `Products` | `Product Info.description` | 首屏摘要优先轻量 |
| `description_full` | `Product Info` | 无 | 权威详情描述 |
| `image_url` | `Products.product_images[0]` | `Product Info.images[0]` / `Sellers.image_url` / `Reviews.image_url` | 搜索阶段优先快速展示 |
| `images[]` | `Product Info.images[]` | `Reviews.items[].images[]` | 主图和图集分开 |
| `brand` | `Product Info.specifications` | 标题推断 | 允许为空 |
| `platform` | 常量 `Google Shopping` 或内部 `channel -> display_name` 映射 | 无 | 当前 `MVP` 固定为单渠道值 |
| `domain` | `Products.domain` | `Sellers.items[].domain` | 表示卖家站点域名，不等于渠道名 |
| `price_current` | `Products.price` | `Sellers.items[].total_price` | 候选阶段先展示 |
| `price_range` | `Sellers.items[]` | 无 | 卖家比较权威 |
| `seller_name` | `Products.seller` | `Sellers.items[].seller_name` | 首屏先展示单商家 |
| `seller_summary[]` | `Sellers.items[]` | `Product Info.sellers[]` | `Sellers` 更权威 |
| `spec_highlights` | `Product Info.specifications[]` | 无 | 对比表关键 |
| `feature_bullets` | `Product Info.features[]` | 无 | 推荐理由关键 |
| `variations[]` | `Product Info.variations[]` | 无 | 变体信息 |
| `reviews_count` | `Reviews.reviews_count` | `Products.reviews_count` | 评论端点更权威 |
| `average_rating` | `Reviews.rating.value` | `Products.product_rating.value` / `Product Info.rating.value` | 评论端点更权威 |
| `top_keywords` | `Reviews.top_keywords[]` | 无 | 只来自评论 |
| `sample_reviews` | `Reviews.items[]` | 无 | 只来自评论 |

## 12. 字段优先级与覆盖规则

不同端点都可能返回同名或近似字段，必须定义覆盖规则。

### 12.1 标题

- 搜索阶段先用 `Products.title`
- 若 `Product Info.title` 更完整，可覆盖
- `Sellers.title` 和 `Reviews.title` 只作兜底

### 12.2 图片

- 搜索阶段先用 `Products.product_images[0]`
- 若 `Product Info.images[0]` 存在，则作为详情阶段主图
- `Sellers.image_url` 和 `Reviews.image_url` 仅用于补缺

### 12.3 价格

- 候选卡片阶段：`Products.price`
- 卖家比较阶段：`Sellers.items[].total_price` 权威
- 对于最终推荐说明中的“价格区间”，以 `Sellers` 为准

### 12.4 评论

- 轻量展示阶段可用 `Products.reviews_count`
- 最终口碑说明以 `Reviews` 为准

## 13. 缓存层落盘建议

## 13.1 建议缓存结构

```json
{
  "product_ref": "dfs:gshopping:pid:3805205938126402128",
  "identifiers": {
    "product_id": "3805205938126402128",
    "gid": "4702526954592161872",
    "data_docid": "9874368152810998595"
  },
  "base_card": {},
  "product_info_snapshot": {},
  "sellers_snapshot": {},
  "reviews_snapshot": {},
  "freshness": {
    "base_card_at": "2026-04-14T12:00:00Z",
    "product_info_at": null,
    "sellers_at": null,
    "reviews_at": null
  }
}
```

## 13.2 会话层与缓存层的分工

会话层应保存：

- `product_ref`
- 最近候选列表
- Top 3
- 用户偏好和 follow-up 目标

缓存层应保存：

- 完整标识符包
- 基础卡片
- 详情快照
- 卖家快照
- 评论快照

不要把：

- 评论正文大块文本
- 大量图片数组
- 全量 seller 列表

直接塞进会话状态。

## 13.3 建议的 freshness 策略

建议为不同数据段定义不同新鲜度：

| 数据段 | 建议 TTL |
| --- | --- |
| `base_card` | 24 小时 |
| `product_info_snapshot` | 7 天 |
| `sellers_snapshot` | 6 小时 |
| `reviews_snapshot` | 7 天 |

原因：

- 价格和卖家变化最快
- 评论和规格变化相对慢

## 14. 实施建议

开始编码时建议先做这三件事：

1. 在 `domain.models` 里把 `identifier_bundle`、`product_card`、`seller_summary`、`review_summary` 定义清楚
2. 在 `integrations.dataforseo` 里按本文件逐端点写 mapper，而不是直接把外部 JSON 扔给业务层
3. 在 `storage.cache` 里按“分段快照”而不是“单个大 JSON blob”落盘

## 15. 总结

这份映射文档的核心作用，是把外部 `DataForSEO` 数据转换成系统内部稳定、可缓存、可流式发送的领域模型。

最终要保证三件事：

- 同一个商品在不同端点返回的数据能通过 `product_ref` 收敛到同一对象
- 搜索阶段和补全阶段的数据可以自然叠加，而不是互相覆盖混乱
- 会话层、缓存层和流式事件层都使用同一套内部字段语义
