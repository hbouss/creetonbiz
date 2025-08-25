// src/components/Loader.jsx
import React from "react";

export default function Loader({ text = "Génération en cours…" }) {
  return (
    <div className="fixed inset-0 z-[9999] bg-black/60 backdrop-blur-sm">
      <div
        className="absolute inset-0 flex items-center justify-center"
        /* safe-area iOS pour éviter que ça colle en haut */
        style={{
          paddingTop: "env(safe-area-inset-top)",
          paddingBottom: "env(safe-area-inset-bottom)",
          paddingLeft: "env(safe-area-inset-left)",
          paddingRight: "env(safe-area-inset-right)",
        }}
      >
        <div className="bg-gray-800/85 rounded-2xl p-6 shadow-xl text-center">
          <div className="mx-auto mb-3 h-12 w-12 border-4 border-white/20 border-t-white rounded-full animate-spin" />
          <p className="text-sm text-gray-100">{text}</p>
        </div>
      </div>
    </div>
  );
}