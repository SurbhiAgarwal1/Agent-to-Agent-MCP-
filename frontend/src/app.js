// Emergency Command Center UI Client (Part 13)

const API_BASE = "/api/v1";

document.addEventListener("DOMContentLoaded", () => {
  fetchRequests();
  setupEventListeners();
  // Poll backend every 5 seconds for live status updates
  setInterval(fetchRequests, 5000);
});

function setupEventListeners() {
  const form = document.getElementById("create-request-form");
  if (form) {
    form.addEventListener("submit", handleCreateRequest);
  }
  const refreshBtn = document.getElementById("btn-refresh");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", fetchRequests);
  }
}

async function fetchRequests() {
  try {
    const res = await fetch(`${API_BASE}/blood-requests`);
    if (!res.ok) return;
    const requests = await res.json();
    renderRequests(requests);
  } catch (err) {
    console.error("Failed to fetch requests:", err);
  }
}

function renderRequests(requests) {
  const tbody = document.getElementById("requests-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  requests.forEach((req) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>#${req.request_id}</td>
      <td>Hospital #${req.hospital_id}</td>
      <td><span class="badge blood">${req.blood_group}</span></td>
      <td>${req.units_required}</td>
      <td><span class="badge urgency-${req.urgency.toLowerCase()}">${req.urgency}</span></td>
      <td><span class="badge status-${req.status.toLowerCase()}">${req.status}</span></td>
      <td>
        <button class="btn-action" onclick="coordinateRequest(${req.request_id})">Coordinate</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function handleCreateRequest(e) {
  e.preventDefault();
  const hospital_id = parseInt(document.getElementById("hospital-id").value, 10);
  const blood_group = document.getElementById("blood-group").value;
  const units_required = parseInt(document.getElementById("units-required").value, 10);
  const urgency = document.getElementById("urgency").value;

  try {
    const res = await fetch(`${API_BASE}/blood-requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hospital_id, blood_group, units_required, urgency }),
    });
    if (res.ok) {
      alert("Emergency request dispatched successfully!");
      fetchRequests();
    } else {
      const err = await res.json();
      alert(`Error creating request: ${JSON.stringify(err.detail || err)}`);
    }
  } catch (err) {
    alert(`Failed to send request: ${err.message}`);
  }
}

function setAgentState(cardId, stateId, text, className) {
  const card = document.getElementById(cardId);
  const state = document.getElementById(stateId);
  if (card) card.className = `agent-card ${className}`;
  if (state) state.innerText = text;
}

function resetAllAgents() {
  const agents = [
    ["card-req-agent", "state-req"],
    ["card-match-agent", "state-match"],
    ["card-loc-agent", "state-loc"],
    ["card-opt-agent", "state-opt"],
    ["card-coord-agent", "state-coord"],
    ["card-notif-agent", "state-notif"],
  ];
  agents.forEach(([cid, sid]) => setAgentState(cid, sid, "Ready", ""));
}

async function coordinateRequest(requestId) {
  const detailContainer = document.getElementById("plan-detail-content");
  detailContainer.innerHTML = `<p>🚀 Coordinating Request #${requestId} through autonomous multi-agent pipeline...</p>`;

  const pipelinePill = document.getElementById("pipeline-status");
  if (pipelinePill) {
    pipelinePill.className = "status-pill active";
    pipelinePill.innerText = "Pipeline Executing...";
  }

  // Visual execution simulation across agents
  setAgentState("card-req-agent", "state-req", "Validating", "running");
  setAgentState("card-match-agent", "state-match", "Searching", "running");
  setAgentState("card-loc-agent", "state-loc", "Routing", "running");
  setAgentState("card-opt-agent", "state-opt", "Optimizing", "running");
  setAgentState("card-coord-agent", "state-coord", "Coordinating", "running");
  setAgentState("card-notif-agent", "state-notif", "Alerting", "running");

  try {
    const res = await fetch(`${API_BASE}/blood-requests/${requestId}/coordinate`, {
      method: "POST",
    });
    const data = await res.json();

    if (!data.success) {
      if (pipelinePill) {
        pipelinePill.className = "status-pill";
        pipelinePill.style.color = "#ef4444";
        pipelinePill.innerText = `Halted at ${data.failed_at}`;
      }
      detailContainer.innerHTML = `
        <div class="alert error" style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; padding: 1rem; border-radius: 6px;">
          <strong style="color: #ef4444;">Coordination Halted at ${data.failed_at}:</strong> ${data.error}
        </div>
      `;
      return;
    }

    // Mark all agents completed
    setAgentState("card-req-agent", "state-req", "Validated", "done");
    setAgentState("card-match-agent", "state-match", "Matched", "done");
    setAgentState("card-loc-agent", "state-loc", "Routed", "done");
    setAgentState("card-opt-agent", "state-opt", "Optimized", "done");
    setAgentState("card-coord-agent", "state-coord", "Completed", "done");
    setAgentState("card-notif-agent", "state-notif", "Alerted", "done");

    if (pipelinePill) {
      pipelinePill.className = "status-pill idle";
      pipelinePill.innerText = "Plan Dispatched";
    }

    const plan = data.fulfillment_plan;
    let planHtml = `
      <div class="plan-summary" style="margin-bottom: 1rem; padding: 1rem; background: #0f172a; border-radius: 6px; border: 1px solid #334155;">
        <h3 style="margin-top: 0; color: #10b981;">Request #${data.request_id} — ${plan.status}</h3>
        <p><strong>Allocated Units:</strong> ${plan.total_units} / ${data.requirement.units_required}</p>
        <p><strong>Requesting Hospital:</strong> ${data.hospital.name}</p>
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
          <td><span class="badge blood">${item.source_type}</span></td>
          <td>#${item.source_id} ${item.name || ""}</td>
          <td><strong style="color: #10b981;">${item.units}</strong></td>
          <td>${item.distance_km} km</td>
          <td>${item.estimated_time || "~"}</td>
        </tr>
      `;
    });

    planHtml += `</tbody></table>`;
    detailContainer.innerHTML = planHtml;
    fetchRequests();
  } catch (err) {
    detailContainer.innerHTML = `<p class="error" style="color: #ef4444;">Coordination failed: ${err.message}</p>`;
    resetAllAgents();
  }
}

// Attach coordinateRequest to window for inline onclick
window.coordinateRequest = coordinateRequest;
