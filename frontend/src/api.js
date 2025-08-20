// src/api.js
// Centralisation des appels backend

// 1) Base URL (sans trailing slash pour éviter les //)
const BASE_URL =
  (import.meta.env.VITE_API_URL?.replace(/\/$/, "")) || "http://127.0.0.1:8000";

// 2) Helpers Auth
function getAuthToken() {
  try {
    return localStorage.getItem("auth_token");
  } catch {
    return null;
  }
}

function buildHeaders(extra = {}) {
  const token = getAuthToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

// Petit helper pour construire un querystring propre
function qs(obj = {}) {
  const sp = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    sp.append(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function request(path, { headers = {}, ...options } = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: buildHeaders(headers),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Erreur ${res.status}: ${text}`);
  }
  // 204 No Content → pas de JSON
  if (res.status === 204) return null;
  return res.json();
}

// --- Petit helper pour endpoints Premium qui exigent project_id ---
function withProjectId(path, projectId) {
  if (!projectId && projectId !== 0) {
    throw new Error("project_id obligatoire pour cet appel.");
  }
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}project_id=${encodeURIComponent(projectId)}`;
}

/* =========================================================
   FREE ENDPOINTS
   ========================================================= */
export const generateIdea = (profil) =>
  request("/api/generate", {
    method: "POST",
    body: JSON.stringify(profil),
  });

/* =========================================================
   AUTH
   ========================================================= */
export const register = (credentials) =>
  request("/register", {
    method: "POST",
    body: JSON.stringify(credentials),
  });

// /token attend du form-urlencoded
export const login = (credentials) =>
  fetch(`${BASE_URL}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      username: credentials.username,
      password: credentials.password,
    }),
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Erreur ${res.status}: ${text}`);
    }
    return res.json();
  });

export const getMe = () => request("/api/me");

// Settings (compte)
export const changePassword = ({ current_password, new_password }) =>
  request("/api/me/password", {
    method: "PUT",
    body: JSON.stringify({ current_password, new_password }),
  });

export const deleteMe = ({ current_password, cancel_stripe = false }) =>
  request("/api/me", {
    method: "DELETE",
    body: JSON.stringify({ current_password, cancel_stripe }),
  });

/* =========================================================
   BILLING / STRIPE
   ========================================================= */
export const createCheckoutSession = (pack) =>
  request("/api/create-checkout-session", {
    method: "POST",
    body: JSON.stringify({ pack }),
  });

export const verifyCheckoutSession = (sessionId) =>
  request(`/api/verify-checkout-session${qs({ session_id: sessionId })}`, {
    method: "GET",
  });

/* =========================================================
   PROJETS (listing + filtres + CRUD minimal)
   (adapte les routes si ton backend diffère)
   ========================================================= */

// GET /api/projects?status=...&q=...&from=...&to=... (exemple de filtres)
export const listProjects = (filters = {}) =>
  request(`/api/projects${qs(filters)}`, { method: "GET" });

// POST /api/projects  { title, idea_id? }
export const createProject = ({ title, secteur, objectif, competences, idea_id } = {}) =>
  request("/api/projects", {
    method: "POST",
    body: JSON.stringify({ title, secteur, objectif, competences, idea_id }),
  });

// GET /api/projects/:id
export const getProject = (projectId) =>
  request(`/api/projects/${encodeURIComponent(projectId)}`, { method: "GET" });

// PATCH /api/projects/:id  { title?, archived?, notes? ... }
export const updateProject = (projectId, patch = {}) =>
  request(`/api/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

// DELETE /api/projects/:id
export const deleteProject = (projectId) =>
  request(`/api/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });

/* =========================================================
   DELIVERABLES (filtrés par projet &/ou type)
   ========================================================= */

// GET /api/me/deliverables?project_id=...&kind=...
export const listDeliverables = ({ projectId, kind } = {}) =>
  request(`/api/me/deliverables${qs({ project_id: projectId, kind })}`, {
    method: "GET",
  });

// GET /api/me/deliverables/:id
export const getDeliverable = (id) =>
  request(`/api/me/deliverables/${id}`, { method: "GET" });

// Download (HTML/PDF/JSON) avec Authorization
export const downloadDeliverable = async (
  id,
  { format = "pdf", filename } = {}
) => {
  const res = await fetch(
    `${BASE_URL}/api/me/deliverables/${id}/download${qs({ format })}`,
    { headers: buildHeaders() }
  );
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Erreur ${res.status}: ${text}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download =
    filename || `deliverable-${id}.${format === "pdf" ? "pdf" : "html"}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

/* =========================================================
   PREMIUM (exige project_id)
   ========================================================= */
export const generateOffer = (profil, projectId) =>
  request(withProjectId("/api/premium/offer", projectId), {
    method: "POST",
    body: JSON.stringify(profil),
  });

export const generateModel = (profil, projectId) =>
  request(withProjectId("/api/premium/model", projectId), {
    method: "POST",
    body: JSON.stringify(profil),
  });

export const generateBrand = (profil, projectId) =>
  request(withProjectId("/api/premium/brand", projectId), {
    method: "POST",
    body: JSON.stringify(profil),
  });

export const generateLanding = (profil, projectId) =>
  request(withProjectId("/api/premium/landing", projectId), {
    method: "POST",
    body: JSON.stringify(profil),
  });

export const generateMarketing = (profil, projectId) =>
  request(withProjectId("/api/premium/marketing", projectId), {
    method: "POST",
    body: JSON.stringify(profil),
  });

export const generatePlan = (profil, projectId) =>
  request(withProjectId("/api/premium/plan", projectId), {
    method: "POST",
    body: JSON.stringify(profil),
  });

/* =========================================================
   ORCHESTRATEUR STARTNOW (pack complet sur un projet)
   ========================================================= */
export async function generateAllPremium(profil, projectId, onProgress) {
  const steps = [
    ["offer", generateOffer],
    ["model", generateModel],
    ["brand", generateBrand],
    ["landing", generateLanding],
    ["marketing", generateMarketing],
    ["plan", generatePlan],
  ];
  for (const [key, fn] of steps) {
    onProgress?.(key);
    await fn(profil, projectId);
  }
}

// MES IDÉES
export const listIdeas = () =>
  request("/api/me/ideas", { method: "GET" });

// SUPPRESSION
export const deleteIdea = (id) => request(`/api/me/ideas/${id}`, { method: "DELETE" });

// …
export const publishLanding = (projectId) =>
  request(`/api/premium/landing/publish?project_id=${projectId}`, {
    method: 'POST',
  });

// Forcer le navigateur à télécharger le .ics
export function openPlanICS(projectId) {
  const url = `/api/premium/plan/ics?project_id=${projectId}`;
  // Ouvre dans le même onglet -> déclenche le téléchargement
  window.location.href = url;
}
