// components/BrandingHelp.jsx
"use client";
import React, { useEffect, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";

export default function BrandingHelp() {
  const [isOpen, setIsOpen] = useState(false);
  const kindRef = useRef("pdf");   // "pdf" | "html"
  const reqIdRef = useRef(null);
  const afterRef = useRef(null);   // ✅ callback download

  // Ouverture via CustomEvent
  useEffect(() => {
    const onOpen = (e) => {
      kindRef.current = (e?.detail?.kind) || "pdf";
      reqIdRef.current = e?.detail?.requestId ?? null;
      afterRef.current  = typeof e?.detail?.after === "function" ? e.detail.after : null;
      setIsOpen(true);
    };
    window.addEventListener("brand-help:open", onOpen);
    return () => window.removeEventListener("brand-help:open", onOpen);
  }, []);

  // Scroll lock
  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [isOpen]);

  const emitResolved = useCallback((action, executed = false) => {
    const detail = {
      modal: "branding",
      requestId: reqIdRef.current,
      format: kindRef.current,
      action,
      executed,
    };
    window.dispatchEvent(new CustomEvent("brand-help:resolved", { detail }));
    window.dispatchEvent(new CustomEvent("deliverable-help:resolved", { detail }));
  }, []);

  const closeWith = useCallback((action) => {
    let executed = false;
    if (action === "confirm" && typeof afterRef.current === "function") {
      try { afterRef.current(); executed = true; } catch(_) {}
      afterRef.current = null;
    }
    emitResolved(action, executed);
    setIsOpen(false);
  }, [emitResolved]);

  // ESC
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => { if (e.key === "Escape") closeWith("escape"); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen, closeWith]);

  if (!isOpen) return null;

  const isPDF = kindRef.current === "pdf";
  const title = "À propos du document Branding";
  const sub   = isPDF
    ? "Tu télécharges le PDF : voici comment l’utiliser rapidement"
    : "Tu télécharges la version HTML : voici comment l’adapter et la partager";

  const copyChecklist = async () => {
    const text = `CHECKLIST Branding
- Nom de marque + tagline
- Mission, promesse et valeurs (3-5 max)
- Logos (couleurs, noir/blanc, fond clair/foncé) + zones de protection
- Palette couleurs (HEX/RGB), usages recommandés
- Typographies (titres / textes) + alternatives web
- Iconographie et style d’images (exemples)
- Ton de voix (do / don't) + exemples de messages
- Templates clés (post social, bannière, slide, carte de visite)
- Exemples d'usages corrects / incorrects
- Dossier partagé (assets, exports SVG/PNG/PDF, polices)`;

    let copied = false;
    try { if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); copied = true; } } catch {}
    if (!copied) {
      const ta = document.createElement("textarea");
      ta.value = text; ta.readOnly = true; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.focus(); ta.select();
      try { document.execCommand("copy"); } catch {}
      document.body.removeChild(ta);
    }

    const btn = document.getElementById("brand-help-copy");
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
        aria-labelledby="brand-help-title"
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
              <div id="brand-help-title" style={{ fontWeight: 800, fontSize: 18 }}>{title}</div>
              <div id="brand-help-sub" style={{ color: "#9ca3af", fontSize: 12 }}>{sub}</div>
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
                <li><b>Charte de marque</b> : promesse, valeurs, message.</li>
                <li><b>Logos</b> : versions couleur/monochrome + règles d’usage.</li>
                <li><b>Couleurs & typos</b> : codes HEX, polices titres & textes.</li>
                <li><b>Ton & style</b> : comment parler, exemples “do/don’t”.</li>
                <li><b>Exemples</b> : posts, bannières, slides, cartes, etc.</li>
                <li><b>Pack d’assets</b> : exports (SVG/PNG/PDF), polices, gabarits.</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>À quoi ça sert</strong>
              <p style={{ marginTop: 8 }}>
                À garder une <b>image cohérente</b> partout (site, réseaux, docs) et à <b>gagner du temps</b> :
                moins d’hésitations, plus de propreté, plus d’impact.
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>L’objectif</strong>
              <p style={{ marginTop: 8 }}>
                Faire parler ta marque d’une seule voix : un univers visuel et un ton clairs,
                faciles à réutiliser par toi et par ton équipe/tes prestas.
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Le “gain” pour toi</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>Pro</b> : rendu propre et crédible, même avec peu de moyens.</li>
                <li><b>Vitesse</b> : templates prêts → tu publies plus vite.</li>
                <li><b>Facile à déléguer</b> : brief clair pour un designer/une agence.</li>
              </ul>
            </div>

            {/* Utilisation */}
            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Comment t’en servir</strong>
              <ol style={{ margin: "8px 0 0 18px" }}>
                <li>Parcours la charte : logos, couleurs, typos, ton.</li>
                <li>Installe les polices et récupère les fichiers logos.</li>
                <li>Duplique les <b>templates</b> (post, bannière, slide) et remplace textes/visuels.</li>
                <li>Centralise tout dans un <b>dossier partagé</b> (Drive/Notion) pour l’équipe.</li>
              </ol>
            </div>

            {/* Formats */}
            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>PDF ou HTML ?</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>PDF</b> : parfait pour partager à l’équipe, partenaires, prestas.</li>
                <li><b>HTML</b> : version web consultable (Netlify/Vercel) → pratique pour on-boarder une agence.</li>
              </ul>
            </div>

            {/* Adaptations */}
            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Ce que tu peux (et dois) adapter</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>Ton</b> : plus sérieux, fun, premium… selon ta cible.</li>
                <li><b>Palette</b> : ajuste 1–2 couleurs si besoin (accessibilité d’abord).</li>
                <li><b>Logo</b> : variantes simplifiées pour petits formats.</li>
                <li><b>Templates</b> : titres/CTA, formats réseaux, cas d’usages.</li>
              </ul>
            </div>

            {/* Actions */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                onClick={copyChecklist}
                id="brand-help-copy"
                style={{ background: "#8b93ff", border: "none", color: "#fff",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 600, cursor: "pointer" }}
              >
                Copier la checklist
              </button>
              <button
                onClick={() => closeWith("confirm")}
                id="brand-help-close"
                style={{ background: "#14b8a6", border: "none", color: "#052e2b",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 800, cursor: "pointer" }}
              >
                J’ai compris
              </button>
            </div>

            <div style={{ color: "#9ca3af", fontSize: 12 }}>
              Retiens : cohérence visuelle + ton clair = marque mémorable. Commence simple, améliore au fil des retours.
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}