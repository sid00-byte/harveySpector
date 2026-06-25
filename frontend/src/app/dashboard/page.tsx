"use client";

import { useState, useEffect } from "react";
import { useSession } from "@/lib/auth-client";
import { useRouter } from "next/navigation";
import styles from "./dashboard.module.css";

interface CaseAnalysis {
  id: string;
  complianceScore: number | null;
  requiredForms: string[];
  status: string;
}

interface CaseItem {
  id: string;
  title: string;
  status: string;
  tags: string[];
  createdAt: string;
  analyses?: CaseAnalysis[];
}

function getStatusBadge(status: string) {
  const map: Record<string, { label: string; className: string }> = {
    completed: { label: "Completed", className: styles.badgeCompleted },
    analyzing: { label: "Analyzing...", className: styles.badgeAnalyzing },
    processing: { label: "Analyzing...", className: styles.badgeAnalyzing },
    pending: { label: "Pending", className: styles.badgePending },
    failed: { label: "Failed", className: styles.badgePending },
  };
  return map[status] || map.pending;
}

function getScoreColor(score: number | null) {
  if (score === null) return "";
  if (score >= 80) return styles.scoreHigh;
  if (score >= 50) return styles.scoreMedium;
  return styles.scoreLow;
}

export default function DashboardPage() {
  const { data: session, isPending: sessionPending } = useSession();
  const router = useRouter();
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);

  // Enforce authentication redirect
  useEffect(() => {
    if (!sessionPending && !session) {
      router.push("/sign-in");
    }
  }, [session, sessionPending, router]);

  // Load cases from API
  useEffect(() => {
    if (session) {
      fetch("/api/cases")
        .then((res) => {
          if (res.status === 401) {
            router.push("/sign-in");
            return null;
          }
          return res.json();
        })
        .then((data) => {
          if (data && data.cases) {
            setCases(data.cases);
          }
        })
        .catch((err) => console.error("Error fetching cases:", err))
        .finally(() => setLoadingCases(false));
    }
  }, [session, router]);

  // Show general page loading if session or initial cases are pending
  if (sessionPending || (loadingCases && cases.length === 0)) {
    return (
      <div className={styles.dashboard} style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center", padding: "4rem 0" }}>
          <div className={styles.pulsingDot} style={{ width: "16px", height: "16px", margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-secondary)" }}>Loading Workspace...</p>
        </div>
      </div>
    );
  }

  // If no session after load, render nothing (effect will redirect)
  if (!session) {
    return null;
  }

  // Calculate dynamic stats
  const totalCases = cases.length;
  const completedCases = cases.filter((c) => c.status === "completed").length;
  const inProgressCases = cases.filter((c) => c.status === "analyzing" || c.status === "processing").length;

  const scoredCases = cases.filter((c) => {
    const latestAnalysis = c.analyses?.[0];
    return latestAnalysis && latestAnalysis.complianceScore !== null;
  });

  const avgCompliance = scoredCases.length > 0
    ? Math.round(
        scoredCases.reduce((sum, c) => sum + (c.analyses?.[0]?.complianceScore ?? 0), 0) / scoredCases.length
      )
    : 0;

  return (
    <div className={styles.dashboard}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div>
            <h1 className={styles.greeting}>Welcome back, {session.user.name || "Counsel"} 👋</h1>
            <p className={styles.subtitle}>
              Here&apos;s an overview of your compliance analyses
            </p>
          </div>
          <a
            href="/analyze"
            className={styles.newAnalysisBtn}
            id="dashboard-new-analysis"
          >
            <span aria-hidden="true">+</span> New Analysis
          </a>
        </div>
      </header>

      {/* Stats Row */}
      <section className={styles.statsRow} aria-label="Statistics">
        <div className={styles.statCard}>
          <div className={styles.statIcon}>📊</div>
          <div className={styles.statInfo}>
            <div className={styles.statNumber}>{totalCases}</div>
            <div className={styles.statLabel}>Total Cases</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>✅</div>
          <div className={styles.statInfo}>
            <div className={styles.statNumber}>{completedCases}</div>
            <div className={styles.statLabel}>Completed</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>🔍</div>
          <div className={styles.statInfo}>
            <div className={styles.statNumber}>{inProgressCases}</div>
            <div className={styles.statLabel}>In Progress</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>📈</div>
          <div className={styles.statInfo}>
            <div className={styles.statNumber}>{avgCompliance}%</div>
            <div className={styles.statLabel}>Avg. Compliance</div>
          </div>
        </div>
      </section>

      {/* Recent Cases */}
      <section className={styles.casesSection}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Recent Analyses</h2>
        </div>

        {cases.length === 0 ? (
          /* Premium Empty State */
          <div className={styles.emptyState}>
            <span className={styles.emptyStateIcon} aria-hidden="true">⚖️</span>
            <h3 className={styles.emptyStateTitle}>No Compliance Analyses Yet</h3>
            <p className={styles.emptyStateText}>
              Your dashboard is clean! Upload a corporate document or board resolution to analyze compliance against the Companies Act, 2013.
            </p>
            <a href="/analyze" className={styles.emptyStateBtn} id="empty-state-cta">
              Analyze Your First Document
            </a>
          </div>
        ) : (
          /* Case Card Grid */
          <div className={styles.casesGrid}>
            {cases.map((c) => {
              const badge = getStatusBadge(c.status);
              const latestAnalysis = c.analyses?.[0];
              const score = latestAnalysis && latestAnalysis.complianceScore !== null
                ? Math.round(latestAnalysis.complianceScore)
                : null;
              
              // Get forms from latest analysis or fallback to case tags
              const forms = latestAnalysis?.requiredForms?.length
                ? latestAnalysis.requiredForms
                : (c.tags || []);

              // Format date cleanly
              const displayDate = new Date(c.createdAt).toLocaleDateString("en-IN", {
                year: "numeric",
                month: "short",
                day: "numeric",
              });

              return (
                <article
                  key={c.id}
                  className={styles.caseCard}
                  id={`case-${c.id}`}
                >
                  <div className={styles.caseHeader}>
                    <h3 className={styles.caseTitle}>{c.title}</h3>
                    <span className={`${styles.badge} ${badge.className}`}>
                      {badge.label}
                    </span>
                  </div>

                  <div className={styles.caseBody}>
                    {score !== null ? (
                      <div className={styles.scoreContainer}>
                        <div className={styles.scoreCircle}>
                          <svg viewBox="0 0 100 100" className={styles.scoreSvg}>
                            <circle
                              cx="50"
                              cy="50"
                              r="42"
                              fill="none"
                              stroke="var(--border-primary)"
                              strokeWidth="8"
                            />
                            <circle
                              cx="50"
                              cy="50"
                              r="42"
                              fill="none"
                              className={getScoreColor(score)}
                              strokeWidth="8"
                              strokeLinecap="round"
                              strokeDasharray={`${(score / 100) * 264} 264`}
                              transform="rotate(-90 50 50)"
                            />
                          </svg>
                          <span className={styles.scoreValue}>{score}%</span>
                        </div>
                        <span className={styles.scoreLabel}>Compliance Score</span>
                      </div>
                    ) : c.status === "failed" ? (
                      <div className={styles.analyzingIndicator} style={{ color: "var(--status-error)" }}>
                        <span>⚠️ Incomplete or failed analysis</span>
                      </div>
                    ) : (
                      <div className={styles.analyzingIndicator}>
                        <span className={styles.pulsingDot} />
                        <span>Analyzing document...</span>
                      </div>
                    )}

                    {forms.length > 0 && (
                      <div className={styles.formsRow}>
                        <span className={styles.formsLabel}>Required Forms:</span>
                        <div className={styles.formsTags}>
                          {forms.map((form) => (
                            <span key={form} className={styles.formTag}>
                              {form}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className={styles.caseFooter}>
                    <span className={styles.caseDate}>{displayDate}</span>
                    <a
                      href={`/case/${c.id}`}
                      className={styles.viewBtn}
                      id={`view-case-${c.id}`}
                    >
                      View Report →
                    </a>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
