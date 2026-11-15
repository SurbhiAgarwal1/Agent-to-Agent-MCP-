import React, { useState } from 'react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import BloodGroupBadge from '../components/common/BloodGroupBadge';
import usePolling from '../hooks/usePolling';
import {
  getPortalMe, listDonorNotifications, respondDonorNotification, setDonorAvailability,
} from '../api/portal';

export default function DonorDashboardPage() {
  const me = usePolling(getPortalMe, 15000);
  const alerts = usePolling(listDonorNotifications, 5000);
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const profile = me.data?.profile;
  const items = alerts.data?.items || [];
  const pending = items.filter((n) => n.response_status === 'pending');
  const history = items.filter((n) => n.response_status !== 'pending');

  const answer = async (id, response) => {
    setBusy(id); setError(null); setMessage(null);
    try {
      await respondDonorNotification(id, response);
      setMessage(response === 'accepted' ? 'Thank you! The hospital has been told you are coming.' : 'Response recorded.');
      await alerts.refresh();
    } catch (err) {
      setError(err.message || 'Could not send your answer.');
    } finally {
      setBusy(null);
    }
  };

  const toggleAvailability = async () => {
    setError(null);
    try {
      await setDonorAvailability(!profile.available);
      await me.refresh();
    } catch (err) {
      setError(err.message || 'Could not update availability.');
    }
  };

  if (me.loading && !me.data) return <LoadingSpinner message="Loading your donor page..." />;

  return (
    <div>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>Donor dashboard</h1>
      <p className="text-secondary" style={{ marginBottom: '1.5rem' }}>
        Blood requests near you appear here as soon as a hospital needs your blood group.
      </p>

      {error && <div className="alert alert-error" role="alert" style={{ marginBottom: '1rem' }}>{error}</div>}
      {message && <div className="alert alert-success" style={{ marginBottom: '1rem' }}>{message}</div>}

      {profile && (
        <Card title={profile.name} subtitle={profile.city}
          action={<Button variant={profile.available ? 'outline' : 'primary'} onClick={toggleAvailability}>
            {profile.available ? 'Pause alerts' : 'Mark me available'}</Button>}>
          <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <BloodGroupBadge group={profile.blood_group} />
            <span>Status: <strong>{profile.available ? 'Available to donate' : 'Not available'}</strong></span>
            <span>Donations: <strong>{profile.donation_count ?? 0}</strong></span>
          </div>
        </Card>
      )}

      <div style={{ height: '1rem' }} />
      <Card title={`Requests for you (${pending.length})`}>
        {pending.length === 0 ? (
          <EmptyState title="No open requests" message="You will see a request here the moment a hospital needs you." />
        ) : pending.map((n) => (
          <div key={n.id} data-testid="donor-alert" style={{ padding: '0.75rem 0', borderBottom: '1px solid var(--color-border)' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <BloodGroupBadge group={n.blood_group} />
              <strong>{n.hospital_name || `Request #${n.blood_request_id}`}</strong>
              {n.urgency && <span className="badge badge-neutral">{n.urgency}</span>}
            </div>
            <p className="text-secondary" style={{ margin: '0.25rem 0 0.5rem' }}>
              {n.hospital_address || ''}{n.units_needed ? ` · ${n.units_needed} unit(s) needed` : ''}
            </p>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <Button variant="primary" loading={busy === n.id} onClick={() => answer(n.id, 'accepted')}>Accept</Button>
              <Button variant="outline" disabled={busy === n.id} onClick={() => answer(n.id, 'declined')}>Decline</Button>
            </div>
          </div>
        ))}
      </Card>

      <div style={{ height: '1rem' }} />
      <Card title="History">
        {history.length === 0 ? <p className="text-secondary">Nothing yet.</p> : (
          <table className="table"><thead><tr><th>When</th><th>Request</th><th>Group</th><th>Your answer</th></tr></thead>
            <tbody>{history.map((n) => (
              <tr key={n.id}><td>{n.attempted_at ? new Date(n.attempted_at).toLocaleString() : '—'}</td>
                <td>#{n.blood_request_id}</td><td>{n.blood_group}</td><td>{n.response_status}</td></tr>
            ))}</tbody></table>
        )}
      </Card>
    </div>
  );
}
