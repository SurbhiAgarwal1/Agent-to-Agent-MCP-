import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import Button from '../components/common/Button';
import Card from '../components/common/Card';

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const from = location.state?.from?.pathname || '/dashboard';

  useEffect(() => {
    if (isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, from]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please provide both email and password.');
      return;
    }

    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || 'Login failed. Please check your credentials.');
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
      <div style={{ width: '100%', maxWidth: '420px' }}>
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
            Sign In to Portal
          </h1>
          <p className="text-secondary" style={{ fontSize: '0.875rem', marginTop: '0.25rem' }}>
            Secure Blood Coordination Portal
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
              <label className="form-label" htmlFor="login-email">
                Email Address
              </label>
              <input
                id="login-email"
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
              <label className="form-label" htmlFor="login-password">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                className="form-control"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <div style={{ marginTop: '1.5rem' }}>
              <Button type="submit" variant="primary" loading={loading} style={{ width: '100%' }}>
                Sign In
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
            <span className="text-secondary">Need an account? </span>
            <Link to="/signup" style={{ color: 'var(--color-primary)', fontWeight: 600 }}>
              Create an account
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
