/* =====================================================================
 * 工单坐席看板 —— 前端逻辑
 * 后端契约：capabilities/human-handoff/manifest.yaml.endpoints
 *   GET  /api/v1/handoff/admin/tickets[?status=&limit=]   工单列表
 *   GET  /api/v1/handoff/admin/tickets/{ticket_id}        工单详情
 *   POST /api/v1/handoff/admin/tickets/{ticket_id}/status 状态更新
 *   GET  /api/v1/handoff/status                           整体队列状态
 *   POST /api/v1/handoff/request                          手工提交一条测试工单
 * ===================================================================== */

(function () {
  "use strict";

  /* ---------- DOM ---------- */
  const tbody = document.getElementById("ticket-rows");
  const summary = document.getElementById("list-summary");
  const filterList = document.getElementById("filter-list");
  const drawer = document.getElementById("drawer");
  const drawerBody = document.getElementById("drawer-body");
  const btnCloseDrawer = document.getElementById("btn-close-drawer");
  const btnRefresh = document.getElementById("btn-refresh");
  const chkAuto = document.getElementById("chk-auto");
  const btnSeed = document.getElementById("btn-seed");
  const metricAgents = document.querySelector('[data-role="metric-agents"]');
  const metricWaiting = document.querySelector('[data-role="metric-waiting"]');
  const metricConnected = document.querySelector('[data-role="metric-connected"]');

  const state = {
    statusFilter: "",
    list: [],
    selectedId: null,
    autoTimer: null,
  };

  const STATUS_LABEL = {
    pending: "Pending",
    processing: "In progress",
    closed: "Closed",
    canceled: "Canceled",
    timeout: "Timeout",
  };

  const PRIORITY_LABEL = {
    low: "Low",
    normal: "Normal",
    high: "High",
    urgent: "Urgent",
  };

  /* ---------- 工具函数 ---------- */
  function fmtTs(ts) {
    if (!ts && ts !== 0) return "--";
    const ms = ts < 1e12 ? ts * 1000 : ts;          // 兼容 epoch (秒/毫秒)
    const d = new Date(ms);
    if (Number.isNaN(d.getTime())) return "--";
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c]));
  }

  function showToast(text, tone) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.setAttribute("data-tone", tone || "");
    el.classList.add("is-visible");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove("is-visible"), 2400);
  }

  /* ---------- 网络 ---------- */
  async function api(path, opts) {
    const init = Object.assign({ credentials: "same-origin" }, opts || {});
    if (init.body && typeof init.body !== "string") {
      init.body = JSON.stringify(init.body);
      init.headers = Object.assign({ "Content-Type": "application/json" }, init.headers || {});
    }
    const resp = await fetch(path, init);
    if (!resp.ok) {
      let detail = `${resp.status} ${resp.statusText}`;
      try {
        const j = await resp.json();
        if (j && j.detail) detail = j.detail;
      } catch (e) { /* swallow */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  async function fetchOverall() {
    try {
      const body = await api("/api/v1/handoff/status");
      const d = body.data || body;
      metricAgents.textContent = d.available_agents != null ? d.available_agents : (d.agent_pool_size ?? "--");
      metricWaiting.textContent = d.waiting ?? "--";
      metricConnected.textContent = d.connected ?? "--";
    } catch (err) {
      console.warn("overall status failed", err);
    }
  }

  async function fetchList() {
    const url = new URL("/api/v1/handoff/admin/tickets", location.origin);
    url.searchParams.set("limit", "100");
    if (state.statusFilter) url.searchParams.set("status", state.statusFilter);
    try {
      const body = await api(url.pathname + url.search);
      const data = body.data || body;
      state.list = (data.items || []).slice();
      renderList();
      summary.textContent = `${state.list.length} ticket(s) · ${state.statusFilter ? STATUS_LABEL[state.statusFilter] : "All"}`;
    } catch (err) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="7">Failed to load: ${escapeHtml(err.message || err)}</td></tr>`;
      summary.textContent = "Failed to load";
    }
  }

  /* ---------- 渲染 ---------- */
  function renderList() {
    if (!state.list.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="7">No tickets yet. Click "Insert test ticket" on the left to create one.</td></tr>';
      return;
    }
    const html = state.list.map((t) => renderRow(t)).join("");
    tbody.innerHTML = html;

    Array.from(tbody.querySelectorAll("tr[data-ticket-id]")).forEach((tr) => {
      tr.addEventListener("click", (ev) => {
        if (ev.target.closest(".row-actions")) return;
        openDrawer(tr.getAttribute("data-ticket-id"));
      });
    });
    Array.from(tbody.querySelectorAll("[data-action]")).forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = btn.getAttribute("data-ticket-id");
        const action = btn.getAttribute("data-action");
        await onActionClick(id, action);
      });
    });
  }

  function renderRow(t) {
    const subj = t.subject || t.reason || "(empty)";
    const sel = state.selectedId === t.ticket_id ? " is-selected" : "";
    const priority = t.priority || "normal";
    const status = t.status || "pending";

    let actions = "";
    if (status === "pending") {
      actions = `
        <button class="btn btn--accent btn--small" data-action="processing" data-ticket-id="${escapeHtml(t.ticket_id)}">Connect</button>
        <button class="btn btn--ghost btn--small btn--danger" data-action="canceled" data-ticket-id="${escapeHtml(t.ticket_id)}">Cancel</button>
      `;
    } else if (status === "processing") {
      actions = `
        <button class="btn btn--ghost btn--small" data-action="closed" data-ticket-id="${escapeHtml(t.ticket_id)}">Close ticket</button>
      `;
    } else {
      actions = '<span style="color: var(--color-text-tertiary); font-size: 12px;">Resolved</span>';
    }

    return `
      <tr data-ticket-id="${escapeHtml(t.ticket_id)}" class="${sel}">
        <td><span class="ticket-id">${escapeHtml(t.ticket_id)}</span></td>
        <td>${escapeHtml(t.user_id || "--")}</td>
        <td>${escapeHtml(subj)}</td>
        <td><span class="priority" data-level="${escapeHtml(priority)}">${escapeHtml(PRIORITY_LABEL[priority] || priority)}</span></td>
        <td><span class="status-pill" data-status="${escapeHtml(status)}">${escapeHtml(STATUS_LABEL[status] || status)}</span></td>
        <td>${escapeHtml(fmtTs(t.created_at))}</td>
        <td class="ticket-table__col-actions"><div class="row-actions">${actions}</div></td>
      </tr>
    `;
  }

  function renderDetail(t) {
    if (!t) {
      drawerBody.innerHTML = '<p class="drawer__placeholder">Ticket not found.</p>';
      return;
    }
    const tx = (t.transcript || []).map((line) => `· ${line}`).join("\n");
    let actions = "";
    if (t.status === "pending") {
      actions = `
        <button class="btn btn--accent btn--small" data-detail-action="processing" data-ticket-id="${escapeHtml(t.ticket_id)}">Connect ticket</button>
        <button class="btn btn--ghost btn--small btn--danger" data-detail-action="canceled" data-ticket-id="${escapeHtml(t.ticket_id)}">Cancel ticket</button>
      `;
    } else if (t.status === "processing") {
      actions = `
        <button class="btn btn--ghost btn--small" data-detail-action="closed" data-ticket-id="${escapeHtml(t.ticket_id)}">Close ticket</button>
      `;
    }
    drawerBody.innerHTML = `
      <dl class="detail-grid">
        <dt>ID</dt><dd><span class="ticket-id">${escapeHtml(t.ticket_id)}</span></dd>
        <dt>User</dt><dd>${escapeHtml(t.user_id || "--")}</dd>
        <dt>Subject</dt><dd>${escapeHtml(t.subject || "(empty)")}</dd>
        <dt>Priority</dt><dd><span class="priority" data-level="${escapeHtml(t.priority || "normal")}">${escapeHtml(PRIORITY_LABEL[t.priority] || t.priority || "Normal")}</span></dd>
        <dt>Status</dt><dd><span class="status-pill" data-status="${escapeHtml(t.status)}">${escapeHtml(STATUS_LABEL[t.status] || t.status)}</span></dd>
        <dt>Agent</dt><dd>${escapeHtml(t.agent_id || "--")}</dd>
        <dt>Created</dt><dd>${escapeHtml(fmtTs(t.created_at))}</dd>
        <dt>Updated</dt><dd>${escapeHtml(fmtTs(t.updated_at))}</dd>
        ${t.closed_at ? `<dt>Closed</dt><dd>${escapeHtml(fmtTs(t.closed_at))}</dd>` : ""}
      </dl>
      <p class="drawer__placeholder" style="font-style:normal;">Description</p>
      <div class="transcript">${escapeHtml(t.description || t.reason || "(none)")}</div>
      ${tx ? `
        <p class="transcript__title">Conversation transcript</p>
        <div class="transcript">${escapeHtml(tx)}</div>
      ` : ""}
      <div class="summary-block" id="summary-block">
        <p class="transcript__title">Session summary</p>
        <div data-role="summary-body" class="summary-body">Loading…</div>
      </div>
      ${actions ? `<div class="action-row">${actions}</div>` : ""}
    `;

    // Summary is auto-attached when the ticket is created (handoff → session-summary link).
    // Prefer the embedded copy; fall back to fetching by session_id if absent.
    if (t.session_summary) {
      renderSummaryBody({ summary: t.session_summary, session_id: t.session_id || t.user_id });
    } else {
      loadSummary(t.session_id || t.user_id || t.ticket_id);
    }

    Array.from(drawerBody.querySelectorAll("[data-detail-action]")).forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-ticket-id");
        const action = btn.getAttribute("data-detail-action");
        await onActionClick(id, action);
      });
    });
  }

  /* ---------- 会话纪要（session-summary 能力，未安装则静默隐藏）---------- */
  function renderSummaryBody(rec) {
    const box = drawerBody.querySelector('[data-role="summary-body"]');
    if (!box) return;
    const s = rec && rec.summary;
    if (!s) {
      box.innerHTML = `
        <p class="summary-empty">No summary yet.</p>
        <button class="btn btn--accent btn--small" data-role="btn-finalize">Generate summary</button>`;
      const btn = box.querySelector('[data-role="btn-finalize"]');
      if (btn) btn.addEventListener("click", () => finalizeSummary(rec.session_id));
      return;
    }
    const chips = (arr) => (arr && arr.length)
      ? arr.map((x) => `<span class="summary-chip">${escapeHtml(x)}</span>`).join("")
      : '<span class="summary-empty">—</span>';
    const wb = rec.writeback;
    box.innerHTML = `
      <dl class="summary-grid">
        <dt>Topics</dt><dd>${chips(s.topics)}</dd>
        <dt>User intents</dt><dd>${chips(s.user_intents)}</dd>
        <dt>Next actions</dt><dd>${chips(s.next_actions)}</dd>
      </dl>
      <p class="summary-meta">Engine: ${escapeHtml(s.engine || "-")}${s.model ? " · " + escapeHtml(s.model) : ""}${
        wb ? " · writeback " + escapeHtml(wb.sink || "") + (wb.record_id ? " (" + escapeHtml(wb.record_id) + ")" : "") : ""
      }</p>`;
  }

  async function loadSummary(sessionId) {
    const box = drawerBody.querySelector('[data-role="summary-body"]');
    if (!box || !sessionId) return;
    try {
      const resp = await fetch(`/api/v1/summary/${encodeURIComponent(sessionId)}`, { credentials: "same-origin" });
      if (resp.status === 404) {
        const blk = document.getElementById("summary-block");
        if (blk) blk.hidden = true;     // 该会话没有纪要记录
        return;
      }
      if (!resp.ok) { box.textContent = "Failed to load summary."; return; }
      const body = await resp.json();
      renderSummaryBody((body && body.data) || {});
    } catch (e) {
      // session-summary 能力未安装时 /api/v1/summary 不存在 → 隐藏整块
      const blk = document.getElementById("summary-block");
      if (blk) blk.hidden = true;
    }
  }

  async function finalizeSummary(sessionId) {
    if (!sessionId) return;
    const box = drawerBody.querySelector('[data-role="summary-body"]');
    if (box) box.innerHTML = '<p class="summary-empty">Generating…</p>';
    try {
      const body = await api(`/api/v1/summary/${encodeURIComponent(sessionId)}/finalize`, { method: "POST" });
      renderSummaryBody((body && body.data) || {});
      showToast("Session summary generated", "success");
    } catch (err) {
      showToast(`Failed to generate summary: ${err.message || err}`, "error");
      if (box) box.innerHTML = '<p class="summary-empty">Generation failed.</p>';
    }
  }

  function openDrawer(ticketId) {
    state.selectedId = ticketId;
    drawer.hidden = false;
    drawer.setAttribute("aria-hidden", "false");
    const t = state.list.find((x) => x.ticket_id === ticketId);
    if (t) renderDetail(t);
    else {
      // 单独拉一次详情（防止列表分页拿不到）
      api(`/api/v1/handoff/admin/tickets/${encodeURIComponent(ticketId)}`)
        .then((b) => renderDetail(b.data || b))
        .catch(() => renderDetail(null));
    }
    Array.from(tbody.querySelectorAll("tr")).forEach((tr) =>
      tr.classList.toggle("is-selected", tr.getAttribute("data-ticket-id") === ticketId),
    );
  }
  function closeDrawer() {
    drawer.hidden = true;
    drawer.setAttribute("aria-hidden", "true");
    state.selectedId = null;
    Array.from(tbody.querySelectorAll("tr")).forEach((tr) => tr.classList.remove("is-selected"));
  }
  btnCloseDrawer.addEventListener("click", closeDrawer);

  /* ---------- 状态切换 ---------- */
  async function onActionClick(ticketId, status) {
    const body = { status };
    if (status === "processing") body.agent_id = "agent_demo_001";
    try {
      await api(`/api/v1/handoff/admin/tickets/${encodeURIComponent(ticketId)}/status`, {
        method: "POST",
        body,
      });
      showToast(`Ticket ${ticketId.slice(0, 12)} → ${STATUS_LABEL[status] || status}`, "success");
    } catch (err) {
      showToast(`Status change failed: ${err.message || err}`, "error");
    }
    await Promise.all([fetchList(), fetchOverall()]);
    if (state.selectedId === ticketId) {
      const t = state.list.find((x) => x.ticket_id === ticketId);
      renderDetail(t);
    }
  }

  /* ---------- 筛选 ---------- */
  filterList.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".filter-item");
    if (!btn) return;
    const status = btn.getAttribute("data-status");
    if (status === null) return;
    state.statusFilter = status;
    Array.from(filterList.querySelectorAll(".filter-item")).forEach((b) =>
      b.classList.toggle("is-active", b === btn),
    );
    await fetchList();
  });

  /* ---------- 刷新 ---------- */
  async function refreshAll() {
    await Promise.all([fetchOverall(), fetchList()]);
  }
  btnRefresh.addEventListener("click", refreshAll);

  function setupAutoRefresh() {
    if (state.autoTimer) {
      clearInterval(state.autoTimer);
      state.autoTimer = null;
    }
    if (chkAuto.checked) {
      state.autoTimer = setInterval(refreshAll, 5000);
    }
  }
  chkAuto.addEventListener("change", setupAutoRefresh);

  /* ---------- 测试工单（仅 dev） ---------- */
  btnSeed.addEventListener("click", async () => {
    const fakeId = "demo_seed_" + Math.random().toString(36).slice(2, 8);
    try {
      await api("/api/v1/handoff/request", {
        method: "POST",
        body: { session_id: fakeId, reason: "Manually inserted test ticket from board" },
      });
      showToast("Test ticket inserted", "success");
    } catch (err) {
      showToast(`Insert failed: ${err.message || err}`, "error");
    }
    await refreshAll();
  });

  /* ---------- 启动 ---------- */
  refreshAll();
  setupAutoRefresh();
})();
