// src/components/IdeaForm.jsx
import React, { useState, useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { AuthContext } from '../contexts/AuthContext'

export default function IdeaForm({ onSubmit, error }) {
  const { logout, user } = useContext(AuthContext)
  const navigate = useNavigate()
  const [form, setForm] = useState({ secteur: '', objectif: '', competences: '' })

  const handleChange = (field) => (e) =>
    setForm(f => ({ ...f, [field]: e.target.value }))

  const submit = (e) => {
    e.preventDefault()
    onSubmit({
      secteur: form.secteur.trim(),
      objectif: form.objectif.trim(),
      competences: form.competences
        .split(',')
        .map(s => s.trim())
        .filter(Boolean),
    })
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-gray-100">
      {/* Header */}
      <header className="max-w-4xl mx-auto flex items-center justify-between py-4 px-6 bg-gray-800/50 backdrop-blur-md rounded-b-2xl shadow-lg">
        <div className="flex items-center space-x-3">
          {/* Logo ou icône */}
          <div className="w-10 h-10 bg-indigo-600 rounded-full flex items-center justify-center text-white text-lg font-bold">
            CTB
          </div>
          <div>
            <p className="text-lg font-semibold">CréeTonBiz</p>
            <p className="text-sm text-gray-400">
              {user?.email} • plan <span className="text-indigo-400">{user?.plan}</span>
            </p>
          </div>
        </div>
        <nav className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition"
          >
            Mon compte
          </button>
          <button
            onClick={() => {
              logout?.()
              navigate('/login')
            }}
            className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg text-sm font-medium transition"
          >
            Déconnexion
          </button>
        </nav>
      </header>

      {/* Contenu */}
      <main className="max-w-md mx-auto mt-12 px-6">
        <div className="bg-gray-800 p-8 rounded-2xl shadow-xl">
          <h1 className="text-3xl font-extrabold mb-6 text-center">Générateur d’idées</h1>
          {error && <div className="text-red-400 mb-4 text-center">{error}</div>}

          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="block mb-2 text-sm font-medium">💼 Secteur d’activité</label>
              <input
                type="text"
                placeholder="Ex. Sport, Tech, Mode..."
                required
                value={form.secteur}
                onChange={handleChange('secteur')}
                className="w-full px-4 py-2 bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block mb-2 text-sm font-medium">🎯 Objectif</label>
              <input
                type="text"
                placeholder="Ex. side project, startup scalable..."
                required
                value={form.objectif}
                onChange={handleChange('objectif')}
                className="w-full px-4 py-2 bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block mb-2 text-sm font-medium">🧩 Compétences</label>
              <textarea
                placeholder="Ex. marketing, dev, design..."
                required
                rows="3"
                value={form.competences}
                onChange={handleChange('competences')}
                className="w-full px-4 py-2 bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <button
              type="submit"
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 rounded-xl text-white font-semibold transition"
            >
              Générer mon idée
            </button>
          </form>

          <details className="mt-6 text-gray-300 text-sm">
            <summary className="cursor-pointer font-semibold">ℹ️ Comment ça marche ?</summary>
            <ul className="mt-3 list-disc list-inside space-y-1">
              <li>Choisis ton secteur pour guider l’IA.</li>
              <li>Définis ton objectif principal.</li>
              <li>Liste tes compétences clés.</li>
              <li>Valide et laisse l’IA créer une idée sur-mesure.</li>
            </ul>
          </details>
        </div>
      </main>
    </div>
  )
}