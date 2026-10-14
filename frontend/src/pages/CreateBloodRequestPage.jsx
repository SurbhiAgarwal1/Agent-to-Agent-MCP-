import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import { createBloodRequest, processNlRequest } from '../api/bloodRequests';
import { listHospitals } from '../api/hospitals';
import Card from '../components/common/Card';
import Button from '../components/common/Button';

const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const URGENCIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

export default function CreateBloodRequestPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState('structured'); // 'structured' | 'nl'
  const [hospitals, setHospitals] = useState([]);
  const [loadingHospitals, setLoadingHospitals] = useState(false);

  // Structured form state
  const [hospitalId, setHospitalId] = useState('');
  const [bloodGroup, setBloodGroup] = useState('A+');
  const [unitsRequired, setUnitsRequired] = useState(1);
  const [urgency, setUrgency] = useState('HIGH');

  // NL form state
  const [nlText, setNlText] = useState('');
  const [nlResult, setNlResult] = useState(null);

  // Status state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    setLoadingHospitals(true);
    listHospitals()
      .then((data) => {
        if (!isMounted) return;
        setHospitals(data || []);
        // Pre-select user's first hospital membership if available
        if (user?.hospital_ids && user.hospital_ids.length > 0) {
          setHospitalId(String(user.hospital_ids[0]));
        } else if (data && data.length > 0) {
          setHospitalId(String(data[0].hospital_id));
        }
      })
      .catch(() => {
        // Fall back gracefully if hospitals endpoint is restricted
        if (user?.hospital_ids && user.hospital_ids.length > 0) {
          setHospitalId(String(user.hospital_ids[0]));
        }
      })
      .finally(() => {
        if (isMounted) setLoadingHospitals(false);
      });
    return () => {
      isMounted = false;
    };
  }, [user]);

  const handleStructuredSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    const parsedHospitalId = parseInt(hospitalId, 10);
    const parsedUnits = parseInt(unitsRequired, 10);

    if (isNaN(parsedHospitalId) || parsedHospitalId <= 0) {
      setError('Please select or specify a valid Hospital ID.');
      return;
    }
    if (isNaN(parsedUnits) || parsedUnits <= 0) {
      setError('Units required must be at least 1.');
      return;
    }

    setSubmitting(true);
    try {
      const created = await createBloodRequest({
        hospital_id: parsedHospitalId,
        blood_group: bloodGroup,
        units_required: parsedUnits,
        urgency,
      });

      navigate(`/blood-requests/${created.request_id}`);
    } catch (err) {
      setError(err.message || 'Failed to lodge blood request.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleNlSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!nlText.trim()) {
      setError('Please describe your emergency blood requirement.');
      return;
    }

    setSubmitting(true);
    try {
      const res = await processNlRequest(nlText.trim());
      setNlResult(res);

      // Check if created request_id was returned
      const newReqId =
        res?.request_id ||
        res?.structured_result?.request_id ||
        res?.requirement?.request_id;

      if (newReqId) {
        setTimeout(() => {
          navigate(`/blood-requests/${newReqId}`);
        }, 1500);
      }
    } catch (err) {
      setError(err.message || 'Natural language processing failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: '780px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <Link to="/blood-requests" className="text-secondary" style={{ fontSize: '0.875rem' }}>
          &larr; Back to Blood Requests
        </Link>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0.5rem 0 0', color: 'var(--color-text-main)' }}>
          Lodge Emergency Blood Request
        </h1>
        <p className="text-secondary" style={{ marginTop: '0.25rem', fontSize: '0.9375rem' }}>
          Coordinate urgent clinical blood needs with the autonomous multi-agent network
        </p>
      </div>

      {/* Mode Switcher Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          marginBottom: '1.25rem',
          borderBottom: '1px solid var(--border-color)',
          paddingBottom: '0.5rem',
        }}
      >
        <button
          type="button"
          onClick={() => {
            setMode('structured');
            setError(null);
          }}
          className={`btn btn-sm ${mode === 'structured' ? 'btn-primary' : 'btn-outline'}`}
        >
          Structured Form Entry
        </button>
        <button
          type="button"
          onClick={() => {
            setMode('nl');
            setError(null);
          }}
          className={`btn btn-sm ${mode === 'nl' ? 'btn-primary' : 'btn-outline'}`}
        >
          Natural Language Assistant
        </button>
      </div>

      <Card>
        {error && (
          <div className="alert alert-error" role="alert" style={{ marginBottom: '1.25rem' }}>
            {error}
          </div>
        )}

        {mode === 'structured' ? (
          <form onSubmit={handleStructuredSubmit} noValidate>
            <div className="form-group">
              <label className="form-label" htmlFor="hospital-select">
                Target Hospital <span style={{ color: 'var(--color-primary)' }}>*</span>
              </label>
              {hospitals.length > 0 ? (
                <select
                  id="hospital-select"
                  className="form-control"
                  value={hospitalId}
                  onChange={(e) => setHospitalId(e.target.value)}
                  required
                >
                  {hospitals.map((h) => (
                    <option key={h.hospital_id} value={h.hospital_id}>
                      {h.name} (#{h.hospital_id}) &bull; {h.city || 'Central'}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="hospital-select"
                  type="number"
                  className="form-control"
                  placeholder="Hospital ID (e.g. 1)"
                  value={hospitalId}
                  onChange={(e) => setHospitalId(e.target.value)}
                  required
                />
              )}
              {user?.hospital_ids && user.hospital_ids.length > 0 && (
                <small className="text-muted" style={{ display: 'block', marginTop: '0.25rem' }}>
                  Your authorized hospital ID(s): {user.hospital_ids.join(', ')}
                </small>
              )}
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '1rem',
              }}
            >
              <div className="form-group">
                <label className="form-label" htmlFor="blood-group">
                  Required Blood Group <span style={{ color: 'var(--color-primary)' }}>*</span>
                </label>
                <select
                  id="blood-group"
                  className="form-control"
                  value={bloodGroup}
                  onChange={(e) => setBloodGroup(e.target.value)}
                >
                  {BLOOD_GROUPS.map((bg) => (
                    <option key={bg} value={bg}>
                      {bg}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="units-required">
                  Units Required <span style={{ color: 'var(--color-primary)' }}>*</span>
                </label>
                <input
                  id="units-required"
                  type="number"
                  min="1"
                  max="100"
                  className="form-control"
                  value={unitsRequired}
                  onChange={(e) => setUnitsRequired(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="urgency-select">
                  Urgency Level <span style={{ color: 'var(--color-primary)' }}>*</span>
                </label>
                <select
                  id="urgency-select"
                  className="form-control"
                  value={urgency}
                  onChange={(e) => setUrgency(e.target.value)}
                >
                  {URGENCIES.map((u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: '0.75rem',
                marginTop: '1.75rem',
                paddingTop: '1rem',
                borderTop: '1px solid var(--border-color)',
              }}
            >
              <Link to="/blood-requests" className="btn btn-outline">
                Cancel
              </Link>
              <Button type="submit" variant="primary" loading={submitting}>
                Lodge Blood Request
              </Button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleNlSubmit} noValidate>
            <div className="form-group">
              <label className="form-label" htmlFor="nl-prompt">
                Clinical Requirement Prompt
              </label>
              <textarea
                id="nl-prompt"
                className="form-control"
                rows={4}
                placeholder="e.g. We urgently need 2 units of A+ blood for an emergency surgery at City General Hospital."
                value={nlText}
                onChange={(e) => setNlText(e.target.value)}
                required
              />
              <small className="text-muted" style={{ display: 'block', marginTop: '0.35rem' }}>
                The Natural Language Interface Agent will parse the hospital name, blood group, units, and urgency,
                verify permissions, and initiate multi-agent coordination.
              </small>
            </div>

            {nlResult && (
              <div className="alert alert-success" style={{ marginTop: '1rem' }}>
                <strong>Agent Coordination Response:</strong>
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem' }}>
                  {nlResult.summary || nlResult.response || 'Request parsed and lodged successfully. Redirecting to request details...'}
                </p>
              </div>
            )}

            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: '0.75rem',
                marginTop: '1.75rem',
                paddingTop: '1rem',
                borderTop: '1px solid var(--border-color)',
              }}
            >
              <Link to="/blood-requests" className="btn btn-outline">
                Cancel
              </Link>
              <Button type="submit" variant="primary" loading={submitting}>
                Process with NL Agent
              </Button>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}
