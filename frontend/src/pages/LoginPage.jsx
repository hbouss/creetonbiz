// src/pages/LoginPage.jsx
import React, { useState, useContext } from "react";
import { useNavigate } from "react-router-dom";
import { AuthContext } from "../contexts/AuthContext";
import { login as apiLogin } from "../api"; // si tu as une fonction login dans api.js

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const { login } = useContext(AuthContext);
  const nav = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const data = await apiLogin({ username: email, password });
      login(data.access_token);
      nav("/");
    } catch (e) {
      setErr("Email ou mot de passe invalide");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 text-gray-100">
      <form onSubmit={handleSubmit} className="p-8 bg-gray-800 rounded space-y-4">
        <h2 className="text-2xl">Connexion</h2>
        {err && <p className="text-red-400">{err}</p>}
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="w-full p-2 rounded bg-gray-700"
        />
        <input
          type="password"
          placeholder="Mot de passe"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="w-full p-2 rounded bg-gray-700"
        />
        <button type="submit" className="w-full py-2 bg-indigo-600 rounded">
          Se connecter
        </button>
        <p className="text-sm">
          Nouveau ? <a href="/register" className="text-indigo-400">Créer un compte</a>
        </p>
      </form>
    </div>
  );
}