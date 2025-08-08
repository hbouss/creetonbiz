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

  useEffect(() => {
    ;(async () => {
      try { await refreshMe() } catch {}
      await fetchIdeas()
      await fetchProjects()
    })()
  }, [])

  async function fetchIdeas() {
    try {
      const list = await listIdeas()
      setIdeas(list)
    } catch {}
  }

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

  async function handleConvertIdea(idea) {
    if (credits <= 0) {
      setError("Il faut un crédit StartNow pour convertir.")
      return
    }
    setLoading(true)
    try {
      const projectBody = {
        title:       idea.nom,
        secteur:     idea.secteur,
        objectif:    idea.objectif,
        competences: idea.competences,
        idea_id:     idea.id,
      }
      const { id: projectId } = await createProject(projectBody)
      await refreshMe()
      await generateAllPremium({
        secteur: idea.secteur,
        objectif: idea.objectif,
        competences: idea.competences,
      }, projectId)
      await fetchIdeas()
      await fetchProjects()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDeleteIdea(id) {
    if (!window.confirm("Supprimer cette idée ?")) return
    try {
      await deleteIdea(id)
      await fetchIdeas()
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleDeleteProject(id) {
    if (!window.confirm("Supprimer ce projet ?")) return
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
        filename: `${deliv.title || deliv.kind}-${deliv.id}.${format}`,
      })
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleBuyCredits() {
    try {
      const { sessionId } = await createCheckoutSession('startnow')
      const stripe = await stripePromise
      await stripe.redirectToCheckout({ sessionId })
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (credits <= 0) { setError('Aucun crédit disponible.'); return }
    const { title, secteur, objectif, competences } = form
    if (!secteur.trim() || !objectif.trim()) {
      setError('Secteur et objectif obligatoires.')
      return
    }
    setError(''); setLoading(true)
    try {
      const body = {
        title: title.trim() || 'Mon projet',
        secteur: secteur.trim(),
        objectif: objectif.trim(),
        competences: competences.split(',').map(s=>s.trim()).filter(Boolean),
      }
      const { id: projectId } = await createProject(body)
      await refreshMe()
      await generateAllPremium(body, projectId)
      await fetchProjects()
      setForm({ title:'', secteur:'', objectif:'', competences:'' })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-6 space-y-8">
      {/* Header */}
      <header className="bg-gray-800 shadow-md rounded-lg p-4 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Espace client</h1>
          <p className="text-gray-400 text-sm">
            {user?.email} • plan <strong>{user?.plan}</strong> • crédits <strong>{credits}</strong>
          </p>
        </div>
        <div className="flex gap-2">
          {(isInfinity || user?.plan==='startnow') && (
            <button
              onClick={()=>navigate('/')}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm"
            >Générer idée</button>
          )}
          <button
            onClick={handleBuyCredits}
            className="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 rounded text-gray-900 text-sm"
          >Racheter jetons</button>
          <button
            onClick={()=>navigate('/settings')}
            className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm"
          >Settings</button>
          <button
            onClick={()=>{logout();navigate('/login')}}
            className="px-3 py-1 bg-red-600 hover:bg-red-500 rounded text-white text-sm"
          >Déconnexion</button>
        </div>
      </header>

      {/* Idées & Formulaire */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Idées */}
        <section className="bg-gray-800 rounded-lg p-6 space-y-4">
          <h2 className="text-xl font-semibold">Mes idées générées</h2>
          {ideas.length===0
            ? <p className="text-gray-400">Aucune idée pour le moment.</p>
            : ideas.map((i, idx) => (
              <div key={idx} className="bg-gray-700 p-4 rounded-lg flex flex-col">
                <p className="font-medium mb-2">💡 {i.idee}</p>
                <p className="text-xs text-gray-400 mb-2">{new Date(i.created_at).toLocaleString()}</p>
                <p className="text-yellow-300 mb-4">🌟 Potentiel : {i.potential_rating?.toFixed(1) ?? '-'} / 10</p>
                <div className="mt-auto flex gap-2">
                  <button
                    disabled={loading}
                    onClick={()=>handleConvertIdea(i)}
                    className={`flex-1 px-3 py-1 rounded text-white text-sm ${
                      credits <= 0
                        ? 'bg-gray-600 cursor-not-allowed'
                        : 'bg-emerald-600 hover:bg-emerald-500'
                    }`}
                  >Convertir</button>
                  <button
                    disabled={loading}
                    onClick={()=>handleDeleteIdea(i.id)}
                    className="px-3 py-1 rounded text-red-400 hover:text-red-600 text-sm"
                  >🗑</button>
                </div>
              </div>
          ))}
        </section>

        {/* Formulaire */}
        <section className="bg-gray-800 rounded-lg p-6 space-y-4">
          <h2 className="text-xl font-semibold">Créer un projet</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              className="w-full p-2 bg-gray-700 rounded"
              value={form.title}
              onChange={e=>setForm({...form,title:e.target.value})}
              placeholder="Nom du projet"
            />
            <input
              className="w-full p-2 bg-gray-700 rounded"
              value={form.secteur}
              onChange={e=>setForm({...form,secteur:e.target.value})}
              placeholder="Secteur"
            />
            <input
              className="w-full p-2 bg-gray-700 rounded"
              value={form.objectif}
              onChange={e=>setForm({...form,objectif:e.target.value})}
              placeholder="Objectif"
            />
            <input
              className="w-full p-2 bg-gray-700 rounded"
              value={form.competences}
              onChange={e=>setForm({...form,competences:e.target.value})}
              placeholder="Compétences (virgules)"
            />
            <button
              type="submit"
              disabled={loading||credits<=0}
              className={`w-full px-4 py-2 rounded text-white text-sm ${
                loading || credits <= 0
                  ? 'bg-gray-600 cursor-not-allowed'
                  : 'bg-emerald-600 hover:bg-emerald-500'  
              }`}
            >
              {loading ? 'Génération en cours…' : 'Créer & générer'}
            </button>
            {error && <p className="text-red-400 text-sm">{error}</p>}
          </form>
        </section>
      </div>

      {/* Projets */}
      <section className="bg-gray-800 rounded-lg p-6 space-y-4">
        <h2 className="text-xl font-semibold">Mes projets & livrables</h2>
        {projects.length===0
          ? <p className="text-gray-400">Aucun projet pour le moment.</p>
          : projects.map(p => (
            <div key={p.id} className="bg-gray-700 p-4 rounded-lg space-y-3">
              <div className="flex justify-between items-center">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  {p.title}
                  {p.idea_id
                    ? <span className="px-2 py-0.5 bg-blue-600 rounded text-xs">💡 Idée</span>
                    : <span className="px-2 py-0.5 bg-gray-600 rounded text-xs">📝 Manuel</span>
                  }
                </h3>
                <button
                  disabled={loading}
                  onClick={() => handleDeleteProject(p.id)}
                  className="text-red-400 hover:text-red-600 text-sm"
                >🗑</button>
              </div>
              <ul className="grid md:grid-cols-2 gap-3">
                {(deliverablesMap[p.id]||[]).map(d => (
                  <li key={d.id} className="bg-gray-600 p-3 rounded flex justify-between items-center">
                    <span>
                      <p className="font-medium">{d.title||d.kind}</p>
                      <p className="text-xs text-gray-400">{new Date(d.created_at).toLocaleString()}</p>
                    </span>
                    <div className="flex gap-2">
                      <button onClick={()=>onDownload(d,'pdf')} className="px-2 py-1 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm">PDF</button>
                      {d.has_file && <button onClick={()=>onDownload(d,'html')} className="px-2 py-1 bg-green-700 hover:bg-green-600 rounded text-white text-sm">HTML</button>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
        ))}
      </section>
    </div>
  )
}