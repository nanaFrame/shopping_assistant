/* Shopping Assistant — Test Page Client (Phase 6: Complete) */

// ── State ────────────────────────────────────────────────────
let sessionId = null;
let eventSource = null;

const state = {
  streamMeta: null,
  candidateMap: {},
  top3List: [],
  comparisonTable: null,
  reasonMap: {},
  pendingPatchBuffer: {},
  seenEventIds: new Set(),
  lastSeq: 0,
  answerMarkdown: "",
  answerRenderTimer: null,
};

const $ = (id) => document.getElementById(id);

// ── Send message ─────────────────────────────────────────────
async function sendMessage() {
  const input = $("msgInput");
  const msg = input.value.trim();
  if (!msg) return;

  $("sendBtn").disabled = true;
  input.value = "";
  addChatBubble(msg);
  resetStreamUI();

  try {
    if (!sessionId) {
      const sessResp = await api("/api/sessions", {});
      sessionId = sessResp.session_id;
      $("sessionBadge").textContent = sessionId.slice(0, 16);
      $("sessionBadge").style.display = "";
    }

    const chatResp = await api("/api/chat", { session_id: sessionId, message: msg });
    showStatus("connecting", "Connecting to stream...");
    connectStream(chatResp.stream_url);
  } catch (e) {
    showStatus("error", "Error: " + e.message);
    $("sendBtn").disabled = false;
  }
}

async function api(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (!data.ok) throw new Error(data.error?.message || "Request failed");
  return data.data;
}

// ── SSE connection ───────────────────────────────────────────
function connectStream(url) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(url);

  eventSource.addEventListener("message", (e) => {
    try {
      handleEvent(JSON.parse(e.data));
    } catch (err) {
      logEvent("parse_error", 0, "", err.message);
    }
  });

  eventSource.addEventListener("heartbeat", () => {});

  eventSource.onerror = () => {
    if (eventSource) eventSource.close();
    $("sendBtn").disabled = false;
  };
}

// ── Event router ─────────────────────────────────────────────
function handleEvent(evt) {
  if (state.seenEventIds.has(evt.event_id)) return;
  state.seenEventIds.add(evt.event_id);
  if (evt.seq) state.lastSeq = Math.max(state.lastSeq, evt.seq);

  logEvent(evt.type, evt.seq, evt.phase, truncate(JSON.stringify(evt.payload), 100));

  const handlers = {
    status: handleStatus,
    candidate_card: handleCandidateCard,
    top3_card: handleTop3Card,
    text_chunk: handleTextChunk,
    intro_chunk: handleIntroChunk,
    product_patch: handleProductPatch,
    comparison_table_init: handleComparisonInit,
    comparison_table_patch: handleComparisonPatch,
    reason_patch: handleReasonPatch,
    warning: handleWarning,
    error: handleError,
    stream_done: handleDone,
  };

  const handler = handlers[evt.type];
  if (handler) handler(evt);
}

// ── Handlers ─────────────────────────────────────────────────
function handleStatus(evt) {
  showStatus("active", evt.payload.message || evt.phase);
}

function handleCandidateCard(evt) {
  const ref = evt.entity.id;
  state.candidateMap[ref] = mergeSafe(state.candidateMap[ref], evt.payload);
  applyPendingPatches(ref);
  renderCandidates();
}

function handleTop3Card(evt) {
  const ref = evt.entity.id;
  if (!state.top3List.includes(ref)) state.top3List.push(ref);
  state.candidateMap[ref] = mergeSafe(state.candidateMap[ref], evt.payload);
  applyPendingPatches(ref);
  renderTop3();
}

function handleTextChunk(evt) {
  const text = evt.payload.text || "";
  if (!text) return;
  state.answerMarkdown += text;
  $("answerSection").style.display = "";
  scheduleAnswerRender();
}

function handleIntroChunk(evt) {
  $("introSection").style.display = "";
  $("introText").textContent += evt.payload.text || "";
}

function handleProductPatch(evt) {
  const ref = evt.entity.id;
  if (state.candidateMap[ref]) {
    if (evt.meta?.replace) {
      state.candidateMap[ref] = { ...evt.payload, product_ref: ref };
    } else {
      mergeSafe(state.candidateMap[ref], evt.payload);
    }
    renderCandidates();
    renderTop3();
  } else {
    if (!state.pendingPatchBuffer[ref]) state.pendingPatchBuffer[ref] = [];
    state.pendingPatchBuffer[ref].push(evt);
  }
}

function handleComparisonInit(evt) {
  state.comparisonTable = evt.payload;
  renderComparison();
}

function handleComparisonPatch(evt) {
  if (!state.comparisonTable) return;
  for (const row of evt.payload.rows || []) {
    const existing = state.comparisonTable.rows.find((r) => r.key === row.key);
    if (existing) {
      Object.assign(existing.cells, row.cells);
    } else {
      state.comparisonTable.rows.push(row);
    }
  }
  renderComparison();
}

function handleReasonPatch(evt) {
  const ref = evt.entity.id;
  state.reasonMap[ref] = mergeSafe(state.reasonMap[ref], evt.payload);
  renderReasons();
}

function handleWarning(evt) {
  logEvent("warning", evt.seq, evt.phase, evt.payload.message);
}

function handleError(evt) {
  showStatus("error", "Error: " + (evt.payload.message || "unknown"));
  $("sendBtn").disabled = false;
  if (eventSource) eventSource.close();
}

function handleDone() {
  showStatus("done", "Completed");
  if (state.answerMarkdown) renderAnswer();
  if (eventSource) eventSource.close();
  $("sendBtn").disabled = false;
}

// ── Helpers ──────────────────────────────────────────────────
function mergeSafe(target, patch) {
  if (!target) return { ...patch };
  Object.assign(target, patch);
  return target;
}

function applyPendingPatches(ref) {
  const patches = state.pendingPatchBuffer[ref];
  if (!patches) return;
  for (const p of patches) mergeSafe(state.candidateMap[ref], p.payload);
  delete state.pendingPatchBuffer[ref];
}

function addChatBubble(text) {
  const el = document.createElement("div");
  el.className = "chat-bubble user";
  el.textContent = text;
  $("chatHistory").appendChild(el);
}

function resetStreamUI() {
  state.candidateMap = {};
  state.top3List = [];
  state.comparisonTable = null;
  state.reasonMap = {};
  state.pendingPatchBuffer = {};
  state.seenEventIds.clear();
  state.lastSeq = 0;
  state.answerMarkdown = "";
  state.answerRenderTimer = null;

  $("top3Grid").innerHTML = "";
  $("answerContent").innerHTML = "";
  $("eventLog").innerHTML = "";
  if ($("candidateGrid")) $("candidateGrid").innerHTML = "";
  if ($("comparisonContainer")) $("comparisonContainer").innerHTML = "";
  if ($("reasonContainer")) $("reasonContainer").innerHTML = "";
  if ($("introText")) $("introText").textContent = "";
  if ($("followupText")) $("followupText").textContent = "";

  for (const id of ["candidateSection", "top3Section", "comparisonSection", "reasonSection", "introSection", "followupSection", "answerSection"]) {
    $(id).style.display = "none";
  }
  showStatus("active", "Processing...");
}

function showStatus(type, msg) {
  const bar = $("statusBar");
  bar.textContent = msg;
  bar.className = "status-bar active" + (type === "done" ? " done" : "") + (type === "error" ? " error" : "");
}

function logEvent(type, seq, phase, detail) {
  const log = $("eventLog");
  const now = new Date().toLocaleTimeString();
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML =
    `<span class="log-time">${now}</span> ` +
    `<span class="log-seq">[${seq || "-"}]</span> ` +
    `<span class="log-type">${esc(type)}</span> ` +
    `<span class="log-phase">${esc(phase || "")}</span> ` +
    esc(detail || "");
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

function truncate(s, n) {
  return s && s.length > n ? s.slice(0, n) + "..." : s;
}

function scheduleAnswerRender() {
  if (state.answerRenderTimer) return;
  state.answerRenderTimer = requestAnimationFrame(() => {
    state.answerRenderTimer = null;
    renderAnswer();
  });
}

function renderAnswer() {
  const el = $("answerContent");
  if (!el) return;
  if (typeof marked !== "undefined" && marked.parse) {
    el.innerHTML = marked.parse(state.answerMarkdown);
  } else {
    el.textContent = state.answerMarkdown;
  }
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}

// ── Renderers ────────────────────────────────────────────────
function renderProductCard(card, isTop3) {
  const ref = card.product_ref || "";
  const imageUrl = card.image_url || "";
  const proxyImageUrl = imageUrl ? `/api/image?url=${encodeURIComponent(imageUrl)}` : "";
  const img = imageUrl
    ? `<img src="${esc(imageUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="if(!this.dataset.proxyLoaded){this.dataset.proxyLoaded='1';this.src='${esc(proxyImageUrl)}';}" />`
    : `<span class="no-img">No image</span>`;

  let badgeHtml = "";
  if (card.badge) {
    const cls = card.badge === "Best Overall" ? "best-overall"
      : card.badge === "Best Value" ? "best-value" : "feature-pick";
    badgeHtml = `<div class="card-badge-wrap"><span class="card-badge ${cls}">${esc(card.badge)}</span></div>`;
  }

  const rankHtml = card.rank ? `<div class="card-rank">${card.rank}</div>` : "";
  const price = card.price_current != null
    ? `${card.currency || "$"} ${card.price_current}` : "";

  const rating = card.product_rating_value != null
    ? `${"★".repeat(Math.round(card.product_rating_value))}${"☆".repeat(5 - Math.round(card.product_rating_value))} ${card.product_rating_value}${card.reviews_count ? ` (${card.reviews_count})` : ""}`
    : "";

  const buyHtml = `<button class="card-buy-btn" onclick="event.stopPropagation(); openSidebar('${esc(ref)}')">Buy →</button>`;

  return `
    <div class="product-card${isTop3 ? " top3" : ""}" data-ref="${esc(ref)}">
      ${rankHtml}
      <div class="card-img-wrap">${img}</div>
      ${badgeHtml}
      <div class="card-title">${esc(card.title || "Untitled")}</div>
      <div class="card-price">${esc(price)}</div>
      <div class="card-meta">${esc(card.seller_name || "")}${card.domain ? " · " + esc(card.domain) : ""}</div>
      ${rating ? `<div class="card-rating">${rating}</div>` : ""}
      ${buyHtml}
    </div>`;
}

function renderCandidates() {
  const refs = Object.keys(state.candidateMap).filter(
    (r) => !state.top3List.includes(r)
  );
  if (!refs.length) { $("candidateSection").style.display = "none"; return; }
  $("candidateSection").style.display = "";
  $("candidateGrid").innerHTML = refs
    .map((r) => renderProductCard(state.candidateMap[r], false))
    .join("");
}

function renderTop3() {
  if (!state.top3List.length) return;
  $("top3Section").style.display = "";
  $("top3Grid").innerHTML = state.top3List
    .map((r) => renderProductCard(state.candidateMap[r] || { title: r, product_ref: r }, true))
    .join("");
}

function renderComparison() {
  const t = state.comparisonTable;
  if (!t || !t.columns || !t.rows || !t.rows.length) return;
  $("comparisonSection").style.display = "";

  const cols = t.columns;
  const header = cols
    .map((c) => {
      const card = state.candidateMap[c];
      const name = card?.title ? truncate(card.title, 25) : c.split(":").pop();
      return `<th>${esc(name)}</th>`;
    })
    .join("");

  const rows = t.rows
    .map(
      (r) =>
        `<tr><td><strong>${esc(r.label || r.key)}</strong></td>${cols
          .map((c) => `<td>${esc(String(r.cells?.[c] ?? "-"))}</td>`)
          .join("")}</tr>`
    )
    .join("");

  $("comparisonContainer").innerHTML = `
    <div class="comparison-wrap">
      <table class="comparison-table">
        <thead><tr><th></th>${header}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function renderReasons() {
  const refs = Object.keys(state.reasonMap);
  if (!refs.length) return;
  $("reasonSection").style.display = "";
  $("reasonContainer").innerHTML = refs
    .map((r) => {
      const reason = state.reasonMap[r];
      const card = state.candidateMap[r];
      const badge = card?.badge || "";
      const evidenceHtml = (reason.evidence || [])
        .map((e) => `${esc(e.field)}: ${esc(String(e.value))}`)
        .join(" · ");
      const risksHtml = (reason.risk_notes || [])
        .map((n) => esc(n))
        .join(", ");

      return `
        <div class="reason-card">
          <div class="reason-header">
            <span class="reason-title">${esc(card?.title || r)}</span>
            ${badge ? `<span class="reason-badge">${esc(badge)}</span>` : ""}
          </div>
          <div class="reason-text">${esc(reason.full_reason || reason.short_reason || "")}</div>
          ${evidenceHtml ? `<div class="reason-evidence">${evidenceHtml}</div>` : ""}
          ${risksHtml ? `<div class="reason-risks">Considerations: ${risksHtml}</div>` : ""}
        </div>`;
    })
    .join("");
}

// ── Sidebar ──────────────────────────────────────────────────
function openSidebar(ref) {
  const card = state.candidateMap[ref];
  if (!card) return;

  $("sidebarTitle").textContent = card.title || "Product Details";
  renderSidebarSellers(card.seller_summary || [], card);
  renderSidebarReviews(card.review_summary || {});

  $("sidebarOverlay").classList.add("open");
  $("sidebarPanel").classList.add("open");
}

function closeSidebar() {
  $("sidebarOverlay").classList.remove("open");
  $("sidebarPanel").classList.remove("open");
}

function renderSidebarSellers(sellers, card) {
  const el = $("sidebarSellers");
  if (!sellers.length && !card.product_url) {
    el.innerHTML = `<div class="sidebar-section-title">Sellers</div>
      <div class="sidebar-empty">No seller data available yet</div>`;
    return;
  }

  let html = `<div class="sidebar-section-title">Sellers &amp; Prices</div>`;

  if (!sellers.length && card.product_url) {
    html += renderSellerRow({
      seller_name: card.seller_name || "Google Shopping",
      domain: card.domain || "",
      total_price: card.price_current,
      base_price: card.price_current,
      shipping_price: null,
      currency: card.currency || "USD",
      rating_value: null,
      url: card.product_url,
    });
  } else {
    for (const s of sellers) {
      html += renderSellerRow(s);
    }
  }

  el.innerHTML = html;
}

function renderSellerRow(s) {
  const cur = s.currency || "USD";
  const priceStr = s.total_price != null ? `${cur} ${s.total_price}` : (s.base_price != null ? `${cur} ${s.base_price}` : "N/A");
  const shippingStr = s.shipping_price != null ? (s.shipping_price > 0 ? `+${cur} ${s.shipping_price} shipping` : "Free shipping") : "";
  const ratingStr = s.rating_value != null ? `${"★".repeat(Math.round(s.rating_value))}${"☆".repeat(5 - Math.round(s.rating_value))} ${s.rating_value}` : "";
  const buyUrl = s.url || "#";

  return `
    <div class="seller-row">
      <div class="seller-info">
        <div class="seller-name">${esc(s.seller_name || "Unknown")}</div>
        <div class="seller-domain">${esc(s.domain || "")}</div>
        ${ratingStr ? `<div class="seller-rating">${ratingStr}</div>` : ""}
      </div>
      <div class="seller-price-col">
        <div class="seller-price">${esc(priceStr)}</div>
        ${shippingStr ? `<div class="seller-shipping">${esc(shippingStr)}</div>` : ""}
      </div>
      <a class="seller-buy" href="${esc(buyUrl)}" target="_blank" rel="noopener">Buy</a>
    </div>`;
}

function renderSidebarReviews(review) {
  const el = $("sidebarReviews");
  if (!review || !review.sample_reviews || !review.sample_reviews.length) {
    el.innerHTML = `<div class="sidebar-section-title">Reviews</div>
      <div class="sidebar-empty">No reviews available yet</div>`;
    return;
  }

  const avgRating = review.average_rating != null ? Number(review.average_rating).toFixed(1) : "—";
  const avgStars = review.average_rating != null
    ? `${"★".repeat(Math.round(review.average_rating))}${"☆".repeat(5 - Math.round(review.average_rating))}`
    : "";
  const totalStr = review.total_reviews != null ? `${review.total_reviews.toLocaleString()} reviews` : "";

  const keywords = (review.top_keywords || []).filter(k => k);

  let html = `<div class="sidebar-section-title">Reviews</div>`;

  html += `<div class="review-summary-bar">
    <div class="review-avg-rating">${avgRating}</div>
    <div>
      <div class="review-avg-stars">${avgStars}</div>
      <div class="review-total">${esc(totalStr)}</div>
    </div>
  </div>`;

  if (keywords.length) {
    html += `<div class="review-keywords">${keywords.map(k => `<span class="review-keyword">${esc(k)}</span>`).join("")}</div>`;
  }

  for (const r of review.sample_reviews) {
    const stars = r.rating_value != null
      ? `${"★".repeat(Math.round(r.rating_value))}${"☆".repeat(5 - Math.round(r.rating_value))}`
      : "";
    const dateStr = r.publication_date || "";

    html += `
      <div class="review-card">
        <div class="review-header">
          ${stars ? `<span class="review-stars">${stars}</span>` : ""}
          <span class="review-author">${esc(r.author || r.provided_by || "Anonymous")}</span>
          ${dateStr ? `<span class="review-date">${esc(dateStr)}</span>` : ""}
        </div>
        ${r.title ? `<div class="review-title">${esc(r.title)}</div>` : ""}
        ${r.text ? `<div class="review-text">${esc(r.text)}</div>` : ""}
      </div>`;
  }

  el.innerHTML = html;
}

// ── Init ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  $("msgInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
});
