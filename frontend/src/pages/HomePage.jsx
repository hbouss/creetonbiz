// src/pages/HomePage.jsx
import React, { useState, useEffect, useContext } from "react";
import { useNavigate } from "react-router-dom";
import { generateIdea, createCheckoutSession } from "../api";
import IdeaForm from "../components/IdeaForm";
import Loader from "../components/Loader";
import Result from "../components/Result";
import OffersModal from "../components/OffersModal.jsx";
import { loadStripe } from "@stripe/stripe-js";
import { AuthContext } from "../contexts/AuthContext";

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY);

export default function HomePage() {
  const [step, setStep] = useState("home");
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [showOffers, setShowOffers] = useState(false);

  const { user } = useContext(AuthContext);
  const navigate = useNavigate();

  // 🔒 Empêche le scroll derrière l'overlay pendant le chargement (UX mobile)
  useEffect(() => {
    if (step === "loading") {
      const prevOverflow = document.body.style.overflow;
      const prevDocHeight = document.documentElement.style.height;
      document.body.style.overflow = "hidden";
      document.documentElement.style.height = "100dvh";
      return () => {
        document.body.style.overflow = prevOverflow;
        document.documentElement.style.height = prevDocHeight;
      };
    }
  }, [step]);

  // Ouvre le popup si l’utilisateur est sur un plan free
  useEffect(() => {
    if (user?.plan === "free") setShowOffers(true);
  }, [user]);

  const handleGenerate = async (profil) => {
    setError(null);
    setStep("loading");
    try {
      const data = await generateIdea(profil);
      setResult(data);
      setStep("result");
    } catch (e) {
      const msg = String(e?.message || "");
      // 402 = quota free atteint → ouvrir le popup
      if (msg.includes("Erreur 402") || msg.includes("FREE_LIMIT_REACHED")) {
        setShowOffers(true);
        setStep("home");
        return;
      }
      // 401 = non authentifié → login
      if (msg.includes("Erreur 401") || msg.toLowerCase().includes("unauthorized")) {
        navigate("/login");
        return;
      }
      setError(e.response?.data?.detail || e.message);
      setStep("home");
    }
  };

  async function buyInfinity() {
    const { sessionId } = await createCheckoutSession("infinity");
    const stripe = await stripePromise;
    await stripe.redirectToCheckout({ sessionId });
  }
  async function buyStartNow() {
    const { sessionId } = await createCheckoutSession("startnow");
    const stripe = await stripePromise;
    await stripe.redirectToCheckout({ sessionId });
  }

  return (
    <div className="min-h-[100dvh] bg-gray-900 text-gray-100 flex flex-col">
      {step === "home" && <IdeaForm onSubmit={handleGenerate} error={error} />}

      {step === "loading" && <Loader />}

      {step === "result" && result && (
        <div className="flex-1 mx-auto max-w-screen-sm px-4 py-6 space-y-6 text-center">
          <Result data={result} onReset={() => setStep("home")} />
          <button
            onClick={() => navigate("/premium", { state: { idea: result } })}
            className="px-6 py-3 bg-yellow-500 text-gray-900 rounded-lg hover:bg-yellow-400 transition"
          >
            Passer au pack Business Premium
          </button>
        </div>
      )}

      {/* ⬇️ Popup d’offres */}
      <OffersModal
        open={showOffers}
        onClose={() => setShowOffers(false)}
        onBuyInfinity={buyInfinity}
        onBuyStartNow={buyStartNow}
      />
    </div>
  );
}