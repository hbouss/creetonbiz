// src/pages/DashboardPage.jsx
import React, { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { loadStripe } from '@stripe/stripe-js'
import { AuthContext } from '../contexts/AuthContext'
import {
  listProjects,
  createProject,
  listDeliverables,
  downloadDeliverable,
  generateAllPremium,
  createCheckoutSession,
  listIdeas,
  deleteIdea,
  deleteProject,
} from '../api.js'

// Initialise Stripe
const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY)

export default function DashboardPage() {
  const { user, refreshMe, logout } = useContext(AuthContext)
  const navigate = useNavigate()

  const [ideas, setIdeas] = useState([])
  const [projects, setProjects] = useState([])
  const [deliverablesMap, setDeliverablesMap] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    title: '',
    secteur: '',
    objectif: '',
    competences: '',
  })

  const credits    = user?.startnow_credits ?? 0
  const isInfinity = user?.plan === 'infinity'

  // ─── INITIALISATION ────────────────────────────────────────────────────────
  useEffect(() => {
    refreshMe?.().catch(() => {})
    fetchIdeas()
    fetchProjects()
  }, [])

  // ─── GESTION DES IDÉES ─────────────────────────────────────────────────────
  async function fetchIdeas() {
    try {
      const list = await listIdeas()
      setIdeas(list)
    } catch {
      // Pas autorisé / pas de pack → ignore
    }
  }

  async function handleConvertIdea(idea) {
    if (credits <= 0) {
      setError("Il faut un crédit StartNow pour convertir une idée.")
      return
    }
    setLoading(true)
    try {
      // 1) création du projet (on peut garder from_idea_id si tu veux tracker)
     const projectBody = {
       title:       idea.nom,
       secteur:     idea.secteur,
       objectif:    idea.objectif,
       competences: idea.competences,
       idea_id:     idea.id, // facultatif : trace le lien avec l’idée
     }
     const { id: projectId } = await createProject(projectBody)
     // 2) décrément du crédit
     await refreshMe()

     // 3) génération du pack complet **uniquement** avec le profil IA
     const profil = {
       secteur:     idea.secteur,
       objectif:    idea.objectif,
       competences: idea.competences,
     }
     await generateAllPremium(profil, projectId)

      // 4) raffraîchir listes
      await fetchIdeas()
      await fetchProjects()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // suppression d’une idée
 async function handleDeleteIdea(id) {
  if (!window.confirm("Supprimer définitivement cette idée ?")) return;
  try {
    await deleteIdea(id);
    await fetchIdeas();
  } catch (e) {
    setError(e.message);
  }
}

  // ─── GESTION DES PROJETS + LIVRABLES ───────────────────────────────────────
  async function fetchProjects() {
    try {
      const list = await listProjects()
      setProjects(list)
      const map = {}
      for (const p of list) {
        map[p.id] = await listDeliverables({ projectId: p.id })
      }
      setDeliverablesMap(map)
    } catch (e) {
      setError(e.message)
    }
  }

  // suppression d’un projet
  async function handleDeleteProject(id) {
    if (!window.confirm("Supprimer définitivement ce projet et ses livrables ?")) return
    setLoading(true)
    try {
      await deleteProject(id)
      await fetchProjects()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function onDownload(deliv, format) {
    try {
      await downloadDeliverable(deliv.id, {
        format,
        filename: `${deliv.title || deliv.kind + '-' + deliv.id}.${format}`,
      })
    } catch (e) {
      setError(e.message)
    }
  }

  // ─── PAIEMENT STRIPE ───────────────────────────────────────────────────────
  async function handleBuyCredits() {
    try {
      const { sessionId } = await createCheckoutSession('startnow')
      const stripe = await stripePromise
      if (!stripe) throw new Error('Stripe non initialisé')
      await stripe.redirectToCheckout({ sessionId })
    } catch (e) {
      setError(e.message || 'Impossible de lancer l’achat de jetons')
    }
  }

  // ─── CRÉER + GÉNÉRER PACK COMPLET ─────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault()
    if (credits <= 0) {
      setError('Aucun crédit disponible. Rachetez des jetons.')
      return
    }
    const { title, secteur, objectif, competences } = form
    if (!secteur.trim() || !objectif.trim()) {
      setError('Secteur et objectif sont obligatoires.')
      return
    }

    setError('')
    setLoading(true)
    try {
      const body = {
        title:       title.trim() || 'Mon projet',
        secteur:     secteur.trim(),
        objectif:    objectif.trim(),
        competences: competences
          .split(',')
          .map(s => s.trim())
          .filter(Boolean),
      }
      const { id: projectId } = await createProject(body)
      await refreshMe()
      await generateAllPremium(body, projectId)
      await fetchProjects()
      setForm({ title: '', secteur: '', objectif: '', competences: '' })
    } catch (e) {
      setError(e.message || 'Erreur lors de la création et génération')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-6 space-y-8">
      {/* Header */}
      <header className="bg-gray-800 shadow-md rounded-lg p-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Espace client</h1>
          <p className="text-gray-400 text-sm">
            {user?.email} • plan <strong>{user?.plan}</strong> • crédits{' '}
            <strong>{credits}</strong>
          </p>
        </div>
        <div className="flex items-center gap-3">
          {(isInfinity || user?.plan === 'startnow') && (
            <button
              onClick={() => navigate('/')}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm"
            >
              Générer une idée
            </button>
          )}
          <button
            onClick={handleBuyCredits}
            className="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 rounded text-gray-900 text-sm"
          >
            Racheter des jetons
          </button>
          <button
            onClick={() => navigate('/settings')}
            className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm"
          >
            Settings
          </button>
          <button
            onClick={() => { logout(); navigate('/login') }}
            className="px-3 py-1 bg-red-600 hover:bg-red-500 rounded text-white text-sm"
          >
            Déconnexion
          </button>
        </div>
      </header>

      {/* Mes idées */}
      <section className="bg-gray-800 rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">Mes idées générées</h2>
        {ideas.length === 0 ? (
          <p className="text-gray-400">Aucune idée pour le moment.</p>
        ) : (
          <ul className="space-y-3">
            {ideas.map((i, idx) => (
              <li
                key={idx}
                className="bg-gray-700 p-4 rounded-lg flex justify-between items-center"
              >
                <div>
                  <p className="font-medium">💡 {i.idee}</p>
                  <p className="text-xs text-gray-400">
                    {new Date(i.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex gap-2">
                <button
                  disabled={loading}
                  onClick={() => handleConvertIdea(i)}
                  className={`px-3 py-1 rounded text-white text-sm ${
                    credits <= 0
                      ? 'bg-gray-600 cursor-not-allowed'
                      : 'bg-emerald-600 hover:bg-emerald-500'
                  }`}
                >
                  Convertir en projet
                </button>
                <button
                  disabled={loading}
                  onClick={() => handleDeleteIdea(i.id)}
                  className="px-2 py-1 rounded text-red-400 hover:text-red-600 text-sm"
                >
                  🗑
                </button>
              </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Erreur */}
      {error && <p className="text-red-400">{error}</p>}

      {/* Nouveau projet & pack complet */}
      <section className="bg-gray-800 rounded-lg p-6 space-y-4">
        <h2 className="text-xl font-semibold">Nouveau projet & pack complet</h2>
        <form
          onSubmit={handleSubmit}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
        >
          <input
            type="text"
            placeholder="Nom du projet"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="p-2 rounded bg-gray-700"
          />
          <input
            type="text"
            placeholder="Secteur"
            value={form.secteur}
            onChange={(e) => setForm({ ...form, secteur: e.target.value })}
            className="p-2 rounded bg-gray-700"
          />
          <input
            type="text"
            placeholder="Objectif"
            value={form.objectif}
            onChange={(e) => setForm({ ...form, objectif: e.target.value })}
            className="p-2 rounded bg-gray-700"
          />
          <input
            type="text"
            placeholder="Compétences (virgules)"
            value={form.competences}
            onChange={(e) => setForm({ ...form, competences: e.target.value })}
            className="p-2 rounded bg-gray-700"
          />
          <button
            type="submit"
            disabled={loading || credits <= 0}
            className={`md:col-span-4 px-4 py-2 rounded font-medium ${
              loading || credits <= 0
                ? 'bg-gray-600 cursor-not-allowed'
                : 'bg-emerald-600 hover:bg-emerald-500'
            }`}
          >
            {loading ? 'Génération en cours…' : 'Créer projet & générer'}
          </button>
        </form>
      </section>

      {/* Liste des projets & livrables */}
      <section className="space-y-6">
        {projects.length === 0 ? (
          <p className="text-gray-400">Aucun projet pour le moment.</p>
        ) : (
          projects.map((p) => (
            <div key={p.id} className="bg-gray-800 rounded-lg p-4 relative">
              <button
                disabled={loading}
                onClick={() => handleDeleteProject(p.id)}
                className="absolute top-2 right-2 text-red-400 hover:text-red-600 text-sm"
              >
                🗑
              </button>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold">
                  {p.title}
                  {p.idea_id ? (
                    <span className="ml-2 inline-block px-2 py-0.5 bg-blue-600 text-xs rounded">
                      💡 Idée
                    </span>
                  ) : (
                    <span className="ml-2 inline-block px-2 py-0.5 bg-gray-600 text-xs rounded">
                      📝 Manuel
                    </span>
                  )}
                </h3>
                <span className="text-sm text-gray-400">
                  {new Date(p.created_at).toLocaleDateString()}
                </span>
              </div>
              <ul className="space-y-2">
                {(deliverablesMap[p.id] || []).map((d) => (
                  <li
                    key={d.id}
                    className="flex items-center justify-between"
                  >
                    <div>
                      <p className="font-medium">{d.title || d.kind}</p>
                      <p className="text-xs text-gray-500">
                        {new Date(d.created_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => onDownload(d, 'pdf')}
                        className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm"
                      >
                        PDF
                      </button>
                      {d.has_file && (
                        <button
                          onClick={() => onDownload(d, 'html')}
                          className="px-3 py-1 bg-green-700 hover:bg-green-600 rounded text-white text-sm"
                        >
                          HTML
                      </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </section>
    </div>
  )
}