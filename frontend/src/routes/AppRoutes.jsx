import React from 'react';
import { Routes, Route } from 'react-router-dom';

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
import NotificationsPage from '../pages/NotificationsPage.jsx';
import ProfilePage from '../pages/ProfilePage.jsx';
import AdminDashboardPage from '../pages/AdminDashboardPage.jsx';
import AuditLogsPage from '../pages/AuditLogsPage.jsx';
import MembershipManagementPage from '../pages/MembershipManagementPage.jsx';
import NotFoundPage from '../pages/NotFoundPage.jsx';

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
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/notifications" element={<NotificationsPage />} />

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
              <MembershipManagementPage />
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
