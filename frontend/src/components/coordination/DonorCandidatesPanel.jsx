import React, { useState } from 'react';
import usePolling from '../../hooks/usePolling';
import { getDonorCandidates, alertDonors } from '../../api/portal';
import { Panel } from '../bc';

const STATE = {
  not_notified: ['Not notified', 'gray'], pending: ['Waiting', 'amber'], accepted: ['Accepted', 'green'],
  rejected: ['Declined', 'gray'], declined: ['Declined', 'gray'], unavailable: ['Declined', 'gray'],
};

export default function DonorCandidatesPanel({ requestId, disabled }) {
  const { data, error, refresh } = usePolling(() => getDonorCandidates(requestId), 6000, [requestId]);
  const [picked, setPicked] = useState({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  if (error && !data) return <Panel title="Donors who can help"><p>{error}</p></Panel>;
  if (!data) return null;
  const donors = data.donors || [];
  const fresh = donors.filter((d) => d.state === 'not_notified');
  const chosen = fresh.filter((d) => picked[d.donor_id]).map((d) => d.donor_id);
  const send = async (ids, label) => {
    setBusy(true); setNote('');
    try { const r = await alertDonors(requestId, ids); setNote(r?.message || label); setPicked({}); await refresh(); }
    catch (e) { setNote(e?.message || 'Could not notify the donors.'); } finally { setBusy(false); }
  };
  const nearest = fresh.slice(0, Math.max(1, data.units_required)).map((d) => d.donor_id);
  return (
    <Panel title="Donors who can help"
      action={!disabled && (
        <span style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
          <button type="button" className="bc-btn ghost sm" disabled={busy || chosen.length === 0} onClick={() => send(chosen, 'Selected donors notified.')}>
            Notify selected ({chosen.length})
          </button>
          <button type="button" className="bc-btn sm" disabled={busy || nearest.length === 0} onClick={() => send(nearest, 'Nearest donors notified.')}>
            Notify nearest {nearest.length || ''} donor(s)
          </button>
        </span>
      )}>
      <p className="bc-sub" style={{ marginTop: 0 }}>
        Nearby donors whose blood can be given to this patient. Notified donors see the request in their own dashboard and answer there.
      </p>
      {note && <p role="status" style={{ fontWeight: 600 }}>{note}</p>}
      {donors.length === 0 ? <p>No eligible donors were found near this hospital.</p> : (
        <table className="bc-table">
          <thead><tr><th /><th>Donor</th><th>Blood group</th><th>Distance</th><th>Travel</th><th>Status</th><th /></tr></thead>
          <tbody>
            {donors.map((d) => {
              const [label, tone] = STATE[d.state] || [d.state, 'gray'];
              return (
                <tr key={d.donor_id}>
                  <td>{d.state === 'not_notified' && !disabled && (
                    <input type="checkbox" aria-label={`Select ${d.name}`} checked={Boolean(picked[d.donor_id])} onChange={(e) => setPicked((p) => ({ ...p, [d.donor_id]: e.target.checked }))} />)}</td>
                  <td><strong>{d.name}</strong><br /><small>{d.city}</small></td>
                  <td>{d.blood_group}</td>
                  <td>{d.distance_km != null ? `${Number(d.distance_km).toFixed(1)} km` : '—'}</td>
                  <td>{d.eta_minutes != null ? `~${d.eta_minutes} min` : '—'}</td>
                  <td><span className={`bc-pill bc-p-${tone}`}>{label}</span></td>
                  <td>{d.state === 'not_notified' && !disabled && (
                    <button type="button" className="bc-btn ghost sm" disabled={busy} onClick={() => send([d.donor_id], 'Donor notified.')}>Notify</button>)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
