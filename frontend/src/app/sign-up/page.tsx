"use client";

import { useState } from "react";
import { signUp } from "@/lib/auth-client";
import styles from "../sign-in/auth.module.css";

export default function SignUpPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [firm, setFirm] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setLoading(true);
    try {
      const result = await signUp.email({
        email,
        password,
        name,
      });
      if (result.error) {
        setError(result.error.message || "Sign up failed");
      } else {
        window.location.href = "/dashboard";
      }
    } catch {
      setError("An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.authContainer}>
      <div className={styles.authCard}>
        <div className={styles.authHeader}>
          <span className={styles.authLogo} aria-hidden="true">⚖️</span>
          <h1 className={styles.authTitle}>Create Your Account</h1>
          <p className={styles.authSubtitle}>
            Start analyzing documents against the Companies Act 2013
          </p>
        </div>

        <form onSubmit={handleSubmit} className={styles.authForm}>
          {error && (
            <div className={styles.errorBanner} role="alert">
              {error}
            </div>
          )}

          <div className={styles.inputGroup}>
            <label htmlFor="signup-name" className={styles.inputLabel}>
              Full Name
            </label>
            <input
              id="signup-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={styles.input}
              placeholder="Priya Sharma"
              required
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="signup-email" className={styles.inputLabel}>
              Email Address
            </label>
            <input
              id="signup-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={styles.input}
              placeholder="you@yourfirm.com"
              required
              autoComplete="email"
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="signup-firm" className={styles.inputLabel}>
              Firm Name <span className={styles.optional}>(Optional)</span>
            </label>
            <input
              id="signup-firm"
              type="text"
              value={firm}
              onChange={(e) => setFirm(e.target.value)}
              className={styles.input}
              placeholder="Sharma & Associates"
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="signup-password" className={styles.inputLabel}>
              Password
            </label>
            <input
              id="signup-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={styles.input}
              placeholder="Min. 8 characters"
              required
              minLength={8}
              autoComplete="new-password"
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="signup-confirm" className={styles.inputLabel}>
              Confirm Password
            </label>
            <input
              id="signup-confirm"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={styles.input}
              placeholder="••••••••"
              required
              autoComplete="new-password"
            />
          </div>

          <button
            type="submit"
            className={styles.submitBtn}
            id="signup-submit"
            disabled={loading}
          >
            {loading ? (
              <span className={styles.spinner} aria-hidden="true" />
            ) : null}
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <div className={styles.authFooter}>
          <p>
            Already have an account?{" "}
            <a href="/sign-in" className={styles.authLink} id="signup-to-signin">
              Sign in
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
