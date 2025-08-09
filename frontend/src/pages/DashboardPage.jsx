// src/pages/DashboardPage.jsx
import React, { useContext, useEffect, useRef, useState } from 'react'
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

  // Lire la suite / Réduire
  const [expandedIdeas, setExpandedIdeas] = useState({})
  const toggleIdea = (id) =>
    setExpandedIdeas((prev) => ({ ...prev, [id]: !prev[id] }))

  // Liens visuels & spinner
  const [convertingIdeaId, setConvertingIdeaId] = useState(null)     // idée en conversion
  const [generatingProjectId, setGeneratingProjectId] = useState(null) // projet en génération
  const [progressStep, setProgressStep] = useState(null)             // étape courante

  // refs pour scroller vers un projet
  const projectRefs = useRef({})
  const scrollToProject = (projectId) => {
    const el = projectRefs.current[projectId]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

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
    setConvertingIdeaId(idea.id)
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

      // spinner projet
      setGeneratingProjectId(projectId)
      setProgressStep('offer')

      await refreshMe()
      await generateAllPremium(
        {
          secteur: idea.secteur,
          objectif: idea.objectif,
          competences: idea.competences,
        },
        projectId,
        (step) => setProgressStep(step)
      )

      await fetchIdeas()
      await fetchProjects()
      // scroll vers le projet fraîchement créé
      setTimeout(() => scrollToProject(projectId), 250)
    } catch (e) {
      setError(e.message)
    } finally {
      setConvertingIdeaId(null)
      setGeneratingProjectId(null)
      setProgressStep(null)
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
    setError('')
    setLoading(true)
    try {
      const body = {
        title: title.trim() || 'Mon projet',
        secteur: secteur.trim(),
        objectif: objectif.trim(),
        competences: competences.split(',').map(s => s.trim()).filter(Boolean),
      }
      const { id: projectId } = await createProject(body)

      setGeneratingProjectId(projectId)
      setProgressStep('offer')

      await refreshMe()
      await generateAllPremium(body, projectId, (step) => setProgressStep(step))
      await fetchProjects()
      setForm({ title: '', secteur: '', objectif: '', competences: '' })

      setTimeout(() => scrollToProject(projectId), 250)
    } catch (e) {
      setError(e.message)
    } finally {
      setGeneratingProjectId(null)
      setProgressStep(null)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-6 space-y-8">
      {/* Overlay spinner global */}
      {(convertingIdeaId || generatingProjectId) && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center">
          <div className="bg-gray-800 p-6 rounded-xl shadow-xl text-center">
            <div className="mx-auto mb-4 h-10 w-10 border-4 border-white/20 border-t-white rounded-full animate-spin" />
            <p className="font-medium">Génération des livrables…</p>
            {progressStep && (
              <p className="text-sm text-gray-300 mt-1">
                Étape : {progressStep}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Header */}
      <header className="bg-gray-800 shadow-md rounded-lg p-4 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Espace client</h1>
          <p className="text-gray-400 text-sm">
            {user?.email} • plan <strong>{user?.plan}</strong> • crédits <strong>{credits}</strong>
          </p>
        </div>
        <div className="flex gap-2">
          {(isInfinity || user?.plan === 'startnow') && (
            <button
              onClick={() => navigate('/')}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm"
            >
              Générer idée
            </button>
          )}
          <button
            onClick={handleBuyCredits}
            className="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 rounded text-gray-900 text-sm"
          >
            Racheter jetons
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

      {/* Idées & Formulaire */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Idées */}
        <section className="bg-gray-800 rounded-lg p-6 space-y-4">
          <h2 className="text-xl font-semibold">Mes idées générées</h2>
          {ideas.length === 0 ? (
            <p className="text-gray-400">Aucune idée pour le moment.</p>
          ) : (
            ideas.map((i) => {
              const stableId = i.id ?? i.nom ?? i.idee
              const isOpen = !!expandedIdeas[stableId]
              const fullText = i.idee || ''
              const isLong = fullText.length > 240
              const displayText = isOpen || !isLong ? fullText : fullText.slice(0, 240) + '…'
              const ratingNum = Number(i.potential_rating)

              // projets liés à cette idée
              const linkedProjects = projects.filter(p => p.idea_id === i.id)
              const alreadyConverted = linkedProjects.length > 0
              const firstProjectId = alreadyConverted ? linkedProjects[0].id : null

              return (
                <div key={stableId} className="bg-gray-700 p-4 rounded-lg flex flex-col gap-2">
                  <div className="flex justify-between items-start gap-3">
                    <div className="flex-1">
                      <p className="font-medium">💡 {displayText}</p>
                      {isLong && (
                        <button
                          type="button"
                          onClick={() => toggleIdea(stableId)}
                          className="mt-1 text-blue-300 hover:text-blue-200 underline text-sm"
                        >
                          {isOpen ? 'Réduire' : 'Lire la suite'}
                        </button>
                      )}
                    </div>

                    {Number.isFinite(ratingNum) && (
                      <div className="shrink-0 flex flex-col items-end">
                        <span className="text-[11px] text-gray-300 mb-1">Potentiel de l'idée</span>
                        <span
                          className={`px-2 py-0.5 rounded text-xs text-white ${
                            ratingNum >= 8 ? 'bg-emerald-600'
                            : ratingNum >= 6 ? 'bg-yellow-600'
                            : 'bg-gray-600'
                          }`}
                          title="Potentiel"
                        >
                          🌟 {ratingNum.toFixed(1)} / 10
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Lien visuel idée → projet */}
                  {alreadyConverted && (
                    <div className="flex items-center gap-2 text-xs">
                      <span className="px-2 py-0.5 bg-emerald-700/40 text-emerald-300 rounded">
                        Convertie en projet
                      </span>
                      <button
                        type="button"
                        onClick={() => scrollToProject(firstProjectId)}
                        className="text-emerald-300 hover:text-emerald-200 underline"
                      >
                        Voir le projet
                      </button>
                    </div>
                  )}

                  <p className="text-xs text-gray-400">
                    {new Date(i.created_at).toLocaleString()}
                  </p>

                  <div className="mt-2 flex gap-2">
                    <button
                      disabled={loading || credits <= 0 || alreadyConverted}
                      onClick={() => handleConvertIdea(i)}
                      className={`flex-1 px-3 py-1 rounded text-white text-sm ${
                        (loading && convertingIdeaId === i.id) ? 'bg-gray-600 cursor-wait'
                        : credits <= 0 || alreadyConverted ? 'bg-gray-600 cursor-not-allowed'
                        : 'bg-emerald-600 hover:bg-emerald-500'
                      }`}
                    >
                      {alreadyConverted
                        ? 'Déjà convertie'
                        : (convertingIdeaId === i.id ? 'Conversion…' : 'Convertir')}
                    </button>
                    <button
                      disabled={loading}
                      onClick={() => handleDeleteIdea(i.id)}
                      className="px-3 py-1 rounded text-red-400 hover:text-red-600 text-sm"
                      title="Supprimer l’idée"
                    >
                      🗑
                    </button>
                  </div>
                </div>
              )
            })
          )}
        </section>

        {/* Formulaire */}
        <section className="bg-gray-800 rounded-lg p-6 space-y-4">
          <h2 className="text-xl font-semibold">Créer un projet</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              className="w-full p-2 bg-gray-700 rounded"
              value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })}
              placeholder="Nom du projet"
            />
            <input
              className="w-full p-2 bg-gray-700 rounded"
              value={form.secteur}
              onChange={e => setForm({ ...form, secteur: e.target.value })}
              placeholder="Secteur"
            />
            <input
              className="w-full p-2 bg-gray-700 rounded"
              value={form.objectif}
              onChange={e => setForm({ ...form, objectif: e.target.value })}
              placeholder="Objectif"
            />
            <input
              className="w-full p-2 bg-gray-700 rounded"
              value={form.competences}
              onChange={e => setForm({ ...form, competences: e.target.value })}
              placeholder="Compétences (virgules)"
            />
            <button
              type="submit"
              disabled={loading || credits <= 0}
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
        {projects.length === 0 ? (
          <p className="text-gray-400">Aucun projet pour le moment.</p>
        ) : (
          projects.map((p) => (
            <div
              key={p.id}
              ref={(el) => (projectRefs.current[p.id] = el)}
              className="bg-gray-700 p-4 rounded-lg space-y-3"
            >
              <div className="flex justify-between items-center">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  {p.title}
                  {p.idea_id ? (
                    <span className="px-2 py-0.5 bg-blue-600 rounded text-xs">💡 Idée</span>
                  ) : (
                    <span className="px-2 py-0.5 bg-gray-600 rounded text-xs">📝 Manuel</span>
                  )}
                  {generatingProjectId === p.id && (
                    <span className="ml-2 inline-flex items-center gap-2 text-xs text-gray-300">
                      <span className="h-3 w-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Génération…
                    </span>
                  )}
                </h3>
                <button
                  disabled={loading}
                  onClick={() => handleDeleteProject(p.id)}
                  className="text-red-400 hover:text-red-600 text-sm"
                >
                  🗑
                </button>
              </div>
              <ul className="grid md:grid-cols-2 gap-3">
                {(deliverablesMap[p.id] || []).map((d) => (
                  <li key={d.id} className="bg-gray-600 p-3 rounded flex justify-between items-center">
                    <span>
                      <p className="font-medium">{d.title || d.kind}</p>
                      <p className="text-xs text-gray-400">
                        {new Date(d.created_at).toLocaleString()}
                      </p>
                    </span>
                    <div className="flex gap-2">
                      <button
                        onClick={() => onDownload(d, 'pdf')}
                        className="px-2 py-1 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm"
                      >
                        PDF
                      </button>
                      {d.has_file && (
                        <button
                          onClick={() => onDownload(d, 'html')}
                          className="px-2 py-1 bg-green-700 hover:bg-green-600 rounded text-white text-sm"
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