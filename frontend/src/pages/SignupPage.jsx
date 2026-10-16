import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import Button from '../components/common/Button';

const ROLE_OPTIONS = [
  { value: 'HOSPITAL_STAFF', label: 'Hospital Staff', description: 'Request and coordinate blood for your facility.' },
  { value: 'ADMIN', label: 'Administrator', description: 'Manage users, system operations, and observability.' },
];

export default function SignupPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [role, setRole] = useState('HOSPITAL_STAFF');
  const [adminSignupKey, setAdminSignupKey] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
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
    if (role === 'ADMIN' && !adminSignupKey.trim()) {
      setError('Enter the admin setup key to create an administrator account.');
      return;
    }

    setLoading(true);
    try {
      await register(email, password, role, adminSignupKey);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err.message || 'Registration failed. Please check your details and try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-shell" aria-labelledby="signup-title">
        <Link to="/" className="auth-brand" aria-label="Blood Coordination home">
          <span className="auth-brand-mark">+</span>
          <span>Blood Coordination</span>
        </Link>

        <div className="auth-heading">
          <span className="auth-eyebrow">Secure account setup</span>
          <h1 id="signup-title">Create your account</h1>
          <p>Choose how you will use the blood coordination portal.</p>
        </div>

        <div className="auth-card">
          {error && <div className="alert alert-error" role="alert">{error}</div>}

          <form onSubmit={handleSubmit} noValidate>
            <div className="form-group">
              <label className="form-label" htmlFor="signup-email">Email Address</label>
              <input
                id="signup-email"
                type="email"
                className="form-input"
                placeholder="you@hospital.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>

            <fieldset className="form-group auth-role-fieldset">
              <legend className="form-label">Account Type</legend>
              <div className="auth-role-grid">
                {ROLE_OPTIONS.map((option) => (
                  <label
                    key={option.value}
                    className={`auth-role-option ${role === option.value ? 'selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="signup-role"
                      value={option.value}
                      checked={role === option.value}
                      onChange={(e) => setRole(e.target.value)}
                    />
                    <span>
                      <strong>{option.label}</strong>
                      <small>{option.description}</small>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            {role === 'ADMIN' && (
              <div className="form-group auth-admin-key">
                <label className="form-label" htmlFor="admin-signup-key">Admin Setup Key</label>
                <input
                  id="admin-signup-key"
                  type="password"
                  className="form-input"
                  placeholder="Enter the setup key configured by the system owner"
                  value={adminSignupKey}
                  onChange={(e) => setAdminSignupKey(e.target.value)}
                  autoComplete="off"
                />
                <small className="form-help">
                  Required for administrator registration. Keep this key private.
                </small>
              </div>
            )}

            <div className="form-group">
              <label className="form-label" htmlFor="signup-password">Password</label>
              <input
                id="signup-password"
                type="password"
                className="form-input"
                placeholder="At least 6 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="signup-confirm-password">Confirm Password</label>
              <input
                id="signup-confirm-password"
                type="password"
                className="form-input"
                placeholder="Repeat your password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <Button type="submit" variant="primary" loading={loading} style={{ width: '100%' }}>
              Create Account
            </Button>
          </form>

          <div className="auth-switch">
            Already have an account? <Link to="/login">Sign in</Link>
          </div>
        </div>

        <Link to="/" className="auth-back">&larr; Back to public homepage</Link>
      </section>
    </main>
  );
}
