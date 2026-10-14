import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import { registerApi } from '../api/auth';
import Button from '../components/common/Button';
import Card from '../components/common/Card';

export default function SignupPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState('HOSPITAL_STAFF');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!email || !password) {
      setError('Please provide both email and password.');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters in length.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await registerApi({ email, password, role });
      // Auto-login upon successful registration
      await login(email, password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err.message || 'Registration failed. The email may already be in use.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '2rem 1rem',
        backgroundColor: 'var(--color-bg)',
      }}
    >
      <div style={{ width: '100%', maxWidth: '440px' }}>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '44px',
              height: '44px',
              borderRadius: '8px',
              backgroundColor: 'var(--color-primary)',
              color: '#FFFFFF',
              fontWeight: 700,
              fontSize: '1.25rem',
              marginBottom: '0.75rem',
            }}
          >
            +
          </div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, color: 'var(--color-text-main)' }}>
            Create an Account
          </h1>
          <p className="text-secondary" style={{ fontSize: '0.875rem', marginTop: '0.25rem' }}>
            Register as Hospital Staff or General Member
          </p>
        </div>

        <Card>
          {error && (
            <div className="alert alert-error" role="alert" style={{ marginBottom: '1.25rem' }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <div className="form-group">
              <label className="form-label" htmlFor="signup-email">
                Email Address
              </label>
              <input
                id="signup-email"
                type="email"
                className="form-control"
                placeholder="staff@cityhospital.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="signup-role">
                Account Role
              </label>
              <select
                id="signup-role"
                className="form-control"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="HOSPITAL_STAFF">Hospital Staff (Can manage hospital requests)</option>
                <option value="USER">General Member</option>
              </select>
              <small className="text-muted" style={{ display: 'block', marginTop: '0.25rem' }}>
                Note: Hospital and Blood Bank memberships are granted by administrators after registration.
              </small>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="signup-password">
                Password
              </label>
              <input
                id="signup-password"
                type="password"
                className="form-control"
                placeholder="Min. 6 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="signup-confirm-password">
                Confirm Password
              </label>
              <input
                id="signup-confirm-password"
                type="password"
                className="form-control"
                placeholder="Repeat password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <div style={{ marginTop: '1.5rem' }}>
              <Button type="submit" variant="primary" loading={loading} style={{ width: '100%' }}>
                Register Account
              </Button>
            </div>
          </form>

          <div
            style={{
              marginTop: '1.5rem',
              paddingTop: '1.25rem',
              borderTop: '1px solid var(--border-color)',
              textAlign: 'center',
              fontSize: '0.875rem',
            }}
          >
            <span className="text-secondary">Already have an account? </span>
            <Link to="/login" style={{ color: 'var(--color-primary)', fontWeight: 600 }}>
              Sign in
            </Link>
          </div>
        </Card>

        <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
          <Link to="/" className="text-secondary" style={{ fontSize: '0.8125rem' }}>
            &larr; Back to public homepage
          </Link>
        </div>
      </div>
    </div>
  );
}
