import React from "react";
import { Card } from "../common/Card.jsx";
import { StatusBadge } from "../common/StatusBadge.jsx";
import { BloodGroupBadge } from "../common/BloodGroupBadge.jsx";

export function CoordinationWorkflow({ result, loading, execution, isRunning }) {
  const data = result || execution;
  const isLoading = loading || isRunning;

  if (isLoading) {
    return (
      <Card title="A2A Coordination Workflow" subtitle="Autonomous Agent Execution in progress">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "1rem" }}>
          {[
            { step: "Agent 1", name: "Requirement Agent", status: "Validating criteria..." },
            { step: "Agent 2", name: "Matching Agent", status: "Searching compatibility..." },
            { step: "Agent 3", name: "Location Agent", status: "Routing spatial distance..." },
            { step: "Engine 4", name: "Optimization Engine", status: "Allocating quota..." },
            { step: "Agent 5", name: "Notification Agent", status: "Preparing dispatches..." },
          ].map((agent, i) => (
            <div
              key={i}
              style={{
                padding: "1rem",
                borderRadius: "var(--radius-md)",
                backgroundColor: "var(--color-bg)",
                border: "1px solid var(--color-primary-border)",
                animation: "pulse 1.5s infinite",
              }}
            >
              <div style={{ fontSize: "0.7rem", fontWeight: 700, color: "var(--color-primary)" }}>
                {agent.step}
              </div>
              <div style={{ fontSize: "0.875rem", fontWeight: 600, margin: "0.25rem 0" }}>
                {agent.name}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                {agent.status}
              </div>
            </div>
          ))}
        </div>
        <style>{`
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
          }
        `}</style>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card title="A2A Coordination Workflow" subtitle="Multi-Agent Execution Pipeline">
        <p className="text-secondary" style={{ fontSize: "0.875rem", margin: 0 }}>
          The Coordinator Agent manages Requirement, Matching, Location, and Notification agents across the distributed protocol network. Run coordination to trigger live multi-agent execution.
        </p>
      </Card>
    );
  }

  const plan = data.fulfillment_plan;
  const history = data.state_history || [];
  const notifications = data.notifications?.notifications || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Visual Agent Progression Pipeline */}
      <Card title="A2A Coordination Workflow" subtitle={`Workflow State: ${data.current_state || 'COMPLETED'}`}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem" }}>
          {[
            {
              step: "Agent 1",
              name: "Requirement Agent",
              desc: data.requirement
                ? `Validated ${data.requirement.units_required} units of ${data.requirement.blood_group}`
                : "Awaiting validation",
              done: !!data.requirement,
            },
            {
              step: "Agent 2",
              name: "Matching Agent",
              desc: `${data.candidates_count ?? 0} compatible candidates discovered`,
              done: (data.candidates_count ?? 0) > 0,
            },
            {
              step: "Agent 3",
              name: "Location Agent",
              desc: "Road distance & travel ETA computed",
              done: !!data.ranked_matches?.length,
            },
            {
              step: "Engine 4",
              name: "Optimization Engine",
              desc: plan ? `Fulfillment: ${plan.status} (${plan.total_units} units)` : "Awaiting allocation",
              done: !!plan,
            },
            {
              step: "Agent 5",
              name: "Notification Agent",
              desc: notifications.length
                ? `${notifications.length} alerts dispatched`
                : "Alerts routed upon hold",
              done: !!data.notifications?.success,
            },
          ].map((agent, i) => (
            <div
              key={i}
              style={{
                padding: "0.85rem",
                borderRadius: "var(--radius-md)",
                backgroundColor: agent.done ? "var(--color-surface)" : "var(--color-bg)",
                border: `1px solid ${agent.done ? "var(--color-success-border)" : "var(--color-border)"}`,
                boxShadow: agent.done ? "var(--shadow-sm)" : "none",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  color: agent.done ? "var(--color-success)" : "var(--color-text-muted)",
                }}
              >
                <span>{agent.step}</span>
                <span>{agent.done ? "✓ Complete" : "Pending"}</span>
              </div>
              <div style={{ fontSize: "0.875rem", fontWeight: 600, margin: "0.3rem 0 0.15rem" }}>
                {agent.name}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                {agent.desc}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Fulfillment Plan Summary */}
      {plan && (
        <Card
          title="⚡ Coordinator Multi-Source Fulfillment Plan"
          subtitle={`Plan Status: ${plan.status} — ${plan.total_units} unit(s) reserved across sources`}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: "1rem",
              marginBottom: "1.25rem",
              padding: "0.85rem",
              backgroundColor: "var(--color-bg)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
            }}
          >
            <div>
              <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>Allocated Units</span>
              <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--color-primary)" }}>
                {plan.total_units}
              </p>
            </div>
            <div>
              <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>Blood Banks Used</span>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>
                {plan.details?.blood_banks_used ?? 0}
              </p>
            </div>
            <div>
              <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>Donors Mobilized</span>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>
                {plan.details?.donors_used ?? 0}
              </p>
            </div>
            <div>
              <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>Unfulfilled Shortage</span>
              <p
                style={{
                  fontSize: "1.25rem",
                  fontWeight: 600,
                  color: (plan.details?.units_shortage ?? 0) > 0 ? "var(--color-danger)" : "var(--color-success)",
                }}
              >
                {plan.details?.units_shortage ?? 0}
              </p>
            </div>
          </div>

          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Source Type</th>
                  <th>Source ID & Details</th>
                  <th>Blood Group</th>
                  <th>Allocated Units</th>
                  <th>Distance (km)</th>
                  <th>ETA</th>
                </tr>
              </thead>
              <tbody>
                {plan.plan?.map((item, idx) => (
                  <tr key={idx}>
                    <td>
                      <span className="badge" style={{ backgroundColor: "#f1f5f9", color: "#334155" }}>
                        {item.source_type}
                      </span>
                    </td>
                    <td>
                      <strong>#{item.source_id}</strong> {item.name || ""}
                    </td>
                    <td>
                      <BloodGroupBadge bloodGroup={item.blood_group} />
                    </td>
                    <td>
                      <strong style={{ color: "var(--color-primary)" }}>{item.units}</strong>
                    </td>
                    <td>{item.distance_km} km</td>
                    <td>{item.estimated_time || "~"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* State Machine Transition Timeline */}
      {history.length > 0 && (
        <Card title="📜 Coordinator State Machine Transitions" subtitle="Deterministic lifecycle progression">
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {history.map((h, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.75rem",
                  fontSize: "0.875rem",
                  paddingBottom: "0.5rem",
                  borderBottom: idx === history.length - 1 ? "none" : "1px solid var(--color-border-subtle)",
                }}
              >
                <StatusBadge status={h.state} />
                <div style={{ flex: 1 }}>
                  <p style={{ color: "var(--color-text-primary)", fontWeight: 500 }}>{h.detail}</p>
                  <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                    {new Date(h.timestamp).toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

export default CoordinationWorkflow;
