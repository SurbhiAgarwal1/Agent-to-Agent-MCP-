import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import { listBloodRequests } from '../api/bloodRequests';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import LoadingSpinner from '../components/common/LoadingSpinner';
import StatusBadge from '../components/common/StatusBadge';
import UrgencyBadge from '../components/common/UrgencyBadge';
import BloodGroupBadge from '../components/common/BloodGroupBadge';
import EmptyState from '../components/common/EmptyState';

export default function DashboardPage() {
  const { user } = useAuth();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const role = user?.role ? user.role.toUpperCase() : 'USER';
  const isHospitalOrAdmin = role === 'HOSPITAL_STAFF' || role === 'ADMIN';

  useEffect(() => {
    let isMounted = true;
    if (isHospitalOrAdmin) {
      setLoading(true);
      listBloodRequests()
        .then((data) => {
          if (isMounted) setRequests(data || []);
        })
        .catch((err) => {
          if (isMounted) setError(err.message || 'Failed to load blood requests.');
        })
        .finally(() => {
          if (isMounted) setLoading(false);
        });
    }
    return () => {
      isMounted = false;
    };
  }, [isHospitalOrAdmin]);

  // Derived stats
  const totalRequests = requests.length;
  const pendingRequests = requests.filter((r) => r.status === 'PENDING' || r.status === 'PROCESSING').length;
  const fulfilledRequests = requests.filter((r) => r.status === 'FULFILLED' || r.status === 'PARTIALLY_FULFILLED').length;
  const criticalRequests = requests.filter((r) => r.urgency === 'CRITICAL' && r.status !== 'FULFILLED').length;

  return (
    <div>
      <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--color-text-main)' }}>
            Operational Dashboard
          </h1>
          <p className="text-secondary" style={{ marginTop: '0.25rem', fontSize: '0.9375rem' }}>
            Welcome back, <strong>{user?.email}</strong> &bull; Role: <span className="badge badge-neutral">{role}</span>
          </p>
        </div>

        {isHospitalOrAdmin && (
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <Link to="/blood-requests/new" className="btn btn-primary">
              + New Blood Request
            </Link>
          </div>
        )}
      </div>

      {/* Hospital / Admin view */}
      {isHospitalOrAdmin ? (
        <>
          {/* Metrics row */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
              gap: '1rem',
              marginBottom: '1.75rem',
            }}
          >
            <div className="card" style={{ padding: '1.25rem' }}>
              <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600, textTransform: 'uppercase' }}>
                Total Requests
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 700, marginTop: '0.5rem', color: 'var(--color-text-main)' }}>
                {loading ? '...' : totalRequests}
              </div>
            </div>

            <div className="card" style={{ padding: '1.25rem' }}>
              <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600, textTransform: 'uppercase' }}>
                Active / In Progress
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 700, marginTop: '0.5rem', color: '#1E40AF' }}>
                {loading ? '...' : pendingRequests}
              </div>
            </div>

            <div className="card" style={{ padding: '1.25rem' }}>
              <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600, textTransform: 'uppercase' }}>
                Fulfilled / Delivered
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 700, marginTop: '0.5rem', color: '#166534' }}>
                {loading ? '...' : fulfilledRequests}
              </div>
            </div>

            <div className="card" style={{ padding: '1.25rem' }}>
              <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600, textTransform: 'uppercase' }}>
                Critical Unresolved
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 700, marginTop: '0.5rem', color: 'var(--color-primary)' }}>
                {loading ? '...' : criticalRequests}
              </div>
            </div>
          </div>

          {/* Recent Requests Section */}
          <Card
            title="Recent Emergency Blood Requests"
            actions={
              <Link to="/blood-requests" className="btn btn-outline btn-sm">
                View All Requests
              </Link>
            }
          >
            {loading && <LoadingSpinner message="Fetching blood requests..." />}
            {error && (
              <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
                {error}
              </div>
            )}

            {!loading && !error && requests.length === 0 && (
              <EmptyState
                title="No Blood Requests Found"
                message="Your hospital has not lodged any blood requests yet."
                action={
                  <Link to="/blood-requests/new" className="btn btn-primary">
                    Create First Request
                  </Link>
                }
              />
            )}

            {!loading && !error && requests.length > 0 && (
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Request ID</th>
                      <th>Hospital</th>
                      <th>Blood Group</th>
                      <th>Units</th>
                      <th>Urgency</th>
                      <th>Status</th>
                      <th>Created</th>
                      <th style={{ textAlign: 'right' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {requests.slice(0, 5).map((req) => (
                      <tr key={req.request_id}>
                        <td>
                          <strong>#{req.request_id}</strong>
                        </td>
                        <td>Hospital #{req.hospital_id}</td>
                        <td>
                          <BloodGroupBadge group={req.blood_group} />
                        </td>
                        <td><strong>{req.units_required}</strong> units</td>
                        <td>
                          <UrgencyBadge urgency={req.urgency} />
                        </td>
                        <td>
                          <StatusBadge status={req.status} />
                        </td>
                        <td className="text-secondary" style={{ fontSize: '0.8125rem' }}>
                          {req.created_at ? new Date(req.created_at).toLocaleString() : '—'}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <Link to={`/blood-requests/${req.request_id}`} className="btn btn-outline btn-sm">
                            View Progress &rarr;
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      ) : role === 'BLOOD_BANK_STAFF' ? (
        <Card title="Blood Bank Staff Portal">
          <p className="text-secondary" style={{ lineHeight: 1.6 }}>
            You are authenticated as <strong>Blood Bank Staff</strong>.
          </p>
          <div className="alert alert-info" style={{ marginTop: '1rem' }}>
            <strong>Assigned Blood Banks:</strong>{' '}
            {user?.bank_ids && user.bank_ids.length > 0
              ? user.bank_ids.map((id) => `Bank #${id}`).join(', ')
              : 'No active blood bank memberships assigned yet. Please contact an Administrator.'}
          </div>
          <p className="text-secondary" style={{ marginTop: '1rem', fontSize: '0.875rem' }}>
            Blood availability is checked when hospital emergency requests are submitted, helping staff find suitable sources.
          </p>
        </Card>
      ) : (
        <Card title="General Member Account">
          <p className="text-secondary">
            You are logged in with the <strong>USER</strong> role.
          </p>
          <p className="text-secondary" style={{ marginTop: '0.5rem' }}>
            To create or coordinate emergency blood requests, an Administrator must grant your account
            Hospital Staff or Blood Bank Staff membership.
          </p>
          <div style={{ marginTop: '1.5rem' }}>
            <Link to="/profile" className="btn btn-outline">
              View Profile & Membership Status
            </Link>
          </div>
        </Card>
      )}
    </div>
  );
}
