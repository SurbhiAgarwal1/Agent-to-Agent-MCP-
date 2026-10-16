import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import Button from '../components/common/Button';

export default function LoginPage() {
  const { login, logout, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('HOSPITAL_STAFF');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const from = location.state?.from?.pathname || '/dashboard';

  useEffect(() => {
    if (isAuthenticated) navigate(from, { replace: true });
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
      const profile = await login(email, password);
      const actualRole = profile?.role?.toUpperCase();
      if (actualRole !== role) {
        logout();
        setError(`This account is registered as ${actualRole === 'ADMIN' ? 'Administrator' : 'Hospital Staff'}. Choose the matching account type.`);
        return;
      }
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-shell" aria-labelledby="login-title">
        <Link to="/" className="auth-brand" aria-label="Blood Coordination home">
          <span className="auth-brand-mark">+</span>
          <span>Blood Coordination</span>
        </Link>

        <div className="auth-heading">
          <span className="auth-eyebrow">Welcome back</span>
          <h1 id="login-title">Sign in securely</h1>
          <p>Choose your account type and continue to your workspace.</p>
        </div>

        <div className="auth-card">
          {error && <div className="alert alert-error" role="alert">{error}</div>}

          <form onSubmit={handleSubmit} noValidate>
            <fieldset className="form-group auth-role-fieldset">
              <legend className="form-label">Account Type</legend>
              <div className="auth-role-grid">
                <label className={`auth-role-option ${role === 'HOSPITAL_STAFF' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="login-role"
                    value="HOSPITAL_STAFF"
                    checked={role === 'HOSPITAL_STAFF'}
                    onChange={(e) => setRole(e.target.value)}
                  />
                  <span><strong>Hospital Staff</strong><small>Request and coordinate blood.</small></span>
                </label>
                <label className={`auth-role-option ${role === 'ADMIN' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="login-role"
                    value="ADMIN"
                    checked={role === 'ADMIN'}
                    onChange={(e) => setRole(e.target.value)}
                  />
                  <span><strong>Administrator</strong><small>Manage operations and system tools.</small></span>
                </label>
              </div>
            </fieldset>

            <div className="form-group">
              <label className="form-label" htmlFor="login-email">Email Address</label>
              <input
                id="login-email"
                type="email"
                className="form-input"
                placeholder="you@hospital.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                className="form-input"
                placeholder="Your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <Button type="submit" variant="primary" loading={loading} style={{ width: '100%' }}>
              Sign In
            </Button>
          </form>

          <div className="auth-switch">
            Need an account? <Link to="/signup">Create one</Link>
          </div>
        </div>

        <Link to="/" className="auth-back">&larr; Back to public homepage</Link>
      </section>
    </main>
  );
}
