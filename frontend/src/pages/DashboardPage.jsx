import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import { listBloodRequests } from '../api/bloodRequests';
import { listHospitals } from '../api/hospitals';
import { getRequestOrder } from '../api/portal';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { PageHeader, StatTile, Panel, StatusPill, UrgencyPill, Bars, fmtEta, fmtWhen } from '../components/bc';

export default function DashboardPage() {
  const { user } = useAuth();
  const [requests, setRequests] = useState([]);
  const [hospitals, setHospitals] = useState([]);
  const [etas, setEtas] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const role = user?.role ? user.role.toUpperCase() : 'USER';
  const isHospitalOrAdmin = role === 'HOSPITAL_STAFF' || role === 'ADMIN';

  useEffect(() => {
    let alive = true;
    if (!isHospitalOrAdmin) return undefined;
    setLoading(true);
    Promise.resolve(listHospitals()).catch(() => []).then((h) => { if (alive) setHospitals(h || []); });
    listBloodRequests()
      .then((data) => {
        if (!alive) return;
        setRequests(data || []);
        (data || []).slice(0, 5).forEach((r) => {
          Promise.resolve(getRequestOrder(r.request_id)).then((o) => {
            if (alive && o) setEtas((prev) => ({ ...prev, [r.request_id]: o }));
          }).catch(() => {});
        });
      })
      .catch((err) => { if (alive) setError(err.message || 'Failed to load blood requests.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [isHospitalOrAdmin]);

  const total = requests.length;
  const inProgress = requests.filter((r) => r.status === 'PENDING' || r.status === 'PROCESSING' || r.status === 'PARTIALLY_FULFILLED').length;
  const fulfilled = requests.filter((r) => r.status === 'FULFILLED').length;
  const urgent = requests.filter((r) => ['CRITICAL', 'HIGH'].includes(r.urgency) && r.status !== 'FULFILLED' && r.status !== 'CANCELLED').length;
  const byGroup = Object.entries(requests.reduce((acc, r) => ({ ...acc, [r.blood_group]: (acc[r.blood_group] || 0) + r.units_required }), {}))
    .map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value).slice(0, 6);
  const hospitalName = (id) => (hospitals.find((h) => h.hospital_id === id) || {}).name || `Hospital #${id}`;

  if (!isHospitalOrAdmin) {
    return (
      <div>
        <PageHeader title="Dashboard" subtitle="Your account does not have hospital access yet." />
        <Panel title="General member account">
          <p>To raise blood requests, an administrator must grant your account hospital staff membership.</p>
          <Link to="/profile" className="bc-btn ghost sm">View profile</Link>
        </Panel>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Hospital Dashboard" subtitle="Operational Dashboard: manage blood requests and track every order.">
        <Link to="/blood-requests/new" className="bc-btn">+ Raise Blood Request</Link>
      </PageHeader>

      <div className="bc-stats">
        <StatTile icon="📝" value={loading ? '…' : total} label="Total Requests" tone="lav" />
        <StatTile icon="⏳" value={loading ? '…' : inProgress} label="In Progress" tone="peach" />
        <StatTile icon="✅" value={loading ? '…' : fulfilled} label="Fulfilled" tone="mint" />
        <StatTile icon="❤" value={loading ? '…' : urgent} label="Urgent" tone="rose" />
      </div>

      <div className="bc-grid two">
        <Panel title="My Recent Requests" action={<Link to="/blood-requests" className="bc-btn ghost sm">View all</Link>}>
          {loading && <LoadingSpinner message="Fetching blood requests..." />}
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          {!loading && !error && requests.length === 0 && <p>No blood requests yet. Raise your first request.</p>}
          {requests.length > 0 && (
            <table className="bc-table">
              <thead><tr><th>#</th><th>Blood Group</th><th>Units</th><th>Requested At</th><th>ETA</th><th>Status</th></tr></thead>
              <tbody>
                {requests.slice(0, 5).map((r) => {
                  const o = etas[r.request_id];
                  const eta = o?.stage === 'confirmed' ? fmtEta(o.eta_minutes) : o?.stage === 'delivered' ? 'Delivered' : '—';
                  return (
                    <tr key={r.request_id}>
                      <td><Link to={`/blood-requests/${r.request_id}`}>#{r.request_id}</Link></td>
                      <td><strong>{r.blood_group}</strong></td>
                      <td>{r.units_required}</td>
                      <td>{fmtWhen(r.created_at)}</td>
                      <td>{eta}</td>
                      <td><StatusPill status={r.status} /> <UrgencyPill urgency={r.urgency} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Panel>
        <div style={{ display: 'grid', gap: '1rem', alignContent: 'start' }}>
          <Panel className="bc-cta">
            <div className="drop" aria-hidden="true">🩸</div>
            <div><strong style={{ fontSize: '1.15rem' }}>Need Blood?</strong><p style={{ margin: '.3rem 0 0' }}>Create a new blood request for your patients.</p></div>
            <Link to="/blood-requests/new" className="bc-btn">+ Raise Blood Request</Link>
          </Panel>
          <Panel title="Units requested by blood group">
            {byGroup.length ? <Bars rows={byGroup} unit=" units" /> : <p>Nothing requested yet.</p>}
          </Panel>
        </div>
      </div>
      {role === 'ADMIN' && requests.length > 0 && <p className="bc-sub">Hospital: {hospitalName(requests[0].hospital_id)}</p>}
    </div>
  );
}
