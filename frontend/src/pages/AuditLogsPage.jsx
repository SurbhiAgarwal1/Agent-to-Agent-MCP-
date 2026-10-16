import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { listAuditLogs } from '../api/admin';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

export default function AuditLogsPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [limit, setLimit] = useState(50);
  const [selectedDetail, setSelectedDetail] = useState(null);

  // Filters
  const [actionFilter, setActionFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAuditLogs(limit);
      setLogs(data || []);
    } catch (err) {
      setError(err.message || 'Failed to load security audit logs.');
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const filteredLogs = logs.filter((l) => {
    if (actionFilter !== 'ALL' && l.action !== actionFilter) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const matchAction = l.action?.toLowerCase().includes(term);
      const matchUser = String(l.user_id).includes(term);
      const matchResource = l.resource?.toLowerCase().includes(term);
      const matchId = String(l.resource_id).includes(term);
      if (!matchAction && !matchUser && !matchResource && !matchId) return false;
    }
    return true;
  });

  return (
    <div>
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
          <Link to="/admin" className="text-secondary" style={{ fontSize: '0.875rem' }}>
            &larr; Back to Admin Console
          </Link>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0.25rem 0 0', color: 'var(--color-text-main)' }}>
            Security & Operations Audit Trail
          </h1>
          <p className="text-secondary" style={{ marginTop: '0.25rem', fontSize: '0.9375rem' }}>
            Immutable logging of clinical requests, coordination events, and authorization grants
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Button variant="outline" onClick={fetchLogs} disabled={loading}>
            Refresh Logs
          </Button>
        </div>
      </div>

      <Card>
        {/* Controls */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '1rem',
            marginBottom: '1.25rem',
            paddingBottom: '1.25rem',
            borderBottom: '1px solid var(--border-color)',
          }}
        >
          <div style={{ flex: '1 1 200px' }}>
            <label className="form-label" htmlFor="search-logs" style={{ fontSize: '0.8125rem' }}>
              Search Logs (Action, User ID, Resource)
            </label>
            <input
              id="search-logs"
              type="text"
              className="form-control"
              placeholder="e.g. COORDINATE or User #1"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div style={{ minWidth: '180px' }}>
            <label className="form-label" htmlFor="filter-action" style={{ fontSize: '0.8125rem' }}>
              Filter Action
            </label>
            <select
              id="filter-action"
              className="form-control"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
            >
              <option value="ALL">All Actions</option>
              <option value="LOGIN">LOGIN</option>
              <option value="CREATE_REQUEST">CREATE_REQUEST</option>
              <option value="COORDINATE">COORDINATE</option>
              <option value="COMPLETE_MATCH">COMPLETE_MATCH</option>
              <option value="REJECT_MATCH">REJECT_MATCH</option>
              <option value="GRANT_MEMBERSHIP">GRANT_MEMBERSHIP</option>
              <option value="REVOKE_MEMBERSHIP">REVOKE_MEMBERSHIP</option>
            </select>
          </div>

          <div style={{ minWidth: '120px' }}>
            <label className="form-label" htmlFor="limit-select" style={{ fontSize: '0.8125rem' }}>
              Fetch Limit
            </label>
            <select
              id="limit-select"
              className="form-control"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              <option value={25}>25 entries</option>
              <option value={50}>50 entries</option>
              <option value={100}>100 entries</option>
              <option value={200}>200 entries</option>
            </select>
          </div>
        </div>

        {loading && <LoadingSpinner message="Retrieving audit logs..." />}

        {error && (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            {error}
          </div>
        )}

        {!loading && !error && filteredLogs.length === 0 && (
          <EmptyState
            title="No Audit Logs Found"
            message="No security logs match your current filter settings."
          />
        )}

        {!loading && !error && filteredLogs.length > 0 && (
          <div className="table-responsive">
            <table className="table" aria-label="Security audit logs">
              <thead>
                <tr>
                  <th>Log ID</th>
                  <th>Timestamp</th>
                  <th>Action</th>
                  <th>User ID</th>
                  <th>Resource</th>
                  <th>Resource ID</th>
                  <th style={{ textAlign: 'right' }}>Details</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((log) => (
                  <tr key={log.id}>
                    <td><strong>#{log.id}</strong></td>
                    <td className="text-secondary" style={{ fontSize: '0.8125rem', whiteSpace: 'nowrap' }}>
                      {log.timestamp ? new Date(log.timestamp).toLocaleString() : '—'}
                    </td>
                    <td>
                      <span className="badge badge-neutral" style={{ fontWeight: 600 }}>
                        {log.action}
                      </span>
                    </td>
                    <td>User #{log.user_id}</td>
                    <td>{log.resource}</td>
                    <td>#{log.resource_id}</td>
                    <td style={{ textAlign: 'right' }}>
                      {log.details ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelectedDetail(log)}
                        >
                          View Payload
                        </Button>
                      ) : (
                        <span className="text-muted" style={{ fontSize: '0.8125rem' }}>None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Details Modal */}
      <Modal
        isOpen={!!selectedDetail}
        onClose={() => setSelectedDetail(null)}
        title={`Audit Log #${selectedDetail?.id} Payload`}
      >
        <div style={{ marginBottom: '1rem' }}>
          <strong>Action:</strong> {selectedDetail?.action} &bull; <strong>Actor:</strong> User #{selectedDetail?.user_id}
        </div>
        <pre
          style={{
            backgroundColor: '#F1F5F9',
            padding: '1rem',
            borderRadius: '6px',
            fontSize: '0.8125rem',
            overflowX: 'auto',
            border: '1px solid var(--border-color)',
          }}
        >
          {JSON.stringify(selectedDetail?.details, null, 2)}
        </pre>
      </Modal>
    </div>
  );
}
