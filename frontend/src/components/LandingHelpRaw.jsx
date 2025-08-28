// components/LandingHelp.jsx
"use client";
import React, { useEffect, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";

export default function LandingHelp() {
  const [isOpen, setIsOpen] = useState(false);
  const kindRef = useRef("html");   // "html" | "publish"
  const reqIdRef = useRef(null);    // requestId

  // Ouvre le modal via un CustomEvent
  useEffect(() => {
    const onOpen = (e) => {
      kindRef.current = (e?.detail?.kind) || "html";
      reqIdRef.current = e?.detail?.requestId ?? null;
      setIsOpen(true);
    };
    window.addEventListener("landing-help:open", onOpen);
    return () => window.removeEventListener("landing-help:open", onOpen);
  }, []);

  // Scroll lock
  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [isOpen]);

  const emitResolved = useCallback((action) => {
    const detail = {
      modal: "landing",
      requestId: reqIdRef.current,
      format: kindRef.current,  // "html" | "publish"
      action,
    };
    window.dispatchEvent(new CustomEvent("landing-help:resolved", { detail }));
    window.dispatchEvent(new CustomEvent("deliverable-help:resolved", { detail }));
  }, []);

  const closeWith = useCallback((action) => {
    emitResolved(action);
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

  const isPublish = kindRef.current === "publish";
  const title = isPublish ? "Mettre en ligne la landing" : "Utiliser le fichier HTML de la landing";
  const sub   = isPublish ? "Publication via l’app ou sur votre propre hébergeur" : "Héberger le fichier et connecter le formulaire";

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
        aria-labelledby="landing-help-title"
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
              <div id="landing-help-title" style={{ fontWeight: 800, fontSize: 18 }}>{title}</div>
              <div id="landing-help-sub" style={{ color: "#9ca3af", fontSize: 12 }}>{sub}</div>
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
              <strong>Option 1 — Serveur perso (Nginx/Apache)</strong>
              <ol style={{ margin: "8px 0 0 18px" }}>
                <li>Télécharge le fichier <code>landing.html</code> depuis l’app.</li>
                <li>Envoie-le sur ton hébergeur via SFTP/FTP dans le dossier principal du site (<code>/var/www/html/</code> ou <code>public_html/</code>).</li>
                <li>Si tu veux que ce soit la page d’accueil, renomme le fichier en <code>index.html</code>.</li>
                <li>Active le HTTPS (certificat Let’s Encrypt). En bref : ton site doit s’ouvrir en <b>https://</b>.</li>
              </ol>
              <details style={{ marginTop: 8 }}>
                <summary>Exemple (terminal Mac/Linux avec SCP)</summary>
                <pre style={{
                  whiteSpace: "pre-wrap", background: "#0b1220", border: "1px solid #1f2937",
                  borderRadius: 8, padding: 10, marginTop: 8
                }}>
scp landing.html user@votre-serveur:/var/www/html/index.html
# puis (si Nginx) :
sudo systemctl reload nginx
                </pre>
                <div style={{ color: "#9ca3af", fontSize: 12 }}>
                  Sous Windows, tu peux utiliser WinSCP (interface graphique) pour glisser-déposer le fichier.
                </div>
              </details>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Option 2 — Hébergement “sans serveur” (simple et gratuit)</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><u>Netlify</u> : clique “New site”, glisse-dépose <code>landing.html</code>. C’est tout.</li>
                <li><u>Vercel</u> : crée un projet “Other / Static”, pousse un dossier avec <code>index.html</code>.</li>
                <li><u>GitHub Pages</u> : mets <code>index.html</code> dans un repo, active “Pages” (branch <code>main</code>, dossier <code>/</code>).</li>
              </ul>
              <div style={{ color: "#9ca3af", fontSize: 12, marginTop: 6 }}>
                Ces plateformes te donnent une URL publique automatiquement. Tu peux brancher ton nom de domaine après.
              </div>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Modifier/brancher le fichier HTML</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li><b>Titre & Google</b> : mets un titre clair dans <code>&lt;title&gt;</code> et une “meta description”.</li>
                <li><b>Boutons & textes</b> : tu peux ouvrir le fichier dans un éditeur (VS Code) et changer les textes facilement.</li>
                <li><b>Formulaire de contact</b> : si tu héberges ailleurs, remplace l’URL de l’attribut <code>action</code> par l’URL de ton API.</li>
              </ul>
              <details style={{ marginTop: 8 }}>
                <summary>Exemple de formulaire prêt à l’emploi</summary>
                <pre style={{
                  whiteSpace: "pre-wrap", background: "#0b1220", border: "1px solid #1f2937",
                  borderRadius: 8, padding: 10, marginTop: 8
                }}>
{`<form action="https://app.ton-domaine.com/api/landing/lead" method="POST">
  <input type="hidden" name="project_id" value="123" />
  <input name="name" required />
  <input name="email" type="email" required />
  <textarea name="message"></textarea>
  <button type="submit">Envoyer</button>
</form>`}
                </pre>
                <div style={{ color: "#9ca3af", fontSize: 12, marginTop: 6 }}>
                  Si ton API est sur un autre domaine, autorise-le dans le CORS (en gros : dis à ton serveur “ce site peut m’appeler”).
                  Sinon, utilise un service de formulaires (Formspree, Netlify Forms).
                </div>
              </details>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Nom de domaine & HTTPS (optionnel, mais conseillé)</strong>
              <ol style={{ margin: "8px 0 0 18px" }}>
                <li>Crée un sous-domaine (ex. <code>landing.ton-domaine.com</code>).</li>
                <li>Relie-le à ton hébergeur :
                  A/AAAA si serveur, ou CNAME si Netlify/Vercel.</li>
                <li>Active le HTTPS (Let’s Encrypt ou via la plateforme). Ton site doit être en <b>https://</b>.</li>
              </ol>
            </div>

            <div style={{ background: "#0b1220", border: "1px solid #1f2937", borderRadius: 12, padding: 14 }}>
              <strong>Le bouton “Mettre en ligne” (dans l’app)</strong>
              <ul style={{ margin: "8px 0 0 18px", listStyle: "disc" }}>
                <li>Il envoie la dernière version de ta landing dans Nginx (sur ton instance) et te renvoie une URL publique.</li>
                <li>Tu peux aussi ignorer ce bouton et prendre le HTML pour l’héberger où tu veux (Netlify, Vercel, serveur perso).</li>
              </ul>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                onClick={() => {
                  const text =
                    "scp landing.html user@votre-serveur:/var/www/html/index.html\n# puis (si Nginx) :\nsudo systemctl reload nginx\n";
                  navigator.clipboard.writeText(text).then(() => {
                    const btn = document.getElementById("landing-help-copy-scp");
                    if (btn) {
                      btn.textContent = "Copié ✓";
                      setTimeout(() => { btn.textContent = "Copier l’exemple SCP"; }, 1500);
                    }
                  });
                }}
                id="landing-help-copy-scp"
                style={{ background: "#8b93ff", border: "none", color: "#fff",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 600, cursor: "pointer" }}
              >
                Copier l’exemple SCP
              </button>
              <button
                onClick={close}
                id="landing-help-close-2"
                style={{ background: "#14b8a6", border: "none", color: "#052e2b",
                         padding: "10px 12px", borderRadius: 10, fontWeight: 800, cursor: "pointer" }}
              >
                J’ai compris
              </button>
            </div>
            <div style={{ color: "#9ca3af", fontSize: 12 }}>
              Si la page ne se met pas à jour, vide le cache (Ctrl/Cmd+Shift+R).
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}