import React, { useEffect, useState } from "react";
import { apiFetch } from "../api/client";

function userDisplay(item) {
  return item.user_full_name || [item.user_name, item.user_surname].filter(Boolean).join(' ') || `User #${item.user_id}`
}

export default function FranchiseDashboardPage() {
  const [data, setData] = useState(null);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");

  const load = async () => {
    const result = await apiFetch("/franchise/dashboard");
    setData(result);
  };

  useEffect(() => {
    load();
  }, []);

  const approveAttendance = async (id) => {
    await apiFetch(`/franchise/attendance/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ manager_note: note }),
    });
    setNote("");
    load();
  };

  const rejectAttendance = async (id) => {
    await apiFetch(`/franchise/attendance/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ manager_note: note, rejected_reason: reason }),
    });
    setNote("");
    setReason("");
    load();
  };

  const approveRegistration = async (id) => {
    await apiFetch(`/franchise/registrations/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ manager_note: note }),
    });
    setNote("");
    load();
  };

  const rejectRegistration = async (id) => {
    await apiFetch(`/franchise/registrations/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ manager_note: note, rejected_reason: reason }),
    });
    setNote("");
    setReason("");
    load();
  };

  if (!data) return <div>Loading franchise dashboard...</div>;

  return (
    <div style={{ padding: 24 }}>
      <h1>Franchise / Manager Approval Dashboard</h1>

      <section style={{ marginBottom: 32 }}>
        <h2>Pending Franchise Registrations</h2>
        {data.pending_franchises?.length === 0 && <p>No pending registrations.</p>}
        {data.pending_franchises?.map((item) => (
          <div key={item.id} style={{ border: "1px solid #ddd", padding: 16, borderRadius: 12, marginBottom: 12 }}>
            <h3>{item.business_name}</h3>
            <p><strong>Trading as:</strong> {item.trading_as}</p>
            <p><strong>Franchisee:</strong> {item.franchisee_name} {item.franchisee_surname}</p>
            <p><strong>Email:</strong> {item.email}</p>
            <p><strong>Contact:</strong> {item.contact_number}</p>
            <p><strong>Office:</strong> {item.office_address}</p>
            <textarea placeholder="Manager note" value={note} onChange={(e) => setNote(e.target.value)} />
            <br />
            <input placeholder="Reject reason" value={reason} onChange={(e) => setReason(e.target.value)} />
            <br />
            <button onClick={() => approveRegistration(item.id)}>Approve</button>
            <button onClick={() => rejectRegistration(item.id)}>Reject</button>
          </div>
        ))}
      </section>

      <section>
        <h2>Pending Attendance Approvals</h2>
        {data.pending_attendance?.length === 0 && <p>No pending attendance approvals.</p>}
        {data.pending_attendance?.map((item) => (
          <div key={item.id} style={{ border: "1px solid #ddd", padding: 16, borderRadius: 12, marginBottom: 12 }}>
            <h3>Event #{item.id} - {userDisplay(item)}</h3>
            <p><strong>Action:</strong> {item.action}</p>
            <p><strong>GPS:</strong> {item.latitude}, {item.longitude}</p>
            <p><strong>Distance:</strong> {item.distance_from_site_m}</p>
            <p><strong>GPS Status:</strong> {item.gps_status}</p>
            <p><strong>Work location:</strong> {item.work_location_type}</p>
            <p><strong>Signature:</strong> {item.signature_status}</p>
            <p><strong>Employee note:</strong> {item.employee_note}</p>
            {item.latitude && item.longitude && (
              <p>
                <a target="_blank" rel="noreferrer" href={`https://www.google.com/maps?q=${item.latitude},${item.longitude}`}>
                  Open Map
                </a>
              </p>
            )}
            <textarea placeholder="Manager note" value={note} onChange={(e) => setNote(e.target.value)} />
            <br />
            <input placeholder="Reject reason" value={reason} onChange={(e) => setReason(e.target.value)} />
            <br />
            <button onClick={() => approveAttendance(item.id)}>Approve</button>
            <button onClick={() => rejectAttendance(item.id)}>Reject</button>
          </div>
        ))}
      </section>
    </div>
  );
}
