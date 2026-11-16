import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import LoadingSpinner from '../components/common/LoadingSpinner';
import usePolling from '../hooks/usePolling';
import { getPortalMe, listDonorNotifications, respondDonorNotification, setDonorAvailability } from '../api/portal';
import { PageHeader, StatTile, Panel, UrgencyPill, fmtWhen } from '../components/bc';

export function useDonor() {
  const me = usePolling(getPortalMe, 15000);
  const alerts = usePolling(listDonorNotifications, 5000);
  const items = alerts.data?.items || [];
  return { me, alerts, profile: me.data?.profile, items,
    pending: items.filter((n) => n.response_status === 'pending'),
    history: items.filter((n) => n.response_status !== 'pending') };
}

export default function DonorDashboardPage() {
  const d = useDonor();
  const [error, setError] = useState(null);
  const p = d.profile;
  const toggle = async () => {
    setError(null);
    try { await setDonorAvailability(!p.available); await d.me.refresh(); } catch (err) { setError(err.message || 'Could not update availability.'); }
  };
  if (d.me.loading && !d.me.data) return <LoadingSpinner message="Loading your donor page..." />;
  const accepted = d.history.filter((n) => n.response_status === 'accepted').length;
  return (
    <div>
      <PageHeader title={`Welcome, ${(p?.name || 'donor').split(' ')[0]}! 👋`} subtitle="Your contribution saves lives.">
        {p && <button type="button" className="bc-btn ghost" onClick={toggle}>{p.available ? 'Pause alerts' : 'Resume alerts'}</button>}
      </PageHeader>
      {(error || d.me.error) && <div className="alert alert-error" role="alert">{error || d.me.error}</div>}
      {p && (
        <div className="bc-stats">
          <StatTile icon="🩸" value={p.blood_group} label="Your Blood Group" tone="lav" />
          <StatTile icon="🏅" value={p.donation_count ?? 0} label="Total Donations" tone="peach" />
          <StatTile icon="📥" value={d.pending.length} label="Open Requests" tone="rose" />
          <StatTile icon={p.available ? '✅' : '⏸'} value={p.available ? 'Eligible' : 'Paused'} label="Available to donate" tone="mint" />
        </div>
      )}
      <div className="bc-grid two">
        <Panel title={`Requests for you (${d.pending.length})`} action={<Link to="/donor/notifications" className="bc-btn ghost sm">Open notifications</Link>}>
          {d.pending.length === 0 ? <p>No open requests. You will see a request here the moment a hospital needs you.</p> : d.pending.slice(0, 3).map((n) => (
            <div key={n.id} className="bc-row"><div className="ico">🩸</div>
              <div className="grow"><b>{n.hospital_name || `Request #${n.blood_request_id}`}</b><span>needs {n.units_needed ?? ''} unit(s) of {n.blood_group}</span></div>
              <UrgencyPill urgency={n.urgency} /></div>
          ))}
        </Panel>
        <Panel title="Donation Impact">
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span style={{ fontSize: '2.2rem', color: '#a61b2b' }}>❤</span>
            <div><div className="bc-h1">{accepted}</div><span style={{ color: '#6b7280' }}>requests you said yes to</span></div>
          </div>
          <p style={{ color: '#6b7280', marginTop: '1rem' }}>{p?.name} · {p?.city}</p>
        </Panel>
      </div>
    </div>
  );
}

/* ---------- Notifications: I Can Donate / Not Now ---------- */
export function DonorNotificationsPage() {
  const d = useDonor();
  const [tab, setTab] = useState('all');
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const answer = async (id, response) => {
    setBusy(id); setError(null); setMessage(null);
    try {
      await respondDonorNotification(id, response);
      setMessage(response === 'accepted' ? 'Thank you! The hospital has been told you are coming.' : 'Response recorded.');
      await d.alerts.refresh();
    } catch (err) { setError(err.message || 'Could not send your answer.'); } finally { setBusy(null); }
  };
  const shown = tab === 'updates' ? d.history : tab === 'requests' ? d.pending : d.items;
  return (
    <div>
      <PageHeader title="Notifications" subtitle="Stay updated on blood requirements near you." />
      {(error || d.alerts.error) && <div className="alert alert-error" role="alert">{error || d.alerts.error}</div>}
      {message && <div className="alert alert-success" role="status">{message}</div>}
      <div className="bc-tabs">
        {[['all', `All (${d.items.length})`], ['requests', `Blood Request (${d.pending.length})`], ['updates', `Updates (${d.history.length})`]].map(([k, l]) => (
          <button key={k} type="button" className={`bc-tab${tab === k ? ' on' : ''}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      {shown.length === 0 && <Panel><p>Nothing here yet.</p></Panel>}
      {shown.map((n) => (
        <div key={n.id} className="bc-row">
          <div className="ico" aria-hidden="true">🩸</div>
          <div className="grow">
            <b>{n.urgency === 'CRITICAL' ? 'Urgent Blood Requirement' : 'Blood Request'} – {n.blood_group} <UrgencyPill urgency={n.urgency} /></b>
            <span><strong>{n.hospital_name || `Request #${n.blood_request_id}`}</strong> requires {n.units_needed ?? ''} unit(s) of {n.blood_group}. If you are available, please consider donating.</span>
            <span style={{ display: 'block' }}>{fmtWhen(n.attempted_at)}</span>
          </div>
          {n.response_status === 'pending' ? (
            <div style={{ display: 'flex', gap: '.5rem' }}>
              <button type="button" className="bc-btn sm" disabled={busy === n.id} onClick={() => answer(n.id, 'accepted')}>I Can Donate</button>
              <button type="button" className="bc-btn ghost sm" disabled={busy === n.id} onClick={() => answer(n.id, 'declined')}>Not Now</button>
            </div>
          ) : <span className={`bc-pill bc-p-${n.response_status === 'accepted' ? 'green' : 'gray'}`}>{n.response_status === 'accepted' ? 'You said yes' : 'Declined'}</span>}
        </div>
      ))}
    </div>
  );
}

/* ---------- History ---------- */
export function DonorHistoryPage() {
  const d = useDonor();
  return (
    <div>
      <PageHeader title="Donation History" subtitle="Requests you have answered." />
      <Panel>
        {d.history.length === 0 ? <p>Nothing yet.</p> : (
          <table className="bc-table">
            <thead><tr><th>Hospital</th><th>Blood Group</th><th>Requested</th><th>Your answer</th></tr></thead>
            <tbody>{d.history.map((n) => (
              <tr key={n.id}><td>{n.hospital_name || `#${n.blood_request_id}`}</td><td><strong>{n.blood_group}</strong></td><td>{fmtWhen(n.attempted_at)}</td>
                <td><span className={`bc-pill bc-p-${n.response_status === 'accepted' ? 'green' : 'gray'}`}>{n.response_status === 'accepted' ? 'Accepted' : 'Declined'}</span></td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
