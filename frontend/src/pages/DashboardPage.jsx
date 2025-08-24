// src/pages/DashboardPage.jsx
import React, { useContext, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { loadStripe } from "@stripe/stripe-js";
import { AuthContext } from "../contexts/AuthContext";
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
} from "../api.js";
import LandingHelp from "../components/LandingHelpRaw.jsx";
import BusinessPlanHelp from "../components/BusinessPlanHelp.jsx";
import MarketingHelp from "../components/MarketingHelp.jsx";
import BrandingHelp from "../components/BrandingHelp.jsx";
import OfferHelp from "../components/OfferHelp.jsx";

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY);

export default function DashboardPage() {
  const { user, refreshMe, logout } = useContext(AuthContext);
  const navigate = useNavigate();

  // UI state
  const [menuOpen, setMenuOpen] = useState(false);
  const [sheet, setSheet] = useState({ open: false, projectId: null, deliverable: null });

  // data state
  const [ideas, setIdeas] = useState([]);
  const [projects, setProjects] = useState([]);
  const [deliverablesMap, setDeliverablesMap] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [publishingProjectId, setPublishingProjectId] = useState(null);
  const [expandedIdeas, setExpandedIdeas] = useState({});
  const [convertingIdeaId, setConvertingIdeaId] = useState(null);
  const [generatingProjectId, setGeneratingProjectId] = useState(null);
  const [progressStep, setProgressStep] = useState(null);

  const projectRefs = useRef({});
  const scrollToProject = (projectId) => {
    const el = projectRefs.current[projectId];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const credits = user?.startnow_credits ?? 0;
  const isInfinity = user?.plan === "infinity";

  useEffect(() => {
    (async () => {
      try {
        await refreshMe();
      } catch {}
      await fetchIdeas();
      await fetchProjects();
    })();
  }, []);

  async function fetchIdeas() {
    try {
      const list = await listIdeas();
      setIdeas(list);
    } catch {}
  }

  async function fetchProjects() {
    try {
      const list = await listProjects();
      setProjects(list);
      const map = {};
      for (const p of list) {
        map[p.id] = await listDeliverables({ projectId: p.id });
      }
      setDeliverablesMap(map);
    } catch (e) {
      setError(e.message);
    }
  }

  const toggleIdea = (id) => setExpandedIdeas((prev) => ({ ...prev, [id]: !prev[id] }));

  async function handleConvertIdea(idea) {
    if (credits <= 0) {
      setError("Il faut un crédit StartNow pour convertir.");
      return;
    }
    setConvertingIdeaId(idea.id);
    setLoading(true);
    try {
      const projectBody = {
        title: idea.nom,
        secteur: idea.secteur,
        objectif: idea.objectif,
        competences: idea.competences,
        idea_id: idea.id,
      };
      const { id: projectId } = await createProject(projectBody);
      setGeneratingProjectId(projectId);
      setProgressStep("offer");

      await refreshMe();
      await generateAllPremium(
        { secteur: idea.secteur, objectif: idea.objectif, competences: idea.competences },
        projectId,
        (step) => setProgressStep(step)
      );

      await fetchIdeas();
      await fetchProjects();
      setTimeout(() => scrollToProject(projectId), 250);
    } catch (e) {
      setError(e.message);
    } finally {
      setConvertingIdeaId(null);
      setGeneratingProjectId(null);
      setProgressStep(null);
      setLoading(false);
    }
  }

  async function handleDeleteIdea(id) {
    if (!window.confirm("Supprimer cette idée ?")) return;
    try {
      await deleteIdea(id);
      await fetchIdeas();
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleDeleteProject(id) {
    if (!window.confirm("Supprimer ce projet ?")) return;
    setLoading(true);
    try {
      await deleteProject(id);
      await fetchProjects();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function onDownload(deliv, format) {
    try {
      await downloadDeliverable(deliv.id, {
        format,
        filename: `${deliv.title || deliv.kind}-${deliv.id}.${format}`,
      });
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleBuyCredits() {
    try {
      const { sessionId } = await createCheckoutSession("startnow");
      const stripe = await stripePromise;
      await stripe.redirectToCheckout({ sessionId });
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleOpenPortal() {
    try {
      const { url } = await openBillingPortal();
      window.location.href = url;
    } catch (e) {
      setError(e.message || "Impossible d’ouvrir le portail de facturation.");
    }
  }

  async function handlePublishLanding(projectId) {
    try {
      setPublishingProjectId(projectId);
      const { url } = await publishLanding(projectId);
      try {
        await navigator.clipboard.writeText(url);
      } catch {}
      alert(`Landing en ligne:\n${url}\n(Lien copié dans le presse-papiers)`);
      await fetchProjects();
    } catch (e) {
      setError(e.message);
    } finally {
      setPublishingProjectId(null);
    }
  }

  // Helpers feuilles d’action (mobile)
  function openDelivSheet(d, pId) {
    setSheet({ open: true, projectId: pId, deliverable: d });
  }
  function closeDelivSheet() {
    setSheet({ open: false, projectId: null, deliverable: null });
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 overflow-x-hidden">
      {/* Overlay spinner globale */}
      {(convertingIdeaId || generatingProjectId) && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center">
          <div className="bg-gray-800 p-6 rounded-xl shadow-xl text-center">
            <div className="mx-auto mb-4 h-10 w-10 border-4 border-white/20 border-t-white rounded-full animate-spin" />
            <p className="font-medium">Génération des livrables…</p>
            {progressStep && <p className="text-sm text-gray-300 mt-1">Étape : {progressStep}</p>}
          </div>
        </div>
      )}

      {/* Header sticky */}
      <header className="sticky top-0 z-30 bg-gray-900/85 backdrop-blur border-b border-gray-800">
        <div className="p-4 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold">Espace client</h1>
            <p className="text-gray-400 text-sm truncate">
              {user?.email} • plan <strong>{user?.plan}</strong> • crédits <strong>{credits}</strong>
            </p>
          </div>

          {/* ACTIONS DESKTOP */}
          <div className="hidden md:flex flex-wrap gap-2">
            {user?.is_admin && (
              <button
                onClick={() => navigate("/admin")}
                className="h-10 px-3 rounded-xl bg-purple-700 hover:bg-purple-600 text-white text-sm font-medium"
              >
                Admin
              </button>
            )}

            {(user?.plan === "infinity" || user?.plan === "startnow") && (
              <button
                onClick={handleOpenPortal}
                className="h-10 px-3 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium"
              >
                Gérer mon abonnement
              </button>
            )}

            {(isInfinity || user?.plan === "startnow") && (
              <button
                onClick={() => navigate("/")}
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
              onClick={() => navigate("/settings")}
              className="h-10 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
            >
              Settings
            </button>

            <button
              onClick={() => {
                logout();
                navigate("/login");
              }}
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
        </div>

        {/* Quick actions strip (mobile) */}
        <div className="md:hidden px-4 pb-3">
          <div className="flex gap-2 overflow-x-auto">
            {user?.is_admin && (
              <button
                onClick={() => navigate("/admin")}
                className="shrink-0 w-[160px] h-12 rounded-xl bg-purple-700 text-white text-sm font-medium"
                title="Espace admin"
              >
                👑 Admin
              </button>
            )}
            {(user?.plan === "infinity" || user?.plan === "startnow") && (
              <button
                onClick={handleOpenPortal}
                className="shrink-0 w-[160px] h-12 rounded-xl bg-teal-600 text-white text-sm font-medium"
              >
                💳 Abonnement
              </button>
            )}
            {(isInfinity || user?.plan === "startnow") && (
              <button
                onClick={() => navigate("/")}
                className="shrink-0 w-[160px] h-12 rounded-xl bg-blue-600 text-white text-sm font-medium"
              >
                ✨ Générer idée
              </button>
            )}
            <button
              onClick={handleBuyCredits}
              className="shrink-0 w-[160px] h-12 rounded-xl bg-yellow-500 text-gray-900 text-sm font-medium"
            >
              🔄 Racheter jetons
            </button>
            <button
              onClick={() => navigate("/settings")}
              className="shrink-0 w-[160px] h-12 rounded-xl bg-indigo-600 text-white text-sm font-medium"
            >
              ⚙️ Settings
            </button>
            <button
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="shrink-0 w-[160px] h-12 rounded-xl bg-red-600 text-white text-sm font-medium"
            >
              🚪 Déconnexion
            </button>
          </div>
        </div>
      </header>

      {/* MOBILE DRAWER */}
      <div
        id="mobile-actions"
        className={`md:hidden fixed inset-0 z-50 ${menuOpen ? "pointer-events-auto" : "pointer-events-none"}`}
        role="dialog"
        aria-modal="true"
      >
        <div
          onClick={() => setMenuOpen(false)}
          className={`absolute inset-0 transition-opacity duration-200 ${
            menuOpen ? "opacity-100 bg-black/50" : "opacity-0"
          }`}
        />
        <div
          className={`absolute right-0 top-0 h-full w-10/12 max-w-xs bg-gray-800 shadow-2xl border-l border-gray-700
                transition-transform duration-200 ${menuOpen ? "translate-x-0" : "translate-x-full"}`}
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
            {user?.is_admin && (
              <button
                onClick={() => {
                  setMenuOpen(false);
                  navigate("/admin");
                }}
                className="w-full h-12 rounded-xl bg-purple-700 hover:bg-purple-600 text-white text-sm font-medium"
              >
                👑 Admin
              </button>
            )}

            {(user?.plan === "infinity" || user?.plan === "startnow") && (
              <button
                onClick={() => {
                  setMenuOpen(false);
                  handleOpenPortal();
                }}
                className="w-full h-12 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium"
              >
                💳 Abonnement
              </button>
            )}

            {(isInfinity || user?.plan === "startnow") && (
              <button
                onClick={() => {
                  setMenuOpen(false);
                  navigate("/");
                }}
                className="w-full h-12 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
              >
                ✨ Générer idée
              </button>
            )}

            <button
              onClick={() => {
                setMenuOpen(false);
                handleBuyCredits();
              }}
              className="w-full h-12 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-gray-900 text-sm font-medium"
            >
              🔄 Racheter jetons
            </button>

            <button
              onClick={() => {
                setMenuOpen(false);
                navigate("/settings");
              }}
              className="w-full h-12 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
            >
              ⚙️ Settings
            </button>

            <button
              onClick={() => {
                setMenuOpen(false);
                logout();
                navigate("/login");
              }}
              className="w-full h-12 rounded-xl bg-red-600 hover:bg-red-500 text-white text-sm font-medium"
            >
              🚪 Déconnexion
            </button>
          </div>

          <div className="mt-auto p-4 text-xs text-gray-400 border-t border-gray-700">
            {user?.email} • plan <strong className="text-gray-200">{user?.plan}</strong> • crédits{" "}
            <strong className="text-gray-200">{credits}</strong>
          </div>
        </div>
      </div>

      {/* Corps */}
      <main className="p-4 sm:p-6 space-y-6">
        {/* Idées */}
        <section className="bg-gray-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Mes idées générées</h2>
            {ideas.length > 0 && (
              <span className="text-xs text-gray-400">{ideas.length} idée(s)</span>
            )}
          </div>

          {ideas.length === 0 ? (
            <div className="text-gray-400 text-sm">
              Aucune idée pour le moment.
              {(isInfinity || user?.plan === "startnow") && (
                <>
                  {" "}
                  <button
                    onClick={() => navigate("/")}
                    className="underline text-blue-300 hover:text-blue-200"
                  >
                    Générer ma première idée
                  </button>
                  .
                </>
              )}
            </div>
          ) : (
            ideas.map((i) => {
              const stableId = i.id ?? i.nom ?? i.idee;
              const isOpen = !!expandedIdeas[stableId];
              const fullText = i.idee || "";
              const isLong = fullText.length > 240;
              const displayText = isOpen || !isLong ? fullText : fullText.slice(0, 240) + "…";
              const ratingNum = Number(i.potential_rating);
              const linkedProjects = projects.filter((p) => p.idea_id === i.id);
              const alreadyConverted = linkedProjects.length > 0;
              const firstProjectId = alreadyConverted ? linkedProjects[0].id : null;

              return (
                <div key={stableId} className="bg-gray-700 p-4 rounded-lg flex flex-col gap-2">
                  <div className="flex justify-between items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium leading-relaxed break-words">{displayText}</p>
                      {isLong && (
                        <button
                          type="button"
                          onClick={() => toggleIdea(stableId)}
                          className="mt-1 text-blue-300 hover:text-blue-200 underline text-sm"
                        >
                          {isOpen ? "Réduire" : "Lire la suite"}
                        </button>
                      )}
                    </div>

                    {Number.isFinite(ratingNum) && (
                      <div className="shrink-0 flex flex-col items-end">
                        <span className="text-[11px] text-gray-300 mb-1">
                          Potentiel de l'idée
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded text-xs text-white ${
                            ratingNum >= 8
                              ? "bg-emerald-600"
                              : ratingNum >= 6
                              ? "bg-yellow-600"
                              : "bg-gray-600"
                          }`}
                        >
                          🌟 {ratingNum.toFixed(1)} / 10
                        </span>
                      </div>
                    )}
                  </div>

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

                  <p className="text-xs text-gray-400">{new Date(i.created_at).toLocaleString()}</p>

                  <div className="mt-2 grid grid-cols-2 gap-2 sm:flex sm:gap-2">
                    <button
                      disabled={loading || credits <= 0 || alreadyConverted}
                      onClick={() => handleConvertIdea(i)}
                      className={`w-full h-10 rounded-lg text-white text-sm ${
                        loading && convertingIdeaId === i.id
                          ? "bg-gray-600 cursor-wait"
                          : credits <= 0 || alreadyConverted
                          ? "bg-gray-600 cursor-not-allowed"
                          : "bg-emerald-600 hover:bg-emerald-500"
                      }`}
                    >
                      {alreadyConverted
                        ? "Déjà convertie"
                        : convertingIdeaId === i.id
                        ? "Conversion…"
                        : "Convertir"}
                    </button>
                    <button
                      disabled={loading}
                      onClick={() => handleDeleteIdea(i.id)}
                      className="w-full h-10 rounded-lg text-red-200 hover:text-red-400 text-sm bg-gray-800"
                      title="Supprimer l’idée"
                    >
                      🗑 Supprimer
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </section>

        {/* Projets */}
        <section className="bg-gray-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Mes projets & livrables</h2>
            {projects.length > 0 && (
              <span className="text-xs text-gray-400">{projects.length} projet(s)</span>
            )}
          </div>

          {projects.length === 0 ? (
            <div className="text-gray-400 text-sm">
              Aucun projet pour le moment.
              {(isInfinity || user?.plan === "startnow") && (
                <>
                  {" "}
                  <button
                    onClick={() => navigate("/")}
                    className="underline text-blue-300 hover:text-blue-200"
                  >
                    Créer un projet à partir d’une idée
                  </button>
                  .
                </>
              )}
            </div>
          ) : (
            projects.map((p) => (
              <div
                key={p.id}
                ref={(el) => (projectRefs.current[p.id] = el)}
                className="bg-gray-700 p-4 rounded-lg space-y-3"
              >
                <div className="flex justify-between items-start gap-3">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <span className="break-words">{p.title}</span>
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
                    className="shrink-0 text-red-400 hover:text-red-600 text-sm"
                    title="Supprimer le projet"
                  >
                    🗑
                  </button>
                </div>

                <ul className="grid sm:grid-cols-2 gap-3">
                  {(deliverablesMap[p.id] || [])
                    .filter((d) => d.kind !== "landing_public")
                    .map((d) => {
                      const isLanding = d.kind === "landing";
                      const publicUrl = d?.json_content?.public_url ?? null;
                      const isPublished = Boolean(publicUrl);
                      const isPlan = d.kind === "plan" || /plan d'action/i.test(d.title || "");
                      const isBusinessPlan =
                        d.kind === "business_plan" ||
                        d.kind === "model" ||
                        /business\s*plan/i.test(d.title || "");
                      const isMarketing = d.kind === "marketing" || /marketing/i.test(d.title || "");
                      const isBrand =
                        d.kind === "brand" ||
                        d.kind === "branding" ||
                        /brand|branding|identité|charte/i.test(d.title || "");
                      const isOffer = d.kind === "offer" || /offre|offer/i.test(d.title || "");

                      const openHelpPDF = () => {
                        if (isBusinessPlan) window.dispatchEvent(new CustomEvent("bp-help:open", { detail: { kind: "pdf" } }));
                        if (isMarketing) window.dispatchEvent(new CustomEvent("mkt-help:open", { detail: { kind: "pdf" } }));
                        if (isBrand) window.dispatchEvent(new CustomEvent("brand-help:open", { detail: { kind: "pdf" } }));
                        if (isOffer) window.dispatchEvent(new CustomEvent("offer-help:open", { detail: { kind: "pdf" } }));
                      };
                      const openHelpHTML = () => {
                        if (isLanding) {
                          window.dispatchEvent(
                            new CustomEvent("landing-help:open", {
                              detail: { kind: "html", deliverableId: d.id, projectId: p.id },
                            })
                          );
                        }
                        if (isBusinessPlan) window.dispatchEvent(new CustomEvent("bp-help:open", { detail: { kind: "html" } }));
                        if (isMarketing) window.dispatchEvent(new CustomEvent("mkt-help:open", { detail: { kind: "html" } }));
                        if (isBrand) window.dispatchEvent(new CustomEvent("brand-help:open", { detail: { kind: "html" } }));
                        if (isOffer) window.dispatchEvent(new CustomEvent("offer-help:open", { detail: { kind: "html" } }));
                      };

                      return (
                        <li key={d.id} className="bg-gray-600 p-3 rounded-lg">
                          <div className="flex items-center justify-between gap-2">
                            <span className="min-w-0">
                              <p className="font-medium break-words">{d.title || d.kind}</p>
                              <p className="text-xs text-gray-300">
                                {new Date(d.created_at).toLocaleString()}
                              </p>
                            </span>

                            {/* Actions desktop */}
                            <div className="hidden sm:flex gap-2 items-center">
                              <button
                                onClick={() => {
                                  openHelpPDF();
                                  onDownload(d, "pdf");
                                }}
                                className="px-2 py-1 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm"
                              >
                                PDF
                              </button>

                              {d.has_file && (
                                <button
                                  onClick={() => {
                                    openHelpHTML();
                                    onDownload(d, "html");
                                  }}
                                  className="px-2 py-1 bg-green-700 hover:bg-green-600 rounded text-white text-sm"
                                >
                                  HTML
                                </button>
                              )}

                              {isPlan && (
                                <button
                                  onClick={() => onDownload(d, "ics")}
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
                                    window.dispatchEvent(
                                      new CustomEvent("landing-help:open", {
                                        detail: { kind: "publish", deliverableId: d.id, projectId: p.id },
                                      })
                                    );
                                  }}
                                  className={`px-2 py-1 rounded text-white text-sm ${
                                    publishingProjectId === p.id
                                      ? "bg-gray-500 cursor-wait"
                                      : "bg-teal-600 hover:bg-teal-500"
                                  }`}
                                  title="Publier via Nginx"
                                >
                                  {publishingProjectId === p.id ? "Publication…" : "Mettre en ligne"}
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
                                      try {
                                        await navigator.clipboard.writeText(publicUrl);
                                      } catch {}
                                    }}
                                    className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-white text-sm"
                                    title="Copier l’URL"
                                  >
                                    Copier
                                  </button>
                                </>
                              )}
                            </div>

                            {/* Actions mobile -> bouton ⋯ ouvre feuille d’action */}
                            <button
                              onClick={() => openDelivSheet(d, p.id)}
                              className="sm:hidden h-9 w-9 grid place-items-center rounded-lg bg-gray-800 text-white"
                              aria-label="Actions"
                              title="Actions"
                            >
                              ⋯
                            </button>
                          </div>
                        </li>
                      );
                    })}
                </ul>
              </div>
            ))
          )}
        </section>
      </main>

      {/* Bottom sheet actions (mobile) */}
      {sheet.open && sheet.deliverable && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={closeDelivSheet} />
          <div
            className="absolute bottom-0 left-0 right-0 bg-gray-800 border-t border-gray-700 rounded-t-2xl p-4 space-y-3"
            style={{ paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 16px)" }}
          >
            <div className="flex items-center justify-between">
              <p className="font-semibold truncate">{sheet.deliverable.title || sheet.deliverable.kind}</p>
              <button onClick={closeDelivSheet} className="p-2 rounded-lg bg-gray-700">
                ✕
              </button>
            </div>

            <button
              onClick={() => {
                window.dispatchEvent(new CustomEvent("bp-help:open", { detail: { kind: "pdf" } })); // ne gêne pas si non-BP
                onDownload(sheet.deliverable, "pdf");
                closeDelivSheet();
              }}
              className="w-full h-12 rounded-xl bg-indigo-600 text-white font-medium"
            >
              Télécharger PDF
            </button>

            {sheet.deliverable.has_file && (
              <button
                onClick={() => {
                  onDownload(sheet.deliverable, "html");
                  closeDelivSheet();
                }}
                className="w-full h-12 rounded-xl bg-green-700 text-white font-medium"
              >
                Télécharger HTML
              </button>
            )}

            {sheet.deliverable.kind === "plan" && (
              <button
                onClick={() => {
                  onDownload(sheet.deliverable, "ics");
                  closeDelivSheet();
                }}
                className="w-full h-12 rounded-xl bg-amber-600 text-white font-medium"
              >
                Ajouter à l’agenda (.ics)
              </button>
            )}

            {sheet.deliverable.kind === "landing" && !sheet.deliverable?.json_content?.public_url && (
              <button
                onClick={async () => {
                  await handlePublishLanding(sheet.projectId);
                  closeDelivSheet();
                }}
                className="w-full h-12 rounded-xl bg-teal-600 text-white font-medium"
              >
                Mettre en ligne
              </button>
            )}

            {sheet.deliverable.kind === "landing" && sheet.deliverable?.json_content?.public_url && (
              <div className="grid grid-cols-2 gap-2">
                <a
                  href={sheet.deliverable.json_content.public_url}
                  target="_blank"
                  rel="noreferrer"
                  className="h-12 grid place-items-center rounded-xl bg-blue-600 text-white font-medium"
                >
                  Ouvrir
                </a>
                <button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(sheet.deliverable.json_content.public_url);
                    } catch {}
                    closeDelivSheet();
                  }}
                  className="h-12 rounded-xl bg-gray-700 text-white font-medium"
                >
                  Copier l’URL
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <LandingHelp />
      <BusinessPlanHelp />
      <MarketingHelp />
      <BrandingHelp />
      <OfferHelp />
    </div>
  );
}