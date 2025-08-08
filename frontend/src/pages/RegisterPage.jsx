import React, { useState, useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthContext } from '../contexts/AuthContext';
import { register, login as loginApi } from '../api'

export default function RegisterPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login } = useContext(AuthContext);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      // Appel à l'endpoint /register
      await register({ email, password });
      // Puis on récupère le token via /token
      const result = await loginApi({ username: email, password })
      const token = result.access_token
      login(token)
      navigate('/');
    } catch (err) {
      setError(err.message || 'Erreur lors de l’inscription');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 text-gray-100">
      <form onSubmit={handleSubmit} className="p-8 bg-gray-800 rounded space-y-4">
        <h2 className="text-2xl">Inscription</h2>
        {error && <p className="text-red-400">{error}</p>}
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
        <button
          type="submit"
          className="w-full py-2 bg-indigo-600 rounded hover:bg-indigo-500 transition"
        >
          S’inscrire
        </button>
        <p className="text-sm">
          Déjà inscrit ? <a href="/login" className="text-indigo-400">Connexion</a>
        </p>
      </form>
    </div>
  );
}