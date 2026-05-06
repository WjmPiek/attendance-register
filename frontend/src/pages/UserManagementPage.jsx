import React, { useEffect, useState } from "react";
import { apiFetch } from "../api/client";

export default function UserManagementPage() {
  const [users, setUsers] = useState([]);
  const [role, setRole] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try {
      const query = role ? `?role=${encodeURIComponent(role)}` : "";
      const data = await apiFetch(`/users${query}`);
      setUsers(data);
    } catch (err) {
      setError(err.message || "Failed to load users");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const deactivate = async (id) => {
    await apiFetch(`/users/${id}/deactivate`, { method: "POST", body: JSON.stringify({}) });
    load();
  };

  const activate = async (id) => {
    await apiFetch(`/users/${id}/activate`, { method: "POST", body: JSON.stringify({}) });
    load();
  };

  return (
    <div style={{ padding: 24 }}>
      <h1>System User Management</h1>
      <p>SuperUser can deactivate Franchise, Manager, and Employee users across the whole system.</p>

      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">All roles</option>
          <option value="FranchiseUser">FranchiseUser</option>
          <option value="ManagerUser">ManagerUser</option>
          <option value="EmployeeUser">EmployeeUser</option>
          <option value="SuperUser">SuperUser</option>
        </select>
        <button onClick={load}>Refresh</button>
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
            <th>ID</th>
            <th>Name</th>
            <th>Email</th>
            <th>Roles</th>
            <th>Active</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>{u.id}</td>
              <td>{u.full_name}</td>
              <td>{u.email}</td>
              <td>{u.roles}</td>
              <td>{u.is_active ? "Yes" : "No"}</td>
              <td>
                {u.is_active ? (
                  <button onClick={() => deactivate(u.id)}>Deactivate</button>
                ) : (
                  <button onClick={() => activate(u.id)}>Activate</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
