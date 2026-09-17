import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getUserProfile, sendVerificationCode, verifyCode } from "./api";
import { Loader2, Mail, Phone, ArrowRight, CheckCircle2 } from "lucide-react";

export default function Onboarding() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(1); // 1 = Email, 2 = WhatsApp
  
  const [otpCode, setOtpCode] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  
  const navigate = useNavigate();

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      setLoading(true);
      const res = await getUserProfile();
      setProfile(res.data);
      
      // Auto-advance logic
      if (res.data.email_verified && res.data.whatsapp_verified) {
        navigate("/chat");
      } else if (res.data.email_verified) {
        setStep(2);
      }
    } catch (err) {
      setError("Failed to load profile.");
    } finally {
      setLoading(false);
    }
  };

  const handleSendCode = async (channel) => {
    try {
      setActionLoading(true);
      setError("");
      setSuccess("");
      await sendVerificationCode(channel);
      setCodeSent(true);
      setSuccess(`Verification code sent to your ${channel.toLowerCase()}!`);
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to send ${channel} code`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleVerifyCode = async (channel) => {
    try {
      setActionLoading(true);
      setError("");
      await verifyCode(channel, otpCode);
      setSuccess(`${channel} verified successfully!`);
      setOtpCode("");
      setCodeSent(false);
      
      const res = await getUserProfile();
      setProfile(res.data);
      
      if (channel === "EMAIL") {
        setStep(2);
        setSuccess("");
      } else if (channel === "WHATSAPP") {
        navigate("/chat");
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid or expired code");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading || !profile) {
    return (
      <div className="flex items-center justify-center w-full min-h-screen">
        <Loader2 className="w-8 h-8 text-[var(--accent-amber)] animate-spin" />
      </div>
    );
  }

  const renderEmailStep = () => (
    <div className="animate-enter">
      <div className="flex items-center justify-center w-12 h-12 rounded-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] mx-auto mb-4">
        <Mail className="w-6 h-6 text-[var(--accent-amber)]" />
      </div>
      <h2 className="text-xl font-semibold text-center mb-2">Verify Email</h2>
      <p className="text-center text-[var(--text-muted)] text-sm mb-6">
        We need to verify {profile.email} to send you important updates.
      </p>
      
      {!codeSent ? (
        <button
          onClick={() => handleSendCode("EMAIL")}
          disabled={actionLoading}
          className="w-full py-3.5 rounded-xl font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50 flex justify-center items-center"
        >
          {actionLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "Send Code"}
        </button>
      ) : (
        <div className="space-y-4">
          <input
            type="text"
            placeholder="000000"
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value)}
            className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 px-4 outline-none focus:border-[var(--accent-amber)] text-center tracking-[0.5em] font-mono text-xl"
            maxLength={6}
          />
          <button
            onClick={() => handleVerifyCode("EMAIL")}
            disabled={actionLoading || otpCode.length !== 6}
            className="w-full py-3.5 rounded-xl font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50 flex justify-center items-center"
          >
            {actionLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "Verify"}
          </button>
        </div>
      )}
    </div>
  );

  const renderWhatsAppStep = () => (
    <div className="animate-enter">
      <div className="flex items-center justify-center w-12 h-12 rounded-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] mx-auto mb-4">
        <Phone className="w-6 h-6 text-[var(--accent-amber)]" />
      </div>
      <h2 className="text-xl font-semibold text-center mb-2">Verify WhatsApp</h2>
      <p className="text-center text-[var(--text-muted)] text-sm mb-6">
        Let's connect your WhatsApp number: {profile.whatsapp_number}.
      </p>
      
      <div className="bg-[var(--bg-surface)] border border-[var(--border-subtle)] p-4 rounded-xl mb-6 text-sm">
        <ol className="list-decimal list-inside space-y-2 text-[var(--text-primary)]">
          <li>Send <strong>"hello"</strong> to our WhatsApp bot.</li>
          <li>Click the <strong>Send Code</strong> button below.</li>
          <li>Enter the 6-digit code you receive.</li>
        </ol>
      </div>

      {!codeSent ? (
        <button
          onClick={() => handleSendCode("WHATSAPP")}
          disabled={actionLoading}
          className="w-full py-3.5 rounded-xl font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50 flex justify-center items-center"
        >
          {actionLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "Send Code"}
        </button>
      ) : (
        <div className="space-y-4">
          <input
            type="text"
            placeholder="000000"
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value)}
            className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-xl py-3 px-4 outline-none focus:border-[var(--accent-amber)] text-center tracking-[0.5em] font-mono text-xl"
            maxLength={6}
          />
          <button
            onClick={() => handleVerifyCode("WHATSAPP")}
            disabled={actionLoading || otpCode.length !== 6}
            className="w-full py-3.5 rounded-xl font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50 flex justify-center items-center"
          >
            {actionLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "Verify"}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col items-center justify-center w-full min-h-screen p-4">
      <div className="text-center mb-8">
        <h1 className="heading-premium text-3xl">Secure your account</h1>
        <p className="text-[var(--text-muted)] mt-2">Just two quick steps before we begin.</p>
      </div>
      
      <div className="glass-panel max-w-md w-full p-8 rounded-[1.5rem] relative">
        <div className="flex items-center justify-between mb-8 px-4 relative">
          <div className="absolute top-1/2 left-8 right-8 h-0.5 bg-[var(--border-subtle)] -z-10 -translate-y-1/2"></div>
          
          {/* Step 1 indicator */}
          <div className={`flex flex-col items-center gap-2 bg-transparent ${step >= 1 ? "text-[var(--accent-amber)]" : "text-[var(--text-muted)]"}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${step > 1 ? "bg-[var(--accent-amber)] text-black" : step === 1 ? "bg-[var(--bg-surface)] border-2 border-[var(--accent-amber)]" : "bg-[var(--bg-surface)] border border-[var(--border-subtle)]"}`}>
              {step > 1 ? <CheckCircle2 className="w-5 h-5" /> : "1"}
            </div>
            <span className="text-xs font-medium bg-[var(--bg-background)] px-2">Email</span>
          </div>

          {/* Step 2 indicator */}
          <div className={`flex flex-col items-center gap-2 bg-transparent ${step >= 2 ? "text-[var(--accent-amber)]" : "text-[var(--text-muted)]"}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${step > 2 ? "bg-[var(--accent-amber)] text-black" : step === 2 ? "bg-[var(--bg-surface)] border-2 border-[var(--accent-amber)]" : "bg-[var(--bg-surface)] border border-[var(--border-subtle)]"}`}>
              {step > 2 ? <CheckCircle2 className="w-5 h-5" /> : "2"}
            </div>
            <span className="text-xs font-medium bg-[var(--bg-background)] px-2">WhatsApp</span>
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg mb-6 text-sm text-center">
            {error}
          </div>
        )}

        {success && (
          <div className="bg-green-500/10 border border-green-500/20 text-green-400 p-3 rounded-lg mb-6 text-sm text-center">
            {success}
          </div>
        )}

        {step === 1 && renderEmailStep()}
        {step === 2 && renderWhatsAppStep()}
      </div>
    </div>
  );
}
