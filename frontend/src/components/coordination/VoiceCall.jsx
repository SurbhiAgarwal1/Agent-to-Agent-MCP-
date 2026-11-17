import React, { useState, useCallback, useEffect, useRef } from 'react';
import { dispatchVoiceCall, sendVoiceWebhook } from '../../api/calling';

const IDLE = { isOpen: false, target: null, status: 'IDLE', callId: null, script: '', digit: null };
const OPTIONS = 'Press 1 to accept this request. Press 2 to decline.';
const PAUSE_AFTER_SCRIPT_MS = 2000; // silence after the script before the keypad listens
const NO_RESPONSE_MS = 20000;

// Browsers cut off long utterances, so speak sentence by sentence; resolves when all are done.
function speak(text) {
  return new Promise((resolve) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      setTimeout(resolve, Math.min(15000, text.length * 60));
      return;
    }
    const parts = text.match(/[^.!?]+[.!?]*/g) || [text];
    window.speechSynthesis.cancel();
    let i = 0;
    const next = () => {
      if (i >= parts.length) return resolve();
      const u = new SpeechSynthesisUtterance(parts[i++].trim());
      u.onend = next;
      u.onerror = next;
      window.speechSynthesis.speak(u);
    };
    next();
  });
}

/**
 * Voice (calling) agent. start(source) rings the source, reads the FULL script (including
 * "press 1 to accept, press 2 to decline"), pauses ~2s, then waits for the receiver's keypress.
 * Only a real press of 1 confirms; 2 declines; no press = no response.
 * In this demo the receiver's keypad is on screen (or press 1 / 2 on the keyboard).
 */
export function useVoiceCall({ request, hospitalName }) {
  const [call, setCall] = useState(IDLE);
  const run = useRef(0); // id of the active call, so stale timers are ignored

  const close = useCallback(() => {
    run.current += 1;
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel();
    setCall(IDLE);
  }, []);

  const press = useCallback(async (digit) => {
    const id = run.current;
    let callId = null;
    setCall((p) => { callId = p.callId; return p.status === 'WAITING' ? { ...p, status: 'PROCESSING', digit } : p; });
    await Promise.resolve();
    if (id !== run.current) return;
    try { if (callId) await sendVoiceWebhook({ call_id: callId, call_status: 'COMPLETED', digits_pressed: digit, duration_seconds: 20 }); } catch { /* keep the call moving */ }
    if (id !== run.current) return;
    const accepted = digit === '1';
    setCall((p) => ({ ...p, status: accepted ? 'CONFIRMED' : 'DECLINED', digit }));
    await speak(accepted ? 'Thank you for your response. Your acceptance has been recorded. Goodbye.' : 'Thank you for your response. We have noted that you cannot help this time. Goodbye.');
  }, []);

  const start = useCallback(async (source) => {
    if (!source || !request) return;
    run.current += 1;
    const id = run.current;
    const name = source.name || source.source_name || (source.source_type === 'DONOR' ? `Donor #${source.source_id}` : `Blood bank #${source.source_id}`);
    setCall({ isOpen: true, target: { ...source, name }, status: 'DIALING', callId: null, script: `Calling ${name}...`, digit: null });
    try {
      const res = await dispatchVoiceCall({
        request_id: request.request_id,
        recipient_type: source.source_type || 'BLOOD_BANK',
        recipient_id: source.source_id || 1,
        recipient_phone: source.phone || source.contact_phone || '+919876543210',
        recipient_name: name,
        hospital_id: request.hospital_id,
        hospital_name: hospitalName || `Hospital #${request.hospital_id}`,
        blood_group: request.blood_group,
        units_required: request.units_required,
        urgency: request.urgency,
      });
      if (id !== run.current) return;
      const callId = res?.call_id;
      let script = (res?.tts_script || `Hello ${name}. This is the emergency blood coordination system calling on behalf of ${hospitalName || 'the hospital'}. We urgently need ${request.units_required} units of ${request.blood_group} blood.`).trim();
      if (!/press\s*1/i.test(script)) script = `${script} ${OPTIONS}`;
      setCall((p) => ({ ...p, status: 'SPEAKING', callId, script }));
      await speak(script);
      if (id !== run.current) return;
      await new Promise((r) => setTimeout(r, PAUSE_AFTER_SCRIPT_MS));
      if (id !== run.current) return;
      setCall((p) => ({ ...p, status: 'WAITING' }));
      setTimeout(() => {
        if (id !== run.current) return;
        setCall((p) => (p.status === 'WAITING' ? { ...p, status: 'NO_RESPONSE' } : p));
      }, NO_RESPONSE_MS);
    } catch (err) {
      if (id !== run.current) return;
      setCall((p) => ({ ...p, status: 'FAILED', script: err?.message || 'Call dispatch failed.' }));
    }
  }, [request, hospitalName]);

  useEffect(() => {
    if (call.status !== 'WAITING') return undefined;
    const onKey = (e) => { if (e.key === '1' || e.key === '2') press(e.key); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [call.status, press]);

  const title = {
    DIALING: 'Calling blood source…',
    SPEAKING: 'Voice agent is speaking…',
    WAITING: 'Waiting for the receiver to press a key…',
    PROCESSING: 'Recording response…',
    CONFIRMED: 'Receiver pressed 1: request accepted',
    DECLINED: 'Receiver pressed 2: request declined',
    NO_RESPONSE: 'No key pressed: no response',
    FAILED: 'Call attempt unsuccessful',
  }[call.status];
  const icon = { CONFIRMED: '✓', DECLINED: '✕', NO_RESPONSE: '⌛' }[call.status] || '📞';
  const bg = { CONFIRMED: '#dcfce7', DECLINED: '#fee2e2', NO_RESPONSE: '#fef3c7' }[call.status] || '#eff6ff';

  const modal = call.isOpen ? (
    <div role="dialog" aria-label="Voice agent call" style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, padding: '1.5rem' }}>
      <div className="bc-panel" style={{ maxWidth: 480, width: '100%', textAlign: 'center', padding: '1.75rem' }}>
        <div style={{ width: 64, height: 64, margin: '0 auto 1rem', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.8rem', background: bg }}>{icon}</div>
        <h3 style={{ margin: '0 0 .3rem' }}>{title}</h3>
        <p style={{ color: '#64748b', margin: '0 0 1rem' }}>Target: <strong>{call.target?.name}</strong>
          {call.target?.distance_km != null && ` (${Number(call.target.distance_km).toFixed(1)} km away)`}</p>
        <div style={{ textAlign: 'left', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '1rem', fontSize: '.88rem', marginBottom: '1.25rem' }}>
          <div style={{ color: '#0284c7', fontWeight: 700, fontSize: '.72rem', textTransform: 'uppercase', marginBottom: '.3rem' }}>Voice script and interactive IVR</div>
          <em>"{call.script}"</em>
          {call.digit && <div style={{ marginTop: '.7rem', fontWeight: 600 }}>Key pressed by receiver: [{call.digit}]</div>}
        </div>
        {call.status === 'WAITING' && (
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ color: '#64748b', fontSize: '.8rem', marginBottom: '.5rem' }}>Receiver keypad (demo): press 1 or 2, on screen or on your keyboard</div>
            <div style={{ display: 'flex', gap: '.75rem', justifyContent: 'center' }}>
              <button type="button" className="bc-btn" onClick={() => press('1')}>1 · Accept</button>
              <button type="button" className="bc-btn ghost" onClick={() => press('2')}>2 · Decline</button>
            </div>
          </div>
        )}
        <button type="button" className="bc-btn ghost" onClick={close}>
          {['CONFIRMED', 'DECLINED', 'NO_RESPONSE', 'FAILED'].includes(call.status) ? 'Done' : 'End call'}
        </button>
      </div>
    </div>
  ) : null;
  return { start, modal };
}

export function CallButton({ onCall, source }) {
  return <button type="button" className="bc-btn ghost sm" onClick={() => onCall(source)}>📞 Call</button>;
}
