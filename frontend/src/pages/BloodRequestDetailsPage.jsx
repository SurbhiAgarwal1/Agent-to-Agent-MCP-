import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { listHospitals } from "../api/hospitals";
import {
  getBloodRequest,
  updateBloodRequestStatus,
  getRequestMatches,
  coordinateBloodRequest,
  orchestrateBloodRequest,
  completeMatch,
  rejectMatch,
} from '../api/bloodRequests';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import LoadingSpinner from '../components/common/LoadingSpinner';
import StatusBadge from '../components/common/StatusBadge';
import UrgencyBadge from '../components/common/UrgencyBadge';
import BloodGroupBadge from '../components/common/BloodGroupBadge';
import CoordinationWorkflow from '../components/coordination/CoordinationWorkflow';
import MatchesList from '../components/matching/MatchesList';
import useAuth from '../hooks/useAuth';

export default function BloodRequestDetailsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role?.toUpperCase() === 'ADMIN';
  const { id } = useParams();
  const requestId = parseInt(id, 10);

  const [request, setRequest] = useState(null);
  const [hospitalInfo, setHospitalInfo] = useState(null);
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // Agent execution state
  const [coordinating, setCoordinating] = useState(false);
  const [coordinationResult, setCoordinationResult] = useState(null);
  const [matchActionLoading, setMatchActionLoading] = useState(false);

  // Animated Order Placement & Location Detection Simulation State
  const [orderModal, setOrderModal] = useState({
    isOpen: false,
    step: 0, // 0: Idle, 1: Detecting Location, 2: Arranging Sources, 3: Order Placed & Fulfilled!
    targetMatch: null,
  });

  const loadData = useCallback(async () => {
    if (isNaN(requestId)) {
      setError('Invalid Blood Request ID.');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const reqData = await getBloodRequest(requestId);
      setRequest(reqData);
      try {
        const hList = await listHospitals();
        const found = hList?.find(h => h.hospital_id === reqData.hospital_id);
        if (found) setHospitalInfo(found);
      } catch (e) {}

      // Attempt to load existing candidate matches preview if available
      try {
        const matchesData = await getRequestMatches(requestId);
        if (matchesData?.matches) {
          setMatches(matchesData.matches);
        }
      } catch {
        // Preview might not be populated yet if request has not been coordinated
      }
    } catch (err) {
      setError(err.message || 'Failed to load blood request details.');
    } finally {
      setLoading(false);
    }
  }, [requestId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Trigger full lifecycle coordinator
  const handleCoordinate = async () => {
    setCoordinating(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await coordinateBloodRequest(requestId);
      setCoordinationResult(res);
      if (res?.ranked_matches) {
        setMatches(res.ranked_matches);
      }
      setSuccessMessage('Blood availability has been checked and the request progress was updated.');
      const updatedReq = await getBloodRequest(requestId);
      setRequest(updatedReq);
    } catch (err) {
      setError(err.message || 'We could not update the request progress. Please try again.');
    } finally {
      setCoordinating(false);
    }
  };

  // Trigger autonomous orchestrator (allocation + reservation)
  const handleOrchestrate = async () => {
    setCoordinating(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await orchestrateBloodRequest(requestId);
      setCoordinationResult(res);
      if (res?.ranked_matches || res?.allocations) {
        setMatches(res.ranked_matches || res.allocations || []);
      }
      setSuccessMessage('Blood allocation has been updated successfully.');
      const updatedReq = await getBloodRequest(requestId);
      setRequest(updatedReq);
    } catch (err) {
      setError(err.message || 'We could not update the blood allocation. Please try again.');
    } finally {
      setCoordinating(false);
    }
  };

  // Match fulfillment action with animated LocationAgent Detection & Order Placement flow
  const handleCompleteMatch = async (matchId) => {
    const matchObj = matches.find(m => (m.match_id || m.id) === matchId);
    
    // Open animated simulation modal
    setOrderModal({
      isOpen: true,
      step: 1, // Step 1: LocationAgent auto-detecting hospital & route
      targetMatch: matchObj,
    });

    // Step 1 -> Step 2 after 1.4s
    setTimeout(() => {
      setOrderModal(prev => ({ ...prev, step: 2 }));
    }, 1400);

    // Step 2 -> Execute Backend API & transition to Step 3 (Order Placed & Fulfilled!) after 2.6s
    setTimeout(async () => {
      try {
        await completeMatch(requestId, matchId);
        setOrderModal(prev => ({ ...prev, step: 3 }));
        setSuccessMessage(`Order placed! Match #${matchId} completed and blood units dispatched.`);
        await loadData();
      } catch (err) {
        setError(err.message || `Failed to complete match #${matchId}.`);
        setOrderModal({ isOpen: false, step: 0, targetMatch: null });
      }
    }, 2800);
  };

  // Match fulfillment action: reject match
  const handleRejectMatch = async (matchId, reason) => {
    setMatchActionLoading(true);
    setError(null);
    try {
      await rejectMatch(requestId, matchId, reason);
      setSuccessMessage(`Match #${matchId} rejected and units released.`);
      await loadData();
    } catch (err) {
      setError(err.message || `Failed to reject match #${matchId}.`);
    } finally {
      setMatchActionLoading(false);
    }
  };

  // Manual status change (e.g. CANCELLED)
  const handleStatusUpdate = async (newStatus) => {
    if (!window.confirm(`Are you sure you want to mark this request as ${newStatus}?`)) return;
    try {
      const updated = await updateBloodRequestStatus(requestId, newStatus);
      setRequest(updated);
      setSuccessMessage(`Request status updated to ${newStatus}.`);
    } catch (err) {
      setError(err.message || 'Failed to update request status.');
    }
  };

  if (loading) {
    return <LoadingSpinner message={`Loading blood request #${requestId}...`} />;
  }

  if (error && !request) {
    return (
      <div>
        <Link to="/blood-requests" className="text-secondary" style={{ fontSize: '0.875rem' }}>
          &larr; Back to Blood Requests
        </Link>
        <div className="alert alert-error" style={{ marginTop: '1rem' }}>
          {error}
        </div>
      </div>
    );
  }

  const isResolved = request?.status === 'FULFILLED' || request?.status === 'CANCELLED';

  return (
    <div>
      {/* Top Breadcrumb & Actions */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <Link to="/blood-requests" className="text-secondary" style={{ fontSize: '0.875rem' }}>
            &larr; Back to Blood Requests
          </Link>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.25rem' }}>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--color-text-main)' }}>
              Emergency Blood Request #{request.request_id}
            </h1>
            <StatusBadge status={request.status} />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {!isResolved && (
            <>
              {isAdmin ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCoordinate}
                    loading={coordinating}
                    title="Run the end-to-end A2A coordination workflow"
                  >
                    Run A2A Coordination
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleOrchestrate}
                    loading={coordinating}
                    title="Execute autonomous allocation and reserve candidate holds"
                  >
                    Orchestrate & Allocate
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCoordinate}
                    loading={coordinating}
                  >
                    Find Available Blood
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleOrchestrate}
                    loading={coordinating}
                  >
                    Confirm Booking / Place Order
                  </Button>
                </>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleStatusUpdate('CANCELLED')}
                title="Cancel request"
              >
                Cancel Request
              </Button>
            </>
          )}
          <Button variant="outline" size="sm" onClick={loadData}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Notifications / Alerts */}
      {error && (
        <div className="alert alert-error" style={{ marginBottom: '1.25rem' }}>
          {error}
        </div>
      )}
      {successMessage && (
        <div className="alert alert-success" style={{ marginBottom: '1.25rem' }}>
          {successMessage}
        </div>
      )}

      {/* Overview Metadata Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <Card>
          <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
            HOSPITAL
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, marginTop: '0.25rem' }}>
            {hospitalInfo?.name || `Hospital #${request.hospital_id}`}
          </div>
        </Card>

        <Card>
          <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
            BLOOD GROUP
          </div>
          <div style={{ marginTop: '0.25rem' }}>
            <BloodGroupBadge group={request.blood_group} />
          </div>
        </Card>

        <Card>
          <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
            UNITS REQUIRED
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, marginTop: '0.25rem' }}>
            {request.units_required} <span style={{ fontSize: '0.875rem', fontWeight: 400 }}>units</span>
          </div>
        </Card>

        <Card>
          <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
            URGENCY LEVEL
          </div>
          <div style={{ marginTop: '0.25rem' }}>
            <UrgencyBadge urgency={request.urgency} />
          </div>
        </Card>
      </div>

      {/* Request Progress Tracker */}
      <div style={{ marginBottom: '1.5rem' }}>
        {isAdmin ? (
          <CoordinationWorkflow execution={coordinationResult} isRunning={coordinating} />
        ) : (
          <Card title="Request Progress">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                gap: '0.75rem',
              }}
            >
              {[
                ['Request received', true],
                ['Blood availability checked', !!coordinationResult || request.status !== 'PENDING'],
                ['Sources being arranged', ['PROCESSING', 'MATCHED', 'PARTIALLY_FULFILLED'].includes(request.status) || orderModal.step >= 2],
                ['Fulfilled', request.status === 'FULFILLED' || orderModal.step >= 3],
              ].map(([label, done]) => (
                <div
                  key={label}
                  style={{
                    padding: '0.8rem',
                    borderRadius: 'var(--radius-md)',
                    border: done ? '1px solid #10b981' : '1px solid var(--color-border)',
                    backgroundColor: done ? 'rgba(16, 185, 129, 0.08)' : 'var(--color-bg)',
                    transition: 'all 0.3s ease',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.875rem', color: done ? '#047857' : 'inherit' }}>
                    {done ? '✓ ' : '○ '}{label}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* Candidate Matches Table */}
      <Card
        title={`Available Blood Sources & Allocations (${matches.length})`}
        actions={
          <span className="text-secondary" style={{ fontSize: '0.8125rem' }}>
            Compatible Donors & Blood Banks
          </span>
        }
      >
        <MatchesList
          matches={matches}
          requestId={requestId}
          onComplete={handleCompleteMatch}
          onReject={handleRejectMatch}
          actionLoading={matchActionLoading}
        />
      </Card>

      {/* Interactive Location Detection & Order Placement Modal */}
      {orderModal.isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: '#fff',
              borderRadius: '12px',
              maxWidth: '520px',
              width: '100%',
              padding: '2rem',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2)',
              textAlign: 'center',
              animation: 'fadeIn 0.3s ease',
            }}
          >
            {/* Step 1: LocationAgent Detecting Location */}
            {orderModal.step === 1 && (
              <div>
                <div style={{ fontSize: '3rem', marginBottom: '1rem', animation: 'bounce 1s infinite' }}>
                  📍
                </div>
                <h3 style={{ fontSize: '1.35rem', fontWeight: 700, marginBottom: '0.5rem', color: '#1e293b' }}>
                  LocationAgent Detecting Hospital Location...
                </h3>
                <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: '1.25rem' }}>
                  Triangulating delivery destination and calculating optimal emergency transit route.
                </p>
                <div
                  style={{
                    padding: '0.75rem 1rem',
                    backgroundColor: '#f1f5f9',
                    borderRadius: '8px',
                    fontSize: '0.85rem',
                    color: '#334155',
                    textAlign: 'left',
                  }}
                >
                  <div>🏥 <strong>Hospital:</strong> {hospitalInfo?.name || `Hospital #${request.hospital_id}`}</div>
                  <div>📍 <strong>Address:</strong> {hospitalInfo?.address || 'Sri Aurobindo Marg, Ansari Nagar East, New Delhi 110029'}</div>
                  <div>🧭 <strong>Coordinates:</strong> {hospitalInfo?.latitude || '28.5672'}° N, {hospitalInfo?.longitude || '77.2100'}° E</div>
                </div>
              </div>
            )}

            {/* Step 2: Sources being arranged */}
            {orderModal.step === 2 && (
              <div>
                <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>
                  🔄
                </div>
                <h3 style={{ fontSize: '1.35rem', fontWeight: 700, marginBottom: '0.5rem', color: '#0284c7' }}>
                  Sources Being Arranged...
                </h3>
                <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: '1.25rem' }}>
                  Reserving units from closest vault: <strong>{orderModal.targetMatch?.name || orderModal.targetMatch?.source_name || 'AIIMS Department of Transfusion Medicine'}</strong>
                </p>
                <div
                  style={{
                    padding: '0.75rem 1rem',
                    backgroundColor: '#e0f2fe',
                    borderRadius: '8px',
                    fontSize: '0.85rem',
                    color: '#0369a1',
                    textAlign: 'left',
                  }}
                >
                  <div>✓ <strong>Units Reserved:</strong> {request.units_required} units ({request.blood_group})</div>
                  <div>✓ <strong>Transit ETA:</strong> {orderModal.targetMatch?.estimated_time || '~1 min straight-line'}</div>
                  <div>✓ <strong>Urgency Protocol:</strong> {request.urgency}</div>
                </div>
              </div>
            )}

            {/* Step 3: Order Placed & Fulfilled! */}
            {orderModal.step === 3 && (
              <div>
                <div style={{ fontSize: '3.5rem', marginBottom: '1rem' }}>
                  🎉
                </div>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#059669', marginBottom: '0.5rem' }}>
                  Your Order Has Been Placed!
                </h2>
                <p style={{ fontSize: '0.95rem', color: '#475569', marginBottom: '1.25rem' }}>
                  Blood units have been confirmed and dispatched. The request has been transitioned to <strong>FULFILLED</strong>.
                </p>

                <div
                  style={{
                    backgroundColor: '#ecfdf5',
                    border: '1px solid #a7f3d0',
                    borderRadius: '8px',
                    padding: '1rem',
                    marginBottom: '1.5rem',
                    textAlign: 'left',
                    fontSize: '0.875rem',
                  }}
                >
                  <div style={{ color: '#065f46', fontWeight: 600, marginBottom: '0.25rem' }}>
                    ✓ Order Summary
                  </div>
                  <div>• <strong>Request:</strong> #{request.request_id}</div>
                  <div>• <strong>Blood Group:</strong> {request.blood_group} ({request.units_required} Units)</div>
                  <div>• <strong>Delivering To:</strong> {hospitalInfo?.name || `Hospital #${request.hospital_id}`}</div>
                  <div>• <strong>Source:</strong> {orderModal.targetMatch?.name || orderModal.targetMatch?.source_name || 'Blood Bank Vault'}</div>
                </div>

                <button
                  className="btn btn-primary"
                  style={{ width: '100%', padding: '0.75rem', fontSize: '1rem', backgroundColor: '#059669', borderColor: '#059669' }}
                  onClick={() => setOrderModal({ isOpen: false, step: 0, targetMatch: null })}
                >
                  View Updated Order
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
