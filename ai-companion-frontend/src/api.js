import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("companion_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const getUserProfile = () => api.get("/users/me");
export const updateUserProfile = (data) => api.patch("/users/me", data);
export const sendVerificationCode = (channel) => api.post("/users/me/verify/send", { channel });
export const verifyCode = (channel, code) => api.post("/users/me/verify", { channel, code });

export default api;
