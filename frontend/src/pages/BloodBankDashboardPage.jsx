import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import LoadingSpinner from '../components/common/LoadingSpinner';
import usePolling from '../hooks/usePolling';
import { getBankInventory, saveBankInventory, listBankNotifications, respondBankNotification } from '../api/portal';
import { PageHeader, StatTile, Panel, Columns, Donut, UrgencyPill, fmtWhen } from '../components/bc';

const GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const COMPONENTS = [['packed_red_blood_cells', 'Packed red cells'], ['whole_blood', 'Whole blood']];
const ANSWER = { pending: ['Awaiting your reply', 'amber'], accepted: ['Confirmed', 'green'], partially_available: ['Partly confirmed', 'blue'], rejected: ['Declined', 'gray'], unavailable: ['Declined', 'gray'] };

export function useBank() {
  const inv = usePolling(getBankInventory, 5000);
  const reqs = usePolling(listBankNotifications, 5000);
  const items = inv.data?.items || [];
  const all = reqs.data?.items || [];
  const soon = Date.now() + 7 * 86400000;
  const isSoon = (i) => i.expiry_date && new Date(i.expiry_date).getTime() <= soon && i.available_units > 0;
  return {
    inv, reqs, bank: inv.data?.bank, items, all,
    open: all.filter((n) => n.response_status === 'pending'),
    done: all.filter((n) => n.response_status !== 'pending'),
    total: items.reduce((s, i) => s + (i.available_units || 0), 0),
    reserved: items.reduce((s, i) => s + (i.reserved_units || 0), 0),
    expiring: items.filter(isSoon).reduce((s, i) => s + i.available_units, 0),
    isSoon,
    refresh: () => Promise.all([inv.refresh(), reqs.refresh()]),
  };
}

export function BankHeader({ bank, title, subtitle }) {
  return <PageHeader title={title} subtitle={subtitle || (bank ? `${bank.name} · ${bank.address || ''} ${bank.city || ''}` : '')} />;
}

export default function BloodBankDashboardPage() {
  const b = useBank();
  if (b.inv.loading && !b.inv.data) return <LoadingSpinner message="Loading your blood bank..." />;
  const perGroup = GROUPS.map((g) => ({ label: g, value: b.items.filter((i) => i.blood_group === g).reduce((s, i) => s + i.available_units, 0) }));
  const free = Math.max(0, b.total - b.reserved - b.expiring);
  return (
    <div>
      <PageHeader title="Blood Bank Dashboard" subtitle={b.bank ? `${b.bank.name}: manage inventory, requests and donations.` : 'Manage inventory, requests and donations.'} />
      {b.inv.error && <div className="alert alert-error" role="alert">{b.inv.error}</div>}
      <div className="bc-stats">
        <StatTile icon="🧊" value={b.total} label="Total Units" tone="lav" />
        <StatTile icon="🔒" value={b.reserved} label="Units Reserved" tone="peach" />
        <StatTile icon="📥" value={b.open.length} label="Incoming Requests" tone="lav" />
        <StatTile icon="⏰" value={b.expiring} label="Expiring Soon" tone="rose" />
      </div>
      <div className="bc-grid two">
        <Panel title="Blood Inventory (Units)"><Columns rows={perGroup} /></Panel>
        <Panel title="Inventory Status">
          <Donut centre={b.total} caption="Units" segments={[
            { label: 'Available', value: free, color: '#22a05a' }, { label: 'Reserved', value: b.reserved, color: '#f0b429' }, { label: 'Expiring Soon', value: b.expiring, color: '#e04b4b' }]} />
        </Panel>
      </div>
      <Panel title="Recent Requests from Hospitals" action={<Link to="/bank/requests" className="bc-btn ghost sm">Open requests</Link>}>
        {b.all.length === 0 ? <p>Hospital requests for your stock appear here.</p> : (
          <table className="bc-table">
            <thead><tr><th>Hospital</th><th>Blood Group</th><th>Units</th><th>Priority</th><th>Status</th></tr></thead>
            <tbody>
              {b.all.slice(0, 5).map((n) => {
                const [label, tone] = ANSWER[n.response_status] || [n.response_status, 'gray'];
                return (
                  <tr key={n.id}>
                    <td><strong>{n.hospital_name || `Request #${n.blood_request_id}`}</strong></td>
                    <td><strong>{n.blood_group}</strong></td><td>{n.required_units}</td>
                    <td><UrgencyPill urgency={n.urgency} /></td><td><span className={`bc-pill bc-p-${tone}`}>{label}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

/* ---------- Inventory ---------- */
function StockEditor({ group, component, item, onSaved, onError }) {
  const [units, setUnits] = useState(String(item?.available_units ?? 0));
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  React.useEffect(() => { if (!dirty) setUnits(String(item?.available_units ?? 0)); }, [item?.available_units, dirty]);
  const save = async () => {
    const n = parseInt(units, 10);
    if (!Number.isInteger(n) || n < 0) { onError('Units must be zero or more.'); return; }
    setSaving(true);
    try { await saveBankInventory(group, { available_units: n, component_type: component }); setDirty(false); await onSaved(); }
    catch (err) { onError(err.message || 'Could not save stock.'); } finally { setSaving(false); }
  };
  return (
    <span style={{ display: 'inline-flex', gap: '.4rem', alignItems: 'center' }}>
      <input aria-label={`Units ${group} ${component}`} type="number" min="0" className="bc-input" style={{ width: 80 }} value={units}
        onChange={(e) => { setUnits(e.target.value); setDirty(true); }} />
      <button type="button" className="bc-btn sm" disabled={saving} onClick={save} aria-label={`Save ${group} ${component}`}>{saving ? '…' : 'Save'}</button>
    </span>
  );
}

export function BankInventoryPage() {
  const b = useBank();
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const onSaved = async () => { setError(null); setSaved(true); await b.refresh(); setTimeout(() => setSaved(false), 2500); };
  if (b.inv.loading && !b.inv.data) return <LoadingSpinner message="Loading inventory..." />;
  return (
    <div>
      <BankHeader bank={b.bank} title="Blood Inventory" subtitle="Current stock of blood units at your blood bank. Accepted requests are deducted automatically." />
      {(error || b.inv.error) && <div className="alert alert-error" role="alert">{error || b.inv.error}</div>}
      {saved && <div className="alert alert-success" role="status">Stock saved.</div>}
      <Panel>
        <table className="bc-table">
          <thead><tr><th>Blood Group</th>{COMPONENTS.map(([, l]) => <th key={l}>{l}</th>)}<th>Reserved</th><th>Expiring (≤7 days)</th><th>Status</th></tr></thead>
          <tbody>
            {GROUPS.map((g) => {
              const rows = Object.fromEntries(b.items.filter((i) => i.blood_group === g).map((i) => [i.component_type, i]));
              const sum = Object.values(rows).reduce((s, i) => s + i.available_units, 0);
              const reserved = Object.values(rows).reduce((s, i) => s + (i.reserved_units || 0), 0);
              const exp = Object.values(rows).filter(b.isSoon).reduce((s, i) => s + i.available_units, 0);
              const tone = sum <= 0 ? 'red' : sum < 25 ? 'amber' : 'green';
              return (
                <tr key={g} data-testid={`inv-${g}`}>
                  <td><strong>{g}</strong></td>
                  {COMPONENTS.map(([c]) => <td key={c}><StockEditor group={g} component={c} item={rows[c]} onSaved={onSaved} onError={setError} /></td>)}
                  <td>{reserved}</td><td style={{ color: exp ? '#b91c1c' : undefined, fontWeight: 700 }}>{exp}</td>
                  <td><span className={`bc-pill bc-p-${tone}`}>{sum <= 0 ? 'Out' : sum < 25 ? 'Low' : 'Healthy'}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

/* ---------- Requests (accept / decline) ---------- */
function RequestRow({ n, onDone, onError, onInfo }) {
  const stock = n.in_stock_units ?? 0;
  const max = Math.min(stock, n.required_units);
  const [qty, setQty] = useState(String(max));
  const [busy, setBusy] = useState(false);
  const send = async (body, okMsg) => {
    setBusy(true);
    try { await respondBankNotification(n.id, body); onInfo(okMsg); await onDone(); }
    catch (err) { onError(err.message || 'Could not send the answer.'); } finally { setBusy(false); }
  };
  return (
    <div data-testid="bank-request" className="bc-row" style={{ alignItems: 'flex-start' }}>
      <div className="ico" aria-hidden="true">🩸</div>
      <div className="grow">
        <b>{n.hospital_name || `Request #${n.blood_request_id}`} <span className="bc-pill bc-p-red">{n.blood_group}</span> <UrgencyPill urgency={n.urgency} /></b>
        <span>{n.hospital_address || ''} · needs <strong>{n.required_units}</strong> unit(s) · you have <strong>{stock}</strong> of {n.inventory_blood_group || n.blood_group}</span>
        <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center', flexWrap: 'wrap', marginTop: '.6rem' }}>
          <input aria-label="Units to supply" type="number" min="1" max={max} className="bc-input" style={{ width: 90 }} value={qty} onChange={(e) => setQty(e.target.value)} />
          <button type="button" className="bc-btn sm" disabled={busy || max < 1} onClick={() => {
            const q = parseInt(qty, 10);
            if (!(q >= 1 && q <= max)) { onError(`Enter between 1 and ${max} units.`); return; }
            send({ response_status: q < n.required_units ? 'partially_available' : 'accepted', confirmed_available_units: q }, `Confirmed ${q} unit(s). Your stock has been reduced.`);
          }}>Accept</button>
          <button type="button" className="bc-btn ghost sm" disabled={busy}
            onClick={() => send({ response_status: 'rejected', rejection_reason: 'Not enough stock' }, 'Declined.')}>Decline</button>
        </div>
      </div>
      <span style={{ color: '#6b7280', fontSize: '.8rem' }}>{fmtWhen(n.attempted_at)}</span>
    </div>
  );
}

export function BankRequestsPage() {
  const b = useBank();
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const fail = (m) => { setInfo(null); setError(m); };
  const ok = (m) => { setError(null); setInfo(m); };
  if (b.inv.loading && !b.inv.data) return <LoadingSpinner message="Loading requests..." />;
  return (
    <div>
      <BankHeader bank={b.bank} title="Blood Requests" subtitle="Hospital requests for your stock. Accepting takes the units off your inventory and tells the hospital." />
      {(error || b.inv.error || b.reqs.error) && <div className="alert alert-error" role="alert">{error || b.inv.error || b.reqs.error}</div>}
      {info && <div className="alert alert-success" role="status">{info}</div>}
      <Panel title={`Incoming requests (${b.open.length})`}>
        {b.open.length === 0 ? <p>No open requests. They appear here as soon as a hospital orders blood.</p>
          : b.open.map((n) => <RequestRow key={n.id} n={n} onDone={b.refresh} onError={fail} onInfo={ok} />)}
      </Panel>
      <div style={{ height: '1rem' }} />
      <Panel title="Answered requests">
        {b.done.length === 0 ? <p>Nothing yet.</p> : (
          <table className="bc-table">
            <thead><tr><th>Hospital</th><th>Group</th><th>Needed</th><th>Your answer</th><th>Units</th></tr></thead>
            <tbody>{b.done.map((n) => {
              const [label, tone] = ANSWER[n.response_status] || [n.response_status, 'gray'];
              return <tr key={n.id}><td>{n.hospital_name || `#${n.blood_request_id}`}</td><td>{n.blood_group}</td><td>{n.required_units}</td>
                <td><span className={`bc-pill bc-p-${tone}`}>{label}</span></td><td>{n.confirmed_available_units ?? '—'}</td></tr>;
            })}</tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

/* ---------- Donations (supplied units) ---------- */
export function BankDonationsPage() {
  const b = useBank();
  const supplied = b.done.filter((n) => ['accepted', 'partially_available'].includes(n.response_status));
  const units = supplied.reduce((s, n) => s + (n.confirmed_available_units || 0), 0);
  return (
    <div>
      <BankHeader bank={b.bank} title="Donations & Deliveries" subtitle="Blood your bank has committed to hospitals." />
      <div className="bc-stats">
        <StatTile icon="🤝" value={supplied.length} label="Requests served" tone="mint" />
        <StatTile icon="🩸" value={units} label="Units supplied" tone="rose" />
      </div>
      <Panel title="Supplied to hospitals">
        {supplied.length === 0 ? <p>Nothing supplied yet.</p> : (
          <table className="bc-table">
            <thead><tr><th>Hospital</th><th>Blood Group</th><th>Units</th><th>Answered</th></tr></thead>
            <tbody>{supplied.map((n) => <tr key={n.id}><td>{n.hospital_name || `#${n.blood_request_id}`}</td><td>{n.blood_group}</td><td>{n.confirmed_available_units}</td><td>{fmtWhen(n.response_at || n.attempted_at)}</td></tr>)}</tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
