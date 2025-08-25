// src/pages/HomePage.jsx
import React, { useState, useEffect } from "react";
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

  // 🔒 Empêche le scroll derrière l'overlay pendant le chargement (UX mobile)
  useEffect(() => {
    if (step === "loading") {
      const prevOverflow = document.body.style.overflow;
      const prevDocHeight = document.documentElement.style.height;

      document.body.style.overflow = "hidden";
      // corrige le bug 100vh sur iOS (barres d'adresse)
      document.documentElement.style.height = "100dvh";

      return () => {
        document.body.style.overflow = prevOverflow;
        document.documentElement.style.height = prevDocHeight;
      };
    }
  }, [step]);

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
    <div className="min-h-[100dvh] bg-gray-900 text-gray-100 flex flex-col">
      {step === "home" && <IdeaForm onSubmit={handleGenerate} error={error} />}

      {/* Overlay centré plein écran */}
      {step === "loading" && <Loader />}

      {step === "result" && result && (
        <div className="flex-1 mx-auto max-w-screen-sm px-4 py-6 space-y-6 text-center">
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