import React from 'react'

export default function PackComparison({ selectedPack }) {
  const isInfinity  = selectedPack === 'infinity'
  const isStartNow  = selectedPack === 'startnow'

  // Lignes du comparatif
  const rows = [
    { label: 'Prix',                          infinity: '29,90€ / mois',            startnow: '350€ (forfait) + 29,90€ / mois' },
    { label: 'Engagement',                    infinity: 'Sans engagement',           startnow: 'Forfait unique + abo mensuel' },
    { label: 'Génération d’idées (illimitée)',infinity: true,                        startnow: true },
    { label: 'AI Rating (score 0–100)',       infinity: true,                        startnow: true },
    { label: 'Noms de marque (3)',           infinity: true,                        startnow: true },
    { label: 'Nom de domaine disponible (.com)', infinity: false,                   startnow: true },
    { label: 'Offre & Positionnement',        infinity: false,                       startnow: true },
    { label: 'Branding (nom + slogan)',       infinity: false,                       startnow: true },
    { label: 'MVP no-code réalisé',           infinity: false,                       startnow: true },
    { label: 'Business plan',                 infinity: false,                       startnow: true },
    { label: 'Landing page HTML prête',       infinity: false,                       startnow: true },
    { label: 'Stratégie d’acquisition (Ads, SEO, TikTok, LinkedIn…)', infinity: false, startnow: true },
    { label: 'To-do + plan de lancement (4 semaines)', infinity: false,             startnow: true },
  ]

  const cellClasses = (active) =>
    `px-4 py-3 text-sm text-gray-200 ${active ? 'bg-indigo-950/30 ring-1 ring-inset ring-indigo-500/30' : ''}`

  const renderVal = (val) => {
    if (val === true) {
      return (
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-600/20 text-green-400">
          ✓
        </span>
      )
    }
    if (val === false) {
      return (
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-gray-600/30 text-gray-400">
          –
        </span>
      )
    }
    return <span className="text-gray-100">{val}</span>
  }

  return (
    <section className="w-full max-w-5xl">
      <h3 className="text-2xl font-bold mb-4">Comparatif des packs</h3>
      <div className="overflow-x-auto rounded-lg border border-gray-700">
        <table className="w-full divide-y divide-gray-800">
          <thead className="bg-gray-800/60">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold text-gray-200">Caractéristiques</th>
              <th className={`px-4 py-3 text-left text-sm font-semibold ${isInfinity ? 'text-indigo-300' : 'text-gray-300'}`}>Infinity</th>
              <th className={`px-4 py-3 text-left text-sm font-semibold ${isStartNow ? 'text-indigo-300' : 'text-gray-300'}`}>StartNow</th>
            </tr>
          </thead>
          <tbody className="bg-gray-900 divide-y divide-gray-800">
            {rows.map((row, idx) => (
              <tr key={idx} className="hover:bg-gray-800/30">
                <td className="px-4 py-3 text-sm text-gray-300">{row.label}</td>
                <td className={cellClasses(isInfinity)}>{renderVal(row.infinity)}</td>
                <td className={cellClasses(isStartNow)}>{renderVal(row.startnow)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Section “Ce que vous obtenez” (résumé) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
        <div className={`p-5 rounded-lg border ${isInfinity ? 'border-indigo-500' : 'border-gray-700'}`}>
          <h4 className="text-xl font-semibold">Infinity — 29,90€/mois</h4>
          <p className="text-gray-300 mt-1">Sans engagement</p>
          <ul className="mt-3 space-y-2 text-gray-200">
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> Génération illimitée d’idées</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> AI rating automatique</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> 3 noms de marque proposés</li>
          </ul>
          <p className="text-xs text-gray-400 mt-3">Domaines, offre détaillée, MVP, etc. non inclus (voir StartNow).</p>
        </div>

        <div className={`p-5 rounded-lg border ${isStartNow ? 'border-indigo-500' : 'border-gray-700'}`}>
          <h4 className="text-xl font-semibold">StartNow — 350€ (forfait) + 29,90€/mois</h4>
          <p className="text-gray-300 mt-1">Accompagnement complet</p>
          <ul className="mt-3 space-y-2 text-gray-200">
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> Idée validée + positionnement</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> Branding (nom + slogan) & nom de domaine dispo</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> MVP no-code réalisé</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> Business plan</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> Landing page HTML prête à l’emploi</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> Stratégie d’acquisition (Ads, SEO, TikTok, LinkedIn…)</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> To-do list + plan de lancement (4 semaines)</li>
            <li className="flex items-start"><span className="mt-1 mr-2 h-2 w-2 rounded-full bg-indigo-500" /> Génération d’idées illimitée incluse (29,90€/mois)</li>
          </ul>
          <p className="text-xs text-gray-400 mt-3">Le forfait couvre la mise en route ; l’abonnement maintient l’idéation continue.</p>
        </div>
      </div>
    </section>
  )
}