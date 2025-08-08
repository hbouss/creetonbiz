// src/pages/PremiumPage.jsx
import React, { useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AuthContext } from '../contexts/AuthContext'
import { loadStripe } from '@stripe/stripe-js'
import PackComparison from '../components/PackComparison.jsx'

// Initialise Stripe (nécessite VITE_STRIPE_PUBLISHABLE_KEY dans frontend/.env)
const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY)

export default function PremiumPage() {
  const { token, user, logout, refreshMe } = useContext(AuthContext) || {}
  const navigate = useNavigate()
  const [params]  = useSearchParams()

  // 👉 Pré-sélection StartNow
  const [selectedPack, setSelectedPack] = useState('startnow')
  const [acceptedCGV, setAcceptedCGV]   = useState(false)
  const [error, setError]               = useState('')
  const [loading, setLoading]           = useState(false)
  const [banner, setBanner]             = useState(null) // { type: 'success'|'warning'|'info', text: string }

  const success   = params.get('success') === '1'
  const canceled  = params.get('canceled') === '1'
  const sessionId = params.get('session_id') || null

  // Empêche la double-confirmation si React refait un render
  const confirmingRef = useRef(false)

  // 1) Au retour de Stripe : on confirme la session + refresh me + redirection → /dashboard
  useEffect(() => {
    if (!success || !sessionId || confirmingRef.current) return
    confirmingRef.current = true

    ;(async () => {
      try {
        // Confirme la session côté backend (idempotent)
        const resp = await fetch(`/api/verify-checkout-session?session_id=${encodeURIComponent(sessionId)}`, {
          method: 'GET',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        // Si verify échoue (ex: webhook seul), on tente tout de même un refresh du profil
        if (!resp.ok) {
          const txt = await resp.text().catch(() => '')
          console.warn('verify-checkout-session non OK:', resp.status, txt)
        }

        await (refreshMe?.())

        setBanner({
          type: 'success',
          text: `Paiement confirmé ✅ ${sessionId ? `(session ${sessionId})` : ''}. Votre pack est activé.`,
        })

        // Laisse la bannière 1.2s puis redirige vers le Dashboard (où on liste les livrables)
        setTimeout(() => navigate('/dashboard', { replace: true }), 1200)
      } catch (e) {
        console.error(e)
        setBanner({
          type: 'warning',
          text: 'Paiement confirmé, mais la confirmation de session a échoué. Rafraîchis la page ou reconnecte-toi.',
        })
        confirmingRef.current = false
      }
    })()
  }, [success, sessionId, token, refreshMe, navigate])

  // 2) Gestion “paiement annulé”
  useEffect(() => {
    if (canceled) {
      setBanner({
        type: 'warning',
        text: 'Paiement annulé. Vous pouvez réessayer quand vous voulez.',
      })
    }
  }, [canceled])

  // Packs + “Recommandé” sur StartNow
  const packs = useMemo(() => ([
    {
      id: 'infinity',
      title: 'Pack Infinity',
      price: '29,90€ / mois',
      badge: 'Sans engagement',
      type: 'recurring',
      description: 'Génération illimitée d’idées de business',
      features: [
        'Génération illimitée d’idées',
        'Scoring automatique (rating 0–100)',
        '3 noms de marque proposés',
      ],
      finePrint: 'Annulable à tout moment.',
      recommended: false,
    },
    {
      id: 'startnow',
      title: 'Pack StartNow',
      price: '350€ (forfait) + 29,90€ / mois',
      badge: 'Accompagnement complet',
      type: 'one_time',
      description: 'Pack complet pour démarrer vite et bien',
      features: [
        'Idée validée + positionnement',
        'Branding (nom + slogan) & nom de domaine dispo',
        'MVP no-code réalisé',
        'Business plan',
        'Landing page HTML prête à l’emploi',
        'Stratégie d’acquisition (Ads, SEO, TikTok, LinkedIn…)',
        'To-do list + plan de lancement (4 semaines)',
        'Génération d’idées illimitée incluse (29,90€/mois)',
      ],
      finePrint: 'Forfait unique pour la mise en route + abonnement pour l’idéation continue.',
      recommended: true,
    },
  ]), [])

  const selected = useMemo(
    () => packs.find((p) => p.id === selectedPack),
    [packs, selectedPack]
  )

  // Désactive l’achat si déjà abonné
  const alreadySubscribed = user?.plan === 'infinity' || user?.plan === 'startnow'

  async function handleCheckout() {
    if (!selectedPack) {
      setError('Veuillez sélectionner un pack')
      return
    }
    if (!acceptedCGV) {
      setError('Vous devez accepter les CGV pour continuer')
      return
    }
    if (!import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY) {
      setError('Clé publique Stripe manquante (VITE_STRIPE_PUBLISHABLE_KEY)')
      return
    }
    if (!token) {
      navigate('/login')
      return
    }

    setError('')
    setLoading(true)

    try {
      // Endpoint backend : POST /api/create-checkout-session
      const resp = await fetch('/api/create-checkout-session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ pack: selectedPack }),
      })

      if (!resp.ok) {
        const txt = await resp.text()
        throw new Error(`Erreur ${resp.status}: ${txt}`)
      }

      const { sessionId } = await resp.json()
      const stripe = await stripePromise
      if (!stripe) throw new Error('Stripe non initialisé')

      const { error: stripeErr } = await stripe.redirectToCheckout({ sessionId })
      if (stripeErr) throw stripeErr
    } catch (e) {
      console.error(e)
      setError(e.message || 'Erreur lors de la redirection vers le paiement')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-6 flex flex-col items-center space-y-8">
      {/* Header simple + Déconnexion */}
      <div className="w-full max-w-5xl flex items-center justify-between">
        <h1 className="text-2xl font-bold">CréeTonBiz — Premium</h1>
        <div className="flex items-center gap-3">
          {user?.email && (
            <span className="text-sm text-gray-300">
              Connecté en tant que <span className="font-medium">{user.email}</span>
              {user?.plan && (
                <span className="ml-2 px-2 py-0.5 text-xs rounded bg-indigo-700/50 border border-indigo-600">
                  plan: {user.plan}
                </span>
              )}
            </span>
          )}
          <button
            onClick={() => {
              logout?.()
              navigate('/login')
            }}
            className="px-3 py-1 bg-red-600 rounded"
          >
            Déconnexion
          </button>
        </div>
      </div>

      {/* Bannière */}
      {banner && (
        <div
          className={`w-full max-w-5xl p-3 rounded border ${
            banner.type === 'success'
              ? 'bg-green-900/40 border-green-700 text-green-200'
              : banner.type === 'warning'
              ? 'bg-yellow-900/40 border-yellow-700 text-yellow-200'
              : 'bg-gray-800 border-gray-700 text-gray-200'
          }`}
        >
          {banner.text}
        </div>
      )}

      <h2 className="text-3xl font-extrabold">Choisissez votre pack Business Premium</h2>

      {/* Cards de packs */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-5xl">
        {packs.map((pack) => (
          <div
            key={pack.id}
            onClick={() => setSelectedPack(pack.id)}
            className={`relative p-6 rounded-lg shadow-lg cursor-pointer transition transform hover:scale-105 ${
              selectedPack === pack.id ? 'border-4 border-indigo-500' : 'border border-gray-700'
            }`}
          >
            {/* Badge “Recommandé” */}
            {pack.recommended && (
              <span className="absolute -top-3 -right-3 bg-indigo-600 text-white text-xs px-3 py-1 rounded-full shadow">
                Recommandé
              </span>
            )}

            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-2xl font-semibold">{pack.title}</h3>
                <p className="text-sm text-gray-400 mt-1">{pack.badge}</p>
              </div>
              <span className="text-xl font-bold">{pack.price}</span>
            </div>

            <p className="mt-3 text-gray-300">{pack.description}</p>

            <ul className="mt-4 space-y-2">
              {pack.features.map((f, i) => (
                <li key={i} className="flex items-start">
                  <span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" />
                  <span>{f}</span>
                </li>
              ))}
            </ul>

            {pack.finePrint && (
              <p className="mt-4 text-xs text-gray-400">{pack.finePrint}</p>
            )}
          </div>
        ))}
      </div>

      {/* Comparatif */}
      <PackComparison selectedPack={selectedPack} />

      {/* CGV */}
      {!alreadySubscribed && (
        <label className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={acceptedCGV}
            onChange={() => setAcceptedCGV((v) => !v)}
            className="w-5 h-5 text-indigo-600 bg-gray-700 rounded"
          />
          <span className="text-gray-300">
            J'accepte les <a href="/cgv" className="underline text-indigo-400">CGV</a>
          </span>
        </label>
      )}

      {/* Erreurs */}
      {error && <p className="text-red-400">{error}</p>}

      {/* CTA */}
      <div className="flex gap-3">
        <button
          onClick={handleCheckout}
          disabled={loading || !acceptedCGV || alreadySubscribed}
          className={`px-8 py-3 rounded-lg font-medium transition ${
            loading || !acceptedCGV || alreadySubscribed
              ? 'bg-gray-600 cursor-not-allowed'
              : 'bg-indigo-600 hover:bg-indigo-500'
          }`}
        >
          {alreadySubscribed
            ? 'Pack déjà actif'
            : loading
            ? 'Redirection…'
            : selected
            ? `Choisir ${selected.title}`
            : 'Procéder au paiement'}
        </button>

        {/* Accès livrables si abonné */}
        {alreadySubscribed && (
          <button
            onClick={() => navigate('/dashboard')}
            className="px-8 py-3 rounded-lg font-medium bg-green-700 hover:bg-green-600"
          >
            Voir mes livrables
          </button>
        )}
      </div>
    </div>
  )
}