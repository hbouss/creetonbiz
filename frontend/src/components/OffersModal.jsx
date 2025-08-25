// src/components/OffersModal.jsx
import React, { useEffect } from "react";

export default function OffersModal({ open, onClose, onBuyInfinity, onBuyStartNow }) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] bg-black/60 flex items-end sm:items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-gray-800 rounded-2xl shadow-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-700 flex items-center justify-between">
          <h3 className="text-white font-semibold text-lg">Choisissez votre pack</h3>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-gray-300 hover:text-white hover:bg-gray-700"
            aria-label="Fermer"
          >
            ✕
          </button>
        </div>

        <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="bg-gray-700 rounded-xl p-4 flex flex-col">
            <div className="flex items-start justify-between">
              <h4 className="text-white font-semibold text-lg">Infinity</h4>
              <span className="text-emerald-300 text-sm font-medium">Abonnement</span>
            </div>
            <p className="text-gray-300 text-sm mt-2 flex-1">
              Idées illimitées, accès continu, portail client Stripe.
            </p>
            <ul className="mt-3 text-gray-200 text-sm space-y-1">
              <li>• Idées illimitées</li>
              <li>• Portail d’abonnement</li>
              <li>• Support prioritaire</li>
            </ul>
            <button
              onClick={onBuyInfinity}
              className="mt-4 h-12 rounded-xl bg-teal-600 hover:bg-teal-500 text-white font-medium"
            >
              Choisir Infinity
            </button>
          </div>

          <div className="bg-gray-700 rounded-xl p-4 flex flex-col">
            <div className="flex items-start justify-between">
              <h4 className="text-white font-semibold text-lg">StartNow</h4>
              <span className="text-yellow-300 text-sm font-medium">Pack projet</span>
            </div>
            <p className="text-gray-300 text-sm mt-2 flex-1">
              1 crédit = génération complète d’un projet (offre, BP, branding, landing, marketing, plan).
            </p>
            <ul className="mt-3 text-gray-200 text-sm space-y-1">
              <li>• 1 crédit projet</li>
              <li>• Téléchargements PDF/HTML</li>
              <li>• Publication landing</li>
            </ul>
            <button
              onClick={onBuyStartNow}
              className="mt-4 h-12 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-gray-900 font-medium"
            >
              Choisir StartNow
            </button>
          </div>
        </div>

        <div className="px-5 pb-5 text-xs text-gray-400">
          Paiement sécurisé Stripe. Gérez/annulez depuis le portail.
        </div>
      </div>
    </div>
  );
}