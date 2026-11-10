import React, { createContext, useContext, useState, useEffect } from 'react';
import { listHospitals } from '../api/hospitals';
import useAuth from '../hooks/useAuth';

const HospitalContext = createContext(null);

const STORAGE_KEY = 'bdm_selected_hospital_id';

export function HospitalProvider({ children }) {
  const { user } = useAuth();
  const [hospitals, setHospitals] = useState([]);
  const [selectedHospitalId, setSelectedHospitalId] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? parseInt(saved, 10) : 1;
  });
  const [loadingHospitals, setLoadingHospitals] = useState(false);

  useEffect(() => {
    let isMounted = true;
    async function load() {
      if (!user) return;
      setLoadingHospitals(true);
      try {
        const list = await listHospitals();
        if (isMounted && Array.isArray(list) && list.length > 0) {
          setHospitals(list);
          // If current selectedHospitalId is not in list, fallback to first hospital
          setSelectedHospitalId((prev) => {
            const exists = list.some((h) => h.hospital_id === prev);
            const fallback = exists ? prev : list[0].hospital_id;
            localStorage.setItem(STORAGE_KEY, fallback.toString());
            return fallback;
          });
        }
      } catch (err) {
        console.warn('Failed to fetch hospitals list:', err);
      } finally {
        if (isMounted) setLoadingHospitals(false);
      }
    }
    load();
    return () => {
      isMounted = false;
    };
  }, [user]);

  const selectHospital = (id) => {
    const parsedId = parseInt(id, 10);
    setSelectedHospitalId(parsedId);
    localStorage.setItem(STORAGE_KEY, parsedId.toString());
  };

  const currentHospital = hospitals.find((h) => h.hospital_id === selectedHospitalId) || null;

  return (
    <HospitalContext.Provider
      value={{
        hospitals,
        selectedHospitalId,
        currentHospital,
        selectHospital,
        loadingHospitals,
      }}
    >
      {children}
    </HospitalContext.Provider>
  );
}

export function useHospital() {
  const context = useContext(HospitalContext);
  if (!context) {
    throw new Error('useHospital must be used within a HospitalProvider');
  }
  return context;
}

export default useHospital;
