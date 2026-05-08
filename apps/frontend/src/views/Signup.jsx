import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../auth";
import { AuthLayout } from "./AuthLayout";

export function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await signup(email, password, displayName);
      navigate("/", { replace: true });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail === "email_already_registered") {
        setError("That email is already registered. Try signing in instead.");
      } else {
        setError("Signup failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      eyebrow="Get started"
      title="Create your account"
      subtitle="Connect a repository and let Aura's agents build the documentation."
      footerSwitch={
        <>
          Already using Aura? <Link to="/login">Sign in</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="auth-form" noValidate>
        <div className="auth-field">
          <span className="auth-field-label">
            Display name
            <span className="auth-field-hint">Optional</span>
          </span>
          <input
            type="text"
            placeholder="Ada Lovelace"
            maxLength={255}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            autoFocus
          />
        </div>

        <div className="auth-field">
          <span className="auth-field-label">Work email</span>
          <input
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="auth-field">
          <span className="auth-field-label">
            Password
            <span className="auth-field-hint">8+ characters</span>
          </span>
          <input
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && <div className="auth-error">{error}</div>}

        <button className="primary auth-submit" type="submit" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </button>

        <p className="muted" style={{ fontSize: 12, textAlign: "center", margin: "10px 0 0" }}>
          By signing up, you agree to Aura's <a href="#" onClick={(e) => e.preventDefault()}>Terms</a> and{" "}
          <a href="#" onClick={(e) => e.preventDefault()}>Privacy Policy</a>.
        </p>
      </form>
    </AuthLayout>
  );
}
