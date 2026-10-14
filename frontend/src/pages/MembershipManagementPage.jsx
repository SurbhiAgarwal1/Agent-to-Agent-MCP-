import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createUser,
  grantHospitalMembership,
  grantBloodBankMembership,
  revokeHospitalMembership,
  revokeBloodBankMembership,
} from '../api/admin';
import Card from '../components/common/Card';
import Button from '../components/common/Button';

export default function MembershipManagementPage() {
  const [successMsg, setSuccessMsg] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);

  // Create User form state
  const [userEmail, setUserEmail] = useState('');
  const [userPassword, setUserPassword] = useState('');
  const [userRole, setUserRole] = useState('HOSPITAL_STAFF');
  const [userLoading, setUserLoading] = useState(false);

  // Grant Hospital Membership state
  const [hospUserId, setHospUserId] = useState('');
  const [hospOrgId, setHospOrgId] = useState('');
  const [hospMemType, setHospMemType] = useState('STAFF');
  const [hospLoading, setHospLoading] = useState(false);

  // Grant Blood Bank Membership state
  const [bankUserId, setBankUserId] = useState('');
  const [bankOrgId, setBankOrgId] = useState('');
  const [bankMemType, setBankMemType] = useState('STAFF');
  const [bankLoading, setBankLoading] = useState(false);

  // Revoke state
  const [revokeMemId, setRevokeMemId] = useState('');
  const [revokeType, setRevokeType] = useState('hospital');
  const [revokeLoading, setRevokeLoading] = useState(false);

  const clearAlerts = () => {
    setSuccessMsg(null);
    setErrorMsg(null);
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    clearAlerts();
    setUserLoading(true);
    try {
      const res = await createUser(userEmail, userPassword, userRole);
      setSuccessMsg(`Successfully created user #${res.id} (${res.email}) with role ${res.role}.`);
      setUserEmail('');
      setUserPassword('');
    } catch (err) {
      setErrorMsg(err.message || 'Failed to create user account.');
    } finally {
      setUserLoading(false);
    }
  };

  const handleGrantHospital = async (e) => {
    e.preventDefault();
    clearAlerts();
    setHospLoading(true);
    try {
      const res = await grantHospitalMembership(Number(hospUserId), Number(hospOrgId), hospMemType);
      setSuccessMsg(`Granted hospital membership #${res.membership_id} to User #${hospUserId} for Hospital #${hospOrgId}.`);
      setHospUserId('');
      setHospOrgId('');
    } catch (err) {
      setErrorMsg(err.message || 'Failed to grant hospital membership.');
    } finally {
      setHospLoading(false);
    }
  };

  const handleGrantBank = async (e) => {
    e.preventDefault();
    clearAlerts();
    setBankLoading(true);
    try {
      const res = await grantBloodBankMembership(Number(bankUserId), Number(bankOrgId), bankMemType);
      setSuccessMsg(`Granted blood bank membership #${res.membership_id} to User #${bankUserId} for Blood Bank #${bankOrgId}.`);
      setBankUserId('');
      setBankOrgId('');
    } catch (err) {
      setErrorMsg(err.message || 'Failed to grant blood bank membership.');
    } finally {
      setBankLoading(false);
    }
  };

  const handleRevoke = async (e) => {
    e.preventDefault();
    clearAlerts();
    setRevokeLoading(true);
    try {
      if (revokeType === 'hospital') {
        await revokeHospitalMembership(Number(revokeMemId));
        setSuccessMsg(`Hospital membership #${revokeMemId} revoked.`);
      } else {
        await revokeBloodBankMembership(Number(revokeMemId));
        setSuccessMsg(`Blood bank membership #${revokeMemId} revoked.`);
      }
      setRevokeMemId('');
    } catch (err) {
      setErrorMsg(err.message || 'Failed to revoke membership.');
    } finally {
      setRevokeLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <Link to="/admin" className="text-secondary" style={{ fontSize: '0.875rem' }}>
          &larr; Back to Admin Console
        </Link>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0.25rem 0 0', color: 'var(--color-text-main)' }}>
          Membership & User Governance
        </h1>
        <p className="text-secondary" style={{ marginTop: '0.25rem', fontSize: '0.9375rem' }}>
          Provision system users and bind clinical personnel to authorized healthcare facilities
        </p>
      </div>

      {successMsg && (
        <div className="alert alert-success" style={{ marginBottom: '1.25rem' }}>
          {successMsg}
        </div>
      )}
      {errorMsg && (
        <div className="alert alert-error" style={{ marginBottom: '1.25rem' }}>
          {errorMsg}
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
          gap: '1.5rem',
        }}
      >
        {/* Create User Form */}
        <Card title="Provision New User">
          <form onSubmit={handleCreateUser}>
            <div className="form-group">
              <label className="form-label" htmlFor="user-email">
                Email Address
              </label>
              <input
                id="user-email"
                type="email"
                className="form-control"
                placeholder="clinician@hospital.org"
                value={userEmail}
                onChange={(e) => setUserEmail(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="user-pwd">
                Initial Password
              </label>
              <input
                id="user-pwd"
                type="password"
                className="form-control"
                placeholder="Min. 6 characters"
                value={userPassword}
                onChange={(e) => setUserPassword(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="user-role">
                User Role
              </label>
              <select
                id="user-role"
                className="form-control"
                value={userRole}
                onChange={(e) => setUserRole(e.target.value)}
              >
                <option value="HOSPITAL_STAFF">HOSPITAL_STAFF</option>
                <option value="BLOOD_BANK_STAFF">BLOOD_BANK_STAFF</option>
                <option value="USER">USER</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </div>

            <Button type="submit" variant="primary" loading={userLoading} style={{ width: '100%' }}>
              Create User Account
            </Button>
          </form>
        </Card>

        {/* Grant Hospital Membership */}
        <Card title="Grant Hospital Membership">
          <p className="text-secondary" style={{ fontSize: '0.8125rem', marginBottom: '1rem' }}>
            Requires target user to have the <code>HOSPITAL_STAFF</code> role.
          </p>
          <form onSubmit={handleGrantHospital}>
            <div className="form-group">
              <label className="form-label" htmlFor="hosp-user-id">
                User ID
              </label>
              <input
                id="hosp-user-id"
                type="number"
                min="1"
                className="form-control"
                placeholder="e.g. 2"
                value={hospUserId}
                onChange={(e) => setHospUserId(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="hosp-org-id">
                Hospital ID
              </label>
              <input
                id="hosp-org-id"
                type="number"
                min="1"
                className="form-control"
                placeholder="e.g. 1"
                value={hospOrgId}
                onChange={(e) => setHospOrgId(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="hosp-type">
                Membership Type
              </label>
              <select
                id="hosp-type"
                className="form-control"
                value={hospMemType}
                onChange={(e) => setHospMemType(e.target.value)}
              >
                <option value="STAFF">STAFF</option>
                <option value="CHIEF_MEDICAL">CHIEF_MEDICAL</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </div>

            <Button type="submit" variant="primary" loading={hospLoading} style={{ width: '100%' }}>
              Grant Hospital Membership
            </Button>
          </form>
        </Card>

        {/* Grant Blood Bank Membership */}
        <Card title="Grant Blood Bank Membership">
          <p className="text-secondary" style={{ fontSize: '0.8125rem', marginBottom: '1rem' }}>
            Requires target user to have the <code>BLOOD_BANK_STAFF</code> role.
          </p>
          <form onSubmit={handleGrantBank}>
            <div className="form-group">
              <label className="form-label" htmlFor="bank-user-id">
                User ID
              </label>
              <input
                id="bank-user-id"
                type="number"
                min="1"
                className="form-control"
                placeholder="e.g. 3"
                value={bankUserId}
                onChange={(e) => setBankUserId(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="bank-org-id">
                Blood Bank ID
              </label>
              <input
                id="bank-org-id"
                type="number"
                min="1"
                className="form-control"
                placeholder="e.g. 1"
                value={bankOrgId}
                onChange={(e) => setBankOrgId(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="bank-type">
                Membership Type
              </label>
              <select
                id="bank-type"
                className="form-control"
                value={bankMemType}
                onChange={(e) => setBankMemType(e.target.value)}
              >
                <option value="STAFF">STAFF</option>
                <option value="SUPERVISOR">SUPERVISOR</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </div>

            <Button type="submit" variant="primary" loading={bankLoading} style={{ width: '100%' }}>
              Grant Blood Bank Membership
            </Button>
          </form>
        </Card>

        {/* Revoke Membership */}
        <Card title="Revoke Facility Membership">
          <p className="text-secondary" style={{ fontSize: '0.8125rem', marginBottom: '1rem' }}>
            Deactivates an active facility membership by its primary membership ID.
          </p>
          <form onSubmit={handleRevoke}>
            <div className="form-group">
              <label className="form-label" htmlFor="revoke-type">
                Organization Scope
              </label>
              <select
                id="revoke-type"
                className="form-control"
                value={revokeType}
                onChange={(e) => setRevokeType(e.target.value)}
              >
                <option value="hospital">Hospital Membership</option>
                <option value="blood-bank">Blood Bank Membership</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="revoke-id">
                Membership ID
              </label>
              <input
                id="revoke-id"
                type="number"
                min="1"
                className="form-control"
                placeholder="e.g. 5"
                value={revokeMemId}
                onChange={(e) => setRevokeMemId(e.target.value)}
                required
              />
            </div>

            <Button type="submit" variant="danger" loading={revokeLoading} style={{ width: '100%' }}>
              Revoke Membership
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
