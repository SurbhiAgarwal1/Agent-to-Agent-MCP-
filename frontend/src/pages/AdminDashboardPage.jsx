import React from 'react';
import { Link } from 'react-router-dom';
import Card from '../components/common/Card';

export default function AdminDashboardPage() {
  const telemetryLinks = [
    ['Grafana', import.meta.env.VITE_GRAFANA_URL, 'Coordinator and agent pipeline metrics'],
    ['Jaeger', import.meta.env.VITE_JAEGER_URL, 'Distributed traces across A2A agents and MCP'],
    ['Prometheus', import.meta.env.VITE_PROMETHEUS_URL, 'Metrics collection and alert rules'],
  ];

  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--color-text-main)' }}>
          System Administration Console
        </h1>
        <p className="text-secondary" style={{ marginTop: '0.25rem', fontSize: '0.9375rem' }}>
          Platform governance, facility memberships, security auditing, and telemetry links
        </p>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '1.5rem',
          marginBottom: '2rem',
        }}
      >
        <Card title="User & Membership Management">
          <p className="text-secondary" style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>
            Provision staff accounts, grant hospital or blood bank facility memberships, and revoke active memberships.
          </p>
          <div style={{ marginTop: '1.25rem' }}>
            <Link to="/admin/memberships" className="btn btn-primary btn-sm">
              Manage Memberships &rarr;
            </Link>
          </div>
        </Card>

        <Card title="Security & Operations Audit Trail">
          <p className="text-secondary" style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>
            Inspect audit logs for critical actions including logins, blood request creation, coordination executions,
            and match fulfillment.
          </p>
          <div style={{ marginTop: '1.25rem' }}>
            <Link to="/admin/audit-logs" className="btn btn-primary btn-sm">
              View Audit Logs &rarr;
            </Link>
          </div>
        </Card>
      </div>

      <Card title="Agent Network & Observability">
        <p className="text-secondary" style={{ fontSize: '0.875rem', marginBottom: '1.25rem', lineHeight: 1.6 }}>
          Technical operations for the Coordinator Agent, A2A communication, MCP tools, LLM reasoning, metrics, and distributed tracing.
        </p>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '1rem',
          }}
        >
          {telemetryLinks.map(([name, href, description]) => {
            return (
              <div
                key={name}
                style={{
                  padding: '1rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  backgroundColor: 'var(--color-bg)',
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{name}</div>
                <div className="text-secondary" style={{ fontSize: '0.8125rem', marginBottom: '0.75rem' }}>
                  {description}
                </div>

                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-outline btn-sm"
                  >
                    Open {name} ↗
                  </a>
                ) : (
                  <span className="text-secondary" style={{ fontSize: '0.875rem' }}>
                    Not configured
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
