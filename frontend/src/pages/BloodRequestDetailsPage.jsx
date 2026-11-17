import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { listHospitals } from '../api/hospitals';
import { getBloodRequest, updateBloodRequestStatus, orchestrateBloodRequest } from '../api/bloodRequests';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ResponsesPanel from '../components/coordination/ResponsesPanel';
import OrderStatusPanel from '../components/coordination/OrderStatusPanel';
import DonorCandidatesPanel from '../components/coordination/DonorCandidatesPanel';
import { PageHeader, StatTile, StatusPill, UrgencyPill } from '../components/bc';

export default function BloodRequestDetailsPage() {
  const { id } = useParams();
  const requestId = parseInt(id, 10);
  const [request, setRequest] = useState(null);
  const [hospital, setHospital] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await getBloodRequest(requestId);
      setRequest(r);
      const hs = await Promise.resolve(listHospitals()).catch(() => []);
      setHospital((hs || []).find((h) => h.hospital_id === r.hospital_id) || null);
      setError(null);
    } catch (err) { setError(err.message || 'Could not load this request.'); } finally { setLoading(false); }
  }, [requestId]);
  useEffect(() => { load(); }, [load]);

  const placeOrder = async () => {
    setBusy(true); setError(null); setMessage(null);
    try {
      await orchestrateBloodRequest(requestId);
      setMessage('Order placed! The nearest blood banks have been notified. Use "Donors who can help" below to alert donors too.');
      await load();
    } catch (err) { setError(err.message || 'We could not place the order. Please try again.'); } finally { setBusy(false); }
  };
  const cancel = async () => {
    setBusy(true); setError(null);
    try { await updateBloodRequestStatus(requestId, 'CANCELLED'); await load(); }
    catch (err) { setError(err.message || 'Could not cancel the request.'); } finally { setBusy(false); }
  };

  if (loading) return <LoadingSpinner message="Loading blood request..." />;
  if (!request) return <div><Link to="/blood-requests">&larr; Back to Blood Requests</Link><div className="alert alert-error" role="alert" style={{ marginTop: '1rem' }}>{error || 'Request not found.'}</div></div>;

  const closed = request.status === 'FULFILLED' || request.status === 'CANCELLED';
  return (
    <div>
      <Link to="/blood-requests" style={{ fontSize: '.85rem' }}>&larr; Back to Blood Requests</Link>
      <PageHeader title={`Blood Request #${request.request_id}`} subtitle="Place the order, alert donors, and track who confirms.">
        <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <StatusPill status={request.status} /> <UrgencyPill urgency={request.urgency} />
          {!closed && (request.order_placed_at
            ? <span data-testid="order-placed-badge" className="bc-pill bc-p-green">✓ Order placed</span>
            : <button type="button" className="bc-btn" disabled={busy} onClick={placeOrder}>{busy ? 'Placing…' : 'Place Order'}</button>)}
          {!closed && <button type="button" className="bc-btn ghost" disabled={busy} onClick={cancel}>Cancel Request</button>}
          <button type="button" className="bc-btn ghost" onClick={load}>Refresh</button>
        </div>
      </PageHeader>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {message && <div className="alert alert-success" role="status">{message}</div>}

      <div className="bc-stats">
        <StatTile icon="🏥" value={hospital?.name || `Hospital #${request.hospital_id}`} label={hospital?.address || ''} tone="lav" />
        <StatTile icon="🩸" value={request.blood_group} label="Blood group" tone="rose" />
        <StatTile icon="📦" value={request.units_required} label="Units required" tone="peach" />
        <StatTile icon="⏱" value={(request.urgency || '').charAt(0) + (request.urgency || '').slice(1).toLowerCase()} label="Urgency" tone="mint" />
      </div>

      <div style={{ display: 'grid', gap: '1rem' }}>
        <OrderStatusPanel requestId={requestId} />
        <ResponsesPanel requestId={requestId} />
        <DonorCandidatesPanel requestId={requestId} disabled={closed} />
      </div>
    </div>
  );
}
