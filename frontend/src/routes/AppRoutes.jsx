import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import { homeForRole } from '../utils/roles';
import DonorDashboardPage from '../pages/DonorDashboardPage.jsx';
import BloodBankDashboardPage, { BankInventoryPage, BankRequestsPage, BankDonationsPage } from '../pages/BloodBankDashboardPage.jsx';
import { DonorNotificationsPage, DonorHistoryPage } from '../pages/DonorDashboardPage.jsx';
import AdminHomePage from '../pages/AdminHomePage.jsx';

import ProtectedRoute from './ProtectedRoute.jsx';
import RoleRoute from './RoleRoute.jsx';
import AppLayout from '../components/layout/AppLayout.jsx';

import LandingPage from '../pages/LandingPage.jsx';
import LoginPage from '../pages/LoginPage.jsx';
import SignupPage from '../pages/SignupPage.jsx';
import DashboardPage from '../pages/DashboardPage.jsx';
import BloodRequestsPage from '../pages/BloodRequestsPage.jsx';
import CreateBloodRequestPage from '../pages/CreateBloodRequestPage.jsx';
import BloodRequestDetailsPage from '../pages/BloodRequestDetailsPage.jsx';
import PharmacyCatalogPage from '../pages/PharmacyCatalogPage.jsx';
import NotificationsPage from '../pages/NotificationsPage.jsx';
import ProfilePage from '../pages/ProfilePage.jsx';
import AdminDashboardPage from '../pages/AdminDashboardPage.jsx';
import AuditLogsPage from '../pages/AuditLogsPage.jsx';
import MembershipManagementPage from '../pages/MembershipManagementPage.jsx';
import NotFoundPage from '../pages/NotFoundPage.jsx';

function DashboardGate() {
  const { user } = useAuth();
  const home = homeForRole(user?.role);
  return home === '/dashboard' ? <DashboardPage /> : <Navigate to={home} replace />;
}

export default function AppRoutes() {
  return (
    <Routes>
      {/* Public Pages */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />

      {/* Authenticated Dashboard Pages */}
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardGate />} />
        <Route path="/donor" element={<RoleRoute allowedRoles={['USER']}><DonorDashboardPage /></RoleRoute>} />
        <Route path="/donor/notifications" element={<RoleRoute allowedRoles={['USER']}><DonorNotificationsPage /></RoleRoute>} />
        <Route path="/donor/history" element={<RoleRoute allowedRoles={['USER']}><DonorHistoryPage /></RoleRoute>} />
        <Route path="/bank" element={<RoleRoute allowedRoles={['BLOOD_BANK_STAFF']}><BloodBankDashboardPage /></RoleRoute>} />
        <Route path="/bank/inventory" element={<RoleRoute allowedRoles={['BLOOD_BANK_STAFF']}><BankInventoryPage /></RoleRoute>} />
        <Route path="/bank/requests" element={<RoleRoute allowedRoles={['BLOOD_BANK_STAFF']}><BankRequestsPage /></RoleRoute>} />
        <Route path="/bank/donations" element={<RoleRoute allowedRoles={['BLOOD_BANK_STAFF']}><BankDonationsPage /></RoleRoute>} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/pharmacy" element={<PharmacyCatalogPage />} />

        {/* Hospital Staff & Admin Blood Requests */}
        <Route
          path="/blood-requests"
          element={
            <RoleRoute allowedRoles={['HOSPITAL_STAFF', 'ADMIN']}>
              <BloodRequestsPage />
            </RoleRoute>
          }
        />
        <Route
          path="/blood-requests/new"
          element={
            <RoleRoute allowedRoles={['HOSPITAL_STAFF', 'ADMIN']}>
              <CreateBloodRequestPage />
            </RoleRoute>
          }
        />
        <Route
          path="/blood-requests/:id"
          element={
            <RoleRoute allowedRoles={['HOSPITAL_STAFF', 'ADMIN']}>
              <BloodRequestDetailsPage />
            </RoleRoute>
          }
        />

        {/* Admin Console & Governance */}
        <Route
          path="/admin"
          element={
            <RoleRoute allowedRoles={['ADMIN']}>
              <AdminHomePage />
            </RoleRoute>
          }
        />
        <Route
          path="/admin/agents"
          element={
            <RoleRoute allowedRoles={['ADMIN']}>
              <AdminDashboardPage />
            </RoleRoute>
          }
        />
        <Route
          path="/admin/memberships"
          element={
            <RoleRoute allowedRoles={['ADMIN']}>
              <MembershipManagementPage />
            </RoleRoute>
          }
        />
        <Route
          path="/admin/users"
          element={
            <RoleRoute allowedRoles={['ADMIN']}>
              <MembershipManagementPage mode="users" />
            </RoleRoute>
          }
        />
        <Route
          path="/admin/audit-logs"
          element={
            <RoleRoute allowedRoles={['ADMIN']}>
              <AuditLogsPage />
            </RoleRoute>
          }
        />
      </Route>

      {/* Fallback 404 */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
