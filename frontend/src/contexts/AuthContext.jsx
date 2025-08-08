import React, { createContext, useEffect, useState, useMemo } from "react";
import { getMe } from "../api";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // Lis/écris la même clé que dans api.js
  const [token, setToken] = useState(() => localStorage.getItem("auth_token"));
  const [user, setUser] = useState(null); // { id, email, plan }

  // Quand le token change : persiste + (re)charge le profil
  useEffect(() => {
    if (token) {
      localStorage.setItem("auth_token", token);
      refreshMe(); // récupère {id,email,plan} via /api/me
    } else {
      localStorage.removeItem("auth_token");
      setUser(null);
    }
  }, [token]);

  // Récupère l'utilisateur depuis l'API
  async function refreshMe() {
    try {
      const me = await getMe();
      setUser(me);
    } catch {
      // 401 etc. → on invalide le profil mais on ne casse pas la session tout de suite
      setUser(null);
    }
  }

  // Connexion / Déconnexion
  function login(newToken) {
    setToken(newToken);
  }
  function logout() {
    setToken(null);
  }

  const value = useMemo(
    () => ({ token, user, login, logout, refreshMe }),
    [token, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}