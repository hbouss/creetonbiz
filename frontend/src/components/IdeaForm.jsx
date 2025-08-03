// src/components/IdeaForm.jsx
import { useState } from 'react';

export default function IdeaForm({ onSubmit, error }) {
  const [form, setForm] = useState({ secteur: '', objectif: '', competences: '' });

  const handleChange = (field) => (e) =>
    setForm(f => ({ ...f, [field]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    onSubmit({
      secteur: form.secteur.trim(),
      objectif: form.objectif.trim(),
      competences: form.competences
        .split(',')
        .map(s => s.trim())
        .filter(Boolean),
    });
  };

  return (
    <div className="max-w-md w-full space-y-6 bg-gray-800 p-6 rounded-xl shadow-lg">
      <h1 className="text-3xl font-bold text-center">CréeTonBiz</h1>
      {error && <div className="text-red-400 text-sm">{error}</div>}

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="block mb-1 text-sm">💼 Secteur d’activité</label>
          <input
            type="text"
            placeholder="Ex. Sport, Tech, Mode..."
            required
            value={form.secteur}
            onChange={handleChange('secteur')}
            className="w-full px-3 py-2 bg-gray-700 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label className="block mb-1 text-sm">🎯 Objectif</label>
          <input
            type="text"
            placeholder="Ex. revenu complémentaire, startup scalable..."
            required
            value={form.objectif}
            onChange={handleChange('objectif')}
            className="w-full px-3 py-2 bg-gray-700 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label className="block mb-1 text-sm">🧩 Compétences</label>
          <textarea
            placeholder="Ex. marketing, développement, design"
            required
            rows="2"
            value={form.competences}
            onChange={handleChange('competences')}
            className="w-full px-3 py-2 bg-gray-700 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <button
          type="submit"
          className="w-full py-2 bg-indigo-600 rounded text-white font-medium hover:bg-indigo-500 transition"
        >
          Générer mon idée
        </button>
      </form>

      {/* Tutoriel détaillé intégré */}
      <details className="mt-4 text-gray-300 text-sm">
        <summary className="cursor-pointer font-semibold">ℹ️ Comment remplir le formulaire ?</summary>
        <div className="mt-2 space-y-2">
          <p>1. <strong>Secteur d’activité</strong> : décris ton domaine principal, par exemple <em>Sport</em>, <em>Tech</em>, <em>Coaching</em> ou <em>Mode</em>. Sois précis pour affiner l’IA.</p>
          <p>2. <strong>Objectif</strong> : indique ton but principal : <em>revenu complémentaire</em>, <em>créer une startup scalable</em>, <em>lancer un side project</em>, etc.</p>
          <p>3. <strong>Compétences</strong> : liste tes expertises clés, séparées par des virgules : <em>marketing</em>, <em>développement web</em>, <em>graphisme</em>, etc.</p>
          <p>4. Clique sur <em>Générer mon idée</em> et attends quelques secondes : l’IA analysera ton profil pour te proposer une idée de business personnalisée.</p>
        </div>
      </details>
    </div>
  );
}