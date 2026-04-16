# LLM 交互设计

## 1. 文档目标

本文档定义导购系统中与 LLM 相关的任务划分、输入输出格式、模型分层、提示词结构和越权边界。

它要解决的问题是：

- 哪些节点真的需要模型参与
- 每类模型任务该吃什么输入
- 每类模型任务必须输出什么结构
- 什么时候用快模型，什么时候用质量模型
- 如何保证模型不编造价格、卖家、评论等事实

## 2. 与现有文档的关系

- [docs/project-architecture.md](docs/project-architecture.md)：定义 `integrations.llm` 作为统一模型调用入口
- [docs/shopping-agent-architecture.md](docs/shopping-agent-architecture.md)：定义 `IntentParse`、`CandidateScore`、`AnswerGenerate` 等节点职责
- [docs/langgraph-topology.md](docs/langgraph-topology.md)：定义节点拓扑和降级路径
- [docs/dataforseo-field-mapping.md](docs/dataforseo-field-mapping.md)：定义内部领域模型和字段来源
- [docs/streaming-event-contract.md](docs/streaming-event-contract.md)：定义最终流式事件与前端结构

本文件不定义 DataForSEO 字段，也不定义流式事件格式，只定义模型如何参与这些流程。

## 3. 总体原则

## 3.1 模型负责判断与解释，不负责事实采集

模型可以负责：

- 理解用户意图
- 把需求组织成更好的搜索计划
- 基于候选商品做匹配度判断
- 生成推荐理由和导语

模型不负责：

- 凭空生成商品事实
- 编造价格、卖家、评论数量、规格参数
- 在没有外部字段支撑时补齐缺失数据

## 3.2 优先结构化输出

除最终用户可见文案外，所有模型任务优先输出结构化 JSON，而不是自由文本。

## 3.3 尽量让模型只看“必要上下文”

不要把全量商品详情、全量评论正文都塞给模型。

优先只提供：

- 当前轮用户输入
- 会话摘要
- 结构化需求对象
- 候选商品的轻量字段
- 已补齐的关键信息摘要

## 3.4 模型调用必须可降级

若模型失败：

- 意图识别可以退到规则兜底
- 候选评分可以退到启发式排序
- 推荐理由可以退到模板化理由

## 4. 模型分层建议

## 4.1 默认策略

建议采用：

- `Gemini-first`

但不把“某个单一模型”写死在业务逻辑中，而是按任务类型抽象成两层能力：

- 快模型
- 质量模型

这里的 `Gemini-first` 代表默认优先使用 Gemini 作为推荐配置，而不是要求业务代码直接耦合 Gemini SDK。

模型选择应通过统一配置层完成，例如在 `config.yaml` 中为每个角色声明：

- `llm.fast.provider` / `llm.fast.model`
- `llm.quality.provider` / `llm.quality.model`
- `llm.suggestion.provider` / `llm.suggestion.model`

首批推荐兼容的 provider 至少包括：

- `gemini`
- `openai`
- `qwen`

并为后续的：

- `kimi`
- `glm`

预留扩展位。

## 4.2 快模型使用边界

适合：

- `IntentParse`
- `QueryBuild` 辅助
- `CandidateScore`
- 轻量摘要与字段压缩

特点：

- 响应快
- 成本低
- 以结构化输出为主

## 4.3 质量模型使用边界

适合：

- 最终导语生成
- 推荐理由润色
- 多商品对比表述
- 需要较好语言质量的总结

特点：

- 更强调表达质量和稳定性
- 输入应基于已经筛过的少量结构化事实

## 4.4 不建议的做法

不要：

- 用质量模型做所有步骤
- 在大批量候选评分时直接喂完整详情
- 让推荐理由生成模型重新决定 Top 3
- 在业务节点中直接写死某个 provider 的 SDK 或专有参数
- 假设所有 provider 的响应都使用同一个字段，例如统一写死 `response.text`

## 4.5 Provider 适配边界

为避免模型源切换时波及业务层，建议明确以下边界：

- 业务节点只调用统一的 `LlmGateway`
- `LlmGateway` 只区分 `fast`、`quality`、`suggestion` 这类角色
- provider adapter 负责处理 Gemini、OpenAI、Qwen 等模型源的初始化差异
- Gemini 专有参数（例如 `vertexai`）只能留在 Gemini adapter 内部
- 响应归一化也由 adapter 负责，不让业务层直接依赖 `response.text`、`response.content` 等具体字段

## 5. 任务划分

建议把模型任务收敛为 5 类。

| 任务 ID | 主要节点 | 是否必须 LLM | 输出类型 |
| --- | --- | --- | --- |
| `intent_parse` | `IntentParse` | 是 | 结构化 JSON |
| `query_build_assist` | `QueryBuild` | 是 | 结构化 JSON |
| `candidate_score` | `CandidateScore` | 是 | 结构化 JSON |
| `reason_generate` | `AnswerGenerate` / `StreamEnrich` | 是 | 结构化 JSON + 短文案 |
| `answer_summarize` | `AnswerGenerate` | 是 | 用户可见文案 |

## 6. 任务一：`intent_parse`

## 6.1 目标

把当前轮输入识别为：

- 模糊探索
- 条件细化
- 指向商品追问
- 比较请求
- 澄清请求

并抽出结构化约束。

## 6.2 输入来源

- 当前轮用户输入
- 会话摘要
- 上轮推荐结果摘要
- 已提及商品列表

## 6.3 不应输入给模型的内容

- 全量原始评论正文
- 全量 seller 列表
- 历史所有消息未压缩原文

## 6.4 输出结构建议

```json
{
  "intent_type": "discovery",
  "user_goal": "寻找适合学生党的无线耳机",
  "hard_constraints": {
    "budget_max": 500,
    "must_have": []
  },
  "soft_preferences": {
    "preferred_brands": [],
    "preferred_traits": ["性价比", "续航"]
  },
  "needs_external_search": true,
  "needs_followup_resolution": false,
  "followup_target_hint": null,
  "clarification_needed": false,
  "clarification_question": null
}
```

## 6.5 成功标准

- 结构稳定
- 约束提取尽量完整
- 不把模型猜测写成硬条件

## 7. 任务二：`query_build_assist`

## 7.1 目标

辅助 `QueryBuild` 节点把用户需求转成适合 `Products` 端点的搜索计划。

这里强调：

- 模型只生成搜索意图和参数建议
- 最终请求参数仍由业务层组装

## 7.2 输入来源

- `intent_parse` 的结构化结果
- 会话累计需求对象
- follow-up 目标商品信息
- 可复用缓存命中结果摘要

## 7.3 输出结构建议

```json
{
  "query_mode": "refinement",
  "keyword": "student wireless earbuds long battery life",
  "must_filters": {
    "price_max": 500
  },
  "optional_filters": {
    "sort_by": "review_score"
  },
  "query_rationale": "用户强调学生党和续航，预算 500 以内"
}
```

## 7.4 注意事项

- 不要让模型直接输出 DataForSEO 原始请求 JSON
- 不要把模型建议的筛选项视为无条件正确
- 业务层仍需校验 `price_min/max`、`sort_by` 等是否合法

## 8. 任务三：`candidate_score`

## 8.1 目标

对候选商品做匹配度评估，并给 `Top3Select` 提供排序依据。

## 8.2 输入来源

- 当前结构化需求
- 候选商品轻量卡片
- 已有字段可用性

建议输入字段只保留：

- `product_ref`
- `title`
- `brand`
- `price_current`
- `currency`
- `seller_name`
- `domain`
- `product_rating_value`
- `reviews_count`
- `feature_bullets` 的简版
- `spec_highlights` 的关键字段

## 8.3 批量评分优先

建议：

- 一次给模型 10 到 30 个候选的轻量列表
- 让模型统一比较并输出每个候选的评分与理由标签

不建议：

- 每个候选单独调用一次模型

因为那样会：

- 成本高
- 排序参照不一致
- 难以做整体相对比较

## 8.4 输出结构建议

```json
{
  "scored_candidates": [
    {
      "product_ref": "dfs:gshopping:pid:1",
      "score": 0.91,
      "matched_constraints": ["budget", "battery_life"],
      "tradeoffs": ["brand_not_preferred"],
      "reject": false
    },
    {
      "product_ref": "dfs:gshopping:pid:2",
      "score": 0.34,
      "matched_constraints": [],
      "tradeoffs": ["price_too_high"],
      "reject": true
    }
  ],
  "ranking_confidence": "medium"
}
```

## 8.5 评分规则建议

模型评分时应明确区分：

- 满足硬条件
- 满足软偏好
- 信息不足
- 明显冲突

对于信息不足的候选，不应直接判死刑，而应允许后续补拉详情后再增强理由。

## 9. 任务四：`reason_generate`

## 9.1 目标

为已入选的商品生成推荐理由。

它可以分两阶段：

1. `Top 3` 刚选出后，先生成简短理由
2. `Product Info / Sellers / Reviews` 补齐后，再生成增强版理由

## 9.2 输入来源

- 当前用户需求摘要
- Top 3 商品结构化字段
- `candidate_score` 的结构化评分结果
- `Sellers` 的价格/平台差异
- `Reviews` 的关键词和评分摘要

## 9.3 输出结构建议

为避免和流式事件协议的字段命名发生漂移，本项目约定：

- 推荐理由长文本统一使用 `full_reason`
- 不再同时使用 `long_reason` 这一别名
- 因此 LLM 输出、应用层中间结果、`reason_patch` 事件 payload 都应沿用同一命名

```json
{
  "reasons": [
    {
      "product_ref": "dfs:gshopping:pid:1",
      "short_reason": "预算内、续航表现突出，适合学生日常通勤使用。",
      "full_reason": "这款产品在预算范围内，同时续航和整体口碑都比较稳定，适合通勤、上课和日常听歌场景。",
      "evidence": [
        {
          "field": "price_current",
          "value": 399
        },
        {
          "field": "review_summary.top_keywords",
          "value": ["Long battery life", "Easy to use"]
        }
      ],
      "risk_notes": ["品牌不是用户明确偏好的品牌"]
    }
  ]
}
```

## 9.4 证据约束

`reason_generate` 的每条理由，建议都能追溯到至少 1 到 3 条结构化证据。

如果缺少证据：

- 允许输出更保守的短理由
- 不允许编造具体卖点

## 10. 任务五：`answer_summarize`

## 10.1 目标

生成本轮导购回答的用户可见文案，包括：

- 开场导语
- Top 3 总体总结
- 缺失字段说明
- 可继续追问的引导

## 10.2 输入来源

- Top 3 列表
- 推荐理由摘要
- 对比表的关键差异点
- 当前轮 warnings

## 10.3 输出结构建议

```json
{
  "intro_text": "我先帮你筛出了 3 款更适合学生党的无线耳机，下面先看核心差异。",
  "comparison_summary": "这 3 款主要差在续航、价格和品牌偏好匹配度。",
  "followup_hint": "如果你更在意佩戴舒适度或通话效果，我可以继续缩小范围。"
}
```

这里的 `intro_text` 最终会被系统侧映射到 `intro_chunk` 或非流式文案区域。

## 11. 提示词结构建议

建议所有模型任务都采用统一骨架：

1. 系统提示
2. 任务说明
3. 输入上下文
4. 输出 schema
5. 约束与禁止事项

## 11.1 通用系统提示骨架

```text
你是一个导购系统中的结构化推理组件。
你的职责是基于给定事实做判断，不允许编造外部事实。
若信息不足，请明确输出 unknown / null / needs_clarification，而不是猜测。
输出必须严格符合给定 JSON schema。
```

## 11.2 `intent_parse` 提示骨架

```text
任务：识别用户本轮意图，并提取结构化约束。
输入：当前轮消息、会话摘要、已提及商品。
要求：
1. 不要把推测写成硬条件。
2. 若用户表达不清，clarification_needed=true。
3. 只返回 JSON。
```

## 11.3 `candidate_score` 提示骨架

```text
任务：比较候选商品与用户需求的匹配度。
输入：结构化需求对象、候选商品列表。
要求：
1. 优先看硬条件是否满足。
2. 软偏好只影响排序，不直接替代硬条件。
3. 不得引用输入中不存在的字段。
4. 只返回 JSON。
```

## 11.4 `reason_generate` 提示骨架

```text
任务：为已选商品生成推荐理由。
输入：用户需求、商品事实字段、评分标签。
要求：
1. 推荐理由必须能被 evidence 支撑。
2. 若证据不足，只输出保守理由。
3. 不得编造具体价格、卖家、规格或评论内容。
4. 只返回 JSON。
```

## 12. 输入裁剪规则

## 12.1 候选评分阶段

每个候选商品尽量控制在轻量对象，不要传：

- 全量图片数组
- 全量 seller 列表
- 全量 review items

## 12.2 理由生成阶段

只传 Top 3，且只传：

- 当前价格或价格区间
- 关键规格
- 评分与评论关键词
- 卖家差异摘要

## 12.3 会话摘要

建议对历史会话先压缩成：

- 用户目标
- 当前硬条件
- 当前软偏好
- 最近一次比较焦点

## 13. 模型越权防护

## 13.1 明确禁止事项

模型不得：

- 编造 `price_current`
- 编造 `seller_count`
- 编造 `rating_value`
- 编造 `top_keywords`
- 编造规格参数
- 在无证据时写“音质更好”“续航更强”这类确定性判断

## 13.2 允许的推理

模型可以：

- 根据已给字段判断“更匹配预算”
- 根据评论关键词判断“口碑更偏向续航”
- 根据价格区间和品牌偏好说明权衡点

## 13.3 建议的程序级校验

在 `integrations.llm` 或节点层增加以下校验：

1. JSON 反序列化失败即判为模型失败
2. 若输出中引用了不存在的 `product_ref`，直接拒收
3. 若 evidence 引用了输入中没有的字段，直接拒收
4. 若 score 超出 `0..1`，做 schema 校验失败处理

## 14. 降级策略

## 14.1 `intent_parse` 失败

退化为：

- 规则抽取预算
- 规则识别比较词和指代词
- 其余字段标为未知

## 14.2 `candidate_score` 失败

退化为启发式排序：

- 先过滤明显超预算
- 再按评分、评论数、价格接近度排序

## 14.3 `reason_generate` 失败

退化为模板化理由：

```text
这款商品进入推荐名单，主要因为它在预算、当前可见口碑和已拿到的规格信息上更匹配你的需求。
```

## 14.4 `answer_summarize` 失败

退化为固定模板导语，不影响卡片、表格和 patch 流程。

## 15. 建议的实现模块

建议在 `integrations.llm` 中至少拆出：

- `schemas.py`：定义每类任务的输出 schema
- `prompts.py`：定义提示词模板
- `gateway.py`：统一模型调用与重试
- `validators.py`：校验模型输出是否越权

对应节点使用方式建议为：

- `IntentParse` 调 `intent_parse`
- `QueryBuild` 调 `query_build_assist`
- `CandidateScore` 调 `candidate_score`
- `StreamTop3` / `AnswerGenerate` 调轻量 `reason_generate`
- `StreamEnrich` / `AnswerGenerate` 调增强版 `reason_generate`
- `AnswerGenerate` 调 `answer_summarize`

## 16. 总结

这份 LLM 交互设计的核心，不是把模型变成“万能决策者”，而是把它限制在几个高价值、可验证、可降级的任务上。

开始编码时，只要坚持以下四点，模型层就不会失控：

1. 除最终展示文案外，优先结构化 JSON 输出
2. 推荐理由必须能回溯到 DataForSEO 已获取字段
3. 快模型负责判断，质量模型负责表达
4. 任一任务失败，都有明确的规则或模板降级路径
