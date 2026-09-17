import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getUserProfile, updateUserProfile, sendVerificationCode, verifyCode } from "./api";
import { User, Phone, Clock, ArrowLeft, Loader2, Mail, CheckCircle2, AlertCircle } from "lucide-react";

export default function Settings() {
  const [profile, setProfile] = useState(null);
  const [formData, setFormData] = useState({
    first_name: "",
    last_name: "",
    whatsapp_number: "",
    timezone: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  
  // Verification State
  const [verifyModal, setVerifyModal] = useState({ open: false, channel: "" });
  const [otpCode, setOtpCode] = useState("");
  const [verifyLoading, setVerifyLoading] = useState(false);
  
  const navigate = useNavigate();

  useEffect(() => {
    if (!localStorage.getItem("companion_token")) {
      navigate("/login");
      return;
    }
    loadProfile();
  }, [navigate]);

  const loadProfile = async () => {
    try {
      setLoading(true);
      const res = await getUserProfile();
      setProfile(res.data);
      setFormData({
        first_name: res.data.first_name || "",
        last_name: res.data.last_name || "",
        whatsapp_number: res.data.whatsapp_number || "",
        timezone: res.data.timezone || "",
      });
    } catch (err) {
      setError("Failed to load profile data.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await updateUserProfile(formData);
      setSuccess("Profile updated successfully!");
      await loadProfile(); // reload to get updated verified states if number changed
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join(", "));
      } else {
        setError(detail || "Failed to update profile.");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };
  
  const handleSendCode = async (channel) => {
    try {
      setError("");
      setSuccess("");
      await sendVerificationCode(channel);
      setVerifyModal({ open: true, channel });
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to send ${channel} verification code`);
    }
  };
  
  const handleVerifyCode = async () => {
    try {
      setVerifyLoading(true);
      setError("");
      await verifyCode(verifyModal.channel, otpCode);
      setSuccess(`${verifyModal.channel} successfully verified!`);
      setVerifyModal({ open: false, channel: "" });
      setOtpCode("");
      await loadProfile();
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid or expired code");
    } finally {
      setVerifyLoading(false);
    }
  };

  if (loading && !profile) {
    return (
      <div className="flex items-center justify-center w-full min-h-screen">
        <Loader2 className="w-8 h-8 text-[var(--accent-amber)] animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center w-full min-h-screen p-4 relative">
      {/* Verify Modal */}
      {verifyModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-panel max-w-sm w-full p-6 rounded-2xl animate-enter">
            <h3 className="text-lg font-semibold mb-2">Verify {verifyModal.channel}</h3>
            <p className="text-sm text-[var(--text-muted)] mb-4">
              Enter the 6-digit code we just sent to your {verifyModal.channel.toLowerCase()}.
            </p>
            <input
              type="text"
              placeholder="000000"
              value={otpCode}
              onChange={(e) => setOtpCode(e.target.value)}
              className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 px-4 outline-none focus:border-[var(--accent-amber)] text-center tracking-[0.5em] font-mono text-xl mb-4"
              maxLength={6}
            />
            <div className="flex gap-3">
              <button
                onClick={() => setVerifyModal({ open: false, channel: "" })}
                className="flex-1 py-2.5 rounded-xl font-medium text-[var(--text-primary)] border border-[var(--border-subtle)] hover:bg-[var(--bg-surface)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleVerifyCode}
                disabled={verifyLoading || otpCode.length !== 6}
                className="flex-1 py-2.5 rounded-xl font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center"
              >
                {verifyLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="glass-panel max-w-md w-full p-8 rounded-[1.5rem] animate-enter relative">
        <button
          onClick={() => navigate("/chat")}
          className="absolute top-8 left-8 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-2"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>

        <div className="text-center mb-8 mt-2">
          <h1 className="heading-premium">Settings</h1>
          <p className="text-muted mt-2">Manage your profile and verifications.</p>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg mb-6 text-sm">
            {error}
          </div>
        )}

        {success && (
          <div className="bg-green-500/10 border border-green-500/20 text-green-400 p-3 rounded-lg mb-6 text-sm">
            {success}
          </div>
        )}

        {/* Verification Status */}
        {profile && (
          <div className="flex flex-col gap-3 mb-6 p-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Mail className="w-4 h-4 text-[var(--text-muted)]" />
                <span className="text-sm font-medium">Email</span>
              </div>
              {profile.email_verified ? (
                <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Verified
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => handleSendCode("EMAIL")}
                  className="flex items-center gap-1.5 text-xs font-medium text-[var(--accent-amber)] hover:text-white transition-colors"
                >
                  <AlertCircle className="w-3.5 h-3.5" /> Verify Now
                </button>
              )}
            </div>
            
            <div className="flex items-center justify-between pt-3 border-t border-[var(--border-subtle)]">
              <div className="flex items-center gap-2">
                <Phone className="w-4 h-4 text-[var(--text-muted)]" />
                <span className="text-sm font-medium">WhatsApp</span>
              </div>
              {profile.whatsapp_verified ? (
                <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Verified
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => handleSendCode("WHATSAPP")}
                  className="flex items-center gap-1.5 text-xs font-medium text-[var(--accent-amber)] hover:text-white transition-colors"
                >
                  <AlertCircle className="w-3.5 h-3.5" /> Verify Now
                </button>
              )}
            </div>
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
            <Clock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text-muted)]" />
            <input
              required
              type="text"
              name="timezone"
              placeholder="Timezone (e.g. Asia/Karachi)"
              value={formData.timezone}
              onChange={handleChange}
              className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 pl-10 pr-4 outline-none focus:border-[var(--accent-amber)] transition-colors text-[var(--text-primary)]"
            />
            <p className="text-xs text-[var(--text-muted)] mt-1.5 ml-2">Must be a valid IANA timezone (e.g., America/New_York)</p>
          </div>

          <button
            type="submit"
            disabled={saving}
            className="w-full py-3.5 mt-4 rounded-xl font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </form>
      </div>
    </div>
  );
}
