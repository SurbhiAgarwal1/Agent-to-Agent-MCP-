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
          Profile
        </h1>
        <p className="text-secondary" style={{ marginTop: '0.25rem', fontSize: '0.9375rem' }}>
          Manage your account and facility access.
        </p>
      </div>

      <div style={{ display: 'grid', gap: '1.5rem' }}>
        <Card title="Account Details">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', rowGap: '1rem', columnGap: '1rem', fontSize: '0.9375rem' }}>
            <div className="text-secondary" style={{ fontWeight: 600 }}>User ID:</div>
            <div>#{user?.id || '—'}</div>

            <div className="text-secondary" style={{ fontWeight: 600 }}>Email Address:</div>
            <div><strong>{user?.email || '—'}</strong></div>

            <div className="text-secondary" style={{ fontWeight: 600 }}>Role:</div>
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

        <Card title="Facility Access">
          <div style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Hospital Access
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
                Administrator access includes all hospitals.
              </p>
            ) : (
              <p className="text-secondary" style={{ margin: 0, fontSize: '0.875rem' }}>
                No hospital access is currently assigned.
              </p>
            )}
          </div>

          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Blood Bank Access
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
                Administrator access includes all blood banks.
              </p>
            ) : (
              <p className="text-secondary" style={{ margin: 0, fontSize: '0.875rem' }}>
                No blood bank access is currently assigned.
              </p>
            )}
          </div>
        </Card>

        <Card title="Account Actions">
          <p className="text-secondary" style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>
            Sign out of your account on this device.
          </p>
          <Button variant="danger" onClick={logout}>
            Sign Out
          </Button>
        </Card>
      </div>
    </div>
  );
}
