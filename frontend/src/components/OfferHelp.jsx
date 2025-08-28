"use client";
import React, { useEffect, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";

export default function OfferHelp() {
  const [isOpen, setIsOpen] = useState(false);
  const kindRef  = useRef("pdf");   // "pdf" | "html"
  const afterRef = useRef(null);     // callback

  // Ouvre le modal via un CustomEvent
  useEffect(() => {
    const onOpen = (e) => {
      kindRef.current  = (e.detail && e.detail.kind) || "pdf";
      afterRef.current = (e.detail && e.detail.after) || null;
      setIsOpen(true);
    };
    window.addEventListener("offer-help:open", onOpen);
    return () => window.removeEventListener("offer-help:open", onOpen);
  }, []);

  const close = useCallback(() => setIsOpen(false), []);

  // ✨ Fermer avec la croix = exécuter le callback, puis fermer
  const closeAndRun = useCallback(() => {
    const fn = afterRef.current;
    afterRef.current = null;
    try { if (typeof fn === "function") fn(); } catch {}
    setIsOpen(false);
  }, []);

  // ESC pour fermer (sans download)
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen, close]);

  // Lock scroll (mobile)
  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [isOpen]);

  if (!isOpen) return null;

  const isPDF = kindRef.current === "pdf";
  const title = "À propos du document Offre";
  const sub   = isPDF
    ? "Tu télécharges le PDF : comment t’en servir tout de suite"
    : "Tu télécharges la version HTML : comment l’adapter et la partager";

  const copyChecklist = async () => {
    const text = `CHECKLIST Offre
- Proposition de valeur (1 phrase courte)
- Cible principale (persona) + douleurs/problèmes
- Bénéfices clés (3 à 5) + preuves/mini-cas
- Détails de l’offre (features/services inclus)
- Positionnement (différenciateurs vs concurrents)
- Prix et plans (Starter/Pro/Entreprise) + conditions
- Garanties / essai / modalités (ex: 14 jours, support)
- Appels à l’action (démo, essai, devis)
- Objections fréquentes + réponses
- Next steps : comment acheter / qui contacter`;
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch {}
    if (!ok) {
      const ta = document.createElement("textarea");
      ta.value = text; ta.setAttribute("readonly",""); ta.style.position="fixed"; ta.style.opacity="0";
      document.body.appendChild(ta); ta.focus(); ta.select();
      try { document.execCommand("copy"); } catch {}
      document.body.removeChild(ta);
    }
    const btn = document.getElementById("offer-help-copy");
    if (btn) { const prev = btn.textContent; btn.textContent = "Copié ✓"; setTimeout(() => { btn.textContent = prev || "Copier la checklist"; }, 1500); }
  };

  // "J’ai compris" = exécuter le callback puis fermer
  const proceedAndClose = () => {
    const fn = afterRef.current;
    afterRef.current = null;
    try { if (typeof fn === "function") fn(); } catch {}
    setIsOpen(false);
  };

  return createPortal(
    <>
      {/* Overlay (ferme sans download) */}
      <div
        onClick={close}
        style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 9998 }}
      />

      {/* Modal */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="offer-help-title"
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
              <div id="offer-help-title" style={{ fontWeight: 800, fontSize: 18 }}>{title}</div>
              <div id="offer-help-sub" style={{ color: "#9ca3af", fontSize: 12 }}>{sub}</div>
            </div>
            <button
              onClick={closeAndRun}  {/* ✨ maintenant exécute aussi le callback */}
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
                <li><b>Proposition de valeur</b> claire et courte.</li>
                <li><b>Offre détaillée</b> : ce que tu fournis (features/services).</li>
                <li><b>Bénéfices</b> concrets pour le client + preuves rapides.</li>
                <li><b>Plans & prix</b> pour s’adapter aux besoins.</li>
                <li><b>Différenciation</b> vs concurrents (ce qui te rend unique).</li>
                <li><b>Appels à l’action</b> : essai, démo, devis.</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>À quoi ça sert</strong>
              <p style={{ marginTop: 8 }}>
                À présenter ton offre de façon <b>simple et convaincante</b>, pour que le client comprenne vite
                la valeur, le prix, et comment passer à l’action.
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>L’objectif</strong>
              <p style={{ marginTop: 8 }}>
                Aider ton prospect à dire “oui” : lever les doutes, montrer le bénéfice, et rendre l’achat facile.
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Ton positionnement</strong>
              <p style={{ marginTop: 8 }}>
                Sois précis : pour qui c’est fait, en quoi tu es différent, et pourquoi c’est mieux <i>maintenant</i>.
                Quelques comparatifs simples suffisent.
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Le “gain” pour toi</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>Clarté</b> : pitch aligné pour toi et ton équipe.</li>
                <li><b>Conversion</b> : moins d’objections, plus de oui.</li>
                <li><b>Vitesse</b> : une base prête à envoyer/proposer.</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Comment t’en servir</strong>
              <ol style={{ margin: "8px 0 0 18px" }}>
                <li>Relis la proposition de valeur : 1 phrase, compréhensible en 5s.</li>
                <li>Vérifie que les <b>bénéfices</b> répondent bien aux soucis de ta cible.</li>
                <li>Vérifie les <b>prix/plans</b> : cohérents avec ton business plan et ton secteur.</li>
                <li>Ajoute 1–2 <b>preuves</b> (témoignage, chiffre, mini-cas) si tu en as.</li>
                <li>Ajoute un <b>CTA</b> clair : “Essai”, “Démo”, “Devis”.</li>
              </ol>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>PDF ou HTML ?</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>PDF</b> : parfait pour envoyer par email ou imprimer.</li>
                <li><b>HTML</b> : version web facile à partager (Netlify/Vercel), idéale pour un mini-site d’offre.</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Ce que tu peux (et dois) adapter</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li>Les <b>mots</b> (ton simple, ciblé) et les exemples.</li>
                <li>Les <b>prix</b> (Starter/Pro/Entreprise) selon ton marché et ta marge.</li>
                <li>Les <b>différenciateurs</b> : mets ceux qui comptent vraiment pour ta cible.</li>
              </ul>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                onClick={copyChecklist}
                id="offer-help-copy"
                style={{ background: "#8b93ff", border: "none", color: "#fff",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 600, cursor: "pointer" }}
              >
                Copier la checklist
              </button>
              <button
                onClick={proceedAndClose}
                id="offer-help-close"
                style={{ background: "#14b8a6", border: "none", color: "#052e2b",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 800, cursor: "pointer" }}
              >
                J’ai compris
              </button>
            </div>

            <div style={{ color: "#9ca3af", fontSize: 12 }}>
              Rappelle-toi : simplicité + preuves + CTA clair = proposition qui vend.
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}