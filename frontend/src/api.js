// Centralisation des appels backend
export const generateIdea = async (profil) => {
  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profil),
  });
  if (!res.ok) throw new Error(`Erreur ${res.status}`);
  return res.json();
};