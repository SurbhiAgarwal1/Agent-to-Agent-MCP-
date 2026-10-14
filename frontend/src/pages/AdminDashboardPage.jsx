import React from 'react';
import { Link } from 'react-router-dom';
import Card from '../components/common/Card';

export default function AdminDashboardPage() {
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
        {/* User & Membership Management Card */}
        <Card title="User & Membership Management">
          <p className="text-secondary" style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>
            Provision staff accounts, grant hospital or blood bank facility memberships, and revoke active memberships.
          </p>
          <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.5rem' }}>
            <Link to="/admin/memberships" className="btn btn-primary btn-sm">
              Manage Memberships &rarr;
            </Link>
          </div>
        </Card>

        {/* Security Audit Trail Card */}
        <Card title="Security & Operations Audit Trail">
          <p className="text-secondary" style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>
            Inspect real-time audit logs of all critical actions: logins, blood request creation, coordination executions,
            and match fulfillment.
          </p>
          <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.5rem' }}>
            <Link to="/admin/audit-logs" className="btn btn-primary btn-sm">
              View Audit Logs &rarr;
            </Link>
          </div>
        </Card>
      </div>

      {/* Observability Section */}
      <Card title="Observability & Telemetry Infrastructure">
        <p className="text-secondary" style={{ fontSize: '0.875rem', marginBottom: '1.25rem', lineHeight: 1.6 }}>
          Observability metrics and distributed tracing are collected via OpenTelemetry and decoupled from regular users.
          As an Administrator, you can monitor system health directly via the dedicated host ports:
        </p>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '1rem',
          }}
        >
          <div
            style={{
              padding: '1rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--color-bg)',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Grafana Dashboards</div>
            <div className="text-secondary" style={{ fontSize: '0.8125rem', marginBottom: '0.75rem' }}>
              Coordinator and agent pipeline metrics
            </div>
            <a
              href="http://localhost:3001"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-outline btn-sm"
            >
              Open Grafana (Port 3001) &nearr;
            </a>
          </div>

          <div
            style={{
              padding: '1rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--color-bg)',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Jaeger Tracing UI</div>
            <div className="text-secondary" style={{ fontSize: '0.8125rem', marginBottom: '0.75rem' }}>
              Distributed spans across A2A agents and MCP
            </div>
            <a
              href="http://localhost:16686"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-outline btn-sm"
            >
              Open Jaeger (Port 16686) &nearr;
            </a>
          </div>

          <div
            style={{
              padding: '1rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--color-bg)',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Prometheus Server</div>
            <div className="text-secondary" style={{ fontSize: '0.8125rem', marginBottom: '0.75rem' }}>
              Raw metrics scraper and alert rules
            </div>
            <a
              href="http://localhost:9090"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-outline btn-sm"
            >
              Open Prometheus (Port 9090) &nearr;
            </a>
          </div>
        </div>
      </Card>
    </div>
  );
}
