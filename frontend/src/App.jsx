import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext.jsx';
import { HospitalProvider } from './context/HospitalContext.jsx';
import AppRoutes from './routes/AppRoutes.jsx';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <HospitalProvider>
          <AppRoutes />
        </HospitalProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
