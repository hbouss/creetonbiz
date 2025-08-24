import React, { useEffect, useState } from "react";
import { adminListUsers, adminUpdateUser } from "../api";

export default function AdminPage() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");

  async function load() {
    try { setRows(await adminListUsers()); } catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, []);

  async function onPatch(id, patch) {
    try { await adminUpdateUser(id, patch); await load(); }
    catch (e) { alert(e.message); }
  }

  return (
    <div className="p-6 text-gray-100">
      <h1 className="text-2xl font-bold mb-4">Admin — Utilisateurs</h1>
      {err && <p className="text-red-400 mb-3">{err}</p>}
      <div className="overflow-x-auto rounded border border-gray-700">
        <table className="min-w-[900px] w-full">
          <thead className="bg-gray-800">
            <tr>
              <th className="px-3 py-2 text-left">ID</th>
              <th className="px-3 py-2 text-left">Email</th>
              <th className="px-3 py-2">Plan</th>
              <th className="px-3 py-2">Crédits</th>
              <th className="px-3 py-2">Idées utilisées</th>
              <th className="px-3 py-2">Admin</th>
              <th className="px-3 py-2">Stripe</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-gray-900 divide-y divide-gray-800">
            {rows.map(u => (
              <tr key={u.id}>
                <td className="px-3 py-2">{u.id}</td>
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2 text-center">{u.plan}</td>
                <td className="px-3 py-2 text-center">{u.startnow_credits}</td>
                <td className="px-3 py-2 text-center">{u.idea_used}</td>
                <td className="px-3 py-2 text-center">{u.is_admin ? "✅" : "—"}</td>
                <td className="px-3 py-2 text-center">
                  {u.stripe_link ? <a href={u.stripe_link} className="text-indigo-300 underline" target="_blank" rel="noreferrer">Stripe</a> : "—"}
                </td>
                <td className="px-3 py-2 space-x-2 text-center">
                  <button onClick={() => onPatch(u.id, { plan: u.plan === "infinity" ? "free" : "infinity" })}
                          className="px-2 py-1 bg-slate-700 rounded">Toggle plan</button>
                  <button onClick={() => onPatch(u.id, { startnow_credits: (u.startnow_credits || 0) + 1 })}
                          className="px-2 py-1 bg-emerald-700 rounded">+1 crédit</button>
                  <button onClick={() => onPatch(u.id, { is_admin: !u.is_admin })}
                          className="px-2 py-1 bg-purple-700 rounded">Toggle admin</button>
                  {u.plan !== "free" && (
                    <button onClick={() => onPatch(u.id, { cancel_stripe: true })}
                            className="px-2 py-1 bg-red-700 rounded">Annuler abo</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}