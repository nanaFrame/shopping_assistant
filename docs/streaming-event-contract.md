# 前后端流式事件 Contract

## 1. 文档目标

本文档定义导购 Agent 在流式输出场景下的前后端事件协议，用于约定：

- 后端按什么事件类型流式输出
- 每类事件的数据结构是什么
- 前端收到事件后应该更新哪个 UI 区块
- 增量更新、幂等、顺序和结束条件如何处理

该文档服务于结构化导购 UI，而不是普通聊天文本流。

## 2. 适用范围

本协议适用于以下场景：

- `Products` 返回后，先推送候选商品卡片
- 完成候选打分后，推送推荐 `Top 3`
- 后续逐步补充 `Product Info`
- 继续补充 `Sellers`
- 继续补充 `Reviews`
- 增量更新商品卡片、对比表格和推荐理由

本协议不绑定具体传输方式，既可以基于：

- `SSE`
- `WebSocket`
- `HTTP chunked response`

但无论采用哪种传输层，消息体结构应保持一致。

## 3. 设计原则

### 3.1 UI 优先，不是文本优先

流式事件的目标不是“连续吐字符串”，而是驱动前端的结构化渲染。

### 3.2 先展示，再补全

`Products` 阶段可先展示基础卡片，`info / sellers / reviews` 到达后再补字段。

### 3.2.1 即时发送

本协议默认采用“阶段结果一产生就立即发送”的策略。

也就是说：

- 后端不等待整轮推荐全部结束再统一发送
- 任一阶段只要形成可展示内容，就立即发送对应事件
- 后续字段再通过 patch 事件持续补齐

这条规则是本 contract 的核心前提。

### 3.3 事件可幂等

前端收到重复事件时，不应产生重复卡片或重复表格行。

### 3.4 增量更新优先

后端优先输出 patch，而不是频繁全量覆盖整个页面区域。

### 3.5 商品引用稳定

同一商品在整个流式过程中必须使用同一个 `product_ref`，供前后端稳定识别。

## 4. 通用事件包结构

所有流式事件都应遵循统一 envelope。

```json
{
  "version": "v1",
  "event_id": "evt_000012",
  "stream_id": "stream_20260414_001",
  "session_id": "sess_abc123",
  "turn_id": "turn_0003",
  "seq": 12,
  "type": "candidate_card",
  "phase": "candidate_ready",
  "entity": {
    "kind": "product",
    "id": "dfs:gshopping:pid:4485466949985702538"
  },
  "meta": {
    "source_stage": "products",
    "is_partial": true,
    "replace": false
  },
  "payload": {}
}
```

### 4.1 通用字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `version` | string | 协议版本，当前建议固定为 `v1` |
| `event_id` | string | 当前事件唯一 ID，用于幂等去重 |
| `stream_id` | string | 同一次流式推荐过程的唯一标识 |
| `session_id` | string | 用户会话 ID |
| `turn_id` | string | 当前轮对话 ID |
| `seq` | integer | 当前流内递增序号，前端可用来做顺序控制 |
| `type` | string | 事件类型 |
| `phase` | string | 当前流式阶段 |
| `entity.kind` | string | 当前事件作用对象类型，例如 `product`、`table`、`reason` |
| `entity.id` | string | 当前对象 ID，例如 `product_ref` 或表格 ID |
| `meta.source_stage` | string | 数据来源阶段，例如 `products`、`product_info`、`sellers`、`reviews` |
| `meta.is_partial` | boolean | 当前数据是否为部分字段 |
| `meta.replace` | boolean | 是否为整块替换；默认 `false` 表示增量合并 |
| `payload` | object | 当前事件的业务载荷 |

这里需要特别说明：

- `phase` 表示后端当前已经进入的**语义阶段**
- 它不是“这一类事件必须在视觉上最后出现”的意思
- 同一个 `phase` 下可以连续发送多种不同事件

例如：

- 当系统进入 `top3_ready`，说明 `Top 3` 已经在后端选定
- 但这个阶段下，后端可以先发 `intro_chunk`
- 然后再按顺序发 `top3_card`
- 之后也可以初始化 `comparison_table_init`

## 5. 阶段定义

`phase` 建议使用以下枚举值：

| phase | 含义 |
| --- | --- |
| `searching` | 正在检索候选商品 |
| `candidate_ready` | 候选商品已返回，可展示基础卡片 |
| `top3_ready` | `Top 3` 已在后端选定，允许开始发送导语、Top 3 卡片和初版对比表 |
| `enriching` | 正在补充 `info / sellers / reviews` |
| `completed` | 本轮推荐流已完成 |
| `failed` | 本轮推荐流异常结束 |

## 6. 领域对象定义

### 6.1 product_ref

`product_ref` 是前后端识别同一商品的稳定引用，建议至少具备：

本项目在 `MVP` 阶段约定：

- `product_ref` 的 canonical 定义以 [docs/dataforseo-field-mapping.md](docs/dataforseo-field-mapping.md) 为准
- 当前 DataForSEO Google Shopping 主路径示例统一使用 `dfs:gshopping:pid:{product_id}`
- 若未来需要回退到 `gid`、`data_docid` 或 fallback hash，也应继续遵循该文档中的同一命名体系，而不是重新引入其他前缀格式

```json
{
  "product_ref": "dfs:gshopping:pid:4485466949985702538",
  "provider": "dataforseo",
  "channel": "google_shopping",
  "product_id": "4485466949985702538"
}
```

### 6.2 product_card

商品卡片建议拆为“基础字段”和“补充字段”。

基础字段通常来自 `Products`：

- `title`
- `brand`
- `price_current`
- `currency`
- `platform`
- `image_url`
- `product_url`
- `domain`
- `seller_name`
- `reviews_count`
- `product_rating_value`

补充字段通常来自 `Product Info / Sellers / Reviews`：

- `price_range`
- `seller_count`
- `seller_summary`
- `spec_highlights`
- `review_summary`
- `feature_bullets`
- `images`
- `variations`

这里增加一条强约束：

- 商品类事件 payload 默认应沿用内部领域模型字段命名，例如 `price_current`
- 因此不再建议在 contract 中使用语义不清的 `price`、`tags` 这类命名
- 当前 `MVP` 不定义额外的 tag 类展示字段，先保证主流程围绕事实字段和推荐理由跑通

### 6.2.1 事件 payload 与领域模型映射

为避免事件协议和内部模型继续漂移，`candidate_card` / `top3_card` 中常见字段建议按下表映射：

| 事件 payload 字段 | 内部字段或来源 | 说明 |
| --- | --- | --- |
| `product_ref` | `product_card.product_ref` | 稳定商品主键 |
| `title` | `product_card.title` | 商品标题 |
| `brand` | `product_card.brand` | 品牌；允许为 `null` |
| `price_current` | `product_card.price_current` | 当前价格，保持 number 语义 |
| `currency` | `product_card.currency` | 币种 |
| `platform` | `product_card.platform` | 渠道名，例如 `Google Shopping` |
| `image_url` | `product_card.image_url` | 主图 |
| `product_url` | `product_card.product_url` | 商品链接 |
| `domain` | `product_card.domain` | 卖家站点域名 |
| `seller_name` | `product_card.seller_name` | 卖家名称 |
| `reviews_count` | `product_card.reviews_count` | 评论总量或轻量评论量 |
| `product_rating_value` | `product_card.product_rating_value` | 商品评分值 |
| `rank` | `presentation_card.rank` | 推荐区排序 |
| `badge` | `presentation_card.badge` | 推荐角标，属于展示层字段 |
| `summary` | `presentation_card.summary` | 简短推荐摘要，属于展示层字段 |

其中：

- `presentation_card.*` 不要求直接落到 `product_card` 原始领域模型中
- 它们由系统侧基于已有事实字段生成，用于前端展示
- 这些派生字段不得伪装成 DataForSEO 原始字段

### 6.3 comparison_table

对比表格建议统一抽象为：

这里增加一条强约束：

- `comparison_table.columns` 中的列 ID，canonical 形式应直接使用 `product_ref`
- `rows[].cells` 的键也应与 `columns` 保持同一组 `product_ref`
- 不建议在协议层再引入 `prod_a`、`prod_b`、`prod_c` 这类别名列 ID

原因：

- `product_ref` 已经是整套系统的稳定商品主键
- 前端可以直接用它定位卡片、推荐理由和表格列
- 这样不需要额外维护一张 `prod_a -> product_ref` 的映射表

如果前端需要展示更短的列头：

- 应通过列标题、商品标题、排序序号等展示字段解决
- 而不是改变列 ID 本身

```json
{
  "table_id": "comparison_main",
  "columns": [
    "dfs:gshopping:pid:4485466949985702538",
    "dfs:gshopping:pid:14548795243109479428",
    "dfs:gshopping:pid:16770195602838997301"
  ],
  "rows": [
    {
      "key": "price",
      "label": "价格",
      "cells": {
        "dfs:gshopping:pid:4485466949985702538": "5999",
        "dfs:gshopping:pid:14548795243109479428": "5499",
        "dfs:gshopping:pid:16770195602838997301": "6299"
      }
    }
  ]
}
```

## 7. 事件类型定义

### 7.1 `status`

用于更新当前流程状态，不直接渲染业务内容。

适用场景：

- 开始搜索
- 开始补全细节
- 正在比较商品

示例：

```json
{
  "version": "v1",
  "event_id": "evt_000001",
  "stream_id": "stream_001",
  "session_id": "sess_001",
  "turn_id": "turn_001",
  "seq": 1,
  "type": "status",
  "phase": "searching",
  "entity": {
    "kind": "stream",
    "id": "stream_001"
  },
  "meta": {
    "source_stage": "system",
    "is_partial": true,
    "replace": false
  },
  "payload": {
    "message": "正在搜索候选商品"
  }
}
```

前端规则：

- 更新顶部状态条或 loading 文案
- 不生成新的商品卡片

### 7.2 `intro_chunk`

用于流式输出导语内容。

适用场景：

- `Top 3` 确认后先输出一小段导语

语义说明：

- `intro_chunk` 的 `phase` 为 `top3_ready` 是合理的
- 这表示 `Top 3` 已经在后端确定
- 但推荐卡片和对比表还可以继续按顺序发送
- 因此“先导语、后 Top 3 卡片”与 `phase=top3_ready` 不冲突

示例：

```json
{
  "type": "intro_chunk",
  "phase": "top3_ready",
  "entity": {
    "kind": "intro",
    "id": "intro_main"
  },
  "payload": {
    "text": "结合你的预算和通勤需求，我先筛出了 3 个更匹配的候选。"
  }
}
```

前端规则：

- 追加到导语区域
- 不覆盖已经展示的商品卡片

### 7.3 `candidate_card`

用于推送候选商品基础卡片。

适用场景：

- `Products` 阶段拿到结果后立即发送

示例：

```json
{
  "type": "candidate_card",
  "phase": "candidate_ready",
  "entity": {
    "kind": "product",
    "id": "dfs:gshopping:pid:4485466949985702538"
  },
  "meta": {
    "source_stage": "products",
    "is_partial": true,
    "replace": false
  },
  "payload": {
    "product_ref": "dfs:gshopping:pid:4485466949985702538",
    "title": "ASUS Zenbook 14",
    "brand": "ASUS",
    "price_current": 5999,
    "currency": "CNY",
    "platform": "Google Shopping",
    "image_url": "https://example.com/p1.jpg"
  }
}
```

前端规则：

- 以 `product_ref` 为键做 upsert
- 插入到候选商品区
- 如果同一商品已存在，则只更新缺失字段

### 7.4 `top3_card`

用于推送进入推荐结果区的 `Top 3` 商品卡片。

示例：

```json
{
  "type": "top3_card",
  "phase": "top3_ready",
  "entity": {
    "kind": "product",
    "id": "dfs:gshopping:pid:4485466949985702538"
  },
  "payload": {
    "product_ref": "dfs:gshopping:pid:4485466949985702538",
    "rank": 1,
    "badge": "均衡推荐",
    "title": "ASUS Zenbook 14",
    "price_current": 5999,
    "currency": "CNY",
    "platform": "Google Shopping",
    "image_url": "https://example.com/p1.jpg",
    "summary": "轻薄、均衡，适合通勤与日常办公"
  }
}
```

前端规则：

- 将该商品加入或移动到 `Top 3` 区域
- 用 `rank` 控制排序
- 允许该商品同时保留在候选区和推荐区，或仅保留在推荐区，取决于产品设计

### 7.5 `product_patch`

用于对某个商品做字段级增量更新，是最核心的事件。

示例：

```json
{
  "type": "product_patch",
  "phase": "enriching",
  "entity": {
    "kind": "product",
    "id": "dfs:gshopping:pid:4485466949985702538"
  },
  "meta": {
    "source_stage": "sellers",
    "is_partial": true,
    "replace": false
  },
  "payload": {
    "product_ref": "dfs:gshopping:pid:4485466949985702538",
    "patch": {
      "price_range": "5799-6299",
      "seller_count": 4,
      "seller_summary": [
        "京东 5799",
        "天猫 5999"
      ]
    }
  }
}
```

前端规则：

- 以 `product_ref` 定位已有卡片
- 将 `patch` 做字段级 merge
- 若卡片尚未创建，可先暂存 patch，待卡片创建后再回放

发送原则：

- 某个字段一旦准备好就立即发 patch
- 不等待同一商品的其他字段全部准备完
- 不等待其他商品的补全结果

### 7.6 `comparison_table_init`

用于初始化对比表格。

适用场景：

- `Top 3` 刚确定后，先生成一个基础版对比表

示例：

```json
{
  "type": "comparison_table_init",
  "phase": "top3_ready",
  "entity": {
    "kind": "table",
    "id": "comparison_main"
  },
  "payload": {
    "table_id": "comparison_main",
    "columns": [
      "dfs:gshopping:pid:4485466949985702538",
      "dfs:gshopping:pid:14548795243109479428",
      "dfs:gshopping:pid:16770195602838997301"
    ],
    "rows": [
      {
        "key": "price",
        "label": "价格",
        "cells": {
          "dfs:gshopping:pid:4485466949985702538": "5999",
          "dfs:gshopping:pid:14548795243109479428": "5499",
          "dfs:gshopping:pid:16770195602838997301": "6299"
        }
      }
    ]
  }
}
```

前端规则：

- 初始化表格区域
- 若表格已存在且 `replace=true`，则整体替换
- `columns` 应直接作为列级商品主键使用，不再额外映射别名列 ID

### 7.7 `comparison_table_patch`

用于对比表格增量更新。

示例：

```json
{
  "type": "comparison_table_patch",
  "phase": "enriching",
  "entity": {
    "kind": "table",
    "id": "comparison_main"
  },
  "payload": {
    "table_id": "comparison_main",
    "rows_patch": [
      {
        "key": "seller_count",
        "label": "卖家数",
        "cells": {
          "dfs:gshopping:pid:4485466949985702538": "4",
          "dfs:gshopping:pid:14548795243109479428": "2",
          "dfs:gshopping:pid:16770195602838997301": "5"
        }
      }
    ]
  }
}
```

前端规则：

- 按 `row.key` 做 upsert
- 相同 `row.key` 存在时更新该行
- 不应整张表闪烁重建

### 7.8 `reason_patch`

用于更新某个商品的推荐理由。

示例：

```json
{
  "type": "reason_patch",
  "phase": "enriching",
  "entity": {
    "kind": "reason",
    "id": "reason:dfs:gshopping:pid:4485466949985702538"
  },
  "payload": {
    "product_ref": "dfs:gshopping:pid:4485466949985702538",
    "short_reason": "轻薄和通勤属性最匹配",
    "full_reason": "这款更适合你当前的通勤和轻薄需求，同时预算也在可接受范围内。"
  }
}
```

前端规则：

- 更新该商品的推荐理由区域
- 短理由可先展示，长理由可后到后补

### 7.9 `warning`

用于提示字段缺失、价格待确认、平台信息不完整等非致命问题。

示例：

```json
{
  "type": "warning",
  "phase": "enriching",
  "entity": {
    "kind": "product",
    "id": "dfs:gshopping:pid:4485466949985702538"
  },
  "payload": {
    "code": "PRICE_NOT_FINAL",
    "message": "当前价格为搜索结果快照，卖家价格仍在补充中。"
  }
}
```

### 7.10 `error`

用于标记本轮流式过程中出现的错误。

示例：

```json
{
  "type": "error",
  "phase": "failed",
  "entity": {
    "kind": "stream",
    "id": "stream_001"
  },
  "payload": {
    "code": "DETAIL_FETCH_FAILED",
    "message": "补充商品详情失败，请稍后重试。"
  }
}
```

前端规则：

- 展示错误提示
- 保留已成功渲染的候选内容，不要整页清空

### 7.11 `stream_done`

用于标记本轮流式推荐结束。

示例：

```json
{
  "type": "stream_done",
  "phase": "completed",
  "entity": {
    "kind": "stream",
    "id": "stream_001"
  },
  "payload": {
    "message": "本轮推荐已完成"
  }
}
```

前端规则：

- 关闭 loading 状态
- 将当前页面状态标记为“已完成”

## 8. 前端渲染规则

### 8.1 商品卡片区

- `candidate_card` 用于新增或更新候选区商品
- `top3_card` 用于新增或更新推荐区商品
- `product_patch` 只更新已有卡片字段，不重建整个列表

### 8.2 对比表格区

- `comparison_table_init` 初始化对比表
- `comparison_table_patch` 按行或字段做局部刷新
- 若字段暂缺，可显示 `待补充`

### 8.3 推荐理由区

- `reason_patch` 支持先短后长
- 后到的完整理由覆盖早到的简版理由

### 8.4 导语区

- `intro_chunk` 允许逐段追加
- 如果前端不需要打字机效果，也可以在缓冲后一次性展示

## 9. 合并、顺序与幂等规则

### 9.1 幂等

- 前端必须使用 `event_id` 去重
- 同一 `event_id` 不得重复应用

### 9.2 顺序

- 同一 `stream_id` 内，`seq` 应严格递增
- 前端应以 `seq` 作为主顺序依据

### 9.3 merge 规则

- `replace=false` 时按字段 merge
- `replace=true` 时整块替换目标对象
- 对同一字段发生冲突时，以较大的 `seq` 为准

### 9.4 patch 先于实体到达

若前端先收到 `product_patch`，后收到 `candidate_card`：

- 可先将 patch 暂存到 `pending_patch_buffer`
- 在卡片创建后立即回放

## 10. 推荐流式时序示例

下面是一条典型时序：

1. `status(searching)`
2. `candidate_card` x N
3. `status(candidate_ready)`
4. `intro_chunk`
5. `top3_card` x 3
6. `comparison_table_init`
7. `product_patch` for `product_info`
8. `comparison_table_patch`
9. `product_patch` for `sellers`
10. `reason_patch`
11. `product_patch` for `reviews`
12. `comparison_table_patch`
13. `stream_done`

这里的时序只表达常见顺序，不表示“必须等前一步全部完成后才能发下一步的所有内容”。

更准确地说：

- 候选卡片可以逐张发送
- Top 3 卡片可以逐张发送
- `product_patch` 可以按商品、按字段到达顺序发送
- 只要有可展示结果，就应立即向前端推送

同时也需要补充一条阶段解释：

- `status(candidate_ready)` 表示候选结果已经足以开始展示
- `intro_chunk(phase=top3_ready)` 表示后端已经完成 Top 3 选择，开始进入推荐展示阶段
- 随后的 `top3_card` 和 `comparison_table_init` 仍然属于同一个 `top3_ready` 阶段下的连续事件

## 11. 推荐的前端状态模型

前端建议维护以下状态容器：

| 状态键 | 说明 |
| --- | --- |
| `streamMeta` | 当前流状态、phase、loading、error |
| `candidateMap` | 候选商品卡片字典，键为 `product_ref` |
| `top3List` | 推荐区商品顺序列表 |
| `comparisonTable` | 当前对比表结构 |
| `reasonMap` | 每个商品的推荐理由 |
| `pendingPatchBuffer` | 提前到达但尚无宿主对象的 patch |

## 12. 版本策略

当前协议版本定义为 `v1`。

如果后续需要新增字段：

- 非破坏性新增字段：保持 `v1`
- 修改字段语义或事件含义：升级为 `v2`

## 13. 最小可落地建议

如果先做 MVP，建议最少实现这些事件：

- `status`
- `candidate_card`
- `top3_card`
- `comparison_table_init`
- `product_patch`
- `comparison_table_patch`
- `reason_patch`
- `stream_done`
- `error`

这里特别说明：

- `comparison_table_init` 不应从 MVP 最小集合中移除
- 因为前端需要先知道对比表的基础结构，例如表格 ID、列头对应的 3 个商品、初始行集合
- 只有在表格已经存在之后，`comparison_table_patch` 才适合承担增量更新职责

这样已经足够支撑：

- 候选卡片先展示
- Top 3 先展示
- 对比表格先初始化再动态刷新
- 细节逐步补全
- 推荐理由后补

## 14. 总结

这份 contract 的核心作用，是把“流式导购”从抽象想法变成可协作的接口约定。

它解决的是：

- 后端该发什么
- 前端该怎么接
- 哪些内容新增
- 哪些内容更新
- 哪些事件表示结束

有了这份协议，前后端就可以围绕同一套事件模型推进实现，而不是各自理解“流式输出”。
