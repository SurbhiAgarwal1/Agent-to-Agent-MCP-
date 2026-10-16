import React from 'react';
import { Link, Navigate, useLocation, Outlet } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import LoadingSpinner from '../components/common/LoadingSpinner';
import Card from '../components/common/Card';

export default function RoleRoute({ allowedRoles = [], children }) {
  const { user, isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <LoadingSpinner message="Validating permissions..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  const userRole = user?.role ? user.role.toUpperCase() : 'USER';
  const normalizedAllowed = allowedRoles.map((r) => r.toUpperCase());

  if (normalizedAllowed.length > 0 && !normalizedAllowed.includes(userRole)) {
    return (
      <div className="container" style={{ maxWidth: '640px', marginTop: '4rem' }}>
        <Card title="403 — Access Denied">
          <div style={{ padding: '0.5rem 0' }}>
            <p className="text-secondary" style={{ marginBottom: '1rem' }}>
              Your current account role (<strong>{userRole}</strong>) does not have authorization
              to access this view.
            </p>
            <div className="alert alert-error" style={{ marginBottom: '1.5rem' }}>
              Required role(s): <strong>{allowedRoles.join(' or ')}</strong>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <Link to="/dashboard" className="btn btn-primary">
                Return to Dashboard
              </Link>
              <Link to="/profile" className="btn btn-outline">
                View Your Role & Profile
              </Link>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return children ? children : <Outlet />;
}
