import React, { useState } from 'react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import usePolling from '../hooks/usePolling';
import {
  getBankInventory, saveBankInventory, listBankNotifications, respondBankNotification,
} from '../api/portal';

const stockColor = (units) => (units <= 0 ? '#b91c1c' : units < 5 ? '#b45309' : '#15803d');

function InventoryRow({ item, onSaved, onError }) {
  const [units, setUnits] = useState(String(item.available_units));
  const [expiry, setExpiry] = useState(item.expiry_date || '');
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Follow server value after an accept, unless the user is mid-edit.
  React.useEffect(() => {
    if (!dirty) setUnits(String(item.available_units));
  }, [item.available_units, dirty]);

  const save = async () => {
    const n = parseInt(units, 10);
    if (!Number.isInteger(n) || n < 0) { onError('Units must be zero or more.'); return; }
    setSaving(true);
    try {
      await saveBankInventory(item.blood_group, { available_units: n, expiry_date: expiry || undefined });
      setDirty(false);
      await onSaved();
    } catch (err) {
      onError(err.message || 'Could not save stock.');
    } finally { setSaving(false); }
  };

  return (
    <tr data-testid={`inv-${item.blood_group}`}>
      <td><strong>{item.blood_group}</strong></td>
      <td style={{ color: stockColor(item.available_units), fontWeight: 600 }}>{item.available_units}</td>
      <td>
        <input aria-label={`Units ${item.blood_group}`} type="number" min="0" className="form-input" style={{ width: 90 }}
          value={units} onChange={(e) => { setUnits(e.target.value); setDirty(true); }} />
      </td>
      <td>
        <input aria-label={`Expiry ${item.blood_group}`} type="date" className="form-input" value={expiry}
          onChange={(e) => { setExpiry(e.target.value); setDirty(true); }} />
      </td>
      <td><Button size="sm" loading={saving} disabled={!dirty} onClick={save}>Save</Button></td>
    </tr>
  );
}

function RequestRow({ n, onDone, onError, onInfo }) {
  const stock = n.in_stock_units ?? 0;
  const max = Math.min(stock, n.required_units);
  const [qty, setQty] = useState(String(max));
  const [busy, setBusy] = useState(false);

  const send = async (body, okMsg) => {
    setBusy(true);
    try {
      await respondBankNotification(n.id, body);
      onInfo(okMsg);
      await onDone();
    } catch (err) {
      onError(err.message || 'Could not send the answer.');
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="bank-request" style={{ padding: '0.75rem 0', borderBottom: '1px solid var(--color-border)' }}>
      <strong>{n.hospital_name || `Request #${n.blood_request_id}`}</strong>{' '}
      <span className="badge badge-neutral">{n.blood_group}</span>{' '}
      {n.urgency && <span className="badge badge-neutral">{n.urgency}</span>}
      <p className="text-secondary" style={{ margin: '0.25rem 0' }}>
        {n.hospital_address || ''} · needs <strong>{n.required_units}</strong> unit(s) · you have{' '}
        <strong style={{ color: stockColor(stock) }}>{stock}</strong> of {n.inventory_blood_group || n.blood_group}
      </p>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <input aria-label="Units to supply" type="number" min="1" max={max} className="form-input" style={{ width: 90 }}
          value={qty} onChange={(e) => setQty(e.target.value)} />
        <Button loading={busy} disabled={max < 1}
          onClick={() => {
            const q = parseInt(qty, 10);
            if (!(q >= 1 && q <= max)) { onError(`Enter between 1 and ${max} units.`); return; }
            const partial = q < n.required_units;
            send({ response_status: partial ? 'partially_available' : 'accepted', confirmed_available_units: q },
              `Confirmed ${q} unit(s). Your stock has been reduced.`);
          }}>
          Accept
        </Button>
        <Button variant="outline" disabled={busy}
          onClick={() => send({ response_status: 'rejected', rejection_reason: 'Not enough stock' }, 'Declined.')}>
          Decline
        </Button>
      </div>
    </div>
  );
}

export default function BloodBankDashboardPage() {
  const inv = usePolling(getBankInventory, 5000);
  const reqs = usePolling(listBankNotifications, 5000);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);

  const refreshAll = async () => { await Promise.all([inv.refresh(), reqs.refresh()]); };
  const fail = (m) => { setInfo(null); setError(m); };
  const ok = (m) => { setError(null); setInfo(m); };

  if (inv.loading && !inv.data) return <LoadingSpinner message="Loading your blood bank..." />;

  const items = inv.data?.items || [];
  const all = reqs.data?.items || [];
  const open = all.filter((n) => n.response_status === 'pending');
  const done = all.filter((n) => n.response_status !== 'pending');
  const bank = inv.data?.bank;

  return (
    <div>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>{bank?.name || 'Blood bank'}</h1>
      <p className="text-secondary" style={{ marginBottom: '1.5rem' }}>{bank ? `${bank.address || ''} ${bank.city || ''}` : ''}</p>

      {(error || inv.error) && <div className="alert alert-error" role="alert" style={{ marginBottom: '1rem' }}>{error || inv.error}</div>}
      {info && <div className="alert alert-success" style={{ marginBottom: '1rem' }}>{info}</div>}

      <Card title={`Incoming requests (${open.length})`}>
        {open.length === 0 ? <EmptyState title="No open requests" message="Hospital requests for your stock appear here." />
          : open.map((n) => <RequestRow key={n.id} n={n} onDone={refreshAll} onError={fail} onInfo={ok} />)}
      </Card>

      <div style={{ height: '1rem' }} />
      <Card title="Inventory" subtitle="Units on hand by blood group. Accepted requests are deducted automatically.">
        <div className="table-responsive">
          <table className="table">
            <thead><tr><th>Group</th><th>On hand</th><th>Set units</th><th>Earliest expiry</th><th /></tr></thead>
            <tbody>
              {items.map((it) => (
                <InventoryRow key={`${it.blood_group}-${it.component_type}`} item={it} onSaved={refreshAll} onError={fail} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: '1rem' }} />
      <Card title="Answered requests">
        {done.length === 0 ? <p className="text-secondary">Nothing yet.</p> : (
          <table className="table"><thead><tr><th>Request</th><th>Group</th><th>Needed</th><th>Your answer</th><th>Units</th></tr></thead>
            <tbody>{done.map((n) => (
              <tr key={n.id}><td>#{n.blood_request_id}</td><td>{n.blood_group}</td><td>{n.required_units}</td>
                <td>{n.response_status}</td><td>{n.confirmed_available_units ?? '—'}</td></tr>
            ))}</tbody></table>
        )}
      </Card>
    </div>
  );
}
