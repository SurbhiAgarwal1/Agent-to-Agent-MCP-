import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const api = vi.hoisted(() => ({
  getPortalMe: vi.fn(), listDonorNotifications: vi.fn(), respondDonorNotification: vi.fn(),
  setDonorAvailability: vi.fn(), getBankInventory: vi.fn(), saveBankInventory: vi.fn(),
  listBankNotifications: vi.fn(), respondBankNotification: vi.fn(),
  listHospitalAlerts: vi.fn(), markHospitalAlertRead: vi.fn(), getRequestResponses: vi.fn(),
}));
vi.mock('../api/portal', () => api);

import DonorDashboardPage from '../pages/DonorDashboardPage.jsx';
import BloodBankDashboardPage from '../pages/BloodBankDashboardPage.jsx';
import ResponsesPanel from '../components/coordination/ResponsesPanel.jsx';

beforeEach(() => vi.clearAllMocks());

describe('portal pages', () => {
  it('donor sees an alert and accepts it', async () => {
    api.getPortalMe.mockResolvedValue({ kind: 'donor', profile: { name: 'Asha', blood_group: 'B+', city: 'Pune', available: true, donation_count: 2 } });
    api.listDonorNotifications.mockResolvedValue({ items: [{ id: 7, blood_request_id: 3, blood_group: 'B+', units_needed: 2, hospital_name: 'City Hospital', response_status: 'pending' }] });
    api.respondDonorNotification.mockResolvedValue({});
    render(<MemoryRouter><DonorDashboardPage /></MemoryRouter>);
    await screen.findByText('City Hospital');
    fireEvent.click(screen.getByText('Accept'));
    await waitFor(() => expect(api.respondDonorNotification).toHaveBeenCalledWith(7, 'accepted'));
  });

  it('blood bank accept sends the units and shows API errors', async () => {
    api.getBankInventory.mockResolvedValue({ bank: { name: 'Red Bank' }, items: [{ blood_group: 'O+', component_type: 'packed_red_blood_cells', available_units: 4, reserved_units: 0 }] });
    api.listBankNotifications.mockResolvedValue({ items: [{ id: 9, blood_request_id: 5, blood_group: 'O+', inventory_blood_group: 'O+', required_units: 2, in_stock_units: 4, response_status: 'pending', hospital_name: 'City Hospital' }] });
    api.respondBankNotification.mockRejectedValue(new Error('Not enough stock'));
    render(<MemoryRouter><BloodBankDashboardPage /></MemoryRouter>);
    await screen.findByText('Red Bank');
    fireEvent.click(screen.getByText('Accept'));
    await waitFor(() => expect(api.respondBankNotification).toHaveBeenCalledWith(9, { response_status: 'accepted', confirmed_available_units: 2 }));
    await screen.findByText('Not enough stock');
  });

  it('hospital responses panel shows confirmed units', async () => {
    api.getRequestResponses.mockResolvedValue({ units_required: 2, confirmed_units: 1, is_covered: false, counts: { notified: 2, pending: 1, accepted: 1 }, responses: [{ source_type: 'DONOR', source_id: 4, notification_id: 1, response_status: 'accepted', units: 1 }], warnings: [] });
    render(<MemoryRouter><ResponsesPanel requestId={5} /></MemoryRouter>);
    expect(await screen.findByTestId('confirmed-line')).toHaveTextContent('1 of 2 unit(s) confirmed');
  });
});
