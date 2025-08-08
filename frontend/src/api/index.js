// src/api/index.js
import axios from "./axios";

export function generateIdea(profil) {
  return axios.post("/generate", profil).then((r) => r.data);
}

// Premium
export function generateOffer(profil) {
  return axios.post("/premium/offer", profil).then((r) => r.data);
}