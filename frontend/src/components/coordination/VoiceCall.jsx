import React, { useState, useCallback } from 'react';
import { dispatchVoiceCall, sendVoiceWebhook } from '../../api/calling';

const IDLE = { isOpen: false, target: null, status: 'IDLE', callId: null, script: '' };

/**
 * Voice (calling) agent: dials a blood bank or donor about this request.
 * start(source) opens the call window; `modal` must be rendered once by the page.
 * source = { source_type: 'BLOOD_BANK' | 'DONOR', source_id, name, distance_km?, phone? }
 */
export function useVoiceCall({ request, hospitalName }) {
  const [call, setCall] = useState(IDLE);
  const close = useCallback(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel();
    setCall(IDLE);
  }, []);

  const start = useCallback(async (source) => {
    if (!source || !request) return;
    const name = source.name || source.source_name || (source.source_type === 'DONOR' ? `Donor #${source.source_id}` : `Blood bank #${source.source_id}`);
    setCall({ isOpen: true, target: { ...source, name }, status: 'DIALING', callId: null, script: `Calling ${name}...` });
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
      const callId = res?.call_id;
      const script = res?.tts_script || `Emergency blood request for ${hospitalName || 'the hospital'}: ${request.units_required} units of ${request.blood_group} required. Press 1 to confirm supply.`;
      setCall((p) => ({ ...p, status: 'CONNECTED', callId, script }));
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(`Emergency blood coordination. Calling ${name}. Urgent requirement of ${request.units_required} units of ${request.blood_group} blood for ${hospitalName || 'the hospital'}. Please confirm dispatch.`);
        window.speechSynthesis.speak(u);
      }
      // Demo: the recipient's keypress "1" is simulated after a few seconds, exactly as before.
      setTimeout(async () => {
        try { if (callId) await sendVoiceWebhook({ call_id: callId, call_status: 'COMPLETED', digits_pressed: '1', duration_seconds: 15 }); } catch { /* keep the demo moving */ }
        setCall((p) => (p.callId === callId ? { ...p, status: 'CONFIRMED' } : p));
      }, 4000);
    } catch (err) {
      setCall((p) => ({ ...p, status: 'FAILED', script: err?.message || 'Call dispatch failed.' }));
    }
  }, [request, hospitalName]);

  const title = { DIALING: 'Calling blood source…', CONNECTED: 'Voice agent speaking with source', CONFIRMED: 'Availability confirmed by voice', FAILED: 'Call attempt unsuccessful' }[call.status];
  const modal = call.isOpen ? (
    <div role="dialog" aria-label="Voice agent call" style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, padding: '1.5rem' }}>
      <div className="bc-panel" style={{ maxWidth: 480, width: '100%', textAlign: 'center', padding: '1.75rem' }}>
        <div style={{ width: 64, height: 64, margin: '0 auto 1rem', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.8rem',
          background: call.status === 'CONFIRMED' ? '#dcfce7' : '#eff6ff' }}>{call.status === 'CONFIRMED' ? '✓' : '📞'}</div>
        <h3 style={{ margin: '0 0 .3rem' }}>{title}</h3>
        <p style={{ color: '#64748b', margin: '0 0 1rem' }}>Target: <strong>{call.target?.name}</strong>
          {call.target?.distance_km != null && ` (${Number(call.target.distance_km).toFixed(1)} km away)`}</p>
        <div style={{ textAlign: 'left', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '1rem', fontSize: '.88rem', marginBottom: '1.25rem' }}>
          <div style={{ color: '#0284c7', fontWeight: 700, fontSize: '.72rem', textTransform: 'uppercase', marginBottom: '.3rem' }}>Voice script and interactive IVR</div>
          <em>"{call.script}"</em>
          {call.status === 'CONFIRMED' && <div style={{ marginTop: '.7rem', color: '#065f46', fontWeight: 600 }}>✓ Keypress received: [1] supply confirmed (simulated in this demo)</div>}
        </div>
        <button type="button" className="bc-btn" onClick={close}>{call.status === 'CONFIRMED' ? 'Done' : 'End call'}</button>
      </div>
    </div>
  ) : null;
  return { start, modal };
}

export function CallButton({ onCall, source }) {
  return <button type="button" className="bc-btn ghost sm" onClick={() => onCall(source)}>📞 Call</button>;
}
