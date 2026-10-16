import React from 'react';
import { Link } from 'react-router-dom';
import useAuth from '../hooks/useAuth';

export default function LandingPage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="landing-page" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navigation */}
      <header
        style={{
          backgroundColor: '#FFFFFF',
          borderBottom: '1px solid var(--border-color)',
          padding: '1rem 2rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '6px',
              backgroundColor: 'var(--color-primary)',
              color: '#FFFFFF',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: '1rem',
            }}
          >
            +
          </div>
          <span style={{ fontWeight: 700, fontSize: '1.125rem', color: 'var(--color-text-main)' }}>
            Blood Donation Coordination Platform
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          {isAuthenticated ? (
            <Link to="/dashboard" className="btn btn-primary">
              Open Dashboard
            </Link>
          ) : (
            <>
              <Link to="/login" className="btn btn-outline">
                Login
              </Link>
              <Link to="/signup" className="btn btn-primary">
                Sign Up
              </Link>
            </>
          )}
        </div>
      </header>

      {/* Hero Section */}
      <section
        style={{
          padding: '5rem 1.5rem 4rem',
          textAlign: 'center',
          backgroundColor: 'var(--color-bg)',
          maxWidth: '900px',
          margin: '0 auto',
        }}
      >
        <div
          style={{
            display: 'inline-block',
            padding: '0.35rem 0.85rem',
            borderRadius: '9999px',
            backgroundColor: '#FEE2E2',
            color: 'var(--color-primary)',
            fontSize: '0.8125rem',
            fontWeight: 600,
            marginBottom: '1.5rem',
            letterSpacing: '0.025em',
          }}
        >
          FAST, RELIABLE BLOOD COORDINATION
        </div>

        <h1
          style={{
            fontSize: '2.5rem',
            fontWeight: 800,
            color: 'var(--color-text-main)',
            lineHeight: 1.25,
            marginBottom: '1.25rem',
          }}
        >
          Coordinate urgent blood requirements with the right resources, faster.
        </h1>

        <p
          className="text-secondary"
          style={{
            fontSize: '1.125rem',
            maxWidth: '680px',
            margin: '0 auto 2.5rem',
            lineHeight: 1.6,
          }}
        >
          A secure healthcare platform that helps hospitals find compatible blood sources quickly, track requests, and coordinate fulfillment.
        </p>

        <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          {isAuthenticated ? (
            <Link to="/dashboard" className="btn btn-primary" style={{ padding: '0.75rem 1.75rem', fontSize: '1rem' }}>
              Go to Operational Dashboard
            </Link>
          ) : (
            <>
              <Link to="/login" className="btn btn-primary" style={{ padding: '0.75rem 2rem', fontSize: '1rem' }}>
                Login to Portal
              </Link>
              <Link to="/signup" className="btn btn-outline" style={{ padding: '0.75rem 2rem', fontSize: '1rem' }}>
                Create Hospital Account
              </Link>
            </>
          )}
        </div>

        <div
          style={{
            marginTop: '3rem',
            paddingTop: '2rem',
            borderTop: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'center',
            gap: '2.5rem',
            color: 'var(--color-text-muted)',
            fontSize: '0.875rem',
            fontWeight: 500,
          }}
        >
          <span>✓ Secure request coordination</span>
          <span>✓ Real-time blood availability</span>
          <span>✓ Secure role-based access</span>
          <span>✓ Clear activity history</span>
        </div>
      </section>

      {/* Feature Architecture Cards */}
      <section
        style={{
          padding: '3rem 1.5rem 5rem',
          backgroundColor: '#FFFFFF',
          borderTop: '1px solid var(--border-color)',
        }}
      >
        <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
            <h2 style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--color-text-main)', marginBottom: '0.5rem' }}>
              Built for Clinical Urgency
            </h2>
            <p className="text-secondary" style={{ fontSize: '0.9375rem' }}>
              Every request is handled with clear status updates, facility access controls, and healthcare-focused workflows.
            </p>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: '1.5rem',
            }}
          >
            <div
              style={{
                padding: '1.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--color-bg)',
              }}
            >
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '6px',
                  backgroundColor: '#DBEAFE',
                  color: '#1E40AF',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  marginBottom: '1rem',
                }}
              >
                01
              </div>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                Requirement Validation
              </h3>
              <p className="text-secondary" style={{ fontSize: '0.875rem', lineHeight: 1.5 }}>
                Captures blood group, unit requirements, urgency, and other details needed to process a request accurately.
              </p>
            </div>

            <div
              style={{
                padding: '1.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--color-bg)',
              }}
            >
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '6px',
                  backgroundColor: '#DCFCE7',
                  color: '#166534',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  marginBottom: '1rem',
                }}
              >
                02
              </div>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                Blood Matching & Allocation
              </h3>
              <p className="text-secondary" style={{ fontSize: '0.875rem', lineHeight: 1.5 }}>
                Finds compatible blood sources and helps allocate available units based on the request.
              </p>
            </div>

            <div
              style={{
                padding: '1.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--color-bg)',
              }}
            >
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '6px',
                  backgroundColor: '#FEF3C7',
                  color: '#92400E',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  marginBottom: '1rem',
                }}
              >
                03
              </div>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                Location & Dispatch
              </h3>
              <p className="text-secondary" style={{ fontSize: '0.875rem', lineHeight: 1.5 }}>
                Helps identify nearby blood sources and supports faster dispatch planning.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer
        style={{
          marginTop: 'auto',
          padding: '2rem 1.5rem',
          backgroundColor: '#FFFFFF',
          borderTop: '1px solid var(--border-color)',
          textAlign: 'center',
          color: 'var(--color-text-muted)',
          fontSize: '0.8125rem',
        }}
      >
        <p style={{ margin: 0 }}>Blood Donation Coordination Platform &copy; {new Date().getFullYear()}</p>
        <p style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}>
          Secure Healthcare Portal &bull; Audited Operational Access
        </p>
      </footer>
    </div>
  );
}
