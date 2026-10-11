# Emergency Command Center UI (Part 13)

The **Emergency Command Center UI** is a lightweight Single Page Application (SPA) designed to visualize and coordinate active emergency blood requests in real time.

## Features
0. **Sign in / register**: the UI requires a login. Public registration creates a `HOSPITAL_STAFF` account; `BLOOD_BANK_STAFF` and `ADMIN` accounts are created by an administrator. The JWT is kept in `sessionStorage` (cleared when the tab closes) and sent as `Authorization: Bearer <token>`. An expired or invalid token returns you to the sign-in screen.
   - `HOSPITAL_STAFF` / `ADMIN`: can dispatch requests and run coordination.
   - `BLOOD_BANK_STAFF`: read-only view (the dispatch form and Coordinate buttons are hidden; the API enforces this too).
1. **Live Request List**: Displays active blood requests with urgency badges, status pills, and hospital details with automatic 5-second polling.
2. **Request Detail & Fulfillment Plan**: Displays the Coordinator Agent's optimized multi-source fulfillment plan (blood banks and donors with allocated units and transit distance/ETA).
3. **Emergency Blood Request Form**: Allows dispatchers to rapidly submit new requests directly to `POST /api/v1/blood-requests`.
4. **Interactive Coordination Trigger**: Enables triggering the Coordinator Agent (`POST /api/v1/blood-requests/{id}/coordinate`) directly from the dashboard.

## How to Run

### Option 1: Built-in with FastAPI (Zero Setup)
The backend serves the frontend directly at:
```
http://localhost:8000/frontend/
```
(`/dashboard` and `/ui` redirect here.)

### Option 2: Standalone Vite Dev Server
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`.
