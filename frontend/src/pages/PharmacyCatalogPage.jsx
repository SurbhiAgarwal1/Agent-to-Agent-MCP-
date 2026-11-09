import React, { useEffect, useState } from 'react';
import Card from '../components/common/Card';
import LoadingSpinner from '../components/common/LoadingSpinner';
import Button from '../components/common/Button';

export default function PharmacyCatalogPage() {
  const [medicines, setMedicines] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedMed, setSelectedMed] = useState(null);
  const [substitutes, setSubstitutes] = useState([]);
  const [subLoading, setSubLoading] = useState(false);
  const [stockList, setStockList] = useState([]);
  const [orderSuccess, setOrderSuccess] = useState(null);

  useEffect(() => {
    fetchMedicines();
  }, []);

  const fetchMedicines = async (query = '') => {
    setLoading(true);
    try {
      const url = query ? `/api/v1/pharmacy/medicines?query=${encodeURIComponent(query)}` : '/api/v1/pharmacy/medicines';
      const res = await fetch(url);
      const data = await res.json();
      setMedicines(data || []);
    } catch (err) {
      console.error('Failed to fetch medicines:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    fetchMedicines(search);
  };

  const handleSelectMedicine = async (med) => {
    setSelectedMed(med);
    setSubLoading(true);
    setOrderSuccess(null);
    try {
      // 1. Fetch Truemeds-style generic substitutes
      const subRes = await fetch(`/api/v1/pharmacy/medicines/${med.medicine_id}/substitutes`);
      const subData = await subRes.json();
      setSubstitutes(subData || []);

      // 2. Fetch live stock across Sanvivo / Apollo partner pharmacies
      const stockRes = await fetch(`/api/v1/pharmacy/stock?medicine_id=${med.medicine_id}&user_lat=28.6139&user_lon=77.2090`);
      const stockData = await stockRes.json();
      setStockList(stockData || []);
    } catch (err) {
      console.error('Failed to fetch details:', err);
    } finally {
      setSubLoading(false);
    }
  };

  const handleQuickOrder = async (medicineId, qty = 1) => {
    try {
      const res = await fetch('/api/v1/pharmacy/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          delivery_address: '12 Medical Square, Central District, Metro City',
          delivery_latitude: 28.6139,
          delivery_longitude: 77.2090,
          urgency: 'HIGH',
          items: [{ medicine_id: medicineId, quantity: qty, allow_substitute: true }]
        })
      });
      const orderData = await res.json();
      if (res.ok) {
        setOrderSuccess(`Order #${orderData.order_id} placed! Allocated to ${orderData.pharmacy_name || 'Partner Pharmacy'}. ETA: ${orderData.estimated_eta_minutes} mins.`);
      } else {
        alert(orderData.detail || 'Could not place order.');
      }
    } catch (err) {
      alert('Error placing order: ' + err.message);
    }
  };

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '1rem' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>
          Hyperlocal Medicine Delivery & Truemeds Substitutes
        </h1>
        <p className="text-secondary" style={{ marginTop: '0.25rem' }}>
          Explore generic formulations (Truemeds pattern) and order from local partner pharmacies (Sanvivo / Apollo 24x7 pattern).
        </p>
      </div>

      <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <input
          type="text"
          placeholder="Search by brand name or active chemical salt (e.g. Paracetamol, Dolo 650, Augmentin)..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: 1,
            padding: '0.65rem 1rem',
            borderRadius: '6px',
            border: '1px solid #ccc',
            fontSize: '0.95rem'
          }}
        />
        <Button type="submit">Search</Button>
      </form>

      {orderSuccess && (
        <div className="alert alert-success" style={{ marginBottom: '1.5rem', padding: '1rem', background: '#e6fffa', border: '1px solid #38b2ac', borderRadius: '6px' }}>
          <strong>Success!</strong> {orderSuccess}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: selectedMed ? '1fr 1fr' : '1fr', gap: '1.5rem' }}>
        <div>
          <h3>Medication Catalog</h3>
          {loading ? (
            <LoadingSpinner message="Searching catalog..." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
              {medicines.map((med) => (
                <Card key={med.medicine_id} style={{ cursor: 'pointer', border: selectedMed?.medicine_id === med.medicine_id ? '2px solid #3182ce' : '1px solid #e2e8f0' }}>
                  <div onClick={() => handleSelectMedicine(med)}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '1.1rem', fontWeight: 600 }}>{med.brand_name}</span>
                      <span style={{ fontSize: '0.75rem', padding: '2px 8px', borderRadius: '12px', background: med.rx_required ? '#fed7d7' : '#c6f6d5' }}>
                        {med.rx_required ? 'Rx Required' : 'OTC'}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#4a5568', marginTop: '0.2rem' }}>
                      <strong>Active Salt:</strong> {med.generic_name}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#718096', marginTop: '0.2rem' }}>
                      {med.dosage_form} • {med.strength} • {med.manufacturer}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        {selectedMed && (
          <div>
            <h3>Fulfillment & Truemeds Substitutes</h3>
            <Card style={{ marginTop: '0.5rem', background: '#f7fafc' }}>
              <h4>{selectedMed.brand_name}</h4>
              <p style={{ fontSize: '0.85rem', color: '#4a5568' }}>{selectedMed.description}</p>
              
              <div style={{ marginTop: '1rem' }}>
                <h5>Local Partner Pharmacy Stock (Sanvivo Hyperlocal Network):</h5>
                {subLoading ? (
                  <LoadingSpinner message="Checking local pharmacies..." />
                ) : stockList.length > 0 ? (
                  stockList.map((st) => (
                    <div key={st.inventory_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid #edf2f7' }}>
                      <div>
                        <strong>{st.pharmacy_name}</strong>
                        <div style={{ fontSize: '0.8rem', color: '#718096' }}>{st.pharmacy_address} ({st.distance_km || 5} km away)</div>
                        <div style={{ fontSize: '0.8rem', color: '#2b6cb0' }}>Available: {st.units_available} units • ₹{st.unit_price} / unit</div>
                      </div>
                      <Button size="small" onClick={() => handleQuickOrder(selectedMed.medicine_id, 1)}>Order Now</Button>
                    </div>
                  ))
                ) : (
                  <div style={{ fontSize: '0.85rem', color: '#e53e3e' }}>Out of stock in nearby pharmacies. Check Truemeds substitutes below!</div>
                )}
              </div>

              <div style={{ marginTop: '1.5rem' }}>
                <h5 style={{ color: '#2c5282' }}>Truemeds Active Salt Substitutes:</h5>
                <p style={{ fontSize: '0.8rem', color: '#718096' }}>Equivalent medicines containing the exact same active salt: <strong>{selectedMed.generic_name}</strong></p>
                {substitutes.length > 0 ? (
                  substitutes.map((sub) => (
                    <div key={sub.medicine_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem', background: '#ebf8ff', borderRadius: '6px', marginBottom: '0.5rem' }}>
                      <div>
                        <strong>{sub.brand_name}</strong> ({sub.manufacturer})
                        <div style={{ fontSize: '0.75rem', color: '#2b6cb0' }}>Avg Price: ₹{sub.unit_price} • Total Available: {sub.available_units} units</div>
                      </div>
                      <Button size="small" variant="secondary" onClick={() => handleQuickOrder(sub.medicine_id, 1)}>Order Substitute</Button>
                    </div>
                  ))
                ) : (
                  <div style={{ fontSize: '0.8rem', color: '#718096' }}>No alternate brands found for this active formulation.</div>
                )}
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
