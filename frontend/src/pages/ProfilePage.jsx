import React from 'react';
import useAuth from '../hooks/useAuth';
import Card from '../components/common/Card';
import Button from '../components/common/Button';

export default function ProfilePage() {
  const { user, logout } = useAuth();

  const role = user?.role ? user.role.toUpperCase() : 'USER';
  const hospitalIds = user?.hospital_ids || [];
  const bankIds = user?.bank_ids || [];

  return (
    <div style={{ maxWidth: '780px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--color-text-main)' }}>
          User Profile & Credentials
        </h1>
        <p className="text-secondary" style={{ marginTop: '0.25rem', fontSize: '0.9375rem' }}>
          Identity and Role-Based Access Control (RBAC) authorization scope
        </p>
      </div>

      <div style={{ display: 'grid', gap: '1.5rem' }}>
        <Card title="Account Details">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', rowGap: '1rem', columnGap: '1rem', fontSize: '0.9375rem' }}>
            <div className="text-secondary" style={{ fontWeight: 600 }}>User ID:</div>
            <div>#{user?.id || '—'}</div>

            <div className="text-secondary" style={{ fontWeight: 600 }}>Email Address:</div>
            <div><strong>{user?.email || '—'}</strong></div>

            <div className="text-secondary" style={{ fontWeight: 600 }}>Assigned Role:</div>
            <div>
              <span className="badge badge-neutral" style={{ fontSize: '0.875rem' }}>
                {role}
              </span>
            </div>

            <div className="text-secondary" style={{ fontWeight: 600 }}>Account Status:</div>
            <div>
              <span className="badge badge-success">
                {user?.is_active ? 'Active' : 'Pending / Inactive'}
              </span>
            </div>
          </div>
        </Card>

        <Card title="Active Memberships & Facility Scopes">
          <div style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Authorized Hospital Scopes
            </h3>
            {hospitalIds.length > 0 ? (
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {hospitalIds.map((hid) => (
                  <span key={hid} className="badge badge-neutral">
                    Hospital #{hid}
                  </span>
                ))}
              </div>
            ) : role === 'ADMIN' ? (
              <p className="text-secondary" style={{ margin: 0, fontSize: '0.875rem' }}>
                Full system administrator: Authorized across all hospitals.
              </p>
            ) : (
              <p className="text-secondary" style={{ margin: 0, fontSize: '0.875rem' }}>
                No active hospital memberships. An administrator must assign your account to a hospital before you can create requests.
              </p>
            )}
          </div>

          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Authorized Blood Bank Scopes
            </h3>
            {bankIds.length > 0 ? (
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {bankIds.map((bid) => (
                  <span key={bid} className="badge badge-neutral">
                    Blood Bank #{bid}
                  </span>
                ))}
              </div>
            ) : role === 'ADMIN' ? (
              <p className="text-secondary" style={{ margin: 0, fontSize: '0.875rem' }}>
                Full system administrator: Authorized across all blood bank facilities.
              </p>
            ) : (
              <p className="text-secondary" style={{ margin: 0, fontSize: '0.875rem' }}>
                No active blood bank memberships assigned.
              </p>
            )}
          </div>
        </Card>

        <Card title="Session Management">
          <p className="text-secondary" style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>
            Sign out to invalidate your current browser session token.
          </p>
          <Button variant="danger" onClick={logout}>
            Sign Out
          </Button>
        </Card>
      </div>
    </div>
  );
}
