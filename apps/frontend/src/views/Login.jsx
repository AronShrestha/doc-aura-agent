import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth";
import { AuthLayout } from "./AuthLayout";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = location.state?.from?.pathname || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail === "invalid_credentials" ? "Invalid email or password." : "Login failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      eyebrow="Welcome back"
      title="Sign in to Aura"
      subtitle="Your agents are still watching your repositories."
      footerSwitch={
        <>
          New to Aura? <Link to="/signup">Create an account</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="auth-form" noValidate>
        <div className="auth-field">
          <span className="auth-field-label">Email</span>
          <input
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
          />
        </div>

        <div className="auth-field">
          <span className="auth-field-label">
            Password
            <a
              href="#"
              onClick={(e) => e.preventDefault()}
              className="auth-field-hint"
              style={{ color: "var(--ink-accent)" }}
            >
              Forgot?
            </a>
          </span>
          <input
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && <div className="auth-error">{error}</div>}

        <button className="primary auth-submit" type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthLayout>
  );
}
