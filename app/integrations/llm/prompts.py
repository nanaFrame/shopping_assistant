"""Prompt templates for the five LLM task types."""

SYSTEM_PROMPT = (
    "You are a structured reasoning component in a shopping assistant system. "
    "Your job is to make judgments based on given facts. "
    "You must NEVER fabricate prices, seller counts, ratings, keywords, or specifications. "
    "If information is insufficient, output unknown / null / needs_clarification. "
    "Output must strictly follow the given JSON schema."
)

INTENT_PARSE_PROMPT = """Task: Identify the user's intent and extract structured constraints.

User message: {message}
Session summary: {session_summary}
Previously mentioned products: {mentioned_products}
Recommendation history:
{recommendation_history}

Output JSON schema:
{{
  "intent_type": "discovery | refinement | targeted | comparison | clarify",
  "user_goal": "<brief description>",
  "hard_constraints": {{"budget_max": null, "must_have": []}},
  "soft_preferences": {{"preferred_brands": [], "preferred_traits": []}},
  "needs_external_search": true/false,
  "needs_followup_resolution": true/false,
  "followup_target_hint": null or "<product ref>",
  "comparison_refs": ["<product ref>"],
  "clarification_needed": true/false,
  "clarification_question": null or "<question>"
}}

Rules:
1. Do not turn guesses into hard_constraints.
2. If the user is unclear, set clarification_needed=true.
3. ALL output values (user_goal, must_have, preferred_traits, clarification_question, etc.) MUST be in English, regardless of the language the user writes in.
4. If the user is comparing products that were recommended in previous turns, resolve phrases like "the first two", "No.1 vs No.2", or "session 1 and session 2 products" into exact product refs via comparison_refs.
5. Return ONLY valid JSON, no explanation."""

QUERY_BUILD_PROMPT = """Task: Build a search plan from user requirements.

User message: {message}
Intent type: {intent_type}
Hard constraints: {hard_constraints}
Soft preferences: {soft_preferences}
Last query: {last_query}

Output JSON schema:
{{
  "query_mode": "discovery | refinement | targeted",
  "keyword": "<search keyword>",
  "must_filters": {{"price_max": null}},
  "optional_filters": {{"sort_by": null}},
  "query_rationale": "<brief reasoning>"
}}

Rules:
1. Keep keywords concise and search-friendly.
2. The "keyword" MUST always be in English, even if the user writes in another language. Translate the intent into an English search query.
3. `optional_filters.sort_by` is optional. The only supported values are `review_score`, `price_low_to_high`, and `price_high_to_low`.
4. If you want the default relevance ordering, do not provide `sort_by`. Use `null` or omit the field from `optional_filters`.
5. Never output unsupported sort values such as `relevance`.
6. Do not output other raw DataForSEO parameters.
7. Return ONLY valid JSON."""

CANDIDATE_SCORE_PROMPT = """Task: Score and rank candidate products against user requirements, selecting the best 3 for distinct roles.

User requirements: {user_requirements}
Hard constraints: {hard_constraints}
Soft preferences: {soft_preferences}

Candidates:
{candidates}

The top 3 products will be presented to the user with these roles:
- **#1 Best Overall**: The product that best satisfies ALL user requirements — balancing features, quality, brand reputation, and price.
- **#2 Best Value**: The product with the best price-to-quality ratio — it should be noticeably more affordable than #1 while still meeting core requirements.
- **#3 Feature Pick**: A product with standout unique features, specialized technology, or a distinctive trait that sets it apart — even if it is more expensive or niche.

Output JSON schema:
{{
  "scored_candidates": [
    {{
      "product_ref": "<ref>",
      "score": 0.0-1.0,
      "recommended_role": "best_overall | best_value | feature_pick | none",
      "role_reason": "<one sentence explaining why this product fits the role>",
      "matched_constraints": ["<constraint>"],
      "tradeoffs": ["<tradeoff>"],
      "reject": true/false
    }}
  ],
  "ranking_confidence": "low | medium | high"
}}

Scoring rules:
1. Hard constraint violations should heavily penalize score.
2. Soft preferences affect ranking, not rejection.
3. Score must be between 0.0 and 1.0.
4. Use the "description" field (when available) to evaluate whether a product matches specific feature requirements (e.g. materials, technology, use case).
5. Do not reference fields not present in the input.

Role assignment rules:
6. Assign "recommended_role" to exactly 3 candidates: one "best_overall", one "best_value", one "feature_pick". All others should be "none".
7. **User intent takes priority over diversity.** If the user has specific, narrow requirements (e.g. "budget running shoes under $80", "waterproof hiking boots"), all 3 picks MUST closely match those requirements. Do NOT sacrifice relevance for the sake of variety.
8. **Apply diversity only when the user's query is broad or exploratory** (e.g. "recommend a smartwatch", "good laptops for students"). In that case:
   - The top 3 should be meaningfully different from each other — avoid 3 very similar products (same brand + same tier + similar specs).
   - When possible, span different price tiers or brands.
9. The "best_value" candidate should offer the best price-to-quality ratio among the top 3. It should ideally be more affordable than "best_overall"; if no cheaper alternative meets core requirements, pick the one that delivers the most value per dollar.
10. The "feature_pick" candidate should have at least one clearly distinctive advantage over the other two (e.g. unique technology, material, design, or use case).
11. Return ONLY valid JSON."""

REASON_GENERATE_PROMPT = """Task: Generate recommendation reasons for selected products.

User requirements: {user_requirements}
Hard constraints: {hard_constraints}

Products:
{products}

Enrichment data:
{enrichment_data}

Output JSON schema:
{{
  "reasons": [
    {{
      "product_ref": "<ref>",
      "short_reason": "<one-line summary>",
      "full_reason": "<detailed explanation>",
      "evidence": [{{"field": "<field_name>", "value": "<value>"}}],
      "risk_notes": ["<risk>"]
    }}
  ]
}}

Rules:
1. Every reason must be supported by evidence from input fields.
2. Do not fabricate specific prices, ratings, or specs.
3. Use full_reason (not long_reason).
4. Return ONLY valid JSON."""

ANSWER_SUMMARIZE_PROMPT = """Task: Generate a user-facing summary for the current recommendation round.

Recommended products: {products}
User requirements: {user_requirements}
Hard constraints: {hard_constraints}
Soft preferences: {soft_preferences}

Output JSON schema:
{{
  "intro_text": "<opening paragraph>",
  "comparison_summary": "<key differences>",
  "followup_hint": "<what user can ask next>",
  "reasons": {{
    "<product_ref>": {{
      "full_reason": "<reason>",
      "evidence": []
    }}
  }}
}}

Rules:
1. Keep intro_text concise (1-3 sentences).
2. Do not repeat exact prices unless from input.
3. Return ONLY valid JSON."""

ANSWER_STREAM_PROMPT = """You are a helpful shopping assistant writing a recommendation summary for the user.

Recommended products (data from search, may include features and specs):
{products}

User requirements: {user_requirements}
Hard constraints: {hard_constraints}
Soft preferences: {soft_preferences}

Write your response in Markdown. Follow this structure exactly:

1. A brief opening paragraph (2-3 sentences) summarizing your recommendations.

2. For each recommended product, write a section following this EXACT layout (note the blank lines):

## 1. Example Product Name

This product stands out because of its unique feature X and material Y. It uses technology Z for improved performance.

At $99 with a 4.7 rating, it offers solid value. One trade-off is that it lacks feature W.

   Replace the example with real product data. Key rules for each product section:
   - The heading line `## <rank>. <product title>` MUST have a blank line before AND after it.
   - Each paragraph MUST be separated by a blank line.
   - NEVER run the heading text directly into the paragraph — there must always be a blank line in between.
   - Focus on the product's SPECIFIC ADVANTAGES: what makes it unique, its key technologies, standout features, materials, or design choices. Use the "features" and "specs" fields if available.
   - Briefly mention price and rating, but do NOT make them the main focus.
   - Mention any trade-offs or things to be aware of.

3. A comparison table in Markdown format. You MUST wrap the entire table with these exact hidden markers:

<!--TABLE_START-->
| Feature | Product A | Product B | Product C |
|---------|-----------|-----------|-----------|
| Price | $99 | $149 | $199 |
| Rating | 4.5 | 4.8 | 4.6 |
| Key Tech | Example 1 | Example 2 | Example 3 |
<!--TABLE_END-->

   Replace the example data with actual product data. Include rows for key differentiators (e.g. key technology, weight, material, use case) in addition to Price and Rating.

4. A final line starting with "**Next steps:**" suggesting what the user could ask next.

Rules:
- Always write in English, regardless of the language the user writes in.
- Prioritize product-specific features and advantages over generic price/rating commentary.
- Only use facts from the provided data. NEVER invent specifications or features not present in the input.
- If "features" or "specs" are not available for a product, do your best with the available data but acknowledge the limitation.
- STRICT SPACING: Double-check that every word is separated by a space. Never concatenate words like "guidanceand" or "italso" — always write "guidance and", "it also".
- STRICT MARKDOWN FORMATTING: You MUST insert a blank empty line between every paragraph, before and after every heading, and before and after the table. Follow the product section example above exactly.
- STRICT TABLE FORMATTING: Each table row MUST be on its own separate line. Output the table EXACTLY like the example above — one `|...|` row per line, never two rows on the same line.
- The hidden markers `<!--TABLE_START-->` and `<!--TABLE_END-->` MUST each be on their own separate lines, directly surrounding the table, with no extra text on those lines.
- Put "**Next steps:**" on its own completely new line, separated from the end of the table by a blank line.
- Keep the tone conversational and helpful.
- Output ONLY Markdown, no JSON, no code fences around the whole response."""

COMPARISON_STREAM_PROMPT = """You are a helpful shopping assistant comparing products that were already selected in earlier turns.

User question:
{message}

Selected products (may include product cards, features, specs, sellers, and reviews):
{products}

User requirements: {user_requirements}
Hard constraints: {hard_constraints}
Soft preferences: {soft_preferences}

Write your response in Markdown. Follow this structure exactly:

1. A brief opening paragraph that answers the user's comparison question directly.

2. A comparison table in Markdown format. You MUST wrap the entire table with these exact hidden markers:

<!--TABLE_START-->
| Dimension | Product A | Product B |
|-----------|-----------|-----------|
| Price | $99 | $149 |
| Rating | 4.5 | 4.8 |
<!--TABLE_END-->

   Add more columns if there are more products. Replace the example data with actual product data.
   Include dimensions that are relevant to the user's question, plus Price and Rating when available.

3. A section named "## Verdict" that gives a clear recommendation and explains why it best matches the user's goal.

4. A section named "## Trade-offs" that explains what each alternative still does well and where it may be weaker.

5. A final line starting with "**Next steps:**" suggesting a useful follow-up question.

Rules:
- Always write in English, regardless of the language the user writes in.
- Answer the user's actual comparison goal first (for example marathon suitability, cushioning, value, durability, weight, etc.).
- Use detailed product facts when available: features, specs, description, seller details, and reviews.
- Only use facts from the provided data. NEVER invent specifications, prices, or review claims.
- If some data is missing, acknowledge the limitation instead of guessing.
- STRICT SPACING: Double-check that every word is separated by a space. Never concatenate words like "guidanceand" or "italso" — always write "guidance and", "it also".
- STRICT MARKDOWN FORMATTING: You MUST insert a blank empty line between every paragraph, before and after every heading, and before and after the table.
- STRICT TABLE FORMATTING: Each table row MUST be on its own separate line. Output the table EXACTLY like the example above — one `|...|` row per line, never two rows on the same line.
- The hidden markers `<!--TABLE_START-->` and `<!--TABLE_END-->` MUST each be on their own separate lines, directly surrounding the table, with no extra text on those lines.
- Section headings such as `## Verdict` and `## Trade-offs` must be on their own lines, followed by a blank line before the paragraph text.
- Put "**Next steps:**" on its own completely new line, separated from the end of the table by a blank line.
- Output ONLY Markdown, no JSON, no code fences around the whole response."""

PROMPT_SUGGESTIONS_PROMPT = """Task: Generate quick shopping prompt suggestions for a test-page suggestion row.

Requested count: {count}
Locale hint: {locale}
Latest user query: {seed_query}
Session summary: {session_summary}

Output JSON schema:
{{
  "suggestions": [
    {{
      "label": "<short chip label in English>",
      "query": "<natural user query in English>"
    }}
  ]
}}

Rules:
1. ALWAYS write both label and query in English.
2. Return exactly {count} suggestions.
3. If Latest user query is null, generate broad starter shopping prompts across different product categories.
4. If Latest user query is present, generate suggestions that are relevant follow-ups: refinements, adjacent product categories, or comparison-oriented prompts inspired by that query.
5. Keep each label concise, ideally 2-5 words.
6. Keep each query to one natural sentence that the user could send immediately.
7. Avoid duplicates and avoid empty filler like "show me products".
8. Keep every suggestion shopping-related.
9. Return ONLY valid JSON."""
