import React from 'react';
import { Link } from 'react-router-dom';
import Card from '../common/Card';
import Button from '../common/Button';
import usePolling from '../../hooks/usePolling';
import { listHospitalAlerts, markHospitalAlertRead } from '../../api/portal';

export default function HospitalAlertsPanel() {
  const { data, error, refresh } = usePolling(listHospitalAlerts, 5000);
  const items = data?.items || [];
  const read = async (id) => { try { await markHospitalAlertRead(id); } finally { await refresh(); } };
  return (
    <Card title={`Responses to your requests${data?.unread ? ` (${data.unread} new)` : ''}`}>
      {error && !data && <p className="text-secondary">{error}</p>}
      {data && items.length === 0 && <p className="text-secondary">No donor or blood bank has answered yet.</p>}
      {items.map((a) => (
        <div key={a.alert_id} data-testid="hospital-alert"
          style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', padding: '0.6rem 0', borderBottom: '1px solid var(--color-border)', fontWeight: a.read ? 400 : 600 }}>
          <div>
            <div>{a.message}</div>
            <small className="text-secondary">
              <Link to={`/blood-requests/${a.request_id}`}>Request #{a.request_id}</Link> · {a.created_at ? new Date(a.created_at).toLocaleString() : ''}
            </small>
          </div>
          {!a.read && <Button size="sm" variant="outline" onClick={() => read(a.alert_id)}>Mark read</Button>}
        </div>
      ))}
    </Card>
  );
}
