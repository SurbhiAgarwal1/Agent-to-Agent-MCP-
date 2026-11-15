import React from 'react';
import Card from '../common/Card';
import usePolling from '../../hooks/usePolling';
import { getRequestResponses } from '../../api/portal';

const LABEL = {
  accepted: 'Accepted', partially_available: 'Partially available', rejected: 'Declined',
  declined: 'Declined', unavailable: 'Unavailable', pending: 'Waiting',
};

export default function ResponsesPanel({ requestId }) {
  const { data, error } = usePolling(() => getRequestResponses(requestId), 5000, [requestId]);
  if (error && !data) return <Card title="Responses"><p className="text-secondary">{error}</p></Card>;
  if (!data) return null;
  const pct = Math.min(100, Math.round((data.confirmed_units / Math.max(1, data.units_required)) * 100));
  const c = data.counts || {};
  return (
    <Card title="Responses from blood banks and donors"
      subtitle={`${c.notified || 0} notified · ${c.pending || 0} waiting · ${(c.accepted || 0) + (c.partially_available || 0)} accepted · ${c.declined_or_unavailable || 0} declined`}>
      <p data-testid="confirmed-line" style={{ fontWeight: 600 }}>
        {data.confirmed_units} of {data.units_required} unit(s) confirmed{data.is_covered ? ' — fully covered' : ''}
      </p>
      <div style={{ height: 8, background: 'var(--color-border)', borderRadius: 4, marginBottom: '1rem' }}>
        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 4, background: data.is_covered ? '#15803d' : '#b45309' }} />
      </div>
      {(data.responses || []).length === 0 ? <p className="text-secondary">No one has been notified yet.</p> : (
        <table className="table">
          <thead><tr><th>From</th><th>Answer</th><th>Units</th><th>Note</th></tr></thead>
          <tbody>
            {data.responses.map((r) => (
              <tr key={`${r.source_type}-${r.notification_id}`}>
                <td>{r.source_name || `${r.source_type === 'DONOR' ? 'Donor' : 'Blood bank'} #${r.source_id}`}</td>
                <td>{LABEL[r.response_status] || r.response_status}</td>
                <td>{r.units ?? '—'}</td>
                <td>{r.reason || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(data.warnings || []).length > 0 && <small className="text-secondary">Some sources could not be reached.</small>}
    </Card>
  );
}
