import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
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
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // Agent execution state
  const [coordinating, setCoordinating] = useState(false);
  const [coordinationResult, setCoordinationResult] = useState(null);
  const [matchActionLoading, setMatchActionLoading] = useState(false);

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
      // Refresh request status
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

  // Match fulfillment action: complete delivery
  const handleCompleteMatch = async (matchId) => {
    setMatchActionLoading(true);
    setError(null);
    try {
      await completeMatch(requestId, matchId);
      setSuccessMessage(`Match #${matchId} marked completed. Blood units delivered.`);
      await loadData();
    } catch (err) {
      setError(err.message || `Failed to complete match #${matchId}.`);
    } finally {
      setMatchActionLoading(false);
    }
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
                    Update Allocation
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
            Hospital #{request.hospital_id}
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

      {/* Technical workflow is restricted to administrators. */}
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
                ['Sources being arranged', ['PROCESSING', 'MATCHED', 'PARTIALLY_FULFILLED'].includes(request.status)],
                ['Fulfilled', request.status === 'FULFILLED'],
              ].map(([label, done]) => (
                <div
                  key={label}
                  style={{
                    padding: '0.8rem',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--color-border)',
                    backgroundColor: done ? 'var(--color-surface)' : 'var(--color-bg)',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>
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
    </div>
  );
}
