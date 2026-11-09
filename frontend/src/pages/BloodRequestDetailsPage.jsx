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

  // 3D AI Holographic Order Flow State
  const [orderModal, setOrderModal] = useState({
    isOpen: false,
    step: 0, // 0: Idle, 1: Detecting Location, 2: Arranging Sources, 3: Order Placed!
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

  // 3D AI Complete Match Flow
  const handleCompleteMatch = async (matchId) => {
    const matchObj = matches.find(m => (m.match_id || m.id) === matchId);
    
    setOrderModal({
      isOpen: true,
      step: 1, // Step 1: AI Radar Location Detection
      targetMatch: matchObj,
    });

    // Step 1 -> Step 2 after 1.5s
    setTimeout(() => {
      setOrderModal(prev => ({ ...prev, step: 2 }));
    }, 1500);

    // Step 2 -> Execute Backend API & transition to Step 3 (Order Placed!)
    setTimeout(async () => {
      try {
        await completeMatch(requestId, matchId);
        setOrderModal(prev => ({ ...prev, step: 3 }));
        setSuccessMessage(`Order placed! Units dispatched.`);
        await loadData();
      } catch (err) {
        setError(err.message || `Failed to complete match #${matchId}.`);
        setOrderModal({ isOpen: false, step: 0, targetMatch: null });
      }
    }, 3200);
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
      <style>{`
        @keyframes pulseGlow {
          0% { box-shadow: 0 0 15px rgba(56, 189, 248, 0.4); transform: scale(1); }
          50% { box-shadow: 0 0 35px rgba(56, 189, 248, 0.85); transform: scale(1.05); }
          100% { box-shadow: 0 0 15px rgba(56, 189, 248, 0.4); transform: scale(1); }
        }
        @keyframes spinRadar {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes float3D {
          0% { transform: translateY(0px) rotateX(10deg); }
          50% { transform: translateY(-8px) rotateX(15deg); }
          100% { transform: translateY(0px) rotateX(10deg); }
        }
      `}</style>

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

      {/* 3D Holographic AI LocationAgent & Order Placement Modal */}
      {orderModal.isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '1.5rem',
            perspective: '1000px',
          }}
        >
          <div
            style={{
              background: 'linear-gradient(145deg, #0f172a 0%, #1e293b 100%)',
              border: '1px solid rgba(56, 189, 248, 0.35)',
              borderRadius: '24px',
              maxWidth: '540px',
              width: '100%',
              padding: '2.5rem 2rem',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7), 0 0 30px rgba(56, 189, 248, 0.25)',
              textAlign: 'center',
              color: '#f8fafc',
              animation: 'float3D 4s ease-in-out infinite',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            {/* Top AI Badge */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.25rem 0.85rem',
                borderRadius: '9999px',
                background: 'rgba(56, 189, 248, 0.15)',
                border: '1px solid rgba(56, 189, 248, 0.4)',
                color: '#38bdf8',
                fontSize: '0.75rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: '1.25rem',
              }}
            >
              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#38bdf8', boxShadow: '0 0 8px #38bdf8' }} />
              Autonomous A2A LocationAgent Active
            </div>

            {/* Step 1: AI Radar Location Detection */}
            {orderModal.step === 1 && (
              <div>
                <div
                  style={{
                    width: '90px',
                    height: '90px',
                    margin: '0 auto 1.5rem',
                    borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(56,189,248,0.2) 0%, rgba(15,23,42,0.8) 70%)',
                    border: '2px solid #38bdf8',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '2.5rem',
                    animation: 'pulseGlow 2s infinite',
                    position: 'relative',
                  }}
                >
                  📍
                </div>
                <h3 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#38bdf8', marginBottom: '0.5rem', letterSpacing: '-0.02em' }}>
                  LocationAgent Detecting Hospital...
                </h3>
                <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginBottom: '1.5rem' }}>
                  Computing multi-source GPS routing and calculating emergency transit distance.
                </p>

                <div
                  style={{
                    padding: '1rem',
                    background: 'rgba(30, 41, 59, 0.7)',
                    border: '1px solid rgba(148, 163, 184, 0.15)',
                    borderRadius: '12px',
                    fontSize: '0.85rem',
                    color: '#e2e8f0',
                    textAlign: 'left',
                    lineHeight: '1.6',
                  }}
                >
                  <div>🏥 <strong style={{ color: '#38bdf8' }}>Hospital:</strong> {hospitalInfo?.name || `Hospital #${request.hospital_id}`}</div>
                  <div>📍 <strong style={{ color: '#38bdf8' }}>Location:</strong> {hospitalInfo?.address || 'Sri Aurobindo Marg, Ansari Nagar East, New Delhi 110029'}</div>
                  <div>🧭 <strong style={{ color: '#38bdf8' }}>Coordinates:</strong> {hospitalInfo?.latitude || '28.5672'}° N, {hospitalInfo?.longitude || '77.2100'}° E</div>
                </div>
              </div>
            )}

            {/* Step 2: Sources Being Arranged */}
            {orderModal.step === 2 && (
              <div>
                <div
                  style={{
                    width: '90px',
                    height: '90px',
                    margin: '0 auto 1.5rem',
                    borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(16,185,129,0.2) 0%, rgba(15,23,42,0.8) 70%)',
                    border: '2px solid #10b981',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '2.5rem',
                    animation: 'pulseGlow 2s infinite',
                  }}
                >
                  🔄
                </div>
                <h3 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#10b981', marginBottom: '0.5rem' }}>
                  Sources Being Arranged...
                </h3>
                <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginBottom: '1.5rem' }}>
                  Locking stock hold reservation with <strong>{orderModal.targetMatch?.name || orderModal.targetMatch?.source_name || 'AIIMS Transfusion Center'}</strong>.
                </p>

                <div
                  style={{
                    padding: '1rem',
                    background: 'rgba(30, 41, 59, 0.7)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    borderRadius: '12px',
                    fontSize: '0.85rem',
                    color: '#e2e8f0',
                    textAlign: 'left',
                    lineHeight: '1.6',
                  }}
                >
                  <div>✓ <strong style={{ color: '#10b981' }}>Reserved Units:</strong> {request.units_required} units ({request.blood_group})</div>
                  <div>✓ <strong style={{ color: '#10b981' }}>Transit ETA:</strong> {orderModal.targetMatch?.estimated_time || '~1 min straight-line'}</div>
                  <div>✓ <strong style={{ color: '#10b981' }}>Priority Protocol:</strong> Emergency Dispatch Locked</div>
                </div>
              </div>
            )}

            {/* Step 3: Order Placed! */}
            {orderModal.step === 3 && (
              <div>
                <div
                  style={{
                    width: '90px',
                    height: '90px',
                    margin: '0 auto 1.5rem',
                    borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(16,185,129,0.3) 0%, rgba(15,23,42,0.9) 70%)',
                    border: '2px solid #34d399',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '3rem',
                    boxShadow: '0 0 30px rgba(52, 211, 153, 0.5)',
                  }}
                >
                  🎉
                </div>
                <h2 style={{ fontSize: '1.6rem', fontWeight: 800, color: '#34d399', marginBottom: '0.5rem' }}>
                  Your Order Has Been Placed!
                </h2>
                <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginBottom: '1.5rem' }}>
                  Blood units confirmed and dispatched. Order transitioned to <strong>FULFILLED</strong>.
                </p>

                <div
                  style={{
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(52, 211, 153, 0.3)',
                    borderRadius: '12px',
                    padding: '1.15rem',
                    marginBottom: '1.5rem',
                    textAlign: 'left',
                    fontSize: '0.875rem',
                    lineHeight: '1.6',
                  }}
                >
                  <div style={{ color: '#34d399', fontWeight: 700, marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: '0.75rem' }}>
                    ✓ Order Confirmation Receipt
                  </div>
                  <div>• <strong>Request ID:</strong> #{request.request_id}</div>
                  <div>• <strong>Blood Requirement:</strong> {request.blood_group} ({request.units_required} Units)</div>
                  <div>• <strong>Delivering To:</strong> {hospitalInfo?.name || `Hospital #${request.hospital_id}`}</div>
                  <div>• <strong>Source Provider:</strong> {orderModal.targetMatch?.name || orderModal.targetMatch?.source_name || 'Blood Bank Vault'}</div>
                </div>

                <button
                  style={{
                    width: '100%',
                    padding: '0.85rem',
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    color: '#0f172a',
                    background: 'linear-gradient(135deg, #34d399 0%, #10b981 100%)',
                    border: 'none',
                    borderRadius: '10px',
                    boxShadow: '0 4px 14px rgba(16, 185, 129, 0.4)',
                    cursor: 'pointer',
                  }}
                  onClick={() => setOrderModal({ isOpen: false, step: 0, targetMatch: null })}
                >
                  View Fulfilled Order
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
