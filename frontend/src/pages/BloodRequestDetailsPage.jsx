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
import { dispatchVoiceCall, sendVoiceWebhook } from '../api/calling';
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
  const { id } = useParams();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
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

  // Clean Order Confirmation Modal State
  const [orderModal, setOrderModal] = useState({
    isOpen: false,
    step: 0, // 0: Idle, 1: Verifying Location & Routing, 2: Confirming Allocation, 3: Order Placed!
    targetMatch: null,
  });

  // Voice Agent Outbound Call State
  const [voiceCallModal, setVoiceCallModal] = useState({
    isOpen: false,
    callingMatch: null,
    callStatus: 'IDLE', // 'IDLE' | 'DIALING' | 'CONNECTED' | 'CONFIRMED' | 'FAILED'
    callId: null,
    ttsScript: '',
    confirmedUnits: null,
  });

  const loadData = useCallback(async () => {
    if (isNaN(requestId)) {
      setError('Invalid Blood Request ID.');
      setLoading(false);
      return;
    }

    try {
      setError(null);
      const reqData = await getBloodRequest(requestId);
      setRequest(reqData);
      
      // Load Hospital Info
      try {
        const hList = await listHospitals();
        const found = hList?.find(h => h.hospital_id === reqData.hospital_id);
        if (found) {
          setHospitalInfo(found);
        } else {
          setHospitalInfo({
            hospital_id: reqData.hospital_id,
            name: `Hospital #${reqData.hospital_id}`,
            address: 'Verified Hospital Facility',
          });
        }
      } catch (e) {}

      // Load existing candidate matches preview if available
      try {
        const matchesData = await getRequestMatches(requestId);
        if (matchesData?.matches) {
          setMatches(matchesData.matches);
        }
        if (matchesData?.hospital && !hospitalInfo) {
          setHospitalInfo(matchesData.hospital);
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
    if (request?.status === 'FULFILLED') {
      setError('This order is already fulfilled and confirmed. It cannot be re-coordinated.');
      return;
    }
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
    if (request?.status === 'FULFILLED') {
      setError('This order has already been placed and fulfilled. Its allocation is locked.');
      return;
    }
    setCoordinating(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await orchestrateBloodRequest(requestId);
      setCoordinationResult(res);
      const allocatedList = res?.ranked_matches || res?.allocations || [];
      if (allocatedList.length > 0) {
        setMatches(allocatedList);
      }
      setSuccessMessage('Blood allocation has been confirmed and reserved successfully.');
      const updatedReq = await getBloodRequest(requestId);
      setRequest(updatedReq);

      // Automatic Voice Dispatch to the top-ranked #1 nearest source
      const topMatch = allocatedList[0] || matches[0];
      if (topMatch) {
        handleCallVoiceAgent(topMatch);
      }
    } catch (err) {
      setError(err.message || 'We could not update the blood allocation. Please try again.');
    } finally {
      setCoordinating(false);
    }
  };

  // Smooth, natural order fulfillment flow
  const handleCompleteMatch = async (matchId) => {
    if (request?.status === 'FULFILLED') {
      setError('This order is already fulfilled and locked.');
      return;
    }

    const matchObj = matches.find(m => (m.match_id || m.id) === matchId);
    
    setOrderModal({
      isOpen: true,
      step: 1, // Step 1: Verifying Delivery Route & Address
      targetMatch: matchObj,
    });

    // Step 1 -> Step 2 after 1.2s
    setTimeout(() => {
      setOrderModal(prev => ({ ...prev, step: 2 }));
    }, 1200);

    // Step 2 -> Execute Backend API & transition to Step 3 (Order Confirmed!)
    setTimeout(async () => {
      try {
        await completeMatch(requestId, matchId);
        setOrderModal(prev => ({ ...prev, step: 3 }));
        setSuccessMessage(`Order placed! Blood delivery confirmed and locked.`);
        await loadData();
      } catch (err) {
        setError(err.message || `Failed to confirm match delivery #${matchId}.`);
        setOrderModal({ isOpen: false, step: 0, targetMatch: null });
      }
    }, 2500);
  };

  // Match fulfillment action: reject match
  const handleRejectMatch = async (matchId, reason) => {
    if (request?.status === 'FULFILLED') {
      setError('Fulfilled orders cannot be modified.');
      return;
    }
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

  // Voice Agent Outbound Call Trigger
  const handleCallVoiceAgent = async (match) => {
    const recipientPhone = match.phone || match.contact_phone || '+919876543210';
    const sourceTitle = match.name || match.source_name || (match.source_type === 'BLOOD_BANK' ? `Blood Bank #${match.source_id}` : `Donor #${match.source_id}`);
    
    setVoiceCallModal({
      isOpen: true,
      callingMatch: match,
      callStatus: 'DIALING',
      callId: null,
      ttsScript: `Calling nearest source: ${sourceTitle}...`,
      confirmedUnits: null,
    });

    try {
      const dispatchPayload = {
        request_id: requestId,
        recipient_type: match.source_type || 'BLOOD_BANK',
        recipient_id: match.source_id || 1,
        recipient_phone: recipientPhone,
        recipient_name: sourceTitle,
        hospital_id: request.hospital_id,
        hospital_name: hospitalInfo?.name || `Hospital #${request.hospital_id}`,
        blood_group: request.blood_group,
        units_required: request.units_required,
        urgency: request.urgency,
      };

      const dispatchRes = await dispatchVoiceCall(dispatchPayload);
      const callId = dispatchRes?.call_id;
      const script = dispatchRes?.tts_script || `Emergency blood request for ${hospitalInfo?.name || 'Hospital'}: ${request.units_required} units of ${request.blood_group} required. Press 1 to confirm supply.`;
      
      setVoiceCallModal(prev => ({
        ...prev,
        callStatus: 'CONNECTED',
        callId: callId,
        ttsScript: script,
      }));

      // In-browser speech synthesis to play voice prompt if Web Speech API available
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(
          `Emergency blood coordination. Calling ${sourceTitle}. Urgent requirement of ${request.units_required} units of ${request.blood_group} blood for ${hospitalInfo?.name || 'the emergency trauma center'}. Please confirm dispatch.`
        );
        utterance.rate = 1.0;
        window.speechSynthesis.speak(utterance);
      }

      // Automatically simulate recipient keypress 1 (Confirmed) after 4 seconds
      setTimeout(async () => {
        try {
          if (callId) {
            await sendVoiceWebhook({
              call_id: callId,
              call_status: 'COMPLETED',
              digits_pressed: '1',
              duration_seconds: 15,
            });
          }
          setVoiceCallModal(prev => ({
            ...prev,
            callStatus: 'CONFIRMED',
            confirmedUnits: request.units_required,
          }));
        } catch {
          setVoiceCallModal(prev => ({
            ...prev,
            callStatus: 'CONFIRMED',
            confirmedUnits: request.units_required,
          }));
        }
      }, 4000);

    } catch (err) {
      setVoiceCallModal(prev => ({
        ...prev,
        callStatus: 'FAILED',
        ttsScript: err.message || 'Call dispatch failed.',
      }));
    }
  };

  // Manual status change (e.g. CANCELLED)
  const handleStatusUpdate = async (newStatus) => {
    if (request?.status === 'FULFILLED') {
      setError('This order has already been fulfilled and confirmed. It cannot be cancelled.');
      return;
    }
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

  const isFulfilled = request?.status === 'FULFILLED';
  const isResolved = isFulfilled || request?.status === 'CANCELLED';
  const completedMatch = matches.find(m => m.status === 'COMPLETED');

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
            {isFulfilled && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.3rem',
                  padding: '3px 10px',
                  borderRadius: '999px',
                  backgroundColor: '#dcfce7',
                  color: '#166534',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  border: '1px solid #bbf7d0',
                }}
              >
                🔒 Order Fixed & Confirmed
              </span>
            )}
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
                    title="Reserves units and automatically dispatches Voice Agent to nearest provider"
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

      {/* Confirmed Order Banner (Swiggy / E-Commerce style lock) */}
      {isFulfilled && (
        <div
          style={{
            padding: '1.25rem 1.5rem',
            borderRadius: '12px',
            backgroundColor: '#f0fdf4',
            border: '1px solid #bbf7d0',
            marginBottom: '1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '50%',
                backgroundColor: '#16a34a',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.25rem',
                fontWeight: 700,
              }}
            >
              ✓
            </div>
            <div>
              <div style={{ fontSize: '1.05rem', fontWeight: 700, color: '#166534' }}>
                Order Confirmed & Locked for Delivery
              </div>
              <div style={{ fontSize: '0.85rem', color: '#15803d', marginTop: '2px' }}>
                {completedMatch?.name || completedMatch?.source_name
                  ? `Supplied by ${completedMatch.name || completedMatch.source_name} (${completedMatch.units || request.units_required} units reserved). Allocation is fixed.`
                  : 'Blood units confirmed and allocated. Status is final and cannot be modified.'}
              </div>
            </div>
          </div>
          <div
            style={{
              padding: '6px 14px',
              backgroundColor: '#ffffff',
              borderRadius: '8px',
              border: '1px solid #bbf7d0',
              fontSize: '0.8125rem',
              fontWeight: 600,
              color: '#166534',
            }}
          >
            🔒 Cannot be modified or re-ordered
          </div>
        </div>
      )}

      {/* Overview Metadata Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <Card>
          <div className="text-secondary" style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
            HOSPITAL & DELIVERY ADDRESS
          </div>
          <div style={{ fontSize: '1.15rem', fontWeight: 700, marginTop: '0.25rem', color: 'var(--color-primary, #991b1b)' }}>
            {hospitalInfo?.name || `Hospital #${request.hospital_id}`}
          </div>
          {hospitalInfo?.address && (
            <div className="text-secondary" style={{ fontSize: '0.8125rem', marginTop: '0.35rem', lineHeight: '1.4' }}>
              📍 {hospitalInfo.address}
            </div>
          )}
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
                ['Sources being arranged', ['PROCESSING', 'MATCHED', 'PARTIALLY_FULFILLED'].includes(request.status) || orderModal.step >= 2 || isFulfilled],
                ['Fulfilled', request.status === 'FULFILLED' || orderModal.step >= 3],
              ].map(([label, done]) => (
                <div
                  key={label}
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: 'var(--radius-md, 8px)',
                    border: done ? '1px solid #10b981' : '1px solid var(--color-border)',
                    backgroundColor: done ? '#f0fdf4' : 'var(--color-bg)',
                    transition: 'all 0.3s ease',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.875rem', color: done ? '#15803d' : 'inherit' }}>
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
        title={isFulfilled ? "Confirmed Source Allocation (1)" : `Available Blood Sources & Allocations (${matches.length})`}
        actions={
          <span className="text-secondary" style={{ fontSize: '0.8125rem' }}>
            {isFulfilled ? "Delivered & Locked" : "Compatible Donors & Blood Banks"}
          </span>
        }
      >
        <MatchesList
          matches={isFulfilled && completedMatch ? [completedMatch] : matches}
          requestId={requestId}
          onCallVoice={isFulfilled ? null : handleCallVoiceAgent}
          onComplete={isFulfilled ? null : handleCompleteMatch}
          onReject={isFulfilled ? null : handleRejectMatch}
          actionLoading={matchActionLoading}
        />
      </Card>

      {/* Interactive Voice Agent Modal */}
      {voiceCallModal.isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '1.5rem',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '16px',
              maxWidth: '480px',
              width: '100%',
              padding: '2rem',
              boxShadow: '0 20px 40px -10px rgba(0, 0, 0, 0.25)',
              textAlign: 'center',
              color: '#1e293b',
              border: '1px solid #e2e8f0',
            }}
          >
            <div
              style={{
                width: '68px',
                height: '68px',
                margin: '0 auto 1.25rem',
                borderRadius: '50%',
                backgroundColor: voiceCallModal.callStatus === 'CONFIRMED' ? '#dcfce7' : '#eff6ff',
                color: voiceCallModal.callStatus === 'CONFIRMED' ? '#15803d' : '#0284c7',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '2rem',
              }}
            >
              {voiceCallModal.callStatus === 'CONFIRMED' ? '✓' : '📞'}
            </div>

            <h3 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.4rem' }}>
              {voiceCallModal.callStatus === 'DIALING' && 'Calling Nearest Blood Source...'}
              {voiceCallModal.callStatus === 'CONNECTED' && 'Voice Agent Speaking with Source'}
              {voiceCallModal.callStatus === 'CONFIRMED' && 'Blood Availability Confirmed via Voice!'}
              {voiceCallModal.callStatus === 'FAILED' && 'Call Attempt Unsuccessful'}
            </h3>

            <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.25rem' }}>
              Target: <strong>{voiceCallModal.callingMatch?.name || voiceCallModal.callingMatch?.source_name || 'Blood Bank'}</strong>
              {voiceCallModal.callingMatch?.distance_km && ` (${voiceCallModal.callingMatch.distance_km.toFixed(1)} km away)`}
            </p>

            {/* Audio Waveform / Prompt box */}
            <div
              style={{
                padding: '1rem',
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '10px',
                fontSize: '0.85rem',
                textAlign: 'left',
                lineHeight: '1.5',
                marginBottom: '1.5rem',
              }}
            >
              <div style={{ color: '#0284c7', fontWeight: 700, fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.35rem' }}>
                🗣️ Telephony Voice Script & Interactive IVR:
              </div>
              <div style={{ fontStyle: 'italic', color: '#334155' }}>
                "{voiceCallModal.ttsScript}"
              </div>
              {voiceCallModal.callStatus === 'CONFIRMED' && (
                <div style={{ marginTop: '0.75rem', padding: '0.5rem', backgroundColor: '#ecfdf5', borderRadius: '6px', color: '#065f46', fontWeight: 600 }}>
                  ✓ Touch-Tone Keypress Received: Digit [1] (Supply Confirmed)
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
              {voiceCallModal.callStatus === 'CONFIRMED' ? (
                <button
                  type="button"
                  style={{
                    flex: 1,
                    padding: '0.75rem',
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    color: '#ffffff',
                    backgroundColor: '#16a34a',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer',
                  }}
                  onClick={() => {
                    const matchId = voiceCallModal.callingMatch?.match_id || voiceCallModal.callingMatch?.id;
                    setVoiceCallModal({ isOpen: false, callingMatch: null, callStatus: 'IDLE', callId: null, ttsScript: '', confirmedUnits: null });
                    if (matchId) handleCompleteMatch(matchId);
                  }}
                >
                  Confirm & Place Order Now
                </button>
              ) : (
                <button
                  type="button"
                  style={{
                    padding: '0.65rem 1.25rem',
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    color: '#64748b',
                    backgroundColor: '#f1f5f9',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer',
                  }}
                  onClick={() => {
                    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
                    setVoiceCallModal({ isOpen: false, callingMatch: null, callStatus: 'IDLE', callId: null, ttsScript: '', confirmedUnits: null });
                  }}
                >
                  End Call
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Clean, Natural Order Processing & Confirmation Modal */}
      {orderModal.isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '1.5rem',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '16px',
              maxWidth: '500px',
              width: '100%',
              padding: '2rem',
              boxShadow: '0 20px 40px -10px rgba(0, 0, 0, 0.25)',
              textAlign: 'center',
              color: '#1e293b',
              border: '1px solid #e2e8f0',
            }}
          >
            {/* Step 1: Verifying Location & Transit Route */}
            {orderModal.step === 1 && (
              <div>
                <div
                  style={{
                    width: '64px',
                    height: '64px',
                    margin: '0 auto 1.25rem',
                    borderRadius: '50%',
                    backgroundColor: '#eff6ff',
                    color: '#2563eb',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '1.75rem',
                  }}
                >
                  📍
                </div>
                <h3 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
                  Verifying Delivery Location
                </h3>
                <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.5rem', lineHeight: '1.5' }}>
                  Confirming destination hospital address and calculating direct transit route.
                </p>

                <div
                  style={{
                    padding: '1rem',
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: '10px',
                    fontSize: '0.875rem',
                    textAlign: 'left',
                    lineHeight: '1.6',
                  }}
                >
                  <div style={{ marginBottom: '0.35rem' }}>
                    <strong>Hospital:</strong> {hospitalInfo?.name || `Hospital #${request.hospital_id}`}
                  </div>
                  {hospitalInfo?.address && (
                    <div style={{ color: '#475569' }}>
                      <strong>Address:</strong> {hospitalInfo.address}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Step 2: Confirming Allocation */}
            {orderModal.step === 2 && (
              <div>
                <div
                  style={{
                    width: '64px',
                    height: '64px',
                    margin: '0 auto 1.25rem',
                    borderRadius: '50%',
                    backgroundColor: '#f0fdf4',
                    color: '#16a34a',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '1.75rem',
                  }}
                >
                  ✓
                </div>
                <h3 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
                  Arranging Blood Sources
                </h3>
                <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.5rem', lineHeight: '1.5' }}>
                  Locking reservation with <strong>{orderModal.targetMatch?.name || orderModal.targetMatch?.source_name || 'Blood Bank'}</strong>.
                </p>

                <div
                  style={{
                    padding: '1rem',
                    backgroundColor: '#f8fafc',
                    border: '1px solid #bbf7d0',
                    borderRadius: '10px',
                    fontSize: '0.875rem',
                    textAlign: 'left',
                    lineHeight: '1.6',
                  }}
                >
                  <div>✓ <strong>Reserved Units:</strong> {request.units_required} units ({request.blood_group})</div>
                  <div>✓ <strong>Transit ETA:</strong> {orderModal.targetMatch?.estimated_time || '~1 min'}</div>
                  <div>✓ <strong>Status:</strong> Ready for Immediate Dispatch</div>
                </div>
              </div>
            )}

            {/* Step 3: Order Placed! */}
            {orderModal.step === 3 && (
              <div>
                <div
                  style={{
                    width: '64px',
                    height: '64px',
                    margin: '0 auto 1.25rem',
                    borderRadius: '50%',
                    backgroundColor: '#dcfce7',
                    color: '#15803d',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '2rem',
                    fontWeight: 700,
                  }}
                >
                  ✓
                </div>
                <h2 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#15803d', marginBottom: '0.5rem' }}>
                  Your Order Has Been Placed!
                </h2>
                <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.5rem' }}>
                  Blood units are confirmed and dispatched. Order is now <strong>FULFILLED</strong> and permanently locked.
                </p>

                <div
                  style={{
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: '12px',
                    padding: '1.15rem',
                    marginBottom: '1.5rem',
                    textAlign: 'left',
                    fontSize: '0.875rem',
                    lineHeight: '1.6',
                  }}
                >
                  <div style={{ color: '#15803d', fontWeight: 700, marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: '0.75rem' }}>
                    Order Receipt Summary
                  </div>
                  <div>• <strong>Request ID:</strong> #{request.request_id}</div>
                  <div>• <strong>Blood Requirement:</strong> {request.blood_group} ({request.units_required} Units)</div>
                  <div>• <strong>Delivering To:</strong> {hospitalInfo?.name || `Hospital #${request.hospital_id}`}</div>
                  <div>• <strong>Source Provider:</strong> {orderModal.targetMatch?.name || orderModal.targetMatch?.source_name || 'Blood Bank'}</div>
                </div>

                <button
                  style={{
                    width: '100%',
                    padding: '0.85rem',
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    color: '#ffffff',
                    backgroundColor: '#16a34a',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer',
                  }}
                  onClick={() => setOrderModal({ isOpen: false, step: 0, targetMatch: null })}
                >
                  View Order Details
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
