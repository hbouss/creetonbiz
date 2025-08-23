// src/pages/Settings.jsx
import React, { useContext, useState } from 'react'
import { AuthContext } from '../contexts/AuthContext'
import { deleteMe } from "../api";

export default function Settings() {
  const [pwd, setPwd] = useState("");
  const [cancelStripe, setCancelStripe] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const { logout, user } = useContext(AuthContext);

  async function changePassword(e) {
    e.preventDefault()
    setMsg(''); setErr('')
    const fd = new FormData(e.currentTarget)
    const old_password = fd.get('old_password') || ''
    const new_password = fd.get('new_password') || ''
    try {
      const res = await fetch('/api/me/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_password, new_password }),
      })
      if (!res.ok) throw new Error(await res.text())
      setMsg('Mot de passe mis à jour.')
      e.currentTarget.reset()
    } catch (e) {
      setErr(e.message || 'Erreur lors du changement du mot de passe.')
    }
  }

  async function deleteAccount(e) {
  e.preventDefault();
  setMsg("");
  setErr("");

  if (!pwd) {
    setErr("Entre ton mot de passe.");
    return;
  }
  if (!confirm("Supprimer définitivement votre compte et vos livrables ?")) return;

  setBusy(true);
  try {
    await deleteMe({
      current_password: pwd,        // le backend attend exactement ce champ
      cancel_stripe: cancelStripe,  // checkbox optionnelle
    });
    try { localStorage.removeItem("auth_token"); } catch {}
    logout?.();
    window.location.href = "/login";
  } catch (e) {
    setErr(e.message || "Erreur lors de la suppression du compte.");
  } finally {
    setBusy(false);
  }
}

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <h1 className="text-2xl font-bold mb-4">Paramètres du compte</h1>
      <p className="text-sm text-gray-400 mb-6">
        Connecté: <span className="font-medium">{user?.email}</span>
      </p>

      {msg && <p className="text-green-400 mb-4">{msg}</p>}
      {err && <p className="text-red-400 mb-4">{err}</p>}

      <div className="grid md:grid-cols-2 gap-6">
        <form onSubmit={changePassword} className="p-4 bg-gray-800 rounded space-y-2">
          <h2 className="text-lg font-semibold mb-2">Changer le mot de passe</h2>
          <input name="old_password" type="password" placeholder="Ancien mot de passe" className="w-full p-2 rounded bg-gray-700" required />
          <input name="new_password" type="password" placeholder="Nouveau mot de passe" className="w-full p-2 rounded bg-gray-700" required />
          <button className="px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500">Mettre à jour</button>
        </form>

        <form onSubmit={deleteAccount} className="p-4 bg-gray-800 rounded space-y-3">
          <h2 className="text-lg font-semibold mb-2 text-red-300">Supprimer mon compte</h2>
          <p className="text-sm text-gray-400">Cette action est irréversible.</p>

          <label className="block text-sm">Mot de passe</label>
          <input
            type="password"
            value={pwd}
            onChange={(e) => setPwd(e.target.value)}
            placeholder="Confirme ton mot de passe"
            className="w-full p-2 rounded bg-gray-700"
            required
          />

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={cancelStripe}
              onChange={(e) => setCancelStripe(e.target.checked)}
              className="accent-red-600"
            />
            Annuler aussi mon abonnement Stripe (si actif)
          </label>

          <button
            type="submit"
            disabled={busy || !pwd}
            className="px-4 py-2 rounded bg-red-700 hover:bg-red-600 disabled:opacity-60"
          >
            {busy ? "Suppression..." : "Supprimer définitivement"}
          </button>
        </form>
      </div>
    </div>
  )
}