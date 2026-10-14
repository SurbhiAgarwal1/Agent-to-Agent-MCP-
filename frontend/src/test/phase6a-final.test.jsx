import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppLayout } from '../components/layout/AppLayout.jsx';
import { Sidebar } from '../components/layout/Sidebar.jsx';
import AdminDashboardPage from '../pages/AdminDashboardPage.jsx';
import ChatBloodRequest from '../components/blood/ChatBloodRequest.jsx';

const authState = {
  user: { role: 'HOSPITAL_STAFF', email: 'staff@example.com' },
  logout: vi.fn(),
  sessionExpiredMessage: null,
  clearExpiredMessage: vi.fn(),
};

const { mockProcessNlRequest } = vi.hoisted(() => ({
  mockProcessNlRequest: vi.fn(),
}));

vi.mock('../hooks/useAuth.js', () => ({
  default: () => authState,
  useAuth: () => authState,
}));

vi.mock('../api/bloodRequests.js', () => ({
  processNlRequest: mockProcessNlRequest,
}));

describe('Phase 6A final frontend behavior', () => {
  beforeEach(() => {
    authState.user = { role: 'HOSPITAL_STAFF', email: 'staff@example.com' };
    mockProcessNlRequest.mockReset();
    mockProcessNlRequest.mockResolvedValue({
      request_id: 205,
      summary: 'Your request was received.',
    });
    vi.stubEnv('VITE_GRAFANA_URL', '');
    vi.stubEnv('VITE_JAEGER_URL', '');
    vi.stubEnv('VITE_PROMETHEUS_URL', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('hamburger opens and closes the sidebar with accessible state', () => {
    render(<MemoryRouter><AppLayout /></MemoryRouter>);

    const menu = screen.getByRole('button', { name: 'Open navigation' });
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    expect(menu).toHaveAttribute('aria-controls', 'app-sidebar');

    fireEvent.click(menu);
    expect(screen.getByRole('button', { name: 'Close navigation' })).toHaveAttribute(
      'aria-expanded',
      'true'
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close navigation' }));
    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  it('Escape closes the open sidebar', () => {
    render(<MemoryRouter><AppLayout /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
    expect(document.querySelector('.sidebar.open')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(document.querySelector('.sidebar.open')).toBeFalsy();
  });

  it('clicking the mobile backdrop closes the sidebar', () => {
    render(<MemoryRouter><AppLayout /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
    const backdrop = document.querySelector('.mobile-backdrop');
    expect(backdrop).toBeTruthy();

    fireEvent.click(backdrop);
    expect(document.querySelector('.sidebar.open')).toBeFalsy();
  });

  it('navigation items close the sidebar', () => {
    render(<MemoryRouter><AppLayout /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
    fireEvent.click(screen.getByRole('link', { name: /Dashboard/i }));

    expect(document.querySelector('.sidebar.open')).toBeFalsy();
  });

  it('does not render observability links when URLs are not configured', () => {
    authState.user = { role: 'ADMIN', email: 'admin@example.com' };

    render(<MemoryRouter><AdminDashboardPage /></MemoryRouter>);

    expect(screen.getAllByText('Not configured')).toHaveLength(3);
    expect(screen.queryByRole('link', { name: /Open Grafana/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open Jaeger/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open Prometheus/i })).not.toBeInTheDocument();
  });

  it('renders configured observability URLs as real admin links', () => {
    authState.user = { role: 'ADMIN', email: 'admin@example.com' };
    vi.stubEnv('VITE_GRAFANA_URL', 'https://grafana.example.test');
    vi.stubEnv('VITE_JAEGER_URL', 'https://jaeger.example.test');
    vi.stubEnv('VITE_PROMETHEUS_URL', 'https://prometheus.example.test');

    render(<MemoryRouter><AdminDashboardPage /></MemoryRouter>);

    expect(screen.getByRole('link', { name: /Open Grafana/i })).toHaveAttribute(
      'href',
      'https://grafana.example.test'
    );
    expect(screen.getByRole('link', { name: /Open Jaeger/i })).toHaveAttribute(
      'href',
      'https://jaeger.example.test'
    );
    expect(screen.getByRole('link', { name: /Open Prometheus/i })).toHaveAttribute(
      'href',
      'https://prometheus.example.test'
    );
  });

  it('submits the blood request chat and shows the response', async () => {
    render(<MemoryRouter><ChatBloodRequest /></MemoryRouter>);

    const input = screen.getByLabelText(/describe your blood requirement/i);
    fireEvent.change(input, {
      target: { value: 'We need 2 units of O+ blood.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send blood request/i }));

    await waitFor(() => {
      expect(mockProcessNlRequest).toHaveBeenCalledWith('We need 2 units of O+ blood.');
    });

    expect(await screen.findByText('Your request was received.')).toBeInTheDocument();
  });

  it('supports Shift+Enter without submitting the chat', () => {
    render(<MemoryRouter><ChatBloodRequest /></MemoryRouter>);

    const input = screen.getByLabelText(/describe your blood requirement/i);
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });

    expect(mockProcessNlRequest).not.toHaveBeenCalled();
  });
});
