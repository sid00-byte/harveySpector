"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import styles from "./analyze.module.css";

type InputMode = "upload" | "text";
type AnalysisState = "idle" | "uploading" | "analyzing" | "complete" | "error";

interface ComplianceItem {
  status: "COMPLIANT" | "NON_COMPLIANT" | "WARNING";
  title: string;
  description: string;
  suggestion: string;
  references: { section: string; page: number; line_start: number; line_end: number }[];
  relevant_forms: string[];
}

interface AnalysisResult {
  compliance_score: number;
  summary: string;
  items: ComplianceItem[];
  required_forms: string[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AnalyzePage() {
  const router = useRouter();

  // Redirect to dashboard new audit flow
  useEffect(() => {
    router.replace("/dashboard?action=new");
  }, [router]);

  const [mode, setMode] = useState<InputMode>("upload");
  const [state, setState] = useState<AnalysisState>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [textInput, setTextInput] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(e.type === "dragenter" || e.type === "dragover");
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) setFile(droppedFile);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  };

  const handleAnalyze = async () => {
    setError("");
    setState("uploading");

    let createdCaseId: string | null = null;
    let createdDocId: string | null = null;

    try {
      // 1. Initialize case and document in database
      const caseRes = await fetch("/api/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: mode === "upload" && file ? file.name.replace(/\.[^/.]+$/, "") : `Text Snippet — ${new Date().toLocaleDateString("en-IN")}`,
          description: mode === "upload" && file ? `Analysis of uploaded file ${file.name}` : "Analysis of pasted text snippet",
          fileName: mode === "upload" && file ? file.name : "input.txt",
          fileType: mode === "upload" && file ? (file.name.endsWith(".pdf") ? "pdf" : file.name.endsWith(".docx") ? "docx" : "text") : "text",
          fileSizeBytes: mode === "upload" && file ? file.size : new Blob([textInput]).size,
        }),
      });

      if (caseRes.status === 401) {
        router.push("/sign-in");
        return;
      }
      if (!caseRes.ok) throw new Error("Could not initialize case in database");
      const caseData = await caseRes.json();
      createdCaseId = caseData.case.id;
      createdDocId = caseData.case.documents[0]?.id;

      // 2. Upload document to FastAPI backend
      let documentId: string;

      if (mode === "upload" && file) {
        const formData = new FormData();
        formData.append("file", file);
        const uploadRes = await fetch(`${API_URL}/api/v1/documents/upload`, {
          method: "POST",
          body: formData,
        });
        if (!uploadRes.ok) throw new Error("Upload failed");
        const uploadData = await uploadRes.json();
        documentId = uploadData.document_id;
      } else if (mode === "text" && textInput.trim()) {
        const blob = new Blob([textInput], { type: "text/plain" });
        const formData = new FormData();
        formData.append("file", blob, "input.txt");
        const uploadRes = await fetch(`${API_URL}/api/v1/documents/upload`, {
          method: "POST",
          body: formData,
        });
        if (!uploadRes.ok) throw new Error("Upload failed");
        const uploadData = await uploadRes.json();
        documentId = uploadData.document_id;
      } else {
        setError("Please provide a file or text to analyze");
        setState("idle");
        return;
      }

      // 3. Trigger compliance analysis on FastAPI backend
      setState("analyzing");
      const analysisRes = await fetch(`${API_URL}/api/v1/analyze/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: documentId }),
      });

      if (!analysisRes.ok) throw new Error("Analysis failed");
      const analysisData = await analysisRes.json();

      // 4. Save placeholder analysis record to DB with status = processing
      if (analysisData.status === "COMPLETED" || analysisData.status === "PROCESSING") {
        const saveAnalysisRes = await fetch(`/api/cases/${createdCaseId}/analysis`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            complianceScore: null,
            report: null,
            requiredForms: [],
            status: "processing",
            documentId: createdDocId,
            analysisId: analysisData.analysis_id,
          }),
        });

        if (saveAnalysisRes.status === 401) {
          router.push("/sign-in");
          return;
        }
        if (!saveAnalysisRes.ok) {
          console.error("Failed to persist analysis placeholder to DB");
        }

        // Redirect to the dynamic case detail report view immediately
        router.push(`/case/${createdCaseId}`);
        return;
      }

      throw new Error("Analysis failed to start");
    } catch (err) {
      if (createdCaseId) {
        // Record failure status in database
        await fetch(`/api/cases/${createdCaseId}/analysis`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            complianceScore: 0,
            report: {},
            requiredForms: [],
            status: "failed",
            documentId: createdDocId,
          }),
        }).catch((e) => console.error("Error setting failure status:", e));
      }

      setError(err instanceof Error ? err.message : "Analysis failed");
      setState("error");
    }
  };

  const resetAnalysis = () => {
    setState("idle");
    setFile(null);
    setTextInput("");
    setResult(null);
    setError("");
  };

  const statusIcon = (status: string) => {
    if (status === "COMPLIANT") return "✅";
    if (status === "NON_COMPLIANT") return "❌";
    return "⚠️";
  };

  return (
    <div className={styles.analyzePage}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Compliance Analysis</h1>
        <p className={styles.pageSubtitle}>
          Upload a document or paste text to analyze against the Companies Act, 2013
        </p>
      </header>

      {state === "idle" || state === "error" ? (
        <>
          {/* Mode Tabs */}
          <div className={styles.modeTabs} role="tablist">
            <button
              className={`${styles.modeTab} ${mode === "upload" ? styles.modeTabActive : ""}`}
              onClick={() => setMode("upload")}
              role="tab"
              aria-selected={mode === "upload"}
              id="tab-upload"
            >
              📄 Upload File
            </button>
            <button
              className={`${styles.modeTab} ${mode === "text" ? styles.modeTabActive : ""}`}
              onClick={() => setMode("text")}
              role="tab"
              aria-selected={mode === "text"}
              id="tab-text"
            >
              ✏️ Paste Text
            </button>
          </div>

          {/* Upload Area */}
          {mode === "upload" && (
            <div
              className={`${styles.dropZone} ${dragActive ? styles.dropZoneActive : ""} ${file ? styles.dropZoneHasFile : ""}`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              id="drop-zone"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc,.png,.jpg,.jpeg,.tiff,.tif,.txt"
                onChange={handleFileSelect}
                className={styles.fileInput}
                id="file-input"
              />
              {file ? (
                <div className={styles.filePreview}>
                  <span className={styles.fileIcon}>
                    {file.name.endsWith(".pdf") ? "📕" : file.name.endsWith(".docx") ? "📘" : "📄"}
                  </span>
                  <div className={styles.fileInfo}>
                    <span className={styles.fileName}>{file.name}</span>
                    <span className={styles.fileSize}>
                      {(file.size / 1024).toFixed(1)} KB
                    </span>
                  </div>
                  <button
                    className={styles.removeFile}
                    onClick={(e) => { e.stopPropagation(); setFile(null); }}
                    aria-label="Remove file"
                    id="remove-file"
                  >
                    ✕
                  </button>
                </div>
              ) : (
                <div className={styles.dropContent}>
                  <span className={styles.dropIcon} aria-hidden="true">⬆️</span>
                  <p className={styles.dropTitle}>
                    Drop your file here or <span className={styles.dropLink}>browse</span>
                  </p>
                  <p className={styles.dropFormats}>
                    PDF, DOCX, PNG, JPG, TIFF, TXT — Max 50MB
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Text Input */}
          {mode === "text" && (
            <div className={styles.textInputContainer}>
              <textarea
                className={styles.textArea}
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder="Paste your board resolution, agreement, filing document, or any text related to Companies Act compliance here..."
                rows={12}
                id="text-input"
              />
              <div className={styles.textMeta}>
                <span>{textInput.length} characters</span>
                <span>{textInput.split("\n").filter(Boolean).length} lines</span>
              </div>
            </div>
          )}

          {error && (
            <div className={styles.errorBanner} role="alert">{error}</div>
          )}

          {/* Analyze Button */}
          <button
            className={styles.analyzeBtn}
            onClick={handleAnalyze}
            disabled={mode === "upload" ? !file : !textInput.trim()}
            id="analyze-btn"
          >
            🔍 Analyze for Compliance
          </button>
        </>
      ) : state === "uploading" || state === "analyzing" ? (
        /* Loading State */
        <div className={styles.loadingContainer}>
          <div className={styles.loadingAnimation}>
            <div className={styles.loadingRing} />
            <span className={styles.loadingIcon}>⚖️</span>
          </div>
          <h2 className={styles.loadingTitle}>
            {state === "uploading" ? "Uploading Document..." : "Analyzing Compliance..."}
          </h2>
          <p className={styles.loadingSubtitle}>
            {state === "analyzing"
              ? "Cross-referencing against 470 sections of the Companies Act, 2013"
              : "Processing your document"}
          </p>
          <div className={styles.loadingSteps}>
            <div className={`${styles.loadingStep} ${styles.stepComplete}`}>
              <span className={styles.stepCheck}>✓</span> Document received
            </div>
            <div className={`${styles.loadingStep} ${state === "analyzing" ? styles.stepActive : ""}`}>
              <span className={styles.stepDot} /> Extracting text
            </div>
            <div className={styles.loadingStep}>
              <span className={styles.stepDot} /> Searching Companies Act
            </div>
            <div className={styles.loadingStep}>
              <span className={styles.stepDot} /> Generating report
            </div>
          </div>
        </div>
      ) : (
        /* Results */
        <div className={styles.results}>
          <div className={styles.resultHeader}>
            <h2 className={styles.resultTitle}>Compliance Report</h2>
            <button className={styles.newBtn} onClick={resetAnalysis} id="new-analysis">
              + New Analysis
            </button>
          </div>

          {result && (
            <>
              {/* Score Banner */}
              <div className={styles.scoreBanner}>
                <div className={styles.scoreBig}>
                  <svg viewBox="0 0 120 120" className={styles.scoreSvgBig}>
                    <circle cx="60" cy="60" r="50" fill="none" stroke="var(--border-primary)" strokeWidth="10" />
                    <circle
                      cx="60" cy="60" r="50" fill="none"
                      stroke={result.compliance_score >= 80 ? "var(--status-success)" : result.compliance_score >= 50 ? "var(--status-warning)" : "var(--status-error)"}
                      strokeWidth="10" strokeLinecap="round"
                      strokeDasharray={`${(result.compliance_score / 100) * 314} 314`}
                      transform="rotate(-90 60 60)"
                    />
                  </svg>
                  <span className={styles.scoreText}>{result.compliance_score}%</span>
                </div>
                <div className={styles.scoreMeta}>
                  <h3 className={styles.scoreStatus}>
                    {result.compliance_score >= 80 ? "Good Standing" : result.compliance_score >= 50 ? "Needs Attention" : "Critical Issues"}
                  </h3>
                  <p className={styles.scoreSummary}>{result.summary}</p>
                </div>
              </div>

              {/* Required Forms */}
              {result.required_forms.length > 0 && (
                <div className={styles.formsSection}>
                  <h3 className={styles.formsSectionTitle}>📋 Required MCA Forms</h3>
                  <div className={styles.formsGrid}>
                    {result.required_forms.map((form) => (
                      <span key={form} className={styles.formBadge}>{form}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Compliance Items */}
              <div className={styles.itemsList}>
                {result.items.map((item, idx) => (
                  <article
                    key={idx}
                    className={`${styles.complianceItem} ${
                      item.status === "COMPLIANT" ? styles.itemCompliant :
                      item.status === "NON_COMPLIANT" ? styles.itemNonCompliant :
                      styles.itemWarning
                    }`}
                    id={`compliance-item-${idx}`}
                  >
                    <div className={styles.itemHeader}>
                      <span className={styles.itemIcon}>{statusIcon(item.status)}</span>
                      <h4 className={styles.itemTitle}>{item.title}</h4>
                    </div>
                    <p className={styles.itemDesc}>{item.description}</p>

                    {item.references.length > 0 && (
                      <div className={styles.itemRefs}>
                        {item.references.map((ref, ri) => (
                          <code key={ri} className={styles.refTag}>
                            {ref.section}, Page {ref.page}, Lines {ref.line_start}-{ref.line_end}
                          </code>
                        ))}
                      </div>
                    )}

                    {item.suggestion && (
                      <div className={styles.itemSuggestion}>
                        <span className={styles.suggestionLabel}>🔧 Fix:</span> {item.suggestion}
                      </div>
                    )}

                    {item.relevant_forms.length > 0 && (
                      <div className={styles.itemForms}>
                        {item.relevant_forms.map((f) => (
                          <span key={f} className={styles.miniFormTag}>{f}</span>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
