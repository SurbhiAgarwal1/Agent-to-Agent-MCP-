import React from 'react';
import Card from '../common/Card';
import usePolling from '../../hooks/usePolling';
import { getRequestOrder } from '../../api/portal';

const TONE = {
  confirmed: { bg: '#ecfdf5', border: '#86efac', fg: '#166534', icon: '✓' },
  partial: { bg: '#fffbeb', border: '#fcd34d', fg: '#92400e', icon: '…' },
  waiting: { bg: '#eff6ff', border: '#93c5fd', fg: '#1e40af', icon: '…' },
  declined: { bg: '#fef2f2', border: '#fca5a5', fg: '#991b1b', icon: '!' },
  none: { bg: '#fffbeb', border: '#fcd34d', fg: '#92400e', icon: '!' },
  cancelled: { bg: '#f1f5f9', border: '#cbd5e1', fg: '#475569', icon: '–' },
  not_placed: { bg: '#f8fafc', border: '#e2e8f0', fg: '#475569', icon: '○' },
};
const STATE = { confirmed: 'Confirmed', waiting: 'Waiting', declined: 'Declined' };

function clock(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function OrderStatusPanel({ requestId }) {
  const { data, error } = usePolling(() => getRequestOrder(requestId), 5000, [requestId]);
  if (error && !data) return null;
  if (!data) return null;
  const tone = TONE[data.stage] || TONE.not_placed;
  const arrival = clock(data.expected_arrival_at);
  return (
    <Card title="Order status" subtitle={data.placed ? `Placed at ${clock(data.placed_at) || ''}`.trim() : 'Not placed yet'}>
      <div data-testid="order-headline" style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start', padding: '0.9rem 1rem',
        borderRadius: 10, background: tone.bg, border: `1px solid ${tone.border}`, color: tone.fg, marginBottom: '1rem' }}>
        <span style={{ fontWeight: 800, fontSize: '1.2rem' }}>{tone.icon}</span>
        <div>
          <div style={{ fontWeight: 700 }}>{data.headline}</div>
          {data.stage === 'confirmed' && data.eta_minutes ? (
            <div style={{ marginTop: 4 }}>Delivery in about <strong>{data.eta_minutes} min</strong>{arrival ? <> (around <strong>{arrival}</strong>)</> : null}</div>
          ) : null}
          {data.stage !== 'confirmed' && data.placed && data.nearest_eta_minutes ? (
            <div style={{ marginTop: 4 }}>Once confirmed, delivery from the nearest source takes about <strong>{data.nearest_eta_minutes} min</strong>.</div>
          ) : null}
        </div>
      </div>
      {data.placed && (
        <p style={{ fontWeight: 600 }}>{data.units_confirmed} of {data.units_required} unit(s) of {data.blood_group} confirmed for {data.hospital_name}</p>
      )}
      {data.placed && data.sources.length > 0 && (
        <table className="table">
          <thead><tr><th>Source</th><th>Status</th><th>Units</th><th>Distance</th><th>Travel time</th></tr></thead>
          <tbody>
            {data.sources.map((s) => (
              <tr key={`${s.source_type}-${s.source_id}-${s.notification_id}`}>
                <td>{s.name}</td>
                <td>{STATE[s.state] || s.state}</td>
                <td>{s.units ?? '—'}</td>
                <td>{s.distance_km != null ? `${s.distance_km} km` : '—'}</td>
                <td>{s.eta_minutes != null ? `~${s.eta_minutes} min` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data.placed && <small className="text-secondary">{data.eta_note}</small>}
    </Card>
  );
}
