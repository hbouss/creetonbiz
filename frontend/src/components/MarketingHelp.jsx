// components/MarketingHelp.jsx
"use client";
import React, { useEffect, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";

export default function MarketingHelp() {
  const [isOpen, setIsOpen] = useState(false);
  const kindRef = useRef("pdf");     // "pdf" | "html"
  const reqIdRef = useRef(null);     // optionnel: requestId de suivi
  const afterRef = useRef(null);     // ✅ callback passé par Dashboard pour lancer le download

  // Ouverture via CustomEvent
  useEffect(() => {
    const onOpen = (e) => {
      kindRef.current = (e?.detail?.kind) || "pdf";
      reqIdRef.current = e?.detail?.requestId ?? null;
      afterRef.current  = typeof e?.detail?.after === "function" ? e.detail.after : null;
      setIsOpen(true);
    };
    window.addEventListener("mkt-help:open", onOpen);
    return () => window.removeEventListener("mkt-help:open", onOpen);
  }, []);

  // Scroll lock (mobile)
  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [isOpen]);

  const emitResolved = useCallback((action, executed = false) => {
    const detail = {
      modal: "marketing",
      requestId: reqIdRef.current,
      format: kindRef.current, // "pdf" | "html"
      action,                  // "confirm" | "dismiss" | "escape" | "x"
      executed,                // true si le callback after a été exécuté
    };
    window.dispatchEvent(new CustomEvent("mkt-help:resolved", { detail }));
    window.dispatchEvent(new CustomEvent("deliverable-help:resolved", { detail }));
  }, []);

  const closeWith = useCallback((action) => {
    let executed = false;
    if (action === "confirm" && typeof afterRef.current === "function") {
      try { afterRef.current(); executed = true; } catch(_) {}
      afterRef.current = null; // évite double run
    }
    emitResolved(action, executed);
    setIsOpen(false);
  }, [emitResolved]);

  // ESC pour fermer
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => { if (e.key === "Escape") closeWith("escape"); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen, closeWith]);

  if (!isOpen) return null;

  const isPDF = kindRef.current === "pdf";
  const title = "À propos du document Marketing";
  const sub   = isPDF
    ? "Tu télécharges le PDF : voici comment l’utiliser rapidement"
    : "Tu télécharges la version HTML : voici comment l’adapter et la partager";

  const copyChecklist = async () => {
    const text = `CHECKLIST Marketing
- Contexte & cible : personas, pains, objections
- Proposition de valeur : promesse claire, bénéfices clés
- Message & angle : pitch, tagline, preuves
- Canaux : contenu, SEO/SEA, social, email, partenariats
- Parcours (funnel) : attirer → convertir → fidéliser
- Contenus : pages clés, posts, emails, scripts
- Budget & cadence : priorités, calendrier 4-6 semaines
- KPIs : trafic, leads, CAC, taux de conv., LTV
- Outils : analytics, CRM, emailing, design
- À adapter : ton, exemples, visuels, prix & offres par segment`;

    let copied = false;
    try { if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); copied = true; } } catch {}
    if (!copied) {
      const ta = document.createElement("textarea");
      ta.value = text; ta.readOnly = true; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.focus(); ta.select();
      try { document.execCommand("copy"); } catch {}
      document.body.removeChild(ta);
    }

    const btn = document.getElementById("mkt-help-copy");
    if (btn) { const prev = btn.textContent; btn.textContent = "Copié ✓"; setTimeout(() => { btn.textContent = prev || "Copier la checklist"; }, 1500); }
  };

  return createPortal(
    <>
      {/* Overlay */}
      <div
        onClick={() => closeWith("dismiss")}
        style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 9998 }}
      />

      {/* Modal */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="mkt-help-title"
        style={{
          position: "fixed", inset: 0, zIndex: 9999, display: "grid", placeItems: "center",
          fontFamily: "Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial"
        }}
      >
        <div style={{
          width: "min(920px,92vw)", maxHeight: "90vh", overflow: "auto",
          background: "#111827", color: "#e5e7eb", border: "1px solid #1f2937",
          borderRadius: 16, boxShadow: "0 10px 30px rgba(0,0,0,.35)"
        }}>
          {/* Header */}
          <div style={{
            padding: "18px 20px", borderBottom: "1px solid #1f2937",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12
          }}>
            <div>
              <div id="mkt-help-title" style={{ fontWeight: 800, fontSize: 18 }}>{title}</div>
              <div id="mkt-help-sub" style={{ color: "#9ca3af", fontSize: 12 }}>{sub}</div>
            </div>
            <button
              onClick={() => closeWith("x")}
              aria-label="Fermer"
              style={{ background: "#0b1220", border: "1px solid #1f2937", color: "#e5e7eb",
                       borderRadius: 10, padding: "8px 10px", cursor: "pointer" }}
            >
              Fermer ✕
            </button>
          </div>

          {/* Body */}
          <div style={{ padding: "18px 20px", display: "grid", gap: 16 }}>
            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Ce que contient le document</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>Personas & besoins</b> : qui tu cibles et ce qu’ils veulent.</li>
                <li><b>Proposition de valeur</b> : ta promesse simple et claire.</li>
                <li><b>Message</b> : pitch, angle, preuves (témoignages, chiffres).</li>
                <li><b>Canaux</b> : contenu, SEO/SEA, réseaux sociaux, email, partenariats.</li>
                <li><b>Parcours</b> : attirer → convertir → fidéliser (funnel).</li>
                <li><b>Plan d’action</b> : 4–6 semaines, tâches concrètes.</li>
                <li><b>KPIs</b> : trafic, leads, conversions, CAC, LTV.</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>À quoi ça sert</strong>
              <p style={{ marginTop: 8 }}>
                Avoir une <b>feuille de route marketing</b> claire pour lancer/accélérer :
                quoi publier, où, comment mesurer, et quoi améliorer chaque semaine.
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Origine des recommandations</strong>
              <p style={{ marginTop: 8 }}>
                Les propositions sont basées sur les <b>bonnes pratiques marché (France)</b> et
                sur ton secteur. Tu dois <b>adapter</b> les exemples, le ton, le budget et les visuels à ta marque.
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Comment t’en servir</strong>
              <ol style={{ margin: "8px 0 0 18px" }}>
                <li>Lis le <b>résumé</b> (public-cible, message, canaux, KPIs).</li>
                <li>Choisis 2–3 <b>canaux prioritaires</b> pour 4 semaines.</li>
                <li>Crée un <b>calendrier simple</b> (posts, emails, pages à publier).</li>
                <li>Lance, mesure les <b>KPIs</b>, et ajuste chaque semaine.</li>
              </ol>
            </div>

            {/* Formats */}
            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>PDF ou HTML ?</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>PDF</b> : parfait pour partager en interne (équipe, partenaires) ou envoyer par email.</li>
                <li><b>HTML</b> : version web. Tu peux la mettre en ligne (Netlify/Vercel) pour consultation rapide.</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Ce que tu peux (et dois) adapter</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>Ton & exemples</b> : parle comme ta marque.</li>
                <li><b>Budget</b> : selon tes moyens (test petit, scale si ça marche).</li>
                <li><b>Visuels</b> : captures, vidéos, témoignages, logos clients.</li>
                <li><b>Pages & emails</b> : titres, CTA, offres par segment.</li>
              </ul>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                onClick={copyChecklist}
                id="mkt-help-copy"
                style={{ background: "#8b93ff", border: "none", color: "#fff",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 600, cursor: "pointer" }}
              >
                Copier la checklist
              </button>
              <button
                onClick={() => closeWith("confirm")}
                id="mkt-help-close"
                style={{ background: "#14b8a6", border: "none", color: "#052e2b",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 800, cursor: "pointer" }}
              >
                J’ai compris
              </button>
            </div>

            <div style={{ color: "#9ca3af", fontSize: 12 }}>
              Objectif : publier vite, mesurer, améliorer. Pas besoin d’être parfait dès le jour 1.
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}