import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "./api";
import { User, Mail, Phone, Lock } from "lucide-react";

export default function Register({ onLogin }) {
  const [formData, setFormData] = useState({
    first_name: "",
    last_name: "",
    email: "",
    whatsapp_number: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    tier: "PAID",
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
      await api.post("/users/", formData);
      const loginResponse = await api.post("/users/login", { email: formData.email, password: formData.password });
      onLogin(loginResponse.data.access_token);
      navigate("/onboarding");
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        // Extract Pydantic validation errors
        setError(detail.map(d => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join(", "));
      } else {
        setError(detail || "Registration failed");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  return (
    <div className="flex items-center justify-center w-full min-h-screen p-4">
      <div className="glass-panel max-w-md w-full p-8 rounded-[1.5rem] animate-enter">
        <div className="text-center mb-8">
          <h1 className="heading-premium">
            <span>Companion</span> AI
          </h1>
          <p className="text-muted mt-2">Initialize your personal companion.</p>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg mb-6 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex gap-4">
            <div className="flex-1 relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text-muted)]" />
              <input
                required
                name="first_name"
                placeholder="First Name"
                value={formData.first_name}
                onChange={handleChange}
                className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 pl-10 pr-4 outline-none focus:border-[var(--accent-amber)] transition-colors text-[var(--text-primary)]"
              />
            </div>
            <div className="flex-1 relative">
              <input
                required
                name="last_name"
                placeholder="Last Name"
                value={formData.last_name}
                onChange={handleChange}
                className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 px-4 outline-none focus:border-[var(--accent-amber)] transition-colors text-[var(--text-primary)]"
              />
            </div>
          </div>

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
            <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text-muted)]" />
            <input
              required
              type="tel"
              name="whatsapp_number"
              placeholder="WhatsApp Number (e.g. +92...)"
              value={formData.whatsapp_number}
              onChange={handleChange}
              className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 pl-10 pr-4 outline-none focus:border-[var(--accent-amber)] transition-colors text-[var(--text-primary)]"
            />
          </div>

          <div className="relative">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text-muted)]"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <input
              required
              type="text"
              name="timezone"
              placeholder="Timezone (e.g. Asia/Karachi)"
              value={formData.timezone}
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
              placeholder="Create Password"
              value={formData.password}
              onChange={handleChange}
              className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 pl-10 pr-4 outline-none focus:border-[var(--accent-amber)] transition-colors text-[var(--text-primary)]"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 mt-2 rounded-xl font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? "Initializing..." : "Upgrade to Premium Companion"}
          </button>

          <div className="text-center mt-6 text-sm text-[var(--text-muted)]">
            Already have a premium account?{" "}
            <Link
              to="/login"
              className="text-[var(--accent-amber)] hover:underline"
            >
              Log in
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
