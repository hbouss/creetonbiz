// src/pages/PremiumPage.jsx
import React, { useContext, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AuthContext } from '../contexts/AuthContext'   // ← on garde ton pattern actuel
import { loadStripe } from '@stripe/stripe-js'

// Initialise Stripe (nécessite VITE_STRIPE_PUBLISHABLE_KEY dans frontend/.env)
const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY)

export default function PremiumPage() {
  const { token, logout } = useContext(AuthContext) || { token: null, logout: () => {} }
  const navigate = useNavigate()

  const [selectedPack, setSelectedPack] = useState(null)
  const [acceptedCGV, setAcceptedCGV]   = useState(false)
  const [error, setError]               = useState('')
  const [loading, setLoading]           = useState(false)

  // Définition des packs avec contenu détaillé
  const packs = [
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
        'Branding (nom, slogan, .com disponible)',
        'MVP no-code réalisé',
        'Business plan',
        'Landing page HTML prête',
        'Stratégie d’acquisition (Ads, SEO, TikTok, LinkedIn…)',
        'To-do list + plan de lancement (4 semaines)',
        'Génération d’idée illimitée incluse (29,90€/mois)',
      ],
      finePrint: 'Forfait unique pour la mise en route + abonnement mensuel pour l’idéation.',
    },
  ]

  const selected = packs.find((p) => p.id === selectedPack)

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

    setError('')
    setLoading(true)

    try {
      // Endpoint backend à créer : POST /api/create-checkout-session
      const resp = await fetch('/api/create-checkout-session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

      <h2 className="text-3xl font-extrabold">Choisissez votre pack Business Premium</h2>

      {/* Cards de packs avec contenu détaillé */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-5xl">
        {packs.map((pack) => (
          <div
            key={pack.id}
            onClick={() => setSelectedPack(pack.id)}
            className={`p-6 rounded-lg shadow-lg cursor-pointer transition transform hover:scale-105 ${
              selectedPack === pack.id ? 'border-4 border-indigo-500' : 'border border-gray-700'
            }`}
          >
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

      {/* CGV */}
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

      {/* Erreurs */}
      {error && <p className="text-red-400">{error}</p>}

      {/* CTA */}
      <button
        onClick={handleCheckout}
        disabled={loading || !acceptedCGV}
        className={`mt-1 px-8 py-3 rounded-lg font-medium transition ${
          loading || !acceptedCGV
            ? 'bg-gray-600 cursor-not-allowed'
            : 'bg-indigo-600 hover:bg-indigo-500'
        }`}
      >
        {loading ? 'Redirection…' : selected ? `Choisir ${selected.title}` : 'Procéder au paiement'}
      </button>
    </div>
  )
}