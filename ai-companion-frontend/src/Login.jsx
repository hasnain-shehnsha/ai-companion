import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "./api";
import { Mail, Lock } from "lucide-react";

export default function Login({ onLogin }) {
  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await api.post("/users/login", formData);
      onLogin(response.data.id);
      navigate("/chat");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  return (
    <div className="flex items-center justify-center w-full min-h-screen p-4 bg-[var(--bg-obsidian)]">
      <div className="glass-panel max-w-md w-full p-8 rounded-[1.5rem] animate-enter">
        <div className="text-center mb-8">
          <h1 className="heading-premium">
            <span>Companion</span> AI
          </h1>
          <p className="text-muted mt-2">Welcome back to your companion.</p>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg mb-6 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text-muted)]" />
            <input
              required
              type="email"
              name="email"
              placeholder="Email Address"
              value={formData.email}
              onChange={handleChange}
              className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 pl-10 pr-4 outline-none focus:border-[var(--accent-amber)] transition-colors text-[var(--text-primary)]"
            />
          </div>

          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text-muted)]" />
            <input
              required
              type="password"
              name="password"
              placeholder="Password"
              value={formData.password}
              onChange={handleChange}
              className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 pl-10 pr-4 outline-none focus:border-[var(--accent-amber)] transition-colors text-[var(--text-primary)]"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 mt-6 rounded-xl font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? "Authenticating..." : "Log In"}
          </button>

          <div className="text-center mt-6 text-sm text-[var(--text-muted)]">
            Don't have a premium account?{" "}
            <Link
              to="/register"
              className="text-[var(--accent-amber)] hover:underline"
            >
              Register here
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
