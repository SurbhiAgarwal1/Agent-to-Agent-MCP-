// Emergency Command Center UI Client (Part 13 + Step 1B authentication)

const API_BASE = "/api/v1";
const SESSION_KEY = "bdm_session";
const WRITE_ROLES = ["HOSPITAL_STAFF", "ADMIN"];

let session = null; // { token, email, role }
let pollTimer = null;
let authMode = "login"; // "login" | "register"
let toastTimer = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

// Token lives in sessionStorage (cleared when the tab closes). Storage can be
// unavailable (private mode, blocked cookies), so every access is guarded.
function loadSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed && parsed.token && parsed.role) return parsed;
  } catch (_) {
    /* ignore */
  }
  return null;
}

function saveSession(value) {
  session = value;
  try {
    if (value) sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch (_) {
    /* keep the in-memory session */
  }
}

function canWrite() {
  return !!session && WRITE_ROLES.includes(session.role);
}

function showToast(message, isError = false) {
  const toast = $("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = isError ? "toast error" : "toast";
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 4500);
}

// FastAPI returns detail as a string (HTTP errors) or a list (validation errors).
function describeError(body, fallback) {
  if (!body) return fallback;
  const detail = body.detail ?? body.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  }
  return fallback;
}

async function readJson(res) {
  try {
    return await res.json();
  } catch (_) {
    return null;
  }
}

class SessionExpiredError extends Error {}

// All API calls except login/register go through here so the bearer token is
// always attached and an expired/invalid token sends the user back to sign-in.
async function authFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (session && session.token) headers.Authorization = `Bearer ${session.token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    logout("Your session has expired. Please sign in again.");
    throw new SessionExpiredError();
  }
  return res;
}

// ---------------------------------------------------------------------------
// Screens: sign-in vs dashboard
// ---------------------------------------------------------------------------

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

function showAuthScreen(message) {
  stopPolling();
  $("app-content").hidden = true;
  $("user-area").hidden = true;
  $("auth-screen").hidden = false;
  $("polling-status").textContent = "SIGNED OUT";
  $("auth-password").value = "";
  setAuthMode("login");
  setAuthError(message || "");
}

function showApp() {
  $("auth-screen").hidden = true;
  $("app-content").hidden = false;
  $("user-area").hidden = false;
  $("user-email").textContent = session.email;
  $("user-role").textContent = session.role.replace("_", " ");
  $("polling-status").textContent = "LIVE SYNC (5s)";

  // Blood bank staff are read-only: hide the dispatch form entirely.
  const formPanel = document.querySelector(".form-panel");
  if (formPanel) formPanel.hidden = !canWrite();

  loadHospitals();
  fetchRequests();
  stopPolling();
  pollTimer = setInterval(() => {
    if (!document.hidden) fetchRequests();
  }, 5000);
}

function logout(message) {
  saveSession(null);
  const detail = $("plan-detail-content");
  if (detail) {
    detail.innerHTML = '<p class="placeholder-text">Select a request or click "Coordinate" above to view multi-source fulfillment plan.</p>';
  }
  const tbody = $("requests-tbody");
  if (tbody) tbody.innerHTML = "";
  showAuthScreen(message);
}

// ---------------------------------------------------------------------------
// Sign in / register
// ---------------------------------------------------------------------------

function setAuthError(message) {
  const box = $("auth-error");
  box.textContent = message;
  box.hidden = !message;
}

function setAuthMode(mode) {
  authMode = mode;
  const isLogin = mode === "login";
  $("auth-title").textContent = isLogin ? "Sign in" : "Create hospital staff account";
  $("auth-hint").textContent = isLogin
    ? "Use your hospital or blood bank staff account."
    : "Self-registration creates a hospital staff account. Other roles are created by an administrator.";
  $("btn-auth-submit").textContent = isLogin ? "Sign in" : "Register and sign in";
  $("auth-switch-text").textContent = isLogin ? "New hospital staff?" : "Already have an account?";
  $("btn-auth-switch").textContent = isLogin ? "Create an account" : "Sign in";
  $("auth-password").autocomplete = isLogin ? "current-password" : "new-password";
}

async function postJson(path, payload) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return { res, body: await readJson(res) };
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const email = $("auth-email").value.trim();
  const password = $("auth-password").value;
  setAuthError("");

  if (!email || !password) {
    setAuthError("Enter your email and password.");
    return;
  }
  if (password.length < 6) {
    setAuthError("Password must be at least 6 characters.");
    return;
  }

  const submitBtn = $("btn-auth-submit");
  submitBtn.disabled = true;
  try {
    if (authMode === "register") {
      const reg = await postJson("/auth/register", { email, password });
      if (!reg.res.ok) {
        setAuthError(describeError(reg.body, "Registration failed."));
        return;
      }
    }

    const { res, body } = await postJson("/auth/login", { email, password });
    if (!res.ok || !body || !body.access_token) {
      setAuthError(describeError(body, "Sign in failed."));
      return;
    }
    saveSession({ token: body.access_token, email, role: body.role });
    $("auth-password").value = "";
    showApp();
  } catch (err) {
    setAuthError("Cannot reach the server. Check that the backend is running.");
  } finally {
    submitBtn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadHospitals() {
  const select = $("hospital-id");
  if (!select) return;
  try {
    const res = await authFetch("/hospitals");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const hospitals = await res.json();
    select.innerHTML = "";
    if (!hospitals.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No hospitals available";
      select.appendChild(opt);
      return;
    }
    hospitals.forEach((h) => {
      const opt = document.createElement("option");
      opt.value = String(h.hospital_id);
      opt.textContent = `${h.name} (ID #${h.hospital_id})`;
      select.appendChild(opt);
    });
  } catch (err) {
    if (err instanceof SessionExpiredError) return;
    select.innerHTML = '<option value="">Could not load hospitals</option>';
  }
}

async function fetchRequests() {
  try {
    const res = await authFetch("/blood-requests");
    if (!res.ok) return;
    renderRequests(await res.json());
  } catch (err) {
    if (!(err instanceof SessionExpiredError)) console.error("Failed to fetch requests:", err);
  }
}

function renderRequests(requests) {
  const tbody = $("requests-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  requests.forEach((req) => {
    const urgency = String(req.urgency || "");
    const status = String(req.status || "");
    const action = canWrite()
      ? `<button class="btn-action" data-request-id="${Number(req.request_id)}">Coordinate</button>`
      : '<span class="view-only" title="Your role is read-only">View only</span>';

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>#${Number(req.request_id)}</td>
      <td>Hospital #${Number(req.hospital_id)}</td>
      <td><span class="badge blood">${escapeHtml(req.blood_group)}</span></td>
      <td>${Number(req.units_required)}</td>
      <td><span class="badge urgency-${escapeHtml(urgency.toLowerCase())}">${escapeHtml(urgency)}</span></td>
      <td><span class="badge status-${escapeHtml(status.toLowerCase())}">${escapeHtml(status)}</span></td>
      <td>${action}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------------------
// Create request
// ---------------------------------------------------------------------------

async function handleCreateRequest(e) {
  e.preventDefault();
  const hospital_id = parseInt($("hospital-id").value, 10);
  if (Number.isNaN(hospital_id)) {
    showToast("Select a hospital first.", true);
    return;
  }
  const blood_group = $("blood-group").value;
  const units_required = parseInt($("units-required").value, 10);
  const urgency = $("urgency").value;

  const btn = $("btn-submit-request");
  btn.disabled = true;
  try {
    const res = await authFetch("/blood-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hospital_id, blood_group, units_required, urgency }),
    });
    if (res.ok) {
      showToast("Emergency request dispatched.");
      fetchRequests();
    } else {
      const body = await readJson(res);
      showToast(describeError(body, `Could not create request (HTTP ${res.status}).`), true);
    }
  } catch (err) {
    if (!(err instanceof SessionExpiredError)) showToast(`Failed to send request: ${err.message}`, true);
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Coordination
// ---------------------------------------------------------------------------

const AGENT_CARDS = [
  ["card-req-agent", "state-req"],
  ["card-match-agent", "state-match"],
  ["card-loc-agent", "state-loc"],
  ["card-opt-agent", "state-opt"],
  ["card-coord-agent", "state-coord"],
  ["card-notif-agent", "state-notif"],
];

function setAgentState(cardId, stateId, text, className) {
  const card = $(cardId);
  const state = $(stateId);
  if (card) card.className = `agent-card ${className}`;
  if (state) state.innerText = text;
}

function resetAllAgents() {
  AGENT_CARDS.forEach(([cid, sid]) => setAgentState(cid, sid, "Ready", ""));
}

function setPipelinePill(text, className, color) {
  const pill = $("pipeline-status");
  if (!pill) return;
  pill.className = className;
  pill.style.color = color || "";
  pill.innerText = text;
}

async function coordinateRequest(requestId) {
  if (!canWrite()) {
    showToast("Your role is read-only.", true);
    return;
  }
  const detailContainer = $("plan-detail-content");
  detailContainer.innerHTML = `<p>🚀 Coordinating Request #${Number(requestId)} through autonomous multi-agent pipeline...</p>`;
  setPipelinePill("Pipeline Executing...", "status-pill active");

  const running = [
    ["Validating"], ["Searching"], ["Routing"], ["Optimizing"], ["Coordinating"], ["Alerting"],
  ];
  AGENT_CARDS.forEach(([cid, sid], i) => setAgentState(cid, sid, running[i][0], "running"));

  try {
    const res = await authFetch(`/blood-requests/${Number(requestId)}/coordinate`, { method: "POST" });
    const data = await readJson(res);

    if (!res.ok || !data || !data.success) {
      resetAllAgents();
      const reason = describeError(data, `HTTP ${res.status}`);
      const where = data && data.failed_at ? ` at ${escapeHtml(data.failed_at)}` : "";
      setPipelinePill(res.status === 403 ? "Not permitted" : "Halted", "status-pill", "#ef4444");
      detailContainer.innerHTML = `
        <div class="alert error" style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; padding: 1rem; border-radius: 6px;">
          <strong style="color: #ef4444;">Coordination halted${where}:</strong> ${escapeHtml(reason)}
        </div>
      `;
      return;
    }

    setAgentState("card-req-agent", "state-req", "Validated", "done");
    setAgentState("card-match-agent", "state-match", "Matched", "done");
    setAgentState("card-loc-agent", "state-loc", "Routed", "done");
    setAgentState("card-opt-agent", "state-opt", "Optimized", "done");
    setAgentState("card-coord-agent", "state-coord", "Completed", "done");
    setAgentState("card-notif-agent", "state-notif", "Alerted", "done");
    setPipelinePill("Plan Dispatched", "status-pill idle");

    const plan = data.fulfillment_plan;
    let planHtml = `
      <div class="plan-summary" style="margin-bottom: 1rem; padding: 1rem; background: #0f172a; border-radius: 6px; border: 1px solid #334155;">
        <h3 style="margin-top: 0; color: #10b981;">Request #${Number(data.request_id)} — ${escapeHtml(plan.status)}</h3>
        <p><strong>Allocated Units:</strong> ${Number(plan.total_units)} / ${Number(data.requirement.units_required)}</p>
        <p><strong>Requesting Hospital:</strong> ${escapeHtml(data.hospital.name)}</p>
        <p><strong>Active Agents:</strong> RequirementAgent, MatchingAgent, LocationAgent, OptimizationService, CoordinatorAgent, NotificationAgent</p>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Source Type</th>
            <th>Source ID</th>
            <th>Units</th>
            <th>Distance</th>
            <th>ETA</th>
          </tr>
        </thead>
        <tbody>
    `;

    plan.plan.forEach((item) => {
      planHtml += `
        <tr>
          <td><span class="badge blood">${escapeHtml(item.source_type)}</span></td>
          <td>#${Number(item.source_id)} ${escapeHtml(item.name || "")}</td>
          <td><strong style="color: #10b981;">${Number(item.units)}</strong></td>
          <td>${escapeHtml(item.distance_km)} km</td>
          <td>${escapeHtml(item.estimated_time || "~")}</td>
        </tr>
      `;
    });

    planHtml += "</tbody></table>";
    detailContainer.innerHTML = planHtml;
    fetchRequests();
  } catch (err) {
    if (err instanceof SessionExpiredError) return;
    resetAllAgents();
    detailContainer.innerHTML = `<p class="error" style="color: #ef4444;">Coordination failed: ${escapeHtml(err.message)}</p>`;
  }
}

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------

function setupEventListeners() {
  $("auth-form").addEventListener("submit", handleAuthSubmit);
  $("btn-auth-switch").addEventListener("click", () => {
    setAuthError("");
    setAuthMode(authMode === "login" ? "register" : "login");
  });
  $("btn-logout").addEventListener("click", () => logout(""));

  const form = $("create-request-form");
  if (form) form.addEventListener("submit", handleCreateRequest);

  const refreshBtn = $("btn-refresh");
  if (refreshBtn) refreshBtn.addEventListener("click", fetchRequests);

  // Event delegation instead of inline onclick handlers.
  $("requests-tbody").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-request-id]");
    if (btn) coordinateRequest(btn.dataset.requestId);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  session = loadSession();
  if (session) showApp();
  else showAuthScreen("");
});
