"use client";

import { use, useState, useEffect } from "react";
import { useSession } from "@/lib/auth-client";
import { useRouter } from "next/navigation";
import styles from "./case.module.css";

interface ReferenceItem {
  section: string;
  page: number;
  line_start: number;
  line_end: number;
}

interface FindingItem {
  status: "COMPLIANT" | "NON_COMPLIANT" | "WARNING";
  title: string;
  description: string;
  references: ReferenceItem[];
  suggestion: string;
  relevant_forms: string[];
}

interface ReportData {
  compliance_score: number;
  summary: string;
  overall_status: string;
  required_forms: string[];
  items: FindingItem[];
}

interface CaseDetails {
  id: string;
  title: string;
  description: string;
  status: string;
  createdAt: string;
  analyses?: {
    id: string;
    status: string;
    complianceScore: number | null;
    report: ReportData | null;
    requiredForms: string[];
  }[];
}

function statusIcon(status: string) {
  const norm = status?.toUpperCase();
  if (norm === "COMPLIANT") return "✅";
  if (norm === "NON_COMPLIANT") return "❌";
  return "⚠️";
}

function statusLabel(status: string) {
  const norm = status?.toUpperCase();
  if (norm === "COMPLIANT") return "Compliant";
  if (norm === "NON_COMPLIANT") return "Non-Compliant";
  if (norm === "NEEDS_REVIEW") return "Needs Review";
  return "Warning";
}

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, isPending: sessionPending } = useSession();
  const router = useRouter();
  const [caseData, setCaseData] = useState<CaseDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Session authentication check
  useEffect(() => {
    if (!sessionPending && !session) {
      router.push("/sign-in");
    }
  }, [session, sessionPending, router]);

  // Initial fetch of case details
  useEffect(() => {
    if (session) {
      fetch(`/api/cases/${id}`)
        .then((res) => res.json())
        .then((data) => {
          if (data.error) {
            setError(data.error);
          } else {
            setCaseData(data.case);
          }
        })
        .catch((err) => {
          console.error("Error loading case:", err);
          setError("Failed to fetch case data.");
        })
        .finally(() => setLoading(false));
    }
  }, [id, session]);

  // Polling for in-progress analysis
  useEffect(() => {
    let intervalId: NodeJS.Timeout;
    const isAnalyzing = caseData && (caseData.status === "analyzing" || caseData.status === "pending" || caseData.status === "processing");
    
    if (session && isAnalyzing) {
      intervalId = setInterval(() => {
        fetch(`/api/cases/${id}`)
          .then((res) => res.json())
          .then((data) => {
            if (data.case) {
              setCaseData(data.case);
              if (data.case.status === "completed" || data.case.status === "failed") {
                clearInterval(intervalId);
              }
            }
          })
          .catch((err) => console.error("Error polling case status:", err));
      }, 3000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [id, session, caseData]);

  if (sessionPending || (loading && !caseData)) {
    return (
      <div className={styles.casePage} style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center", padding: "4rem 0" }}>
          <div style={{ width: "16px", height: "16px", background: "var(--status-warning)", borderRadius: "50%", margin: "0 auto 1rem", animation: "pulse 1.5s ease-in-out infinite" }} />
          <p style={{ color: "var(--text-secondary)" }}>Retrieving Analysis Details...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.casePage}>
        <header className={styles.caseHeader}>
          <a href="/dashboard" className={styles.backLink}>← Back to Dashboard</a>
          <h1 className={styles.caseTitle} style={{ color: "var(--status-error)" }}>Case Not Available</h1>
        </header>
        <div style={{ padding: "2rem", background: "var(--glass-bg)", borderRadius: "16px", border: "1px solid var(--border-primary)", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)" }}>{error}</p>
        </div>
      </div>
    );
  }

  if (!caseData) return null;

  // Analysis in-progress state screen
  const isRunning = caseData.status === "analyzing" || caseData.status === "pending" || caseData.status === "processing";
  if (isRunning) {
    return (
      <div className={styles.casePage}>
        <header className={styles.caseHeader}>
          <a href="/dashboard" className={styles.backLink}>← Dashboard</a>
          <h1 className={styles.caseTitle}>{caseData.title}</h1>
        </header>
        <div style={{ padding: "4rem 2rem", background: "var(--glass-bg)", borderRadius: "16px", border: "1px solid var(--border-primary)", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1.5rem", animation: "spin 3s linear infinite" }}>⚖️</div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: "700", color: "var(--text-primary)", marginBottom: "0.5rem" }}>
            Compliance Analysis in Progress
          </h2>
          <p style={{ color: "var(--text-secondary)", maxWidth: "450px", fontSize: "0.938rem", marginBottom: "1.5rem", lineHeight: "1.5" }}>
            Cross-referencing this document against 470 sections of the Companies Act, 2013. The report will display automatically when complete.
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--status-warning)", fontSize: "0.875rem", fontWeight: "600" }}>
            <span style={{ width: "8px", height: "8px", background: "var(--status-warning)", borderRadius: "50%", display: "inline-block", animation: "pulse 1.5s ease-in-out infinite" }} />
            <span>Analyzing clauses...</span>
          </div>
        </div>
      </div>
    );
  }

  // Analysis failed state screen
  if (caseData.status === "failed") {
    return (
      <div className={styles.casePage}>
        <header className={styles.caseHeader}>
          <a href="/dashboard" className={styles.backLink}>← Dashboard</a>
          <h1 className={styles.caseTitle}>{caseData.title}</h1>
        </header>
        <div style={{ padding: "3rem 2rem", background: "var(--glass-bg)", borderRadius: "16px", border: "1px solid var(--border-primary)", textAlign: "center" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>⚠️</div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: "700", color: "var(--status-error)", marginBottom: "0.5rem" }}>
            Compliance Check Failed
          </h2>
          <p style={{ color: "var(--text-secondary)", maxWidth: "420px", margin: "0 auto 1.5rem", fontSize: "0.938rem", lineHeight: "1.5" }}>
            We encountered an unexpected error processing this document. Please ensure it contains readable text and try analyzing it again.
          </p>
          <a href="/analyze" className={styles.actionBtn}>Try Again</a>
        </div>
      </div>
    );
  }

  const latestAnalysis = caseData.analyses?.[0];
  const report = latestAnalysis?.report;

  if (!report) {
    return (
      <div className={styles.casePage}>
        <header className={styles.caseHeader}>
          <a href="/dashboard" className={styles.backLink}>← Dashboard</a>
          <h1 className={styles.caseTitle}>{caseData.title}</h1>
        </header>
        <div style={{ padding: "3rem 2rem", background: "var(--glass-bg)", borderRadius: "16px", border: "1px solid var(--border-primary)", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)" }}>No report data has been generated yet for this case.</p>
        </div>
      </div>
    );
  }

  const compliant = report.items.filter((i) => i.status?.toUpperCase() === "COMPLIANT").length;
  const nonCompliant = report.items.filter((i) => i.status?.toUpperCase() === "NON_COMPLIANT").length;
  const warnings = report.items.filter((i) => {
    const s = i.status?.toUpperCase();
    return s === "WARNING" || s === "NEEDS_REVIEW";
  }).length;

  const displayDate = new Date(caseData.createdAt).toLocaleDateString("en-IN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <div className={styles.casePage}>
      {/* Header */}
      <header className={styles.caseHeader}>
        <a href="/dashboard" className={styles.backLink} id="back-to-dashboard">
          ← Dashboard
        </a>
        <h1 className={styles.caseTitle}>{caseData.title}</h1>
        <div className={styles.caseMeta}>
          <span className={styles.caseDate}>📅 {displayDate}</span>
          <span className={styles.caseId}>ID: {caseData.id}</span>
        </div>
      </header>

      {/* Score + Summary */}
      <section className={styles.summarySection}>
        <div className={styles.scoreBlock}>
          <div className={styles.scoreRingLarge}>
            <svg viewBox="0 0 140 140" className={styles.scoreSvg}>
              <circle cx="70" cy="70" r="58" fill="none" stroke="var(--border-primary)" strokeWidth="12" />
              <circle
                cx="70" cy="70" r="58" fill="none"
                stroke={report.compliance_score >= 80 ? "var(--status-success)" : report.compliance_score >= 50 ? "var(--status-warning)" : "var(--status-error)"}
                strokeWidth="12" strokeLinecap="round"
                strokeDasharray={`${(report.compliance_score / 100) * 364} 364`}
                transform="rotate(-90 70 70)"
              />
            </svg>
            <span className={styles.scoreNumber}>{Math.round(report.compliance_score)}%</span>
          </div>

          <div className={styles.statCounts}>
            <div className={styles.miniStat}>
              <span className={styles.miniStatIcon}>✅</span>
              <span className={styles.miniStatVal}>{compliant}</span>
              <span className={styles.miniStatLabel}>Compliant</span>
            </div>
            <div className={styles.miniStat}>
              <span className={styles.miniStatIcon}>❌</span>
              <span className={styles.miniStatVal}>{nonCompliant}</span>
              <span className={styles.miniStatLabel}>Issues</span>
            </div>
            <div className={styles.miniStat}>
              <span className={styles.miniStatIcon}>⚠️</span>
              <span className={styles.miniStatVal}>{warnings}</span>
              <span className={styles.miniStatLabel}>Warnings</span>
            </div>
          </div>
        </div>

        <div className={styles.summaryText}>
          <h2 className={styles.summaryTitle}>Analysis Summary</h2>
          <p className={styles.summaryBody}>{report.summary}</p>
        </div>
      </section>

      {/* Required Forms */}
      {report.required_forms && report.required_forms.length > 0 && (
        <section className={styles.formsSection}>
          <h2 className={styles.sectionHeading}>📋 Required MCA Forms</h2>
          <div className={styles.formsGrid}>
            {report.required_forms.map((form) => (
              <div key={form} className={styles.formCard}>
                <span className={styles.formName}>{form}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Findings */}
      <section className={styles.findingsSection}>
        <h2 className={styles.sectionHeading}>📝 Detailed Findings</h2>
        <div className={styles.findingsList}>
          {report.items.map((item, idx) => (
            <article
              key={idx}
              className={`${styles.finding} ${
                item.status?.toUpperCase() === "COMPLIANT" ? styles.findingCompliant :
                item.status?.toUpperCase() === "NON_COMPLIANT" ? styles.findingNonCompliant :
                styles.findingWarning
              }`}
              id={`finding-${idx}`}
            >
              <div className={styles.findingHeader}>
                <span className={styles.findingIcon}>{statusIcon(item.status)}</span>
                <div className={styles.findingTitleBlock}>
                  <h3 className={styles.findingTitle}>{item.title}</h3>
                  <span className={`${styles.findingBadge} ${
                    item.status?.toUpperCase() === "COMPLIANT" ? styles.badgeGreen :
                    item.status?.toUpperCase() === "NON_COMPLIANT" ? styles.badgeRed :
                    styles.badgeYellow
                  }`}>
                    {statusLabel(item.status)}
                  </span>
                </div>
              </div>

              <p className={styles.findingDesc}>{item.description}</p>

              {/* References */}
              {item.references && item.references.length > 0 && (
                <div className={styles.refsBlock}>
                  <span className={styles.refsLabel}>📖 References:</span>
                  <div className={styles.refsList}>
                    {item.references.map((ref, ri) => (
                      <code key={ri} className={styles.refCode}>
                        {ref.section} · Page {ref.page} · Lines {ref.line_start}–{ref.line_end}
                      </code>
                    ))}
                  </div>
                </div>
              )}

              {/* Suggestion */}
              {item.suggestion && (
                <div className={styles.suggestionBlock}>
                  <span className={styles.suggestionIcon}>🔧</span>
                  <div>
                    <span className={styles.suggestionLabel}>Recommended Action</span>
                    <p className={styles.suggestionText}>{item.suggestion}</p>
                  </div>
                </div>
              )}

              {/* Relevant Forms */}
              {item.relevant_forms && item.relevant_forms.length > 0 && (
                <div className={styles.findingForms}>
                  {item.relevant_forms.map((f) => (
                    <span key={f} className={styles.findingFormTag}>{f}</span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      </section>

      {/* Actions */}
      <section className={styles.actionsSection}>
        <a href={`/chat?caseId=${caseData.id}`} className={styles.actionBtn} id="ask-followup">
          💬 Ask Follow-up Questions
        </a>
        <a href="/analyze" className={styles.actionBtnSecondary} id="new-analysis-case">
          + New Analysis
        </a>
      </section>
    </div>
  );
}
