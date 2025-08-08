export default function Result({ data, onReset }) {
  // Sécurise la lecture du rating (nombre ou string)
  const rating = Number.parseFloat?.(data?.potential_rating) ?? Number(data?.potential_rating);
  const hasRating = Number.isFinite(rating);

  // Couleur dynamique du badge
  const ratingClass =
    !hasRating ? 'bg-gray-600'
    : rating >= 8 ? 'bg-emerald-600'
    : rating >= 6 ? 'bg-yellow-600'
    : 'bg-gray-600';

  return (
    <div className="max-w-lg w-full space-y-6 bg-gray-800 p-6 rounded-xl shadow-lg">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">🎉 Votre idée</h2>
        {hasRating && (
          <span className={`px-2 py-1 rounded text-xs text-white ${ratingClass}`}>
            🌟 {rating.toFixed(1)} / 10
          </span>
        )}
      </div>

      <div className="space-y-2">
        <p><strong>Nom :</strong> {data?.nom}</p>
        <p className="text-gray-300 italic"><strong>Slogan :</strong> {data?.slogan}</p>
        <p><strong>Idée :</strong> {data?.idee}</p>
        <p><strong>Persona :</strong> {data?.persona}</p>
      </div>

      <button
        onClick={onReset}
        className="mt-4 px-4 py-2 bg-indigo-600 rounded hover:bg-indigo-500 transition"
      >
        Nouvelle idée
      </button>
    </div>
  );
}