import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import Button from '../components/common/Button';
import { homeForRole } from '../utils/roles';

const GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];

const ROLE_OPTIONS = [
  { value: 'HOSPITAL_STAFF', label: 'Hospital Staff', description: 'Request and coordinate blood for your facility.' },
  { value: 'USER', label: 'Blood Donor', description: 'Get alerted when someone near you needs your blood group.' },
  { value: 'BLOOD_BANK_STAFF', label: 'Blood Bank', description: 'List your blood bank, manage stock and answer requests.' },
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
  const [f, setF] = useState({
    name: '', age: '', blood_group: 'O+', city: '', latitude: '', longitude: '',
    organization_name: '', address: '', contact_number: '',
  });
  const [stock, setStock] = useState({});
  const [geoMsg, setGeoMsg] = useState('');
  const setField = (k) => (e) => setF((prev) => ({ ...prev, [k]: e.target.value }));

  const useMyLocation = () => {
    if (!navigator.geolocation) { setGeoMsg('Location is not available in this browser.'); return; }
    setGeoMsg('Finding your location...');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setF((prev) => ({ ...prev, latitude: pos.coords.latitude.toFixed(5), longitude: pos.coords.longitude.toFixed(5) }));
        setGeoMsg('Location filled in.');
      },
      () => setGeoMsg('Could not read your location. Type the latitude and longitude instead.'),
    );
  };

  const buildExtra = () => {
    const lat = parseFloat(f.latitude);
    const lon = parseFloat(f.longitude);
    if (role === 'USER') {
      return { name: f.name.trim(), age: parseInt(f.age, 10), blood_group: f.blood_group, city: f.city.trim(), latitude: lat, longitude: lon };
    }
    if (role === 'BLOOD_BANK_STAFF') {
      const initial_stock = {};
      Object.entries(stock).forEach(([g, v]) => { const n = parseInt(v, 10); if (n > 0) initial_stock[g] = n; });
      return { organization_name: f.organization_name.trim(), address: f.address.trim(), city: f.city.trim(), latitude: lat, longitude: lon, contact_number: f.contact_number.trim(), initial_stock };
    }
    if (role === 'HOSPITAL_STAFF' && f.organization_name.trim()) {
      return { organization_name: f.organization_name.trim(), address: f.address.trim(), latitude: Number.isFinite(lat) ? lat : undefined, longitude: Number.isFinite(lon) ? lon : undefined };
    }
    return {};
  };

  const locationFields = (
    <div className="form-group">
      <label className="form-label">Location</label>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <input aria-label="Latitude" className="form-input" style={{ flex: 1, minWidth: 120 }} placeholder="Latitude" value={f.latitude} onChange={setField('latitude')} />
        <input aria-label="Longitude" className="form-input" style={{ flex: 1, minWidth: 120 }} placeholder="Longitude" value={f.longitude} onChange={setField('longitude')} />
        <Button type="button" variant="outline" onClick={useMyLocation}>Use my current location</Button>
      </div>
      {geoMsg && <small className="form-help">{geoMsg}</small>}
    </div>
  );

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

    const needsLocation = role === 'USER' || role === 'BLOOD_BANK_STAFF';
    if (needsLocation && (!Number.isFinite(parseFloat(f.latitude)) || !Number.isFinite(parseFloat(f.longitude)))) {
      setError('Please provide your location (latitude and longitude, or use the location button).');
      return;
    }
    if (role === 'USER' && (!f.name.trim() || !f.age || !f.city.trim())) {
      setError('Please enter your name, age and city.');
      return;
    }
    if (role === 'BLOOD_BANK_STAFF' && (!f.organization_name.trim() || !f.address.trim() || !f.city.trim() || !f.contact_number.trim())) {
      setError('Please enter the blood bank name, address, city and contact number.');
      return;
    }

    setLoading(true);
    try {
      await register(email, password, role, adminSignupKey, buildExtra());
      navigate(homeForRole(role), { replace: true });
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

            {role === 'USER' && (
              <>
                <div className="form-group"><label className="form-label" htmlFor="su-name">Full name</label>
                  <input id="su-name" className="form-input" value={f.name} onChange={setField('name')} /></div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <div className="form-group" style={{ flex: 1 }}><label className="form-label" htmlFor="su-age">Age</label>
                    <input id="su-age" type="number" min="18" max="65" className="form-input" value={f.age} onChange={setField('age')} /></div>
                  <div className="form-group" style={{ flex: 1 }}><label className="form-label" htmlFor="su-bg">Blood group</label>
                    <select id="su-bg" className="form-input" value={f.blood_group} onChange={setField('blood_group')}>
                      {GROUPS.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
                </div>
                <div className="form-group"><label className="form-label" htmlFor="su-city">City</label>
                  <input id="su-city" className="form-input" value={f.city} onChange={setField('city')} /></div>
                {locationFields}
              </>
            )}

            {role === 'BLOOD_BANK_STAFF' && (
              <>
                <div className="form-group"><label className="form-label" htmlFor="su-org">Blood bank name</label>
                  <input id="su-org" className="form-input" value={f.organization_name} onChange={setField('organization_name')} /></div>
                <div className="form-group"><label className="form-label" htmlFor="su-addr">Address</label>
                  <input id="su-addr" className="form-input" value={f.address} onChange={setField('address')} /></div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <div className="form-group" style={{ flex: 1 }}><label className="form-label" htmlFor="su-bcity">City</label>
                    <input id="su-bcity" className="form-input" value={f.city} onChange={setField('city')} /></div>
                  <div className="form-group" style={{ flex: 1 }}><label className="form-label" htmlFor="su-phone">Contact number</label>
                    <input id="su-phone" className="form-input" value={f.contact_number} onChange={setField('contact_number')} /></div>
                </div>
                {locationFields}
                <div className="form-group">
                  <label className="form-label">Opening stock (units, optional)</label>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.5rem' }}>
                    {GROUPS.map((g) => (
                      <label key={g} style={{ fontSize: '0.8125rem' }}>{g}
                        <input type="number" min="0" aria-label={`Stock ${g}`} className="form-input" value={stock[g] || ''}
                          onChange={(e) => setStock((prev) => ({ ...prev, [g]: e.target.value }))} />
                      </label>
                    ))}
                  </div>
                </div>
              </>
            )}

            {role === 'HOSPITAL_STAFF' && (
              <>
                <div className="form-group"><label className="form-label" htmlFor="su-hosp">Hospital name (optional)</label>
                  <input id="su-hosp" className="form-input" value={f.organization_name} onChange={setField('organization_name')} />
                  <small className="form-help">Fill this in to create your hospital automatically.</small></div>
                {f.organization_name.trim() && (
                  <>
                    <div className="form-group"><label className="form-label" htmlFor="su-haddr">Hospital address</label>
                      <input id="su-haddr" className="form-input" value={f.address} onChange={setField('address')} /></div>
                    {locationFields}
                  </>
                )}
              </>
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
