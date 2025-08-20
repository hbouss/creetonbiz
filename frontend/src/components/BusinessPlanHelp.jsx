// components/BusinessPlanHelp.jsx
"use client";
import React, { useEffect, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";

export default function BusinessPlanHelp() {
  const [isOpen, setIsOpen] = useState(false);
  const kindRef = useRef("pdf"); // "pdf" | "html"

  // Ouvre le modal via un CustomEvent
  useEffect(() => {
    const onOpen = (e) => {
      kindRef.current = (e.detail && e.detail.kind) || "pdf";
      setIsOpen(true);
    };
    window.addEventListener("bp-help:open", onOpen);
    return () => window.removeEventListener("bp-help:open", onOpen);
  }, []);

  const close = useCallback(() => setIsOpen(false), []);

  // ESC pour fermer
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen, close]);

  if (!isOpen) return null;

  const isPDF = kindRef.current === "pdf";
  const title = "À propos du Business Plan";
  const sub   = isPDF
    ? "Tu télécharges le PDF : voici comment l’utiliser et le compléter"
    : "Tu télécharges la version HTML : voici comment l’adapter et le mettre en ligne";

  const copyChecklist = async () => {
    const text = `CHECKLIST Business Plan
- Contexte : problème, solution, marché (FR), cible
- Modèle éco : prix, marges, ARPU, churn (si SaaS), CAC
- Traction/preuves : clients pilotes, précommandes, POC
- Go-to-market : acquisition, partenariats, cycle de vente
- Opérations : équipe, roadmap 12 mois, principaux coûts
- Financier : compte de résultat prévisionnel, trésorerie, besoins de financement
- Risques : 3 risques clés + plan B
- Annexes : devis/factures, lettres d’intention, CV, statuts (brouillon), Kbis si dispo`;

    // Tentative via Clipboard API (HTTPS/localhost)
    let copied = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        copied = true;
      }
    } catch (_) {}

    // Fallback (textarea + execCommand)
    if (!copied) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try { document.execCommand("copy"); } catch (_) {}
      document.body.removeChild(ta);
    }

    // Feedback visuel sur le bouton
    const btn = document.getElementById("bp-help-copy");
    if (btn) {
      const prev = btn.textContent;
      btn.textContent = "Copié ✓";
      setTimeout(() => { btn.textContent = prev || "Copier la checklist"; }, 1500);
    }
  };

  return createPortal(
    <>
      {/* Overlay */}
      <div
        onClick={close}
        style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 9998 }}
      />

      {/* Modal */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="bp-help-title"
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
              <div id="bp-help-title" style={{ fontWeight: 800, fontSize: 18 }}>{title}</div>
              <div id="bp-help-sub" style={{ color: "#9ca3af", fontSize: 12 }}>{sub}</div>
            </div>
            <button
              onClick={close}
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
              <strong>Un business plan, c’est quoi ?</strong>
              <p style={{ marginTop: 8 }}>
                C’est le document qui raconte ton projet, comment tu vas gagner de l’argent,
                et comment tu vas t’organiser. Il sert à montrer que ton idée tient la route.
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>À quoi ça sert ?</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li>Convaincre une banque, des investisseurs ou des partenaires.</li>
                <li>Te donner une feuille de route claire pour les 6–12 prochains mois.</li>
                <li>Aligner toute l’équipe sur les priorités et les chiffres clés.</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>D’où viennent les chiffres ?</strong>
              <p style={{ marginTop: 8 }}>
                Le document est basé sur des données du marché <b>français</b> et adaptées au secteur que tu as choisi.
                C’est une très bonne base, mais tu dois <b>personnaliser</b> avec tes propres infos (prix, coûts, marge, hypothèses).
              </p>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Ce que tu dois ajouter</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>Preuves</b> : devis, lettres d’intention, POC, retours clients.</li>
                <li><b>Financier</b> : compte de résultat prévisionnel, trésorerie, besoin de financement.</li>
                <li><b>Juridique</b> : forme de la société, répartition du capital, statuts (brouillon si besoin).</li>
                <li><b>Équipe</b> : rôles, CV courts, disponibilité, partenaires clés.</li>
                <li><b>Risques</b> : 3 risques principaux + plan B (quoi faire si…?).</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Adapter les chiffres à ton projet</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li>SaaS : vérifie ARPU/prix, marge, churn, CAC, cycle de vente.</li>
                <li>E-com : vérifie panier moyen, taux de conv., retours, logistique.</li>
                <li>Services : vérifie TJM, charge, délais de règlement, sous-traitance.</li>
              </ul>
              <div style={{ color: "#9ca3af", fontSize: 12, marginTop: 6 }}>
                Conseil : fais 3 scénarios (pessimiste / réaliste / ambitieux) pour montrer que tu as réfléchi aux imprévus.
              </div>
            </div>

            {/** Spécifique aux formats **/}
            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>PDF ou HTML : que faire ?</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>PDF</b> : parfait pour envoyer par email ou imprimer. (Pour éditer, regénère le document depuis l’app plutôt que d’annoter le PDF.)</li>
                <li><b>HTML</b> : version web. Tu peux l’héberger comme un site statique (Netlify, Vercel) et mettre un mot de passe si besoin.</li>
              </ul>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Ce que les lecteurs regardent en premier</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li>Le résumé d’une page (problème → solution → marché → modèle → chiffres clés).</li>
                <li>Le prévisionnel simple (CA, marge, coûts, besoin de cash, point mort).</li>
                <li>La crédibilité de l’équipe et les preuves de traction.</li>
              </ul>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                onClick={copyChecklist}
                id="bp-help-copy"
                style={{ background: "#8b93ff", border: "none", color: "#fff",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 600, cursor: "pointer" }}
              >
                Copier la checklist
              </button>
              <button
                onClick={close}
                id="bp-help-close"
                style={{ background: "#14b8a6", border: "none", color: "#052e2b",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 800, cursor: "pointer" }}
              >
                J’ai compris
              </button>
            </div>
            <div style={{ color: "#9ca3af", fontSize: 12 }}>
              Garde une version datée, demande un avis extérieur (mentor, banquier), puis ajuste.
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}