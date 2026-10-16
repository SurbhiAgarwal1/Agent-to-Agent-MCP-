import React, { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { processNlRequest } from '../../api/bloodRequests';
import Card from '../common/Card';

export default function ChatBloodRequest() {
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const textareaRef = useRef(null);

  const handleSubmit = async (event) => {
    event?.preventDefault();
    const text = input.trim();

    if (!text || submitting) {
      if (!text) setError('Please describe your blood requirement.');
      return;
    }

    setError(null);
    setMessages((current) => [...current, { role: 'user', content: text }]);
    setInput('');
    setSubmitting(true);

    try {
      const response = await processNlRequest(text);

      if (!response || response.success === false) {
        throw new Error(
          response?.message || 'We could not process your blood request.'
        );
      }

      const summary =
        response?.message ||
        response?.summary ||
        response?.response ||
        'Your request was received.';

      setMessages((current) => [...current, { role: 'assistant', content: summary }]);

      const requestId =
        response?.request_id ||
        response?.extracted_fields?.request_id ||
        response?.structured_result?.request_id ||
        response?.requirement?.request_id;

      if (requestId) {
        setTimeout(() => navigate(`/blood-requests/${requestId}`), 900);
      }
    } catch (err) {
      setError(err?.message || 'We could not submit your request. Please try again.');
    } finally {
      setSubmitting(false);
      textareaRef.current?.focus();
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  return (
    <div style={{ maxWidth: '820px', margin: '0 auto' }}>
      <Link to="/blood-requests" className="text-secondary" style={{ fontSize: '0.875rem' }}>
        &larr; Back to Blood Requests
      </Link>

      <div style={{ margin: '0.75rem 0 1.5rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--color-text-main)' }}>
          Request Blood
        </h1>
        <p className="text-secondary" style={{ marginTop: '0.35rem', fontSize: '0.9375rem' }}>
          Tell us what blood you need and we'll help find available sources.
        </p>
      </div>

      <Card>
        <div
          aria-live="polite"
          style={{
            minHeight: messages.length ? '260px' : '220px',
            maxHeight: '52vh',
            overflowY: 'auto',
            padding: '0.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.9rem',
          }}
        >
          {messages.length === 0 ? (
            <div
              style={{
                margin: 'auto',
                maxWidth: '560px',
                textAlign: 'center',
                padding: '2rem 1rem',
              }}
            >
              <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>🩸</div>
              <h2 style={{ fontSize: '1.1rem', margin: 0 }}>How can we help?</h2>
              <p className="text-secondary" style={{ margin: '0.5rem 0 0', lineHeight: 1.6 }}>
                Describe the blood group, number of units, urgency, and any other useful details.
              </p>
            </div>
          ) : (
            messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                style={{
                  display: 'flex',
                  justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <div
                  style={{
                    maxWidth: '78%',
                    padding: '0.75rem 0.9rem',
                    borderRadius: '14px',
                    backgroundColor:
                      message.role === 'user' ? 'var(--color-primary-subtle)' : 'var(--color-bg)',
                    border: '1px solid var(--color-border)',
                    lineHeight: 1.55,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {message.content}
                </div>
              </div>
            ))
          )}

          {submitting && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div
                role="status"
                className="text-secondary"
                style={{
                  padding: '0.75rem 0.9rem',
                  borderRadius: '14px',
                  backgroundColor: 'var(--color-bg)',
                  border: '1px solid var(--color-border)',
                }}
              >
                Processing your request…
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="alert alert-error" role="alert" style={{ marginTop: '1rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ marginTop: '1rem' }}>
          <label className="form-label" htmlFor="blood-request-chat">
            Describe your blood requirement
          </label>
          <div className="blood-chat-composer">
            <textarea
              ref={textareaRef}
              id="blood-request-chat"
              rows={3}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Tell us naturally what you need — for example, “We need 2 units of O+ blood urgently for a patient undergoing surgery.”"
              disabled={submitting}
              aria-describedby="blood-request-chat-help"
            />
            <button
              type="submit"
              className="blood-chat-send"
              disabled={submitting || !input.trim()}
              aria-label="Send blood request"
              title="Send request"
            >
              {submitting ? (
                <span aria-hidden="true">…</span>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M22 2 11 13" />
                  <path d="m22 2-7 20-4-9-9-4Z" />
                </svg>
              )}
            </button>
          </div>
          <small id="blood-request-chat-help" className="text-muted">
            Press Enter to send. Use Shift+Enter for a new line.
          </small>
        </form>
      </Card>
    </div>
  );
}
