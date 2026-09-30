/**
 * CareVoice AI - Dental Clinic CRM & Admin Dashboard Script
 * Implements real-time synchronization, interactive calendar, SVG analytics,
 * call transcripts, and seamless integration with existing voice receptionist backend.
 */

(function () {
  "use strict";

  // --- Constants & Config ---
  const API_BASE = "/api/crm";
  const TOKEN_KEY = "carevoice_crm_token";
  const LIVE_SYNC_INTERVAL_MS = 20000; // 20s

  // --- Global State ---
  const state = {
    token: localStorage.getItem(TOKEN_KEY) || "",
    currentUser: null,
    activeTab: "overview",
    calendarDate: new Date(), // default to today
    overview: null,
    calls: [],
    appointments: [],
    patients: [],
    analytics: null,
    leads: [],
    followups: [],
    syncTimer: null,
  };

  // --- Helpers ---
  function $(selector) {
    return document.querySelector(selector);
  }

  function $$(selector) {
    return document.querySelectorAll(selector);
  }

  function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatTime(timeStr) {
    if (!timeStr) return "";
    // If format is HH:MM or HH:MM:SS
    const parts = timeStr.split(":");
    if (parts.length >= 2) {
      let hours = parseInt(parts[0], 10);
      const minutes = (parts[1] || "00").slice(0, 2);
      const ampm = hours >= 12 ? "PM" : "AM";
      hours = hours % 12;
      hours = hours ? hours : 12; // 0 becomes 12
      const hoursPadded = hours < 10 ? `0${hours}` : `${hours}`;
      return `${hoursPadded}:${minutes} ${ampm}`;
    }
    return timeStr;
  }

  function formatPatientName(name) {
    if (!name) return "Patient";
    const cleaned = String(name).trim();
    if (!cleaned) return "Patient";
    return cleaned
      .toLowerCase()
      .split(/\s+/)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    try {
      const d = new Date(dateStr + "T00:00:00");
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  }

  function formatDuration(sec) {
    const s = parseInt(sec, 10) || 0;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    if (m === 0) return `${rem}s`;
    return `${m}m ${rem < 10 ? "0" : ""}${rem}s`;
  }

  // --- Authenticated Fetch Wrapper ---
  async function crmFetch(endpoint, options = {}) {
    const headers = options.headers || {};
    if (state.token) {
      headers["Authorization"] = `Bearer ${state.token}`;
    }
    headers["Content-Type"] = "application/json";

    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
      });

      if (res.status === 401) {
        // Expired or missing token
        showLoginModal();
        throw new Error("Unauthorized");
      }

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP Error ${res.status}`);
      }

      return await res.json();
    } catch (err) {
      console.warn(`[CRM API] ${endpoint} failed:`, err.message);
      throw err;
    }
  }

  // --- Authentication Modal & Handlers ---
  function showLoginModal() {
    const modal = $("#login-modal");
    if (modal) modal.style.display = "flex";
  }

  function hideLoginModal() {
    const modal = $("#login-modal");
    if (modal) modal.style.display = "none";
  }

  async function checkAuthSession() {
    if (!state.token) {
      showLoginModal();
      return false;
    }

    try {
      const res = await crmFetch("/auth/me");
      const user = (res && (res.user || res.data)) || null;
      if (res.status === "success" && user) {
        state.currentUser = user;
        updateUserUI(user);
        hideLoginModal();
        return true;
      }
    } catch {
      showLoginModal();
    }
    return false;
  }

  function updateUserUI(user) {
    const nameEl = $(".profile-meta h4");
    const roleEl = $(".profile-meta p");
    const avatarEl = $(".profile-avatar");
    if (nameEl) nameEl.textContent = user.name || "Hamayoon";
    if (roleEl) roleEl.textContent = user.role || "Dental Clinic Admin";
    if (avatarEl) {
      const initials = (user.name || "Hamayoon")
        .split(" ")
        .map((p) => p[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
      avatarEl.textContent = initials || "HA";
    }
  }

  async function handleLoginSubmit() {
    const usernameInput = $("#login-username");
    const errEl = $("#login-error-msg");
    const val = (usernameInput ? usernameInput.value : "").trim();

    if (!val) {
      if (errEl) {
        errEl.textContent = "Please enter clinic PIN (2026) or admin username";
        errEl.style.display = "block";
      }
      return;
    }

    if (errEl) errEl.style.display = "none";

    try {
      const payload = {
        username: val,
        pin: val === "2026" ? "2026" : undefined,
      };

      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok || data.status !== "success") {
        throw new Error(data.detail || "Authentication failed. Try PIN: 2026");
      }

      const token = data.token || (data.data && data.data.token);
      const user = data.user || (data.data && data.data.user);

      if (!token) {
        throw new Error("No authentication token received from server.");
      }

      state.token = token;
      localStorage.setItem(TOKEN_KEY, state.token);
      state.currentUser = user || { name: "Hamayoon", role: "Dental Clinic Admin" };
      updateUserUI(state.currentUser);
      hideLoginModal();

      // Load initial dashboard data
      initDashboard();
    } catch (err) {
      if (errEl) {
        errEl.textContent = err.message || "Invalid credentials. Use PIN: 2026";
        errEl.style.display = "block";
      }
    }
  }

  function handleLogout() {
    state.token = "";
    state.currentUser = null;
    localStorage.removeItem(TOKEN_KEY);
    showLoginModal();
  }

  // --- Tab Navigation ---
  function switchTab(tabName) {
    if (!tabName) return;
    state.activeTab = tabName;

    // Update nav items
    $$(".sidebar-nav .nav-item").forEach((item) => {
      if (item.getAttribute("data-tab") === tabName) {
        item.classList.add("active");
      } else {
        item.classList.remove("active");
      }
    });

    // Update view containers
    $$(".view-container").forEach((view) => {
      view.classList.remove("active");
    });
    const targetView = $(`#view-${tabName}`);
    if (targetView) targetView.classList.add("active");

    // Push URL hash without jump
    window.location.hash = tabName;

    // Trigger tab-specific refresh
    loadTabContent(tabName);
  }

  function loadTabContent(tabName) {
    switch (tabName) {
      case "overview":
        loadOverview();
        break;
      case "calendar":
        loadCalendar();
        break;
      case "analytics":
        loadAnalytics();
        break;
      case "calls":
        loadCalls();
        break;
      case "appointments":
        loadAppointments();
        break;
      case "patients":
        loadPatients();
        break;
      case "leads":
        loadLeads();
        break;
      case "followups":
        loadFollowups();
        break;
      case "integrations":
        loadIntegrations();
        break;
    }
  }

  // ===========================================================================
  // VIEW 1: OVERVIEW (Reference Image 1)
  // ===========================================================================
  async function loadOverview() {
    try {
      const res = await crmFetch("/overview");
      if (res.status === "success" && res.data) {
        state.overview = res.data;
        renderOverviewMetrics(res.data.cards || res.data.metrics || {});
        renderOverviewFunnel(res.data.funnel || res.data.conversion_funnel || {});
        renderPipelineHealth(res.data.pipeline_health);
      }
    } catch (e) {
      console.warn("Could not load overview:", e);
    }
  }

  function renderOverviewMetrics(metrics) {
    if (!metrics) return;

    const totalLeads = metrics.total_leads ?? metrics.total_inquiries_leads ?? 0;
    const unactedLeads = metrics.new_unacted_leads ?? metrics.new_unacted_requests ?? 0;
    const callsPlaced = metrics.calls_placed ?? metrics.voice_calls_placed ?? 0;
    const callsCompleted = metrics.calls_completed ?? metrics.voice_calls_completed ?? 0;
    const aptsBooked = metrics.appointments_booked ?? 0;
    const convRate = metrics.conversion_rate ?? metrics.book_conversion_rate_percent ?? 0;
    const todaySlots = metrics.today_active_slots ?? metrics.todays_active_slots ?? 0;
    const missedCalls = metrics.missed_failed_calls ?? metrics.failed_missed_calls ?? 0;

    const totalLeadsEl = $("#stat-total-leads");
    const unactedLeadsEl = $("#stat-unacted-leads");
    const callsPlacedEl = $("#stat-calls-placed");
    const callsCompletedEl = $("#stat-calls-completed");
    const aptsBookedEl = $("#stat-appointments-booked");
    const convRateEl = $("#stat-conversion-rate");
    const todaySlotsEl = $("#stat-today-slots");
    const missedCallsEl = $("#stat-missed-calls");

    if (totalLeadsEl) totalLeadsEl.textContent = totalLeads;
    if (unactedLeadsEl) unactedLeadsEl.textContent = unactedLeads;
    if (callsPlacedEl) callsPlacedEl.textContent = callsPlaced;
    if (callsCompletedEl) callsCompletedEl.textContent = callsCompleted;
    if (aptsBookedEl) aptsBookedEl.textContent = aptsBooked;
    if (convRateEl) convRateEl.textContent = `${convRate}%`;
    if (todaySlotsEl) todaySlotsEl.textContent = todaySlots;
    if (missedCallsEl) missedCallsEl.textContent = missedCalls;

    // Sidebar Badges
    const badgeLeads = $("#badge-leads");
    const badgeFollowups = $("#badge-followups");
    if (badgeLeads) badgeLeads.textContent = unactedLeads;
    if (badgeFollowups) badgeFollowups.textContent = unactedLeads + missedCalls;
  }

  function renderOverviewFunnel(funnel) {
    if (!funnel) return;

    const rate = funnel.booking_rate_pct ?? funnel.overall_booking_rate_percent ?? 0;
    const rateBadge = $("#funnel-rate-badge");
    if (rateBadge) {
      rateBadge.textContent = `${rate}% Overall Booking Rate`;
    }

    const inq = funnel.new_leads ?? funnel.new_inquiries ?? 0;
    const placed = funnel.calls_placed ?? 0;
    const completed = funnel.conversations_completed ?? funnel.dialogues_completed ?? 0;
    const booked = funnel.appointments_booked ?? 0;

    const s1 = $("#funnel-step-1");
    const s2 = $("#funnel-step-2");
    const s3 = $("#funnel-step-3");
    const s4 = $("#funnel-step-4");

    if (s1) s1.textContent = inq;
    if (s2) s2.textContent = placed;
    if (s3) s3.textContent = completed;
    if (s4) s4.textContent = booked;

    // Calculate proportional bar widths (max 100%)
    const maxVal = Math.max(inq, 1);
    const b1 = $("#bar-funnel-1");
    const b2 = $("#bar-funnel-2");
    const b3 = $("#bar-funnel-3");
    const b4 = $("#bar-funnel-4");

    if (b1) b1.style.width = inq > 0 ? "100%" : "0%";
    if (b2) b2.style.width = `${Math.min(100, Math.round((placed / maxVal) * 100))}%`;
    if (b3) b3.style.width = `${Math.min(100, Math.round((completed / maxVal) * 100))}%`;
    if (b4) b4.style.width = `${Math.min(100, Math.round((booked / maxVal) * 100))}%`;
  }

  function renderPipelineHealth(healthData) {
    const container = $("#pipeline-health-container");
    const integrationsContainer = $("#integrations-health-list");
    if (!container && !integrationsContainer) return;

    const healthList = Array.isArray(healthData)
      ? healthData
      : (healthData && healthData.services) || [];

    if (!healthList || healthList.length === 0) {
      if (container) container.innerHTML = `<div style="font-size:0.8rem; color:var(--text-light);">No pipeline signals detected.</div>`;
      return;
    }

    const html = healthList
      .map((item) => {
        const isHealthy = String(item.status || "").toLowerCase().includes("healthy") ||
                          String(item.status || "").toLowerCase().includes("connected") ||
                          String(item.status || "").toLowerCase().includes("ready");
        const dotClass = isHealthy ? "pulse" : "";
        const dotBg = isHealthy ? "var(--status-green)" : "var(--status-amber)";
        const statusBadgeClass = isHealthy ? "" : "amber";

        return `
        <div class="pipeline-item">
          <div class="pipeline-item-info">
            <span class="dot-status ${dotClass}" style="background: ${dotBg};"></span>
            <div>
              <div class="pipeline-name">${escapeHtml(item.name || item.service || "Service")}</div>
              <div class="pipeline-meta">${escapeHtml(item.detail || item.note || item.target || "Active service connection")}</div>
            </div>
          </div>
          <div class="pipeline-item-status">
            <span class="health-badge ${statusBadgeClass}">${escapeHtml((item.status || "OK").toUpperCase())}</span>
          </div>
        </div>
      `;
      })
      .join("");

    if (container) container.innerHTML = html;
    if (integrationsContainer) integrationsContainer.innerHTML = html;
  }

  // ===========================================================================
  // VIEW 2: OPERATIONAL PRACTICE GRID (Reference Image 2)
  // ===========================================================================
  async function loadCalendar() {
    const curDate = state.calendarDate;
    const year = curDate.getFullYear();
    const month = curDate.getMonth() + 1;
    const monthStr = `${year}-${month < 10 ? "0" : ""}${month}`;

    const monthHeading = $("#cal-month-heading");
    if (monthHeading) {
      const monthNames = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
      ];
      monthHeading.textContent = `${monthNames[curDate.getMonth()]} ${year}`;
    }

    try {
      const res = await crmFetch(`/calendar?month=${monthStr}`);
      const events = (res.status === "success" && res.data && res.data.events) || [];
      renderCalendarGrid(year, curDate.getMonth(), events);
    } catch (e) {
      console.warn("Could not load calendar events:", e);
      renderCalendarGrid(year, curDate.getMonth(), []);
    }
  }

  function renderCalendarGrid(year, monthIdx, events) {
    const gridEl = $("#cal-body-grid");
    if (!gridEl) return;

    // Group events by YYYY-MM-DD
    const eventsByDate = {};
    events.forEach((ev) => {
      const d = ev.date;
      if (!eventsByDate[d]) eventsByDate[d] = [];
      eventsByDate[d].push(ev);
    });

    const firstDayOfMonth = new Date(year, monthIdx, 1);
    const lastDayOfMonth = new Date(year, monthIdx + 1, 0);
    const startDayOfWeek = firstDayOfMonth.getDay(); // 0 = Sun
    const totalDays = lastDayOfMonth.getDate();

    // Previous month padding
    const prevMonthLastDay = new Date(year, monthIdx, 0).getDate();
    const prevDaysCount = startDayOfWeek;

    const today = new Date();
    const isCurrentMonth = today.getFullYear() === year && today.getMonth() === monthIdx;
    const todayDateNum = today.getDate();

    let cellsHtml = "";

    // 1. Preceding days from previous month
    for (let i = prevDaysCount - 1; i >= 0; i--) {
      const dNum = prevMonthLastDay - i;
      cellsHtml += `
        <div class="cal-day-cell other-month">
          <div class="cal-day-header">
            <span class="cal-day-number">${dNum}</span>
          </div>
          <div class="cal-events-list"></div>
        </div>
      `;
    }

    // 2. Current month days
    for (let day = 1; day <= totalDays; day++) {
      const dStr = `${year}-${monthIdx + 1 < 10 ? "0" : ""}${monthIdx + 1}-${day < 10 ? "0" : ""}${day}`;
      const dayEvents = eventsByDate[dStr] || [];
      const isToday = isCurrentMonth && day === todayDateNum;
      const todayClass = isToday ? "is-today today" : "";

      let chipsHtml = "";
      dayEvents.forEach((ev, idx) => {
        let chipClass = "chip-green";
        const st = (ev.status || "").toLowerCase();
        if (st.includes("cancel")) {
          chipClass = "chip-red";
        } else if (st.includes("pending") || st.includes("resched")) {
          chipClass = "chip-amber";
        } else if (st.includes("complete")) {
          chipClass = "chip-blue";
        } else {
          // Smooth cyclic pastel palette matching reference design: Green -> Blue -> Amber -> Purple
          const pastelCycle = ["chip-green", "chip-blue", "chip-amber", "chip-purple"];
          chipClass = pastelCycle[idx % pastelCycle.length];
        }

        const timeLabel = formatTime(ev.time);
        const rawName = ev.patient_name || "Patient";
        const displayName = formatPatientName(rawName);

        chipsHtml += `
          <div class="cal-event-chip ${chipClass}" data-apt-id="${ev.id || ''}" data-patient="${escapeHtml(displayName)}" title="${escapeHtml(displayName)} — ${timeLabel} (${escapeHtml(ev.service || "Appointment")})">
            <span class="apt-chip-name">${escapeHtml(displayName)}</span>
            <span class="apt-chip-time">${timeLabel}</span>
          </div>
        `;
      });

      cellsHtml += `
        <div class="cal-day-cell ${todayClass}">
          <div class="cal-day-header">
            <span class="cal-day-number ${isToday ? "today-num" : ""}">${day}</span>
            ${isToday ? '<span class="today-badge">TODAY</span>' : ""}
          </div>
          <div class="cal-events-list">
            ${chipsHtml}
          </div>
        </div>
      `;
    }

    // 3. Trailing days to fill standard 35 or 42 cell grid
    const totalCellsSoFar = prevDaysCount + totalDays;
    const remainingCells = (totalCellsSoFar <= 35 ? 35 : 42) - totalCellsSoFar;
    for (let day = 1; day <= remainingCells; day++) {
      cellsHtml += `
        <div class="cal-day-cell other-month">
          <div class="cal-day-header">
            <span class="cal-day-number">${day}</span>
          </div>
          <div class="cal-events-list"></div>
        </div>
      `;
    }

    gridEl.innerHTML = cellsHtml;
  }

  // ===========================================================================
  // VIEW 3: ANALYTICS (Reference Image 3 - Native High-Fidelity SVG Charts)
  // ===========================================================================
  async function loadAnalytics() {
    try {
      const res = await crmFetch("/analytics");
      if (res.status === "success" && res.data) {
        state.analytics = res.data;
        renderAnalyticsCharts(res.data);
      }
    } catch (e) {
      console.warn("Could not load analytics:", e);
      renderAnalyticsCharts(null);
    }
  }

  function renderAnalyticsCharts(data) {
    renderInflowTrendChart(data ? data.inflow_trend : null);
    renderDentalConcernsChart(data ? data.concerns_breakdown : null);
    renderDialerOutcomesChart(data ? data.dialer_outcomes : null);
    renderPeakSlotsChart(data ? data.peak_slots : null);
  }

  // Chart 1: System Growth Inflow Trend (SVG Spline with Gradient Fill)
  function renderInflowTrendChart(trendData) {
    const container = $("#chart-inflow-container");
    if (!container) return;

    const data = trendData || [];
    const w = 480;
    const h = 220;
    const padding = { top: 20, right: 25, bottom: 35, left: 35 };

    // Baseline labels
    const points = data.length > 0 ? data : [
      { label: "Mon", count: 0 },
      { label: "Tue", count: 0 },
      { label: "Wed", count: 0 },
      { label: "Thu", count: 0 },
      { label: "Fri", count: 0 },
      { label: "Sat", count: 0 },
      { label: "Sun", count: 0 },
    ];

    const maxCount = Math.max(...points.map((p) => p.count), 5);
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    const coords = points.map((p, i) => {
      const x = padding.left + (i / (points.length - 1)) * plotW;
      const y = padding.top + plotH - (p.count / maxCount) * plotH;
      return { x, y, count: p.count, label: p.label };
    });

    // Build SVG Path
    let pathD = `M ${coords[0].x} ${coords[0].y}`;
    for (let i = 1; i < coords.length; i++) {
      const prev = coords[i - 1];
      const cur = coords[i];
      const cx = (prev.x + cur.x) / 2;
      pathD += ` C ${cx} ${prev.y}, ${cx} ${cur.y}, ${cur.x} ${cur.y}`;
    }

    const areaD = `${pathD} L ${coords[coords.length - 1].x} ${padding.top + plotH} L ${coords[0].x} ${padding.top + plotH} Z`;

    const svgHtml = `
      <svg width="100%" height="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="overflow: visible;">
        <defs>
          <linearGradient id="inflowGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#0284C7" stop-opacity="0.32" />
            <stop offset="100%" stop-color="#0284C7" stop-opacity="0.01" />
          </linearGradient>
        </defs>
        
        <!-- Grid lines -->
        <line x1="${padding.left}" y1="${padding.top}" x2="${w - padding.right}" y2="${padding.top}" stroke="#E2E8F0" stroke-dasharray="3,3" />
        <line x1="${padding.left}" y1="${padding.top + plotH * 0.5}" x2="${w - padding.right}" y2="${padding.top + plotH * 0.5}" stroke="#E2E8F0" stroke-dasharray="3,3" />
        <line x1="${padding.left}" y1="${padding.top + plotH}" x2="${w - padding.right}" y2="${padding.top + plotH}" stroke="#CBD5E1" />

        <!-- Area Fill -->
        <path d="${areaD}" fill="url(#inflowGrad)" />

        <!-- Main Stroke Line -->
        <path d="${pathD}" fill="none" stroke="#0284C7" stroke-width="2.5" stroke-linecap="round" />

        <!-- Points & X-Labels -->
        ${coords
          .map(
            (c) => `
          <circle cx="${c.x}" cy="${c.y}" r="4" fill="#FFFFFF" stroke="#0284C7" stroke-width="2">
            <title>${escapeHtml(c.label)}: ${c.count} inquiries</title>
          </circle>
          <text x="${c.x}" y="${h - 10}" text-anchor="middle" font-size="10" fill="#64748B" font-family="Inter, sans-serif">${escapeHtml(c.label)}</text>
        `
          )
          .join("")}

        <!-- Y-Axis max & min labels -->
        <text x="${padding.left - 8}" y="${padding.top + 4}" text-anchor="end" font-size="10" fill="#94A3B8">${maxCount}</text>
        <text x="${padding.left - 8}" y="${padding.top + plotH}" text-anchor="end" font-size="10" fill="#94A3B8">0</text>
      </svg>
    `;

    container.innerHTML = svgHtml;
  }

  // Chart 2: Common Patient Dental Concerns (Horizontal Gradient Bars)
  function renderDentalConcernsChart(concernsData) {
    const container = $("#chart-concerns-container");
    if (!container) return;

    const list = concernsData || [
      { name: "Routine Cleaning", count: 0, percent: 0 },
      { name: "Toothache & Pain", count: 0, percent: 0 },
      { name: "Dental Exam & X-Ray", count: 0, percent: 0 },
      { name: "Cavity & Fillings", count: 0, percent: 0 },
      { name: "Crowns & Implants", count: 0, percent: 0 },
    ];

    let barsHtml = `<div style="display:flex; flex-direction:column; gap:12px; width:100%; padding:8px 4px;">`;
    list.slice(0, 5).forEach((item) => {
      const pct = Math.max(0, Math.min(100, item.percent || 0));
      barsHtml += `
        <div style="display:flex; flex-direction:column; gap:4px;">
          <div style="display:flex; justify-content:space-between; font-size:0.78rem; font-weight:600; color:var(--text-dark);">
            <span>${escapeHtml(item.name)}</span>
            <span style="color:var(--text-muted); font-size:0.75rem;">${item.count} (${pct}%)</span>
          </div>
          <div style="width:100%; height:8px; background:var(--bg-main); border-radius:4px; overflow:hidden;">
            <div style="width:${pct}%; height:100%; background:linear-gradient(90deg, #0284C7 0%, #10B981 100%); border-radius:4px; transition:width 0.4s ease;"></div>
          </div>
        </div>
      `;
    });
    barsHtml += `</div>`;

    container.innerHTML = barsHtml;
  }

  // Chart 3: Conversational Dialer Outcomes (SVG Donut with Center Conversion Rate)
  function renderDialerOutcomesChart(outcomesData) {
    const container = $("#chart-outcomes-container");
    if (!container) return;

    const booked = (outcomesData && outcomesData.booked) || 0;
    const inquiry = (outcomesData && outcomesData.inquiry) || 0;
    const resched = (outcomesData && outcomesData.rescheduled) || 0;
    const missed = (outcomesData && outcomesData.missed) || 0;

    const total = booked + inquiry + resched + missed;
    const rate = total > 0 ? Math.round((booked / total) * 100) : 0;

    // Donut SVG parameters
    const size = 180;
    const strokeWidth = 24;
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;

    // Segments calculation
    const segments = [
      { name: "Booked", count: booked, color: "#10B981" },
      { name: "Inquiry", count: inquiry, color: "#0284C7" },
      { name: "Resched", count: resched, color: "#F59E0B" },
      { name: "Missed", count: missed, color: "#EF4444" },
    ];

    let currentOffset = 0;
    let pathsHtml = "";

    if (total === 0) {
      // Empty placeholder ring
      pathsHtml = `
        <circle cx="${size / 2}" cy="${size / 2}" r="${radius}"
          fill="none" stroke="#E2E8F0" stroke-width="${strokeWidth}" />
      `;
    } else {
      segments.forEach((seg) => {
        if (seg.count > 0) {
          const ratio = seg.count / total;
          const strokeDash = ratio * circumference;
          const strokeOffset = -currentOffset;
          pathsHtml += `
            <circle cx="${size / 2}" cy="${size / 2}" r="${radius}"
              fill="none" stroke="${seg.color}" stroke-width="${strokeWidth}"
              stroke-dasharray="${strokeDash} ${circumference - strokeDash}"
              stroke-dashoffset="${strokeOffset}"
              transform="rotate(-90 ${size / 2} ${size / 2})"
            >
              <title>${seg.name}: ${seg.count}</title>
            </circle>
          `;
          currentOffset += strokeDash;
        }
      });
    }

    const html = `
      <div style="display:flex; align-items:center; justify-content:center; gap:20px; width:100%;">
        <div style="position:relative; width:${size}px; height:${size}px; flex-shrink:0;">
          <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            ${pathsHtml}
          </svg>
          <div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none;">
            <span style="font-size:1.35rem; font-weight:800; color:var(--text-dark);">${rate}%</span>
            <span style="font-size:0.68rem; color:var(--text-light); text-transform:uppercase; font-weight:600;">Book Rate</span>
          </div>
        </div>

        <div style="display:flex; flex-direction:column; gap:8px; font-size:0.75rem;">
          ${segments
            .map(
              (s) => `
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="width:10px; height:10px; border-radius:50%; background:${s.color}; display:inline-block;"></span>
              <span style="color:var(--text-muted); font-weight:500;">${s.name}</span>
              <strong style="color:var(--text-dark); margin-left:auto;">${s.count}</strong>
            </div>
          `
            )
            .join("")}
        </div>
      </div>
    `;

    container.innerHTML = html;
  }

  // Chart 4: Peak Preferred Scheduling Slots (Hourly Demand Histogram)
  function renderPeakSlotsChart(peakData) {
    const container = $("#chart-slots-container");
    if (!container) return;

    const slots = peakData || [
      { hour: "8 AM", count: 0 },
      { hour: "9 AM", count: 0 },
      { hour: "10 AM", count: 0 },
      { hour: "11 AM", count: 0 },
      { hour: "1 PM", count: 0 },
      { hour: "2 PM", count: 0 },
      { hour: "3 PM", count: 0 },
      { hour: "4 PM", count: 0 },
    ];

    const maxCount = Math.max(...slots.map((s) => s.count), 1);

    let barsHtml = `<div style="display:flex; align-items:flex-end; justify-content:space-between; width:100%; height:160px; padding:10px 8px 0 8px; border-bottom:1px solid var(--border-light);">`;
    slots.forEach((s) => {
      const heightPct = Math.max(4, Math.round((s.count / maxCount) * 100));
      const isPeak = s.count === maxCount && maxCount > 0;
      const barBg = isPeak ? "var(--status-amber)" : "var(--primary-color)";

      barsHtml += `
        <div style="display:flex; flex-direction:column; align-items:center; gap:6px; flex:1;">
          <div style="font-size:0.68rem; font-weight:700; color:var(--text-muted);">${s.count > 0 ? s.count : ""}</div>
          <div style="width:20px; height:${heightPct}%; background:${barBg}; border-radius:4px 4px 0 0; transition:height 0.3s ease;" title="${escapeHtml(s.hour)}: ${s.count} requests"></div>
          <div style="font-size:0.68rem; font-weight:600; color:var(--text-light); margin-top:4px;">${escapeHtml(s.hour)}</div>
        </div>
      `;
    });
    barsHtml += `</div>`;

    container.innerHTML = barsHtml;
  }

  // ===========================================================================
  // VIEW 4: AI CALLS (Calls, Tool Calling & Transcripts)
  // ===========================================================================
  async function loadCalls() {
    const searchVal = $("#calls-search") ? $("#calls-search").value.trim() : "";
    const statusVal = $("#calls-status-filter") ? $("#calls-status-filter").value : "all";

    const q = new URLSearchParams();
    if (searchVal) q.set("search", searchVal);
    if (statusVal && statusVal !== "all") q.set("status", statusVal);

    try {
      const res = await crmFetch(`/calls?${q.toString()}`);
      state.calls = (res.status === "success" && res.data && (res.data.items || res.data.calls)) || [];
      renderCallsTable(state.calls);
    } catch (e) {
      console.warn("Could not load calls:", e);
      renderCallsTable([]);
    }
  }

  function renderCallsTable(calls) {
    const tbody = $("#calls-table-body");
    if (!tbody) return;

    if (!calls || calls.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7">
            <div class="empty-state-box">
              <div class="empty-icon">📞</div>
              <h4>No Voice Calls Logged Yet</h4>
              <p>Place a call using the top-right <strong>"Open Voice Phone"</strong> link to test the live voice agent. Session audio, transcripts, and n8n tool calls will appear here automatically.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = calls
      .map((call) => {
        const callerName = escapeHtml(call.caller_name || "Web Visitor / Patient");
        const phone = escapeHtml(call.phone_number || "—");
        const dt = escapeHtml(call.started_at ? call.started_at.replace("T", " ").slice(0, 16) : "Just now");
        const duration = formatDuration(call.duration_seconds);
        const intent = escapeHtml(call.intent || "General Inquiry");

        let outcomeBadge = '<span class="status-chip blue">General Inquiry</span>';
        const outLow = (call.outcome || "").toLowerCase();
        if (outLow.includes("book")) {
          outcomeBadge = '<span class="status-chip green">Booked Appointment</span>';
        } else if (outLow.includes("resched")) {
          outcomeBadge = '<span class="status-chip amber">Rescheduled</span>';
        } else if (outLow.includes("cancel")) {
          outcomeBadge = '<span class="status-chip red">Cancelled</span>';
        } else if (call.status === "missed") {
          outcomeBadge = '<span class="status-chip red">Interrupted / Missed</span>';
        }

        return `
        <tr>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="width:28px; height:28px; border-radius:50%; background:var(--primary-bg); color:var(--primary-color); display:flex; align-items:center; justify-content:center; font-size:0.8rem; font-weight:700;">
                ${callerName.slice(0, 1).toUpperCase()}
              </span>
              <strong style="color:var(--text-dark);">${callerName}</strong>
            </div>
          </td>
          <td><span style="font-family:'JetBrains Mono', monospace; font-size:0.78rem;">${phone}</span></td>
          <td>${dt}</td>
          <td><span class="status-chip" style="background:#F1F5F9; color:#475569;">${duration}</span></td>
          <td>${intent}</td>
          <td>${outcomeBadge}</td>
          <td>
            <button class="btn-secondary btn-view-transcript" data-call-id="${call.id}" style="padding:4px 9px; font-size:0.75rem;">
              View Transcript
            </button>
          </td>
        </tr>
      `;
      })
      .join("");

    // Wire transcript click handlers
    tbody.querySelectorAll(".btn-view-transcript").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cId = btn.getAttribute("data-call-id");
        openTranscriptModal(cId);
      });
    });
  }

  function openTranscriptModal(callId) {
    const call = state.calls.find((c) => String(c.id) === String(callId));
    if (!call) return;

    const modal = $("#transcript-modal");
    const callerTitle = $("#modal-caller-title");
    const callMeta = $("#modal-call-meta");
    const toolCallsBox = $("#modal-tool-calls-box");
    const transcriptBox = $("#modal-transcript-container");

    if (callerTitle) {
      callerTitle.textContent = `Call: ${call.caller_name || "Web Patient"} (${call.phone_number || "No Phone"})`;
    }
    if (callMeta) {
      callMeta.textContent = `Duration: ${formatDuration(call.duration_seconds)} • Intent: ${call.intent || "General"} • Outcome: ${call.outcome || "Inquiry"}`;
    }

    // Render Retell-style Tool Calls Badge
    if (toolCallsBox) {
      const toolRecords = call.tool_calls || [];
      if (toolRecords.length > 0) {
        let toolsHtml = `<div style="font-size:0.74rem; font-weight:700; color:var(--text-muted); margin-bottom:6px;">TOOL CALL EXECUTION:</div>`;
        toolsHtml += `<div style="display:flex; flex-direction:column; gap:6px;">`;
        toolRecords.forEach((t) => {
          const fn = t.name || "appointment_tool";
          const isSuccess = t.success !== false;
          const statusClass = isSuccess ? "green" : "red";
          const statusText = isSuccess ? "SUCCESS" : "FAILED";
          toolsHtml += `
            <div style="background:var(--bg-main); border:1px solid var(--border-light); border-radius:6px; padding:6px 10px; font-size:0.75rem;">
              <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
                <strong>⚡ ${escapeHtml(fn)}</strong>
                <span class="status-chip ${statusClass}" style="font-size:0.68rem; padding:2px 6px;">${statusText}</span>
              </div>
              <pre style="margin:0; font-family:'JetBrains Mono', monospace; font-size:0.7rem; color:var(--text-muted); white-space:pre-wrap;">${escapeHtml(JSON.stringify(t.arguments || {}, null, 2))}</pre>
            </div>
          `;
        });
        toolsHtml += `</div>`;
        toolCallsBox.innerHTML = toolsHtml;
        toolCallsBox.style.display = "block";
      } else {
        toolCallsBox.style.display = "none";
      }
    }

    // Render Conversation Bubbles
    if (transcriptBox) {
      const transcripts = call.transcripts || [];
      if (transcripts.length === 0) {
        transcriptBox.innerHTML = `<div style="padding:20px; text-align:center; color:var(--text-light); font-size:0.8rem;">No verbal dialogue recorded for this session.</div>`;
      } else {
        transcriptBox.innerHTML = transcripts
          .map((item) => {
            const isSophia = item.role === "assistant";
            const bubbleClass = isSophia ? "assistant" : "user";
            const roleName = isSophia ? "Sophia (AI Receptionist)" : escapeHtml(call.caller_name || "Caller");
            const avatar = isSophia ? "🦷" : "👤";

            return `
            <div class="transcript-bubble ${bubbleClass}">
              <div class="bubble-header">
                <span>${avatar} ${roleName}</span>
                <span>${escapeHtml(item.time || "")}</span>
              </div>
              <div class="bubble-text">${escapeHtml(item.text)}</div>
            </div>
          `;
          })
          .join("");
      }
    }

    if (modal) modal.style.display = "flex";
  }

  // ===========================================================================
  // VIEW 5: APPOINTMENTS DIRECTORY
  // ===========================================================================
  async function loadAppointments() {
    const searchVal = $("#apt-search") ? $("#apt-search").value.trim() : "";
    const statusVal = $("#apt-status-filter") ? $("#apt-status-filter").value : "all";
    const typeVal = $("#apt-patient-type-filter") ? $("#apt-patient-type-filter").value : "all";

    const q = new URLSearchParams();
    if (searchVal) q.set("search", searchVal);
    if (statusVal && statusVal !== "all") q.set("status", statusVal);
    if (typeVal && typeVal !== "all") q.set("patient_type", typeVal);

    try {
      const res = await crmFetch(`/appointments?${q.toString()}`);
      state.appointments = (res.status === "success" && res.data && (res.data.items || res.data.appointments)) || [];
      renderAppointmentsTable(state.appointments);
    } catch (e) {
      console.warn("Could not load appointments:", e);
      renderAppointmentsTable([]);
    }
  }

  function renderAppointmentsTable(apts) {
    const tbody = $("#apt-table-body");
    if (!tbody) return;

    if (!apts || apts.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7">
            <div class="empty-state-box">
              <div class="empty-icon">📋</div>
              <h4>No Appointments Scheduled Yet</h4>
              <p>Appointments booked by Sophia through Google Calendar & n8n or added manually by clinic staff will appear here.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = apts
      .map((apt) => {
        let statusBadge = '<span class="status-chip green">Confirmed</span>';
        const st = (apt.status || "").toLowerCase();
        if (st.includes("resched")) statusBadge = '<span class="status-chip amber">Rescheduled</span>';
        else if (st.includes("cancel")) statusBadge = '<span class="status-chip red">Cancelled</span>';

        return `
        <tr>
          <td><strong style="color:var(--text-dark);">${escapeHtml(apt.patient_name)}</strong></td>
          <td><span style="font-family:'JetBrains Mono', monospace; font-size:0.78rem;">${escapeHtml(apt.phone_number)}</span></td>
          <td>${formatDate(apt.appointment_date)}</td>
          <td><strong>${formatTime(apt.appointment_time)}</strong></td>
          <td>${escapeHtml(apt.service || "Routine Treatment")}</td>
          <td><span class="status-chip" style="background:#F8FAFC; color:#475569;">${escapeHtml(apt.patient_type || "Existing")}</span></td>
          <td>${statusBadge}</td>
        </tr>
      `;
      })
      .join("");
  }

  async function handleCreateAppointment(e) {
    e.preventDefault();
    const patientName = $("#form-patient-name")?.value.trim();
    const phoneNumber = $("#form-phone-number")?.value.trim();
    const appointmentDate = $("#form-appointment-date")?.value;
    const appointmentTime = $("#form-appointment-time")?.value;
    const service = $("#form-service")?.value.trim();
    const patientType = $("#form-patient-type")?.value;
    const insurance = $("#form-insurance")?.value.trim();

    if (!patientName || !phoneNumber || !appointmentDate || !appointmentTime) {
      alert("Please complete Patient Name, Phone, Date, and Time.");
      return;
    }

    try {
      const payload = {
        patient_name: patientName,
        phone_number: phoneNumber,
        appointment_date: appointmentDate,
        appointment_time: appointmentTime,
        service: service || "Routine Checkup",
        patient_type: patientType || "Existing Patient",
        insurance: insurance || "Self Pay",
      };

      const res = await crmFetch("/appointments", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      if (res.status === "success") {
        $("#create-apt-modal").style.display = "none";
        $("#create-apt-form")?.reset();
        // Refresh views
        loadAppointments();
        loadCalendar();
        loadOverview();
      }
    } catch (err) {
      alert(`Booking failed: ${err.message}`);
    }
  }

  // ===========================================================================
  // VIEW 6: PATIENTS REGISTRY
  // ===========================================================================
  async function loadPatients() {
    const searchVal = $("#patients-search") ? $("#patients-search").value.trim() : "";
    const q = new URLSearchParams();
    if (searchVal) q.set("search", searchVal);

    try {
      const res = await crmFetch(`/patients?${q.toString()}`);
      state.patients = (res.status === "success" && res.data && (res.data.items || res.data.patients)) || [];
      renderPatientsTable(state.patients);
    } catch (e) {
      console.warn("Could not load patients:", e);
      renderPatientsTable([]);
    }
  }

  function renderPatientsTable(patients) {
    const tbody = $("#patients-table-body");
    if (!tbody) return;

    if (!patients || patients.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6">
            <div class="empty-state-box">
              <div class="empty-icon">👥</div>
              <h4>No Patients Registered Yet</h4>
              <p>Patients are automatically registered when they speak with Sophia or book appointments.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = patients
      .map((p) => {
        const patientName = escapeHtml(p.full_name || p.name || "Patient");
        const phone = escapeHtml(p.phone_number || p.phone || "—");
        const visitDate = formatDate(p.last_appointment_date || p.last_visit || p.created_at?.slice(0, 10));
        return `
        <tr>
          <td><strong style="color:var(--text-dark);">${patientName}</strong></td>
          <td><span style="font-family:'JetBrains Mono', monospace; font-size:0.78rem;">${phone}</span></td>
          <td><span class="status-chip" style="background:#F1F5F9; color:#475569;">${escapeHtml(p.patient_type || "Existing")}</span></td>
          <td>${escapeHtml(p.insurance || "None / Self Pay")}</td>
          <td>${visitDate}</td>
          <td><strong style="color:var(--primary-color);">${p.total_visits || 1}</strong></td>
        </tr>
      `;
      })
      .join("");
  }

  // ===========================================================================
  // VIEW 7 & 8: INTEGRATIONS, LEADS & FOLLOW-UPS
  // ===========================================================================
  async function loadIntegrations() {
    loadOverview();
  }

  async function loadLeads() {
    const container = $("#leads-list-container");
    const emptyState = $("#leads-empty-state");
    if (!container) return;

    // Filter calls with inquiry intent but no confirmed booking
    const leads = state.calls.filter((c) => {
      const out = (c.outcome || "").toLowerCase();
      return !out.includes("book") && !out.includes("resched");
    });

    if (leads.length === 0) {
      if (emptyState) emptyState.style.display = "block";
      container.innerHTML = "";
    } else {
      if (emptyState) emptyState.style.display = "none";
      container.innerHTML = `
        <table class="crm-table">
          <thead>
            <tr>
              <th>Lead Name</th>
              <th>Phone</th>
              <th>Date</th>
              <th>Inquiry Intent</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${leads
              .map(
                (l) => `
              <tr>
                <td><strong>${escapeHtml(l.caller_name || "Lead")}</strong></td>
                <td><span style="font-family:'JetBrains Mono', monospace;">${escapeHtml(l.phone_number || "—")}</span></td>
                <td>${escapeHtml(l.started_at?.replace("T", " ").slice(0, 16) || "Recent")}</td>
                <td>${escapeHtml(l.intent || "General Inquiry")}</td>
                <td><span class="status-chip amber">Pending Follow-up</span></td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      `;
    }
  }

  async function loadFollowups() {
    const container = $("#followups-list-container");
    const emptyState = $("#followups-empty-state");
    if (!container) return;

    // Filter missed or interrupted calls
    const followups = state.calls.filter((c) => c.status === "missed");

    if (followups.length === 0) {
      if (emptyState) emptyState.style.display = "block";
      container.innerHTML = "";
    } else {
      if (emptyState) emptyState.style.display = "none";
      container.innerHTML = `
        <table class="crm-table">
          <thead>
            <tr>
              <th>Caller</th>
              <th>Phone</th>
              <th>Date</th>
              <th>Reason</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${followups
              .map(
                (f) => `
              <tr>
                <td><strong>${escapeHtml(f.caller_name || "Interrupted Call")}</strong></td>
                <td><span style="font-family:'JetBrains Mono', monospace;">${escapeHtml(f.phone_number || "—")}</span></td>
                <td>${escapeHtml(f.started_at?.replace("T", " ").slice(0, 16) || "Recent")}</td>
                <td><span class="status-chip red">Disconnected Early</span></td>
                <td>
                  <button class="btn-primary" style="padding:4px 8px; font-size:0.72rem;">Schedule Callback</button>
                </td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      `;
    }
  }

  // ===========================================================================
  // INITIALIZATION & EVENT LISTENERS
  // ===========================================================================
  function wireEventListeners() {
    // 1. Sidebar Nav
    $$(".sidebar-nav .nav-item").forEach((item) => {
      item.addEventListener("click", () => {
        const tab = item.getAttribute("data-tab");
        switchTab(tab);
      });
    });

    // 2. Auth Modal
    $("#login-submit-btn")?.addEventListener("click", handleLoginSubmit);
    $("#login-username")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleLoginSubmit();
    });
    $("#logout-btn")?.addEventListener("click", handleLogout);

    // 3. Calendar Navigation
    $("#cal-prev-btn")?.addEventListener("click", () => {
      state.calendarDate.setMonth(state.calendarDate.getMonth() - 1);
      loadCalendar();
    });
    $("#cal-next-btn")?.addEventListener("click", () => {
      state.calendarDate.setMonth(state.calendarDate.getMonth() + 1);
      loadCalendar();
    });
    $("#cal-today-btn")?.addEventListener("click", () => {
      state.calendarDate = new Date();
      loadCalendar();
    });

    // Calendar Event Chip Click -> inspect in appointments table
    $("#cal-body-grid")?.addEventListener("click", (e) => {
      const chip = e.target.closest(".cal-event-chip");
      if (!chip) return;
      const patient = chip.getAttribute("data-patient") || "";
      if (patient) {
        switchTab("appointments");
        const aptSearch = $("#apt-search");
        if (aptSearch) {
          aptSearch.value = patient;
          loadAppointments();
        }
      }
    });

    // 4. Modals: Create Appointment
    const openCreateApt = () => {
      const m = $("#create-apt-modal");
      if (m) m.style.display = "flex";
    };
    $("#btn-open-create-apt")?.addEventListener("click", openCreateApt);
    $("#btn-add-apt-table")?.addEventListener("click", openCreateApt);
    $("#btn-add-cal-event")?.addEventListener("click", openCreateApt);
    $("#close-create-apt-modal")?.addEventListener("click", () => {
      $("#create-apt-modal").style.display = "none";
    });
    $("#create-apt-form")?.addEventListener("submit", handleCreateAppointment);

    // 5. Modals: Transcript Inspector
    $("#close-transcript-modal")?.addEventListener("click", () => {
      $("#transcript-modal").style.display = "none";
    });

    // 6. Global Search & Filters
    $("#global-search")?.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      // If on calls or appointments, update respective search
      if (state.activeTab === "calls") {
        if ($("#calls-search")) $("#calls-search").value = q;
        loadCalls();
      } else if (state.activeTab === "appointments") {
        if ($("#apt-search")) $("#apt-search").value = q;
        loadAppointments();
      } else if (state.activeTab === "patients") {
        if ($("#patients-search")) $("#patients-search").value = q;
        loadPatients();
      }
    });

    $("#calls-search")?.addEventListener("input", loadCalls);
    $("#calls-status-filter")?.addEventListener("change", loadCalls);

    $("#apt-search")?.addEventListener("input", loadAppointments);
    $("#apt-status-filter")?.addEventListener("change", loadAppointments);
    $("#apt-patient-type-filter")?.addEventListener("change", loadAppointments);

    $("#patients-search")?.addEventListener("input", loadPatients);

    // 7. Sync Buttons
    const triggerSync = async () => {
      const syncBtn = $("#refresh-sync-btn");
      if (syncBtn) syncBtn.classList.add("spinning");
      await loadTabContent(state.activeTab);
      setTimeout(() => {
        if (syncBtn) syncBtn.classList.remove("spinning");
      }, 600);
    };
    $("#refresh-sync-btn")?.addEventListener("click", triggerSync);
    $("#btn-sync-overview")?.addEventListener("click", triggerSync);
    $("#btn-refresh-analytics")?.addEventListener("click", () => loadAnalytics());
    $("#btn-recheck-integrations")?.addEventListener("click", () => loadIntegrations());

    // 8. Close modals on overlay backdrop click
    $$(".modal-overlay").forEach((modal) => {
      modal.addEventListener("click", (e) => {
        if (e.target === modal && modal.id !== "login-modal") {
          modal.style.display = "none";
        }
      });
    });
  }

  function initPeriodicSync() {
    if (state.syncTimer) clearInterval(state.syncTimer);
    state.syncTimer = setInterval(() => {
      if (state.token && state.currentUser) {
        // Silently refresh current view
        loadTabContent(state.activeTab);
      }
    }, LIVE_SYNC_INTERVAL_MS);
  }

  let listenersWired = false;
  function wireAllEventListeners() {
    if (listenersWired) return;
    listenersWired = true;
    wireEventListeners();
  }

  async function initDashboard() {
    wireAllEventListeners();

    // Check URL Hash for deep linking
    const initialHash = window.location.hash.replace("#", "");
    if (initialHash && $(`#view-${initialHash}`)) {
      state.activeTab = initialHash;
    }

    switchTab(state.activeTab);
    initPeriodicSync();
  }

  // --- Bootstrap on DOM Ready ---
  document.addEventListener("DOMContentLoaded", async () => {
    // CRITICAL: Always wire all event listeners (including Login button) immediately!
    wireAllEventListeners();

    // Check if user already has an active session token
    const isAuthed = await checkAuthSession();
    if (isAuthed) {
      initDashboard();
    }
  });
})();
