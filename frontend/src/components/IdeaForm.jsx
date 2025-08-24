import React, { useState, useContext, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { AuthContext } from "../contexts/AuthContext";

export default function IdeaForm({ onSubmit, error }) {
  const { logout, user } = useContext(AuthContext);
  const navigate = useNavigate();

  // Champs
  const [secteur, setSecteur] = useState("");
  const [objectif, setObjectif] = useState("");
  const [competencesInput, setCompetencesInput] = useState("");
  const [competences, setCompetences] = useState([]);

  // Focus pour meilleur UX
  const compInputRef = useRef(null);

  // Suggestions rapides
  const secteurQuick = useMemo(
    () => ["Tech", "Mode", "Sport", "Éducation", "Restauration", "SaaS", "Marketplace"],
    []
  );
  const objectifQuick = useMemo(
    () => ["Side project", "Freelance", "Startup scalable", "E-commerce", "App mobile"],
    []
  );
  const competencesQuick = useMemo(
    () => ["Marketing", "No-code", "Design", "Dév Web", "Vente", "SEO", "Ads", "Data"],
    []
  );

  // Helpers tags compétences
  function addCompetence(token) {
    const t = String(token || "").trim();
    if (!t) return;
    if (competences.includes(t)) return;
    setCompetences((prev) => [...prev, t]);
    setCompetencesInput("");
    compInputRef.current?.focus();
  }
  function removeCompetence(t) {
    setCompetences((prev) => prev.filter((x) => x !== t));
  }
  function onCompetenceKey(e) {
    if (e.key === "Enter" || e.key === "," || e.key === ";") {
      e.preventDefault();
      addCompetence(competencesInput);
    }
  }

  // Soumission
  const canSubmit = secteur.trim().length >= 2 && objectif.trim().length >= 2 && competences.length > 0;
  function submit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    onSubmit({
      secteur: secteur.trim(),
      objectif: objectif.trim(),
      competences,
    });
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex flex-col">
      {/* Header sticky */}
      <header className="sticky top-0 z-20 bg-gray-900/80 backdrop-blur border-b border-gray-800">
        <div className="mx-auto max-w-screen-sm px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-600 rounded-full flex items-center justify-center text-white text-lg font-bold">
              CTB
            </div>
            <div>
              <p className="text-base font-semibold">CréeTonBiz</p>
              <p className="text-xs text-gray-400">
                {user?.email} • plan <span className="text-indigo-400">{user?.plan}</span>
              </p>
            </div>
          </div>

          {/* mini-actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate("/dashboard")}
              className="px-3 h-9 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
            >
              Mon compte
            </button>
            <button
              onClick={() => {
                logout?.();
                navigate("/login");
              }}
              className="px-3 h-9 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-medium"
            >
              Déconnexion
            </button>
          </div>
        </div>
      </header>

      {/* Contenu */}
      <main className="flex-1">
        <div className="mx-auto max-w-screen-sm px-4 pt-6 pb-28">
          <h1 className="text-2xl sm:text-3xl font-extrabold mb-4">Générateur d’idées</h1>
          {error && (
            <div className="mb-4 rounded-lg border border-red-700 bg-red-900/30 text-red-200 px-3 py-2 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={submit} className="space-y-6">
            {/* Secteur */}
            <div>
              <label className="block mb-2 text-sm font-medium">💼 Secteur d’activité</label>
              <input
                type="text"
                placeholder="Ex. Tech, Sport, Mode…"
                value={secteur}
                onChange={(e) => setSecteur(e.target.value)}
                className="w-full h-12 px-4 rounded-xl bg-gray-800 border border-gray-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 text-base"
                autoComplete="organization"
                autoCapitalize="sentences"
                autoCorrect="on"
                inputMode="text"
                enterKeyHint="next"
              />
              {/* Quick picks */}
              <div className="mt-2 flex gap-2 overflow-x-auto no-scrollbar">
                {secteurQuick.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSecteur(s)}
                    className="shrink-0 px-3 h-8 rounded-full bg-gray-800 border border-gray-700 text-gray-200 text-xs hover:border-indigo-500"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {/* Objectif */}
            <div>
              <label className="block mb-2 text-sm font-medium">🎯 Objectif</label>
              <input
                type="text"
                placeholder="Ex. side project, startup scalable…"
                value={objectif}
                onChange={(e) => setObjectif(e.target.value)}
                className="w-full h-12 px-4 rounded-xl bg-gray-800 border border-gray-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 text-base"
                autoComplete="on"
                autoCapitalize="sentences"
                autoCorrect="on"
                inputMode="text"
                enterKeyHint="next"
              />
              {/* Quick picks */}
              <div className="mt-2 flex gap-2 overflow-x-auto no-scrollbar">
                {objectifQuick.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setObjectif(s)}
                    className="shrink-0 px-3 h-8 rounded-full bg-gray-800 border border-gray-700 text-gray-200 text-xs hover:border-indigo-500"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {/* Compétences en tags */}
            <div>
              <label className="block mb-2 text-sm font-medium">🧩 Compétences</label>

              {/* Tags déjà ajoutés */}
              {competences.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-2">
                  {competences.map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-2 px-3 h-8 rounded-full bg-indigo-600/20 text-indigo-200 text-xs border border-indigo-500/40"
                    >
                      {t}
                      <button
                        type="button"
                        onClick={() => removeCompetence(t)}
                        className="w-5 h-5 grid place-items-center rounded-full bg-indigo-800/40 hover:bg-indigo-700/60"
                        aria-label={`Supprimer ${t}`}
                        title="Supprimer"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {/* Champ d’entrée des compétences */}
              <input
                ref={compInputRef}
                type="text"
                placeholder="Tapez une compétence puis Entrée ou , (ex. marketing)"
                value={competencesInput}
                onChange={(e) => setCompetencesInput(e.target.value)}
                onKeyDown={onCompetenceKey}
                className="w-full h-12 px-4 rounded-xl bg-gray-800 border border-gray-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 text-base"
                autoComplete="on"
                autoCapitalize="words"
                autoCorrect="on"
                inputMode="text"
                enterKeyHint="done"
              />

              {/* Suggestions rapides */}
              <div className="mt-2 flex gap-2 overflow-x-auto no-scrollbar">
                {competencesQuick.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => addCompetence(s)}
                    className="shrink-0 px-3 h-8 rounded-full bg-gray-800 border border-gray-700 text-gray-200 text-xs hover:border-indigo-500"
                  >
                    {s}
                  </button>
                ))}
              </div>

              <p className="mt-2 text-xs text-gray-400">
                Appuyez sur <span className="font-semibold text-gray-300">Entrée</span> ou <span className="font-semibold text-gray-300">,</span> pour ajouter.
              </p>
            </div>
          </form>

          {/* Aide repliable */}
          <details className="mt-6 text-gray-300 text-sm">
            <summary className="cursor-pointer font-semibold">ℹ️ Comment ça marche ?</summary>
            <ul className="mt-3 list-disc list-inside space-y-1">
              <li>Choisis ton secteur pour guider l’IA.</li>
              <li>Définis ton objectif principal.</li>
              <li>Ajoute tes compétences clés (tags).</li>
              <li>Lance la génération et valide l’idée.</li>
            </ul>
          </details>
        </div>
      </main>

      {/* Barre d’action sticky (safe-area iOS) */}
      <div
        className="fixed bottom-0 left-0 right-0 z-30 bg-gradient-to-t from-gray-900 via-gray-900/95 to-transparent"
        style={{ paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 12px)" }}
      >
        <div className="mx-auto max-w-screen-sm px-4 pb-3">
          <button
            onClick={submit}
            disabled={!canSubmit}
            className={`w-full h-12 rounded-xl font-semibold transition ${
              canSubmit
                ? "bg-indigo-600 hover:bg-indigo-500 text-white"
                : "bg-gray-700 text-gray-400 cursor-not-allowed"
            }`}
          >
            Générer mon idée
          </button>
        </div>
      </div>
    </div>
  );
}