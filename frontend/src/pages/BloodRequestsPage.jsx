import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { listBloodRequests } from '../api/bloodRequests';
import { listHospitals } from '../api/hospitals';
import { useHospital } from '../context/HospitalContext';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import LoadingSpinner from '../components/common/LoadingSpinner';
import StatusBadge from '../components/common/StatusBadge';
import UrgencyBadge from '../components/common/UrgencyBadge';
import BloodGroupBadge from '../components/common/BloodGroupBadge';
import EmptyState from '../components/common/EmptyState';

export default function BloodRequestsPage() {
  const { selectedHospitalId, selectHospital } = useHospital();
  const [requests, setRequests] = useState([]);
  const [hospitalsMap, setHospitalsMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [hospitalFilter, setHospitalFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [urgencyFilter, setUrgencyFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  const fetchRequests = async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, hList] = await Promise.all([
        listBloodRequests(),
        listHospitals().catch(() => []),
      ]);
      setRequests(data || []);
      if (Array.isArray(hList)) {
        const map = {};
        hList.forEach((h) => { map[h.hospital_id] = h; });
        setHospitalsMap(map);
      }
    } catch (err) {
      setError(err.message || 'Failed to load blood requests.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRequests();
  }, []);

  const filteredRequests = requests.filter((req) => {
    if (hospitalFilter !== 'ALL' && String(req.hospital_id) !== String(hospitalFilter)) return false;
    if (statusFilter !== 'ALL' && req.status !== statusFilter) return false;
    if (urgencyFilter !== 'ALL' && req.urgency !== urgencyFilter) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const matchId = String(req.request_id).includes(term);
      const matchHosp = String(req.hospital_id).includes(term);
      const matchGroup = String(req.blood_group).toLowerCase().includes(term);
      if (!matchId && !matchHosp && !matchGroup) return false;
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
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--color-text-main)' }}>
            Emergency Blood Requests
          </h1>
          <p className="text-secondary" style={{ marginTop: '0.25rem', fontSize: '0.9375rem' }}>
            Manage and track active blood requests across clinical facilities
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Button variant="outline" onClick={fetchRequests} disabled={loading}>
            Refresh
          </Button>
          <Link to="/blood-requests/new" className="btn btn-primary">
            + New Request
          </Link>
        </div>
      </div>

      <Card>
        {/* Filters bar */}
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
          {/* Hospital Filter */}
          <div style={{ minWidth: '200px' }}>
            <label className="form-label" htmlFor="filter-hospital" style={{ fontSize: '0.8125rem' }}>
              Filter by Hospital
            </label>
            <select
              id="filter-hospital"
              className="form-control"
              value={hospitalFilter}
              onChange={(e) => {
                setHospitalFilter(e.target.value);
                if (e.target.value !== 'ALL') {
                  selectHospital(e.target.value);
                }
              }}
            >
              <option value="ALL">All Hospitals</option>
              {Object.values(hospitalsMap).map((h) => (
                <option key={h.hospital_id} value={h.hospital_id}>
                  {h.name}
                </option>
              ))}
            </select>
          </div>

          <div style={{ flex: '1 1 200px' }}>
            <label className="form-label" htmlFor="search-requests" style={{ fontSize: '0.8125rem' }}>
              Search ID or Blood Group
            </label>
            <input
              id="search-requests"
              type="text"
              className="form-control"
              placeholder="e.g. A+ or #12"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div style={{ minWidth: '150px' }}>
            <label className="form-label" htmlFor="filter-status" style={{ fontSize: '0.8125rem' }}>
              Filter by Status
            </label>
            <select
              id="filter-status"
              className="form-control"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="PENDING">Pending</option>
              <option value="PROCESSING">Processing</option>
              <option value="PARTIALLY_FULFILLED">Partially Fulfilled</option>
              <option value="FULFILLED">Fulfilled</option>
              <option value="CANCELLED">Cancelled</option>
            </select>
          </div>

          <div style={{ minWidth: '150px' }}>
            <label className="form-label" htmlFor="filter-urgency" style={{ fontSize: '0.8125rem' }}>
              Filter by Urgency
            </label>
            <select
              id="filter-urgency"
              className="form-control"
              value={urgencyFilter}
              onChange={(e) => setUrgencyFilter(e.target.value)}
            >
              <option value="ALL">All Urgencies</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
        </div>

        {loading && <LoadingSpinner message="Loading blood requests..." />}

        {error && (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            {error}
          </div>
        )}

        {!loading && !error && filteredRequests.length === 0 && (
          <EmptyState
            title="No Blood Requests Found"
            message={
              requests.length === 0
                ? "No blood requests have been logged yet. Click '+ New Request' to create one."
                : 'No blood requests match your selected filters.'
            }
          />
        )}

        {!loading && !error && filteredRequests.length > 0 && (
          <div className="table-responsive">
            <table className="table" aria-label="Emergency blood requests">
              <thead>
                <tr>
                  <th>Request ID</th>
                  <th>Hospital</th>
                  <th>Blood Group</th>
                  <th>Units</th>
                  <th>Urgency</th>
                  <th>Status</th>
                  <th>Created At</th>
                  <th style={{ textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredRequests.map((req) => {
                  const hosp = hospitalsMap[req.hospital_id];
                  const hospName = hosp ? hosp.name : `Hospital #${req.hospital_id}`;
                  const createdDate = req.created_at
                    ? new Date(req.created_at).toLocaleString()
                    : '-';

                  return (
                    <tr key={req.request_id}>
                      <td>
                        <strong>#{req.request_id}</strong>
                      </td>
                      <td>
                        <div style={{ fontWeight: 500 }}>{hospName}</div>
                        {hosp && (
                          <div className="text-secondary" style={{ fontSize: '0.75rem' }}>
                            {hosp.address}
                          </div>
                        )}
                      </td>
                      <td>
                        <BloodGroupBadge bloodGroup={req.blood_group} />
                      </td>
                      <td>
                        <strong>{req.units_required}</strong> units
                      </td>
                      <td>
                        <UrgencyBadge urgency={req.urgency} />
                      </td>
                      <td>
                        <StatusBadge status={req.status} />
                      </td>
                      <td style={{ fontSize: '0.8125rem' }}>
                        {createdDate}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Link
                          to={`/blood-requests/${req.request_id}`}
                          className="btn btn-outline btn-sm"
                        >
                          View Details &rarr;
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
