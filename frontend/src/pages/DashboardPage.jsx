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
  publishLanding,
  openBillingPortal,
} from '../api.js'
import LandingHelp from "../components/LandingHelpRaw.jsx";
import BusinessPlanHelp from "../components/BusinessPlanHelp.jsx"; // adapte le chemin
import MarketingHelp from "../components/MarketingHelp.jsx";
import BrandingHelp from "../components/BrandingHelp.jsx";
import OfferHelp from "../components/OfferHelp.jsx";

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY)

export default function DashboardPage() {
  const { user, refreshMe, logout } = useContext(AuthContext)
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false);
  const [ideas, setIdeas] = useState([])
  const [projects, setProjects] = useState([])
  const [deliverablesMap, setDeliverablesMap] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [publishingProjectId, setPublishingProjectId] = useState(null)
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
  const [progressStep, setProgressStep] = useState(null)// étape courante

  // Styles communs aux boutons (mobile & desktop)
  const btnBase =
    "rounded-xl text-sm font-medium flex items-center justify-center " +
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 " +
    "transition";

  const btnMobile = "w-full h-12";     // 48px — cible tactile confortable
  const btnDesktop = "h-10 px-3";      // plus compact en desktop

  const variants = {
    admin:    "bg-purple-700 hover:bg-purple-600 text-white",
    portal:   "bg-teal-600 hover:bg-teal-500 text-white",
    idea:     "bg-blue-600 hover:bg-blue-500 text-white",
    credits:  "bg-yellow-500 hover:bg-yellow-400 text-gray-900",
    settings: "bg-indigo-600 hover:bg-indigo-500 text-white",
    logout:   "bg-red-600 hover:bg-red-500 text-white",
  };

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

async function handleOpenPortal() {
  try {
    const { url } = await openBillingPortal();
    window.location.href = url; // redirection vers Stripe
  } catch (e) {
    setError(e.message || "Impossible d’ouvrir le portail de facturation.");
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

  async function handlePublishLanding(projectId) {
  try {
    setPublishingProjectId(projectId)
    const { url } = await publishLanding(projectId)
    // petit confort: copie dans le presse-papier et alert
    try { await navigator.clipboard.writeText(url) } catch {}
    alert(`Landing en ligne:\n${url}\n(Lien copié dans le presse-papiers)`)
    await fetchProjects() // pour faire apparaitre le deliverable "landing_public"
  } catch (e) {
    setError(e.message)
  } finally {
    setPublishingProjectId(null)
  }
}

// ouvre le modal Business Plan via un CustomEvent
const fireBpHelp = React.useCallback(
  (kind = "pdf") =>
    window.dispatchEvent(new CustomEvent("bp-help:open", { detail: { kind } })),
  []
);

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-4 sm:p-6 space-y-8 overflow-x-hidden">
      {/* Overlay spinner globale */}
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

      {/* Headerr */}
      <header className="bg-gray-800 shadow-md rounded-lg p-4 flex justify-between items-center">
  <div>
    <h1 className="text-2xl font-bold">Espace client</h1>
    <p className="text-gray-400 text-sm">
      {user?.email} • plan <strong>{user?.plan}</strong> • crédits <strong>{credits}</strong>
    </p>
  </div>

  {/* ACTIONS DESKTOP */}
  <div className="hidden md:flex flex-wrap gap-2">
    {(user?.plan === "infinity" || user?.plan === "startnow") && (
      <button
        onClick={handleOpenPortal}
        className="h-10 px-3 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium"
      >
        Gérer mon abonnement
      </button>
    )}
    {(isInfinity || user?.plan === 'startnow') && (
      <button
        onClick={() => navigate('/')}
        className="h-10 px-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
      >
        Générer idée
      </button>
    )}
    <button
      onClick={handleBuyCredits}
      className="h-10 px-3 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-gray-900 text-sm font-medium"
    >
      Racheter jetons
    </button>
    <button
      onClick={() => navigate('/settings')}
      className="h-10 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
    >
      Settings
    </button>
    <button
      onClick={() => { logout(); navigate('/login') }}
      className="h-10 px-3 rounded-xl bg-red-600 hover:bg-red-500 text-white text-sm font-medium"
    >
      Déconnexion
    </button>
  </div>

  {/* HAMBURGER MOBILE */}
  <button
    type="button"
    onClick={() => setMenuOpen(true)}
    className="md:hidden inline-flex items-center gap-2 px-4 h-10 rounded-xl bg-indigo-600 text-white font-semibold shadow ring-2 ring-indigo-400/50"
    aria-label="Ouvrir le menu"
    aria-haspopup="dialog"
    aria-expanded={menuOpen}
    aria-controls="mobile-actions"
  >
    <span className="text-lg">☰</span>
    <span>Menu</span>
  </button>
</header>

      {/* MOBILE DRAWER */}
<div
  id="mobile-actions"
  className={`md:hidden fixed inset-0 z-50 ${menuOpen ? 'pointer-events-auto' : 'pointer-events-none'}`}
  role="dialog"
  aria-modal="true"
>
  {/* Backdrop */}
  <div
    onClick={() => setMenuOpen(false)}
    className={`absolute inset-0 transition-opacity duration-200 ${menuOpen ? 'opacity-100 bg-black/50' : 'opacity-0'}`}
  />

  {/* Panel */}
  <div
    className={`absolute right-0 top-0 h-full w-10/12 max-w-xs bg-gray-800 shadow-2xl border-l border-gray-700
                transition-transform duration-200 ${menuOpen ? 'translate-x-0' : 'translate-x-full'}`}
  >
    <div className="p-4 border-b border-gray-700 flex items-center justify-between">
      <span className="text-white font-semibold">Menu</span>
      <button
        onClick={() => setMenuOpen(false)}
        className="p-2 rounded-lg text-gray-300 hover:text-white hover:bg-gray-700"
        aria-label="Fermer le menu"
      >
        ✕
      </button>
    </div>

    <div className="p-4 space-y-3">
      {/* ADMIN (si admin) */}
      {user?.is_admin && (
        <button
          onClick={() => { setMenuOpen(false); navigate('/admin') }}
          className="w-full h-12 rounded-xl bg-purple-700 hover:bg-purple-600 text-white text-sm font-medium"
        >
          Admin
        </button>
      )}

      {/* Abonnement (si abonné) */}
      {(user?.plan === "infinity" || user?.plan === "startnow") && (
        <button
          onClick={() => { setMenuOpen(false); handleOpenPortal() }}
          className="w-full h-12 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium"
        >
          Abonnement
        </button>
      )}

      {/* Générer idée (si abonné) */}
      {(isInfinity || user?.plan === 'startnow') && (
        <button
          onClick={() => { setMenuOpen(false); navigate('/') }}
          className="w-full h-12 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
        >
          Générer idée
        </button>
      )}

      {/* Racheter jetons */}
      <button
        onClick={() => { setMenuOpen(false); handleBuyCredits() }}
        className="w-full h-12 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-gray-900 text-sm font-medium"
      >
        Racheter jetons
      </button>

      {/* Settings */}
      <button
        onClick={() => { setMenuOpen(false); navigate('/settings') }}
        className="w-full h-12 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
      >
        Settings
      </button>

      {/* Déconnexion */}
      <button
        onClick={() => { setMenuOpen(false); logout(); navigate('/login') }}
        className="w-full h-12 rounded-xl bg-red-600 hover:bg-red-500 text-white text-sm font-medium"
      >
        Déconnexion
      </button>
    </div>

    {/* Petit rappel plan/crédits */}
    <div className="mt-auto p-4 text-xs text-gray-400 border-t border-gray-700">
      {user?.email} • plan <strong className="text-gray-200">{user?.plan}</strong> • crédits <strong className="text-gray-200">{credits}</strong>
    </div>
  </div>
</div>

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
  {(deliverablesMap[p.id] || [])
    .filter(d => d.kind !== 'landing_public') // on masque l’ancien doublon
    .map((d) => {
      const isLanding   = d.kind === 'landing'
      const publicUrl   = d?.json_content?.public_url ?? null
      const isPublished = Boolean(publicUrl)
      const isPlan      = d.kind === 'plan' || /plan d'action/i.test(d.title || '')
      const isBusinessPlan =
        d.kind === "business_plan" ||            // si ton backend nomme ainsi
        d.kind === "model" ||                    // (souvent votre BP est "model")
        /business\s*plan/i.test(d.title || "");  // fallback robuste sur le titre
      const isMarketing  = d.kind === 'marketing' || /marketing/i.test(d.title || '');
      const isBrand = d.kind === 'brand' || d.kind === 'branding' || /brand|branding|identité|charte/i.test(d.title || '');
      const isOffer = d.kind === 'offer' || /offre|offer/i.test(d.title || '');

      return (
        <li key={d.id} className="bg-gray-600 p-3 rounded flex justify-between items-center">
          <span>
            <p className="font-medium">{d.title || d.kind}</p>
            <p className="text-xs text-gray-400">
              {new Date(d.created_at).toLocaleString()}
            </p>
          </span>

          {/* ✅ un seul conteneur, bien fermé */}
          <div className="flex gap-2 items-center">
            <button
              onClick={() => {
                if (isBusinessPlan) fireBpHelp("pdf");   // <= ouvre le modal BP
                if (isMarketing) {
                  window.dispatchEvent(new CustomEvent('mkt-help:open', { detail: { kind: 'pdf' } }));
                }
                if (isBrand) {
                  window.dispatchEvent(new CustomEvent('brand-help:open', { detail: { kind: 'pdf' } }));
                }
                if (isOffer) {
                  window.dispatchEvent(new CustomEvent('offer-help:open', { detail: { kind: 'pdf' } }));
                }
                onDownload(d, "pdf");                     // puis lance le téléchargement
              }}
              className="px-2 py-1 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm"
            >
              PDF
            </button>

            {d.has_file && (
              <button
                onClick={() => {
                  onDownload(d, 'html');
                  if (isLanding) {
                    window.dispatchEvent(new CustomEvent('landing-help:open', {
                      detail: { kind: 'html', deliverableId: d.id, projectId: p.id }
                    }));
                  }
                  if (isBusinessPlan) fireBpHelp("html"); // <= ouvre le modal BP
                  if (isMarketing) {
                    window.dispatchEvent(new CustomEvent('mkt-help:open', { detail: { kind: 'html' } }));
                  }
                  if (isBrand) {
                    window.dispatchEvent(new CustomEvent('brand-help:open', { detail: { kind: 'html' } }));
                  }
                  if (isOffer) {
                    window.dispatchEvent(new CustomEvent('offer-help:open', { detail: { kind: 'html' } }));
                  }
                    onDownload(d, "html");                   // puis lance le téléchargement
                  }}
                className="px-2 py-1 bg-green-700 hover:bg-green-600 rounded text-white text-sm"
              >
                HTML
              </button>
            )}

            {d.kind === 'plan' && (
              <button
                onClick={() => onDownload(d, 'ics')}
                className="px-2 py-1 bg-amber-600 hover:bg-amber-500 rounded text-white text-sm"
              >
                Agenda (.ics)
              </button>
            )}

            {isLanding && !isPublished && (
              <button
                disabled={!!publishingProjectId}
                onClick={async () => {
                  await handlePublishLanding(p.id);
                  window.dispatchEvent(new CustomEvent('landing-help:open', {
                    detail: { kind: 'publish', deliverableId: d.id, projectId: p.id }
                  }));
                }}
                className={`px-2 py-1 rounded text-white text-sm ${
                  publishingProjectId === p.id
                    ? 'bg-gray-500 cursor-wait'
                    : 'bg-teal-600 hover:bg-teal-500'
                }`}
                title="Publier via Nginx"
              >
                {publishingProjectId === p.id ? 'Publication…' : 'Mettre en ligne'}
              </button>
            )}

            {isLanding && isPublished && (
              <>
                <a
                  href={publicUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="px-2 py-1 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm"
                >
                  Ouvrir
                </a>
                <button
                  onClick={async () => {
                    try { await navigator.clipboard.writeText(publicUrl) } catch {}
                  }}
                  className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-white text-sm"
                  title="Copier l’URL"
                >
                  Copier
                </button>
              </>
            )}
          </div>
        </li>
      )
    })}
</ul>
            </div>
          ))
        )}
      </section>
      <LandingHelp />
      <BusinessPlanHelp />
      <MarketingHelp />
      <BrandingHelp />
      <OfferHelp />
    </div>
  )
}