import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// Common components
import Button from '../components/common/Button.jsx';
import Card from '../components/common/Card.jsx';
import StatusBadge from '../components/common/StatusBadge.jsx';
import UrgencyBadge from '../components/common/UrgencyBadge.jsx';
import BloodGroupBadge from '../components/common/BloodGroupBadge.jsx';
import Modal from '../components/common/Modal.jsx';
import EmptyState from '../components/common/EmptyState.jsx';
import LoadingSpinner from '../components/common/LoadingSpinner.jsx';

// Coordination & Matching
import CoordinationWorkflow from '../components/coordination/CoordinationWorkflow.jsx';
import MatchesList from '../components/matching/MatchesList.jsx';

// Route guards
import ProtectedRoute from '../routes/ProtectedRoute.jsx';
import RoleRoute from '../routes/RoleRoute.jsx';

// Pages
import LandingPage from '../pages/LandingPage.jsx';
import LoginPage from '../pages/LoginPage.jsx';
import SignupPage from '../pages/SignupPage.jsx';
import DashboardPage from '../pages/DashboardPage.jsx';
import BloodRequestsPage from '../pages/BloodRequestsPage.jsx';
import CreateBloodRequestPage from '../pages/CreateBloodRequestPage.jsx';
import BloodRequestDetailsPage from '../pages/BloodRequestDetailsPage.jsx';
import ProfilePage from '../pages/ProfilePage.jsx';
import AdminDashboardPage from '../pages/AdminDashboardPage.jsx';
import AuditLogsPage from '../pages/AuditLogsPage.jsx';
import MembershipManagementPage from '../pages/MembershipManagementPage.jsx';
import NotFoundPage from '../pages/NotFoundPage.jsx';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../hooks/useAuth.js', () => ({
  default: () => mockUseAuth(),
  useAuth: () => mockUseAuth(),
}));

// Mock API modules
vi.mock('../api/bloodRequests.js', () => ({
  listBloodRequests: vi.fn(),
  getBloodRequest: vi.fn(),
  createBloodRequest: vi.fn(),
  updateBloodRequestStatus: vi.fn(),
  getRequestMatches: vi.fn(),
  coordinateBloodRequest: vi.fn(),
  orchestrateBloodRequest: vi.fn(),
  completeMatch: vi.fn(),
  rejectMatch: vi.fn(),
  processNlRequest: vi.fn(),
}));

vi.mock('../api/hospitals.js', () => ({
  listHospitals: vi.fn(),
}));

vi.mock('../api/admin.js', () => ({
  createUser: vi.fn(),
  listAuditLogs: vi.fn(),
  grantHospitalMembership: vi.fn(),
  grantBloodBankMembership: vi.fn(),
  revokeHospitalMembership: vi.fn(),
  revokeBloodBankMembership: vi.fn(),
}));

vi.mock('../api/auth.js', () => ({
  loginApi: vi.fn(),
  registerApi: vi.fn(),
  getMeApi: vi.fn(),
}));

describe('1. Common Healthcare UI Components', () => {
  it('StatusBadge renders appropriate labels for different lifecycle states', () => {
    const { rerender } = render(<StatusBadge status="PENDING" />);
    expect(screen.getByText('Pending')).toBeInTheDocument();

    rerender(<StatusBadge status="FULFILLED" />);
    expect(screen.getByText('Fulfilled')).toBeInTheDocument();

    rerender(<StatusBadge status="ACCEPTED" />);
    expect(screen.getByText('Reserved / Held')).toBeInTheDocument();

    rerender(<StatusBadge status="CANCELLED" />);
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
  });

  it('UrgencyBadge renders correct text', () => {
    const { rerender } = render(<UrgencyBadge urgency="CRITICAL" />);
    expect(screen.getByText('Critical')).toBeInTheDocument();

    rerender(<UrgencyBadge urgency="LOW" />);
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('BloodGroupBadge renders blood type', () => {
    render(<BloodGroupBadge group="O-" />);
    expect(screen.getByText('O-')).toBeInTheDocument();
  });

  it('Card renders title, subtitle and children', () => {
    render(
      <Card title="Emergency Unit" subtitle="Hospital ward 3">
        <p>Operational Content</p>
      </Card>
    );
    expect(screen.getByText('Emergency Unit')).toBeInTheDocument();
    expect(screen.getByText('Hospital ward 3')).toBeInTheDocument();
    expect(screen.getByText('Operational Content')).toBeInTheDocument();
  });

  it('Modal renders when open and handles close', () => {
    const handleClose = vi.fn();
    const { rerender } = render(
      <Modal isOpen={false} onClose={handleClose} title="Test Modal">
        Content
      </Modal>
    );
    expect(screen.queryByText('Test Modal')).not.toBeInTheDocument();

    rerender(
      <Modal isOpen={true} onClose={handleClose} title="Test Modal">
        Modal Body Content
      </Modal>
    );
    expect(screen.getByText('Test Modal')).toBeInTheDocument();
    expect(screen.getByText('Modal Body Content')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Close modal'));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('EmptyState renders message and action button', () => {
    render(
      <EmptyState
        title="No Blood Requests"
        message="Create your first request now"
        action={<button>Create</button>}
      />
    );
    expect(screen.getByText('No Blood Requests')).toBeInTheDocument();
    expect(screen.getByText('Create your first request now')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
  });

  it('LoadingSpinner renders message and status role', () => {
    render(<LoadingSpinner message="Locating nearest donors..." />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('Locating nearest donors...')).toBeInTheDocument();
  });

  it('Button handles loading state and click events', () => {
    const handleClick = vi.fn();
    const { rerender } = render(
      <Button onClick={handleClick} loading={false}>
        Submit
      </Button>
    );
    fireEvent.click(screen.getByRole('button', { name: /Submit/i }));
    expect(handleClick).toHaveBeenCalledTimes(1);

    rerender(
      <Button onClick={handleClick} loading={true}>
        Submit
      </Button>
    );
    expect(screen.getByRole('button')).toBeDisabled();
  });
});

describe('2. Public Landing & Auth Pages', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      user: null,
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
  });

  it('LandingPage renders title, explanation, and Login/SignUp links', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>
    );

    expect(screen.getAllByText(/Blood Donation Coordination Platform/i)[0]).toBeInTheDocument();
    expect(screen.getByText(/Coordinate urgent blood requirements with the right resources, faster/i)).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Login/i })[0]).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Sign Up/i })[0]).toBeInTheDocument();
  });

  it('LoginPage renders form, validates missing fields, and calls login', async () => {
    const mockLogin = vi.fn().mockResolvedValue({});
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      user: null,
      loading: false,
      login: mockLogin,
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();

    // Click submit empty
    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));
    expect(screen.getByRole('alert')).toHaveTextContent(/Please provide both email and password/i);

    // Fill valid credentials
    fireEvent.change(screen.getByLabelText(/Email Address/i), { target: { value: 'staff@hospital.org' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'password123' } });
    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('staff@hospital.org', 'password123');
    });
  });

  it('SignupPage validates password length and match before register', async () => {
    const { registerApi } = await import('../api/auth.js');
    registerApi.mockResolvedValue({ id: 1, email: 'new@hospital.org', role: 'HOSPITAL_STAFF' });

    render(
      <MemoryRouter>
        <SignupPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/Email Address/i), { target: { value: 'new@hospital.org' } });
    fireEvent.change(screen.getByLabelText(/^Password/i), { target: { value: 'short' } });
    fireEvent.change(screen.getByLabelText(/Confirm Password/i), { target: { value: 'mismatch' } });
    fireEvent.click(screen.getByRole('button', { name: /Create Account/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/Password must be at least 6 characters/i);
  });

  it('NotFoundPage renders 404 error and navigation link', () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    );
    expect(screen.getByText('404')).toBeInTheDocument();
    expect(screen.getByText(/Page Not Found/i)).toBeInTheDocument();
  });
});

describe('3. Route Guards & Authorization (RBAC)', () => {
  it('ProtectedRoute redirects unauthenticated visitors to /login', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, loading: false });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/login" element={<div>Login Screen</div>} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Secret Dashboard</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Login Screen')).toBeInTheDocument();
    expect(screen.queryByText('Secret Dashboard')).not.toBeInTheDocument();
  });

  it('ProtectedRoute allows authenticated users through', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: true, loading: false });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Secret Dashboard</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Secret Dashboard')).toBeInTheDocument();
  });

  it('RoleRoute allows authorized user roles', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { role: 'HOSPITAL_STAFF' },
      loading: false,
    });

    render(
      <MemoryRouter initialEntries={['/requests']}>
        <Routes>
          <Route
            path="/requests"
            element={
              <RoleRoute allowedRoles={['HOSPITAL_STAFF', 'ADMIN']}>
                <div>Hospital Staff View</div>
              </RoleRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Hospital Staff View')).toBeInTheDocument();
  });

  it('RoleRoute blocks unauthorized roles and renders 403 Forbidden alert', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { role: 'USER' },
      loading: false,
    });

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route
            path="/admin"
            element={
              <RoleRoute allowedRoles={['ADMIN']}>
                <div>Admin Console</div>
              </RoleRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText(/403 — Access Denied/i)).toBeInTheDocument();
    expect(screen.getByText(/Required role\(s\):/i)).toHaveTextContent('ADMIN');
    expect(screen.queryByText('Admin Console')).not.toBeInTheDocument();
  });
});

describe('4. Dashboard & Blood Requests Workflows', () => {
  it('DashboardPage displays operational metrics and recent requests for Hospital Staff', async () => {
    const { listBloodRequests } = await import('../api/bloodRequests.js');
    listBloodRequests.mockResolvedValue([
      {
        request_id: 101,
        hospital_id: 1,
        blood_group: 'O+',
        units_required: 4,
        urgency: 'CRITICAL',
        status: 'PENDING',
        created_at: new Date().toISOString(),
      },
    ]);

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { id: 1, email: 'staff@city.org', role: 'HOSPITAL_STAFF', hospital_ids: [1] },
      loading: false,
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/Operational Dashboard/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('#101')).toBeInTheDocument();
      expect(screen.getByText('O+')).toBeInTheDocument();
    });
  });

  it('BloodRequestsPage lists requests and supports filtering', async () => {
    const { listBloodRequests } = await import('../api/bloodRequests.js');
    listBloodRequests.mockResolvedValue([
      {
        request_id: 101,
        hospital_id: 1,
        blood_group: 'A+',
        units_required: 2,
        urgency: 'HIGH',
        status: 'PENDING',
        created_at: new Date().toISOString(),
      },
      {
        request_id: 102,
        hospital_id: 2,
        blood_group: 'B-',
        units_required: 1,
        urgency: 'LOW',
        status: 'FULFILLED',
        created_at: new Date().toISOString(),
      },
    ]);

    render(
      <MemoryRouter>
        <BloodRequestsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('#101')).toBeInTheDocument();
      expect(screen.getByText('#102')).toBeInTheDocument();
    });

    // Filter by search query
    fireEvent.change(screen.getByLabelText(/Search ID or Blood Group/i), { target: { value: 'A+' } });
    expect(screen.getByText('#101')).toBeInTheDocument();
    expect(screen.queryByText('#102')).not.toBeInTheDocument();
  });

  it('CreateBloodRequestPage renders the user-facing chat request flow', async () => {
    const { processNlRequest } = await import('../api/bloodRequests.js');
    processNlRequest.mockResolvedValue({
      request_id: 205,
      summary: 'Your request was received.',
    });

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { role: 'HOSPITAL_STAFF', hospital_ids: [1] },
      loading: false,
    });

    render(
      <MemoryRouter>
        <CreateBloodRequestPage />
      </MemoryRouter>
    );

    const input = screen.getByLabelText(/describe your blood requirement/i);
    expect(input).toBeInTheDocument();

    fireEvent.change(input, {
      target: { value: 'We need 2 units of O+ blood urgently.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send blood request/i }));

    await waitFor(() => {
      expect(processNlRequest).toHaveBeenCalledWith(
        'We need 2 units of O+ blood urgently.'
      );
    });

    expect(await screen.findByText('Your request was received.')).toBeInTheDocument();
  });

  it('BloodRequestDetailsPage renders details and triggers coordination', async () => {
    const { getBloodRequest, coordinateBloodRequest, getRequestMatches } = await import('../api/bloodRequests.js');
    getBloodRequest.mockResolvedValue({
      request_id: 42,
      hospital_id: 1,
      blood_group: 'AB+',
      units_required: 3,
      urgency: 'HIGH',
      status: 'PENDING',
    });
    getRequestMatches.mockResolvedValue({ matches: [] });
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { id: 1, email: 'admin@example.com', role: 'ADMIN', hospital_ids: [], bank_ids: [] },
      loading: false,
    });
    coordinateBloodRequest.mockResolvedValue({
      success: true,
      current_state: 'COMPLETED',
      ranked_matches: [
        {
          match_id: 1,
          source_type: 'BLOOD_BANK',
          source_name: 'Metro Blood Bank',
          distance_km: 3.2,
          estimated_travel_time_minutes: 10,
          status: 'PROPOSED',
          reserved_units: 3,
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={['/blood-requests/42']}>
        <Routes>
          <Route path="/blood-requests/:id" element={<BloodRequestDetailsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Emergency Blood Request #42')).toBeInTheDocument();
    });

    // Trigger coordination
    fireEvent.click(screen.getByRole('button', { name: /Run A2A Coordination/i }));

    await waitFor(() => {
      expect(coordinateBloodRequest).toHaveBeenCalledWith(42);
      expect(screen.getByText(/Metro Blood Bank/i)).toBeInTheDocument();
    });
  });
});

describe('5. Coordination Workflow & Match Fulfillment', () => {
  it('CoordinationWorkflow displays state machine progression', () => {
    const execution = {
      success: true,
      current_state: 'MATCHED',
      requirement: { units_required: 2, blood_group: 'A+' },
      candidates_count: 3,
    };

    render(<CoordinationWorkflow execution={execution} isRunning={false} />);
    expect(screen.getByText(/A2A Coordination Workflow/i)).toBeInTheDocument();
    expect(screen.getByText('Requirement Agent')).toBeInTheDocument();
    expect(screen.getByText('Matching Agent')).toBeInTheDocument();
  });

  it('MatchesList triggers Complete and Reject modals', async () => {
    const onComplete = vi.fn();
    const onReject = vi.fn();
    const matches = [
      {
        match_id: 1,
        source_type: 'BLOOD_BANK',
        source_name: 'City Red Cross',
        distance_km: 5.0,
        estimated_time: '12 min',
        priority_score: 0.9,
        units: 2,
        status: 'ACCEPTED',
      },
    ];

    render(
      <MatchesList
        matches={matches}
        requestId={10}
        onComplete={onComplete}
        onReject={onReject}
      />
    );

    expect(screen.getByText('City Red Cross')).toBeInTheDocument();
    expect(screen.getByText('5.0 km')).toBeInTheDocument();

    // Test Complete modal
    fireEvent.click(screen.getByRole('button', { name: 'Complete' }));
    expect(screen.getByText('Complete Match Delivery')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Delivery' }));
    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(1);
    });

    // Test Reject modal
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(screen.getByText('Reject Match')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Rejection Reason/i), { target: { value: 'Traffic delay' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Rejection' }));
    await waitFor(() => {
      expect(onReject).toHaveBeenCalledWith(1, 'Traffic delay');
    });
  });
});

describe('6. Admin Governance & Audit Logs', () => {
  it('AdminDashboardPage provides navigation links to governance and telemetry', () => {
    vi.stubEnv('VITE_GRAFANA_URL', 'https://grafana.example.test');
    vi.stubEnv('VITE_JAEGER_URL', 'https://jaeger.example.test');
    vi.stubEnv('VITE_PROMETHEUS_URL', 'https://prometheus.example.test');

    render(
      <MemoryRouter>
        <AdminDashboardPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/System Administration Console/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Manage Memberships/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /View Audit Logs/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open Grafana/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open Jaeger/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open Prometheus/i })).toBeInTheDocument();
  });

  it('AuditLogsPage renders audit entries', async () => {
    const { listAuditLogs } = await import('../api/admin.js');
    listAuditLogs.mockResolvedValue([
      {
        id: 1,
        action: 'CREATE_REQUEST',
        user_id: 2,
        resource: 'blood_request',
        resource_id: 10,
        timestamp: new Date().toISOString(),
        details: { blood_group: 'O+' },
      },
    ]);

    render(
      <MemoryRouter>
        <AuditLogsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getAllByText('CREATE_REQUEST')[0]).toBeInTheDocument();
      expect(screen.getByText('User #2')).toBeInTheDocument();
    });
  });

  it('MembershipManagementPage grants hospital membership', async () => {
    const { grantHospitalMembership } = await import('../api/admin.js');
    grantHospitalMembership.mockResolvedValue({ membership_id: 7 });

    render(
      <MemoryRouter>
        <MembershipManagementPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getAllByLabelText(/User ID/i)[0], { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText(/^Hospital ID$/i), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /Grant Hospital Membership/i }));

    await waitFor(() => {
      expect(grantHospitalMembership).toHaveBeenCalledWith(3, 1, 'STAFF');
      expect(screen.getByText(/Granted hospital membership #7/i)).toBeInTheDocument();
    });
  });

  it('ProfilePage displays user credentials and facility memberships', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 5, email: 'dr.smith@metro.org', role: 'HOSPITAL_STAFF', is_active: true, hospital_ids: [1, 2], bank_ids: [] },
      logout: vi.fn(),
    });

    render(
      <MemoryRouter>
        <ProfilePage />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { name: /^Profile$/i })).toBeInTheDocument();
    expect(screen.getByText('Account Details')).toBeInTheDocument();
    expect(screen.getByText('Facility Access')).toBeInTheDocument();
    expect(screen.getByText('Account Actions')).toBeInTheDocument();
    expect(screen.queryByText(/session token/i)).not.toBeInTheDocument();
    expect(screen.getByText('dr.smith@metro.org')).toBeInTheDocument();
    expect(screen.getByText('Hospital #1')).toBeInTheDocument();
    expect(screen.getByText('Hospital #2')).toBeInTheDocument();
  });
});
