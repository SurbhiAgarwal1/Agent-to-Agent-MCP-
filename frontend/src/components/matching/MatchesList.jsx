import React, { useState } from 'react';
import StatusBadge from '../common/StatusBadge';
import Button from '../common/Button';
import Modal from '../common/Modal';
import EmptyState from '../common/EmptyState';

export default function MatchesList({
  matches = [],
  requestId,
  onComplete,
  onReject,
  actionLoading = false,
}) {
  const [rejectModalMatch, setRejectModalMatch] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [completeModalMatch, setCompleteModalMatch] = useState(null);

  if (!matches || matches.length === 0) {
    return (
      <EmptyState
        title="No Matches Available"
        message="No candidate matches have been coordinated or allocated for this request yet."
      />
    );
  }

  const handleOpenReject = (match) => {
    setRejectModalMatch(match);
    setRejectReason('');
  };

  const handleConfirmReject = async () => {
    if (!rejectModalMatch) return;
    const matchId = rejectModalMatch.match_id || rejectModalMatch.id;
    await onReject(matchId, rejectReason);
    setRejectModalMatch(null);
  };

  const handleOpenComplete = (match) => {
    setCompleteModalMatch(match);
  };

  const handleConfirmComplete = async () => {
    if (!completeModalMatch) return;
    const matchId = completeModalMatch.match_id || completeModalMatch.id;
    await onComplete(matchId);
    setCompleteModalMatch(null);
  };

  return (
    <div className="matches-list-container">
      <div className="table-responsive">
        <table className="table" aria-label="Candidate matches">
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>Identifier / Location</th>
              <th>Distance</th>
              <th>ETA</th>
              <th>Score</th>
              <th>Units</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m, idx) => {
              const matchId = m.match_id || m.id || idx + 1;
              const sourceType = m.source_type || 'SOURCE';
              const sourceLabel = sourceType === 'BLOOD_BANK' ? 'Blood Bank' : sourceType === 'DONOR' ? 'Donor' : sourceType;
              const distance = m.distance_km != null ? `${Number(m.distance_km).toFixed(1)} km` : '—';
              const eta = m.estimated_time || (m.estimated_travel_time_minutes != null ? `${m.estimated_travel_time_minutes} min` : '—');
              const score = m.priority_score != null ? Number(m.priority_score).toFixed(2) : '—';
              const units = m.reserved_units ?? m.units ?? m.available_units ?? '—';
              const matchStatus = m.status || 'PROPOSED';
              const canComplete = matchStatus === 'ACCEPTED' || matchStatus === 'PROPOSED';
              const canReject = matchStatus === 'ACCEPTED' || matchStatus === 'PROPOSED';

              return (
                <tr key={matchId}>
                  <td><strong>#{matchId}</strong></td>
                  <td>
                    <span className="badge badge-neutral">
                      {sourceLabel}
                    </span>
                  </td>
                  <td>
                    <div style={{ fontWeight: 500 }}>
                      {m.source_name || `${sourceLabel} #${m.source_id || '—'}`}
                    </div>
                    {m.address && (
                      <div className="text-secondary" style={{ fontSize: '0.75rem' }}>
                        {m.address}
                      </div>
                    )}
                  </td>
                  <td>{distance}</td>
                  <td>{eta}</td>
                  <td>{score}</td>
                  <td><strong>{units}</strong></td>
                  <td>
                    <StatusBadge status={matchStatus} />
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="btn-group" style={{ justifyContent: 'flex-end' }}>
                      {canComplete && onComplete && (
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={actionLoading}
                          onClick={() => handleOpenComplete(m)}
                          title="Confirm match fulfillment"
                        >
                          Complete
                        </Button>
                      )}
                      {canReject && onReject && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={actionLoading}
                          onClick={() => handleOpenReject(m)}
                          title="Reject candidate"
                        >
                          Reject
                        </Button>
                      )}
                      {!canComplete && !canReject && (
                        <span className="text-muted" style={{ fontSize: '0.8125rem' }}>
                          Resolved
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Rejection Modal */}
      <Modal
        isOpen={!!rejectModalMatch}
        onClose={() => setRejectModalMatch(null)}
        title="Reject Match"
        footer={
          <>
            <Button variant="outline" onClick={() => setRejectModalMatch(null)} disabled={actionLoading}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleConfirmReject} loading={actionLoading}>
              Confirm Rejection
            </Button>
          </>
        }
      >
        <p>
          Are you sure you want to reject match #{rejectModalMatch?.match_id || rejectModalMatch?.id} ({rejectModalMatch?.source_type})?
          This will release any reserved units and exclude this source.
        </p>
        <div className="form-group" style={{ marginTop: '1rem' }}>
          <label className="form-label" htmlFor="reject-reason">
            Rejection Reason (Optional):
          </label>
          <input
            id="reject-reason"
            type="text"
            className="form-control"
            placeholder="e.g. Incompatible scheduling or transport issue"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            maxLength={300}
          />
        </div>
      </Modal>

      {/* Completion Modal */}
      <Modal
        isOpen={!!completeModalMatch}
        onClose={() => setCompleteModalMatch(null)}
        title="Complete Match Delivery"
        footer={
          <>
            <Button variant="outline" onClick={() => setCompleteModalMatch(null)} disabled={actionLoading}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleConfirmComplete} loading={actionLoading}>
              Confirm Delivery
            </Button>
          </>
        }
      >
        <p>
          Confirm that match #{completeModalMatch?.match_id || completeModalMatch?.id} has arrived and units have been delivered.
          This will deduct units from blood bank inventory or initiate donor cool-down, transitioning the blood request fulfillment state.
        </p>
      </Modal>
    </div>
  );
}
