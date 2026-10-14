import React from 'react';
import { Link } from 'react-router-dom';
import Card from '../components/common/Card';

export default function NotFoundPage() {
  return (
    <div
      style={{
        minHeight: '70vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem 1rem',
      }}
    >
      <div style={{ maxWidth: '480px', width: '100%', textAlign: 'center' }}>
        <Card>
          <div style={{ fontSize: '3rem', fontWeight: 800, color: 'var(--color-primary)' }}>
            404
          </div>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0.75rem 0 0.5rem', color: 'var(--color-text-main)' }}>
            Page Not Found
          </h1>
          <p className="text-secondary" style={{ fontSize: '0.875rem', marginBottom: '1.5rem', lineHeight: 1.5 }}>
            The requested page does not exist or you may not have authorization to view this resource.
          </p>
          <Link to="/" className="btn btn-primary">
            Return to Homepage
          </Link>
        </Card>
      </div>
    </div>
  );
}
