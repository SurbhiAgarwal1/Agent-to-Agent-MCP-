import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ChatBloodRequest from '../components/blood/ChatBloodRequest';
import { listHospitals } from '../api/hospitals';
import { createBloodRequest } from '../api/bloodRequests';
import { PageHeader, Panel } from '../components/bc';
import useAuth from '../hooks/useAuth';
import { getMeApi } from '../api/auth';

const GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const PRIORITY = [['CRITICAL', 'Urgent'], ['HIGH', 'High'], ['MEDIUM', 'Medium'], ['LOW', 'Normal']];

export default function CreateBloodRequestPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [hospitals, setHospitals] = useState([]);
  const [form, setForm] = useState({ hospital_id: '', blood_group: 'O-', component_type: 'packed_red_blood_cells', units_required: 2, urgency: 'HIGH' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const h = await Promise.resolve(listHospitals()).catch(() => []);
      let ids = user?.hospital_ids;
      if (ids === undefined && user?.role !== 'ADMIN') ids = ((await Promise.resolve(getMeApi()).catch(() => null)) || {}).hospital_ids;
      if (!alive) return;
      const mine = user?.role === 'ADMIN' || !(ids || []).length ? (h || []) : (h || []).filter((x) => ids.includes(x.hospital_id));
      setHospitals(mine);
      if (mine.length) setForm((f) => ({ ...f, hospital_id: String(mine[mine.length - 1].hospital_id) }));
    })();
    return () => { alive = false; };
  }, [user]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    const units = parseInt(form.units_required, 10);
    if (!form.hospital_id) { setError('Choose your hospital.'); return; }
    if (!(units >= 1)) { setError('Units required must be at least 1.'); return; }
    setBusy(true); setError(null);
    try {
      const created = await createBloodRequest({ ...form, hospital_id: parseInt(form.hospital_id, 10), units_required: units });
      navigate(`/blood-requests/${created.request_id}`);
    } catch (err) {
      setError(err.message || 'Could not submit the request.');
    } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader title="Raise a Blood Request" subtitle="Submit a new blood requirement for your hospital." />
      <div className="bc-grid two">
        <Panel>
          <form onSubmit={submit} style={{ display: 'grid', gap: '.9rem' }}>
            {error && <div className="alert alert-error" role="alert">{error}</div>}
            <label>Hospital *
              <select className="bc-input" value={form.hospital_id} onChange={set('hospital_id')}>
                {hospitals.map((h) => <option key={h.hospital_id} value={h.hospital_id}>{h.name}</option>)}
              </select>
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.9rem' }}>
              <label>Blood Group *
                <select className="bc-input" value={form.blood_group} onChange={set('blood_group')}>{GROUPS.map((g) => <option key={g}>{g}</option>)}</select>
              </label>
              <label>Component *
                <select className="bc-input" value={form.component_type} onChange={set('component_type')}>
                  <option value="whole_blood">Whole Blood</option><option value="packed_red_blood_cells">Packed Red Blood Cells</option>
                </select>
              </label>
              <label>Units Required *
                <input className="bc-input" type="number" min="1" value={form.units_required} onChange={set('units_required')} />
              </label>
              <label>Priority *
                <select className="bc-input" value={form.urgency} onChange={set('urgency')}>{PRIORITY.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              </label>
            </div>
            <div style={{ display: 'flex', gap: '.6rem', justifyContent: 'flex-end' }}>
              <button type="button" className="bc-btn ghost" onClick={() => navigate(-1)}>Cancel</button>
              <button type="submit" className="bc-btn" disabled={busy}>{busy ? 'Submitting…' : 'Submit Request'}</button>
            </div>
          </form>
        </Panel>
        <Panel title="Request Guidelines">
          <ul style={{ lineHeight: 1.9, paddingLeft: '1.1rem', margin: 0 }}>
            <li>Provide the accurate blood group and units.</li>
            <li>Set the correct priority (Urgent / High / Normal).</li>
            <li>After submitting, press <strong>Find Available Blood</strong> and then <strong>Confirm Booking / Place Order</strong>.</li>
            <li>Or describe the need in plain words in the box below.</li>
          </ul>
        </Panel>
      </div>
      <ChatBloodRequest />
    </div>
  );
}
