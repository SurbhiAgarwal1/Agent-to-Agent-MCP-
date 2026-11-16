import React from 'react';
import { Link } from 'react-router-dom';
import usePolling from '../hooks/usePolling';
import { getRequestSummary } from '../api/admin';
import { PageHeader, StatTile, Panel, Donut, Line, StatusPill, fmtWhen } from '../components/bc';

const OPEN = ['PENDING', 'PROCESSING', 'PARTIALLY_FULFILLED'];

export default function AdminHomePage() {
  const { data, error } = usePolling(getRequestSummary, 10000);
  if (!data) return <div><PageHeader title="Admin Dashboard" subtitle="Overview of the blood network, requests and system activity." />{error ? <div className="alert alert-error" role="alert">{error}</div> : <p>Loading…</p>}</div>;
  const recent = data.recent || [];
  const urgent = recent.filter((r) => ['CRITICAL', 'HIGH'].includes(r.urgency) && OPEN.includes(r.status)).length;
  const pending = recent.filter((r) => OPEN.includes(r.status)).length;
  const fulfilled = data.totals.fulfilled_requests;
  const days = [...Array(7)].map((_, i) => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - (6 - i)); return d; });
  const points = days.map((d) => ({
    label: d.toLocaleDateString([], { month: 'short', day: 'numeric' }),
    value: recent.filter((r) => r.created_at && new Date(r.created_at).toDateString() === d.toDateString()).length,
  }));
  return (
    <div>
      <PageHeader title="Admin Dashboard" subtitle="Overview of the blood network, requests and system activity.">
        <Link to="/admin/agents" className="bc-btn ghost">Agent Console</Link>
      </PageHeader>
      <div className="bc-stats">
        <StatTile icon="📝" value={data.totals.requests} label="Total Requests" tone="lav" />
        <StatTile icon="⏳" value={pending} label="Pending" tone="peach" />
        <StatTile icon="✅" value={fulfilled} label="Fulfilled" tone="mint" />
        <StatTile icon="❤" value={urgent} label="Urgent" tone="rose" />
      </div>
      <div className="bc-grid two">
        <Panel title="Blood Requests (Last 7 Days)"><Line points={points} /></Panel>
        <Panel title="Request Status">
          <Donut centre={data.totals.requests} caption="Requests" segments={[
            { label: 'Fulfilled', value: fulfilled, color: '#22a05a' },
            { label: 'Pending', value: Math.max(0, pending - urgent), color: '#f0b429' },
            { label: 'Urgent', value: urgent, color: '#e04b4b' }]} />
        </Panel>
      </div>
      <Panel title="Recent Blood Requests" action={<Link to="/blood-requests" className="bc-btn ghost sm">All requests</Link>}>
        {recent.length === 0 ? <p>No requests yet. They appear here as soon as hospital staff make one.</p> : (
          <table className="bc-table">
            <thead><tr><th>#</th><th>Hospital</th><th>Blood Group</th><th>Units</th><th>Allocated</th><th>Requested At</th><th>Status</th></tr></thead>
            <tbody>{recent.slice(0, 8).map((r) => (
              <tr key={r.request_id}><td>#{r.request_id}</td><td>{r.hospital_name}</td><td><strong>{r.blood_group}</strong></td><td>{r.units_requested}</td>
                <td>{r.units_secured}</td><td>{fmtWhen(r.created_at)}</td><td><StatusPill status={r.status} /></td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
      <div style={{ height: '1rem' }} />
      <Panel title="Requests by hospital">
        {data.hospitals.length === 0 ? <p>No hospitals have requested blood yet.</p> : (
          <table className="bc-table">
            <thead><tr><th>Hospital</th><th>Requests</th><th>Units requested</th><th>Units allocated</th><th>Fulfilled</th></tr></thead>
            <tbody>{data.hospitals.map((h) => (
              <tr key={h.hospital_id}><td>{h.hospital_name}</td><td>{h.requests}</td><td>{h.units_requested}</td><td>{h.units_secured}</td><td>{h.fulfilled_requests}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
