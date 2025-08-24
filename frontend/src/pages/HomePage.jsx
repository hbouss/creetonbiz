// src/pages/HomePage.jsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { generateIdea } from "../api";
import IdeaForm from "../components/IdeaForm";
import Loader from "../components/Loader";
import Result from "../components/Result";

export default function HomePage() {
  const [step, setStep] = useState("home");
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const navigate = useNavigate();

  const handleGenerate = async (profil) => {
    setError(null);
    setStep("loading");
    try {
      const data = await generateIdea(profil);
      setResult(data);
      setStep("result");
    } catch (e) {
      const msg = String(e?.message || '');
      // 402 = quota free atteint → redirection Premium
      if (msg.includes('Erreur 402') || msg.includes('FREE_LIMIT_REACHED')) {
        navigate('/premium?reason=free_limit', { replace: true });
        return;
      }
      // 401 = non authentifié → login
      if (msg.includes('Erreur 401') || msg.toLowerCase().includes('unauthorized')) {
        navigate('/login');
        return;
      }
      setError(e.response?.data?.detail || e.message);
      setStep("home");
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex flex-col items-center justify-center p-4">
      {step === "home" && <IdeaForm onSubmit={handleGenerate} error={error} />}
      {step === "loading" && <Loader />}
      {step === "result" && result && (
        <div className="space-y-6 text-center">
          <Result data={result} onReset={() => setStep("home")} />
          <button
            onClick={() => navigate('/premium', { state: { idea: result } })}
            className="px-6 py-3 bg-yellow-500 text-gray-900 rounded-lg hover:bg-yellow-400 transition"
          >
            Passer au pack Business Premium
          </button>
        </div>
      )}
    </div>
  );
}