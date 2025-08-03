export default function Result({ data, onReset }) {
  return (
    <div className="max-w-lg w-full space-y-6 bg-gray-800 p-6 rounded-xl shadow-lg">
      <h2 className="text-2xl font-bold">🎉 Votre idée</h2>
      {['idee','persona','nom','slogan'].map((key) => (
        <p key={key}><strong>{key.charAt(0).toUpperCase()+key.slice(1)} :</strong> {data[key]}</p>
      ))}
      <button
        onClick={onReset}
        className="mt-4 px-4 py-2 bg-indigo-600 rounded hover:bg-indigo-500 transition"
      >
        Nouvelle idée
      </button>
    </div>
  );
}