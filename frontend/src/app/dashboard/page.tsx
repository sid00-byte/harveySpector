"use client";

import { useState, useEffect, useRef, useCallback, Suspense } from "react";
import { useSession } from "@/lib/auth-client";
import { useRouter, useSearchParams } from "next/navigation";
import styles from "./dashboard.module.css";

interface Citation {
  raw_citation: string;
  status: "VERIFIED" | "APPROXIMATE" | "UNVERIFIED";
}

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  timestamp: string;
}

interface ComplianceReference {
  section: string;
  page: number;
  line_start: number;
  line_end: number;
}

interface ComplianceItem {
  status: "COMPLIANT" | "NON_COMPLIANT" | "WARNING" | "NEEDS_REVIEW";
  title: string;
  description: string;
  suggestion?: string;
  references?: ComplianceReference[];
  relevant_forms?: string[];
}

interface AnalysisReport {
  compliance_score: number;
  summary: string;
  items: ComplianceItem[];
  required_forms: string[];
}

interface CaseAnalysis {
  id: string;
  complianceScore: number | null;
  requiredForms: string[];
  status: string;
  report: AnalysisReport | null;
  createdAt: string;
}

interface CaseDocument {
  id: string;
  fileName: string;
  fileType: string;
  fileSizeBytes: number;
  status: string;
}

interface CaseItem {
  id: string;
  title: string;
  status: string;
  tags: string[];
  createdAt: string;
  analyses?: CaseAnalysis[];
  documents?: CaseDocument[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Helper for status badge styling
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

function DashboardContent() {
  const { data: session, isPending: sessionPending } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialCaseId = searchParams.get("caseId");
  const initialAction = searchParams.get("action");

  // State Variables
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [activeCase, setActiveCase] = useState<CaseItem | null>(null);
  
  // Chat Q&A State
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  
  // Slide-out Drawer Panel State
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  
  // New Case Mode (drag and drop / onboarding chat screen)
  const [isNewCaseMode, setIsNewCaseMode] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  
  // Live Processing Status State
  const [uploadingFile, setUploadingFile] = useState(false);
  const [uploadingFileName, setUploadingFileName] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const welcomeFileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Auto-scroll chat timeline to the bottom
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, uploadingFile, scrollToBottom]);

  // Auth Protection Redirect
  useEffect(() => {
    if (!sessionPending && !session) {
      router.push("/sign-in");
    }
  }, [session, sessionPending, router]);

  // Load sidebar cases
  const loadSidebarCases = useCallback(async (selectIdAfterLoad?: string | null) => {
    if (!session) return;
    try {
      const res = await fetch("/api/cases");
      if (res.status === 401) {
        router.push("/sign-in");
        return;
      }
      const data = await res.json();
      if (data && data.cases) {
        setCases(data.cases);
        
        // Handle selecting case explicitly requested after creation
        if (selectIdAfterLoad) {
          setActiveCaseId(selectIdAfterLoad);
          setIsNewCaseMode(false);
        }
      }
    } catch (err) {
      console.error("Error fetching cases:", err);
    } finally {
      setLoadingCases(false);
    }
  }, [session, router]);

  // Initial Load
  useEffect(() => {
    if (session) {
      loadSidebarCases();
    }
  }, [session, loadSidebarCases]);

  // Auto-select case on initial mount once cases are loaded
  useEffect(() => {
    if (loadingCases || cases.length === 0) return;

    // Only run if we haven't selected a case yet and aren't explicitly in new case mode
    if (!activeCaseId && !isNewCaseMode) {
      const targetId = initialCaseId;
      if (targetId) {
        const match = cases.find((c) => c.id === targetId);
        if (match) {
          setActiveCaseId(targetId);
          setIsNewCaseMode(false);
        } else {
          setActiveCaseId(cases[0].id);
        }
      } else if (initialAction === "new") {
        setIsNewCaseMode(true);
        setActiveCaseId(null);
      } else {
        // Auto select first case
        setActiveCaseId(cases[0].id);
        setIsNewCaseMode(false);
      }
    }
  }, [loadingCases, cases, activeCaseId, isNewCaseMode, initialCaseId, initialAction]);

  // Handle active case change (load details & chat history)
  useEffect(() => {
    if (!activeCaseId) {
      setActiveCase(null);
      setChatMessages([]);
      setIsDrawerOpen(false);
      return;
    }

    // Cancel any running polls
    if (pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }

    let isSubscribed = true;

    const loadCaseDetailsAndHistory = async () => {
      try {
        // 1. Fetch complete Case Details from Next.js Server
        const caseRes = await fetch(`/api/cases/${activeCaseId}`);
        if (caseRes.status === 401) {
          router.push("/sign-in");
          return;
        }
        const caseData = await caseRes.json();
        if (!isSubscribed) return;

        if (caseData && caseData.case) {
          setActiveCase(caseData.case);

          // If case is currently analyzing or processing, spin up live status polling
          if (caseData.case.status === "analyzing" || caseData.case.status === "processing") {
            startPollingStatus(caseData.case.id);
          }
        }

        // 2. Fetch Chat Q&A history from FastAPI Backend
        const chatRes = await fetch(`${API_URL}/api/v1/chat/history/${activeCaseId}`);
        if (!isSubscribed) return;

        if (chatRes.ok) {
          const chatData = await chatRes.json();
          if (chatData.messages && chatData.messages.length > 0) {
            setChatMessages(
              chatData.messages.map((m: any) => ({
                role: m.role,
                content: m.content,
                citations: m.citations || [],
                timestamp: m.timestamp,
              }))
            );
          } else {
            setChatMessages([]);
          }
        } else {
          setChatMessages([]);
        }
      } catch (err) {
        console.error("Error loading case details/chat history:", err);
        if (isSubscribed) {
          setChatMessages([]);
        }
      }
    };

    loadCaseDetailsAndHistory();

    return () => {
      isSubscribed = false;
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
      }
    };
  }, [activeCaseId, router]);

  // Live polling check for analyzing documents
  const startPollingStatus = (caseId: string) => {
    if (pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current);
    }

    pollingTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/cases/${caseId}`);
        if (res.status === 401) {
          router.push("/sign-in");
          clearInterval(pollingTimerRef.current!);
          return;
        }
        const data = await res.json();
        
        if (data && data.case) {
          // If status completed or failed, stop polling and refresh views
          if (data.case.status === "completed" || data.case.status === "failed") {
            clearInterval(pollingTimerRef.current!);
            pollingTimerRef.current = null;
            
            // Refresh detailed case representation
            setActiveCase(data.case);
            
            // Refresh sidebar list so scores and badges update
            loadSidebarCases(caseId);

            // Fetch final chat history to see if assistant posted a summary
            const chatRes = await fetch(`${API_URL}/api/v1/chat/history/${caseId}`);
            if (chatRes.ok) {
              const chatData = await chatRes.json();
              if (chatData.messages && chatData.messages.length > 0) {
                setChatMessages(
                  chatData.messages.map((m: any) => ({
                    role: m.role,
                    content: m.content,
                    citations: m.citations || [],
                    timestamp: m.timestamp,
                  }))
                );
              }
            }

            // Slide open the report drawer automatically on completion to WOW the user!
            if (data.case.status === "completed") {
              setIsDrawerOpen(true);
            }
          } else {
            // Keep polling and update state
            setActiveCase(data.case);
          }
        }
      } catch (err) {
        console.error("Error polling case status:", err);
      }
    }, 3000);
  };

  // Drag and Drop File Handlers
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
    if (droppedFile) {
      triggerDocumentIngestion(droppedFile);
    }
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      triggerDocumentIngestion(selected);
    }
  };

  // Perform the document ingestion pipeline
  const triggerDocumentIngestion = async (file: File) => {
    setErrorMessage("");
    setUploadingFileName(file.name);
    setUploadingFile(true);
    setUploadProgress(15);

    let targetCaseId = activeCaseId;
    let targetDocId = null;

    try {
      // 1. Initialize case / document record in database
      if (!targetCaseId) {
        // Brand new chat session case
        const caseRes = await fetch("/api/cases", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: file.name.replace(/\.[^/.]+$/, ""),
            description: `Analysis of uploaded file ${file.name}`,
            fileName: file.name,
            fileType: file.name.endsWith(".pdf") ? "pdf" : file.name.endsWith(".docx") ? "docx" : "text",
            fileSizeBytes: file.size,
          }),
        });

        if (caseRes.status === 401) {
          router.push("/sign-in");
          return;
        }
        if (!caseRes.ok) throw new Error("Could not initialize case in database");
        const caseData = await caseRes.json();
        targetCaseId = caseData.case.id;
        targetDocId = caseData.case.documents[0]?.id;

        // Switch workspace to this new case thread
        setActiveCaseId(targetCaseId);
        setIsNewCaseMode(false);
        setUploadProgress(40);
      } else {
        // Attach document to existing case thread
        const docRes = await fetch(`/api/cases/${targetCaseId}/documents`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fileName: file.name,
            fileType: file.name.endsWith(".pdf") ? "pdf" : file.name.endsWith(".docx") ? "docx" : "text",
            fileSizeBytes: file.size,
          }),
        });

        if (docRes.status === 401) {
          router.push("/sign-in");
          return;
        }
        if (!docRes.ok) throw new Error("Could not register document in case");
        const docData = await docRes.json();
        targetDocId = docData.document.id;
        setUploadProgress(40);
      }
      if (!targetCaseId) throw new Error("Audit session could not be created.");

      // 2. Upload file to FastAPI vector store ingest
      const formData = new FormData();
      formData.append("file", file);
      const uploadRes = await fetch(`${API_URL}/api/v1/documents/upload`, {
        method: "POST",
        body: formData,
      });
      if (!uploadRes.ok) throw new Error("Upload failed. Please check backend connection.");
      const uploadData = await uploadRes.json();
      const fastapiDocId = uploadData.document_id;
      setUploadProgress(65);

      // 3. Trigger compliance analysis on FastAPI backend
      const analyzeRes = await fetch(`${API_URL}/api/v1/analyze/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: fastapiDocId }),
      });
      if (!analyzeRes.ok) throw new Error("Compliance analysis trigger failed.");
      const analyzeData = await analyzeRes.json();
      setUploadProgress(85);

      // 4. Save placeholder analysis record to Next.js Postgres
      if (analyzeData.status === "COMPLETED" || analyzeData.status === "PROCESSING") {
        const saveAnalysisRes = await fetch(`/api/cases/${targetCaseId}/analysis`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            complianceScore: null,
            report: null,
            requiredForms: [],
            status: "processing",
            documentId: targetDocId,
            analysisId: analyzeData.analysis_id,
          }),
        });

        if (saveAnalysisRes.status === 401) {
          router.push("/sign-in");
          return;
        }
        if (!saveAnalysisRes.ok) {
          console.error("Failed to save analysis record placeholder to DB");
        }

        setUploadProgress(100);

        // Instantly force sidebar reload and spin up polling status check
        loadSidebarCases(targetCaseId);
        startPollingStatus(targetCaseId);
      } else {
        throw new Error("Analysis failed to schedule on backend.");
      }
    } catch (err) {
      console.error("Ingestion failed:", err);
      setErrorMessage(err instanceof Error ? err.message : "Document analysis failed");
      
      // Update DB to mark failure if possible
      if (targetCaseId) {
        await fetch(`/api/cases/${targetCaseId}/analysis`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            complianceScore: 0,
            report: null,
            requiredForms: [],
            status: "failed",
            documentId: targetDocId,
          }),
        }).catch((e) => console.error("Error setting failure status in DB:", e));
        loadSidebarCases(targetCaseId);
      }
    } finally {
      setUploadingFile(false);
    }
  };

  // Send a Chat Message Q&A
  const handleSend = async () => {
    const msg = chatInput.trim();
    if (!msg || chatLoading) return;

    let currentCaseId = activeCaseId;

    // 1. If no case selected, create a new case session on the fly!
    if (!currentCaseId) {
      setChatLoading(true);
      try {
        const caseRes = await fetch("/api/cases", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: `Chat: ${msg.substring(0, 30)}${msg.length > 30 ? "..." : ""}`,
            description: "General legal chat session",
            fileName: "",
            fileType: "",
            fileSizeBytes: 0,
          }),
        });

        if (caseRes.status === 401) {
          router.push("/sign-in");
          return;
        }
        if (!caseRes.ok) throw new Error("Could not initialize case in database");
        const caseData = await caseRes.json();
        currentCaseId = caseData.case.id;

        // Switch workspace and update sidebar case list
        setActiveCaseId(currentCaseId);
        setIsNewCaseMode(false);
        setCases((prev) => [caseData.case, ...prev]);
      } catch (err) {
        console.error("Failed to create chat session case:", err);
        setChatMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "⚠️ Failed to initialize a new chat session database record.",
            timestamp: new Date().toISOString(),
          },
        ]);
        setChatLoading(false);
        return;
      }
    }

    const userMessage: Message = {
      role: "user",
      content: msg,
      timestamp: new Date().toISOString(),
    };

    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput("");
    setChatLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/v1/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: currentCaseId,
          message: msg,
          history: chatMessages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      if (!res.ok) throw new Error("Chat response failure");
      const data = await res.json();

      const assistantMessage: Message = {
        role: "assistant",
        content: data.reply,
        citations: data.citations || [],
        timestamp: new Date().toISOString(),
      };

      setChatMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      console.error("Error sending chat message:", err);
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "⚠️ I'm currently unable to retrieve a response. Please verify that your local development servers are running.",
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setChatLoading(false);
      chatInputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Start new empty chat session
  const handleNewChat = () => {
    setActiveCaseId(null);
    setActiveCase(null);
    setChatMessages([]);
    setIsNewCaseMode(true);
    setIsDrawerOpen(false);
    router.push("/dashboard?action=new");
  };

  // Format timestamp cleanly
  const formatTime = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  };

  // Parse inline citations section names into custom styled spans
  const parseCitationsMarkup = (text: string) => {
    return text.replace(
      /\[Section\s+([^\]]+)\]/g,
      '<span class="citation">[$1]</span>'
    );
  };

  // Filter cases on query
  const filteredCases = cases.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Status mapping functions
  const statusIcon = (status: string) => {
    if (status?.toUpperCase() === "COMPLIANT") return "✅";
    if (status?.toUpperCase() === "NON_COMPLIANT") return "❌";
    return "⚠️";
  };

  const statusLabel = (status: string) => {
    if (status?.toUpperCase() === "COMPLIANT") return "Compliant";
    if (status?.toUpperCase() === "NON_COMPLIANT") return "Action Required";
    if (status?.toUpperCase() === "WARNING") return "Warning";
    return "Needs Review";
  };

  // Show page loader if session loading
  if (sessionPending || (loadingCases && cases.length === 0)) {
    return (
      <div className={styles.workspace} style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <div style={{ textAlign: "center" }}>
          <div className={styles.loaderProgress} style={{ width: "200px", height: "4px", margin: "0 auto 1.5rem" }}>
            <div className={`${styles.loaderProgressBar} ${styles.shimmerProgressBar}`} style={{ width: "100%" }} />
          </div>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>Loading compliance workspace...</p>
        </div>
      </div>
    );
  }

  // Render nothing if session expired (redirect will trigger)
  if (!session) {
    return null;
  }

  // Active analysis variables
  const latestAnalysis = activeCase?.analyses?.[0];
  const report = latestAnalysis?.report;
  const activeDocument = activeCase?.documents?.[0];

  // Aggregated general stats (shown on welcome screen)
  const totalCases = cases.length;
  const completedCases = cases.filter((c) => c.status === "completed").length;
  const inProgressCases = cases.filter((c) => c.status === "analyzing" || c.status === "processing").length;
  const scoredCases = cases.filter((c) => c.analyses?.[0]?.complianceScore !== null);
  const avgCompliance = scoredCases.length > 0
    ? Math.round(scoredCases.reduce((sum, c) => sum + (c.analyses?.[0]?.complianceScore ?? 0), 0) / scoredCases.length)
    : 0;

  // Calculate detailed counts for the active report
  const compliantCount = report?.items.filter((i) => i.status?.toUpperCase() === "COMPLIANT").length || 0;
  const nonCompliantCount = report?.items.filter((i) => i.status?.toUpperCase() === "NON_COMPLIANT").length || 0;
  const warningsCount = report?.items.filter((i) => {
    const s = i.status?.toUpperCase();
    return s === "WARNING" || s === "NEEDS_REVIEW";
  }).length || 0;

  return (
    <div className={styles.workspace}>
      {/* ── LEFT COLUMN: SIDEBAR ── */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h2 className={styles.sidebarTitle}>Compliance Audits</h2>
          <button className={styles.newChatBtn} onClick={handleNewChat} id="btn-new-chat">
            <span>+</span> New Audit Chat
          </button>
        </div>
        <div className={styles.searchWrapper}>
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Search audit threads..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            id="sidebar-search"
          />
        </div>
        <div className={styles.threadList}>
          {filteredCases.map((c) => {
            const isActive = c.id === activeCaseId;
            const badge = getStatusBadge(c.status);
            const score = c.analyses?.[0]?.complianceScore;
            
            // Cleanup date
            const dateStr = new Date(c.createdAt).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "short",
            });

            return (
              <button
                key={c.id}
                className={`${styles.threadItem} ${isActive ? styles.threadActive : ""}`}
                onClick={() => {
                  setActiveCaseId(c.id);
                  setIsNewCaseMode(false);
                }}
                id={`thread-select-${c.id}`}
              >
                <div className={styles.threadHeader}>
                  <span className={styles.threadTitle}>{c.title}</span>
                  <span className={styles.threadDate}>{dateStr}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
                  <span className={styles.threadSnippet}>
                    {score !== undefined && score !== null ? `Score: ${Math.round(score)}%` : "Pending Compliance Check"}
                  </span>
                  <span className={`${styles.badge} ${badge.className}`} style={{ fontSize: "0.625rem", padding: "0.1rem 0.5rem" }}>
                    {badge.label}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </aside>

      {/* ── MIDDLE COLUMN: CHAT WINDOW ── */}
      <main className={styles.chatArea}>
        {/* Active Chat Thread View */}
        <>
            {/* Header */}
            <header className={styles.chatHeader}>
              <div className={styles.chatHeaderInfo}>
                <span style={{ fontSize: "1.25rem" }}>⚖️</span>
                <span className={styles.chatHeaderTitle}>{activeCase?.title}</span>
              </div>
              <div className={styles.chatActions}>
                {report && (
                  <button
                    className={styles.reportToggleBtn}
                    onClick={() => setIsDrawerOpen(!isDrawerOpen)}
                    id="toggle-report-panel"
                  >
                    📊 View Report Dashboard {isDrawerOpen ? "→" : "←"}
                  </button>
                )}
              </div>
            </header>

            {/* Conversation Timeline */}
            <div className={styles.timeline}>
              {/* Default Welcome Message */}
              <div className={`${styles.message} ${styles.messageAssistant}`}>
                <div className={styles.avatar}>⚖️</div>
                <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                  <div className={styles.bubbleContent}>
                    Hello! I am your legal assistant. I have connected to the knowledge base for the Companies Act, 2013.
                    You can ask any question about the Companies Act, 2013 <strong>straight away</strong> below, or drop/attach a document to start a compliance audit.
                  </div>
                  
                  {/* Quick questions list inside welcome bubble */}
                  <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)", fontWeight: 600 }}>Quick Questions:</span>
                    {[
                      "What are the requirements for appointing a director?",
                      "Explain Section 185 on loans to directors.",
                      "What forms are needed for share transfer?",
                      "What are the CSR compliance rules under Section 135?"
                    ].map((q) => (
                      <button
                        key={q}
                        style={{
                          textAlign: "left",
                          padding: "0.5rem 0.75rem",
                          background: "var(--color-bg-surface)",
                          border: "1px solid var(--color-border)",
                          borderRadius: "var(--radius-sm)",
                          fontSize: "var(--text-xs)",
                          color: "var(--color-primary-light)",
                          transition: "all 0.2s"
                        }}
                        onClick={() => {
                          setChatInput(q);
                          chatInputRef.current?.focus();
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.borderColor = "var(--color-primary)";
                          e.currentTarget.style.background = "var(--color-primary-muted)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.borderColor = "var(--color-border)";
                          e.currentTarget.style.background = "var(--color-bg-surface)";
                        }}
                      >
                        • {q}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Inline Drag & Drop Zone if no case selected or empty thread */}
              {(!activeCaseId || chatMessages.length === 0) && !activeDocument && (
                <div
                  className={`${styles.welcomeDropzone} ${dragActive ? styles.welcomeDropzoneActive : ""}`}
                  onDragEnter={handleDrag}
                  onDragOver={handleDrag}
                  onDragLeave={handleDrag}
                  onDrop={handleDrop}
                  onClick={() => welcomeFileInputRef.current?.click()}
                  style={{ maxWidth: "560px", margin: "1.5rem auto", padding: "1.5rem", width: "100%" }}
                  id="chat-dropzone"
                >
                  <input
                    ref={welcomeFileInputRef}
                    type="file"
                    accept=".pdf,.docx,.doc,.txt"
                    onChange={handleFileSelect}
                    style={{ display: "none" }}
                    id="chat-file-input"
                  />
                  <span className={styles.dropzoneIcon} style={{ fontSize: "1.875rem", marginBottom: "0.5rem", display: "block", textAlign: "center" }}>⬆️</span>
                  <p className={styles.dropzoneText} style={{ fontSize: "var(--text-xs)", textAlign: "center" }}>Drag & drop audit document, or browse files</p>
                  <p className={styles.dropzoneSubtext} style={{ fontSize: "10px", textAlign: "center" }}>Supports PDF, DOCX, TXT — Max 50MB</p>
                </div>
              )}

              {/* General Aggregated Stats Grid (shown under dropzone when empty) */}
              {(!activeCaseId || chatMessages.length === 0) && !activeDocument && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem", maxWidth: "560px", width: "100%", margin: "0 auto 2rem" }}>
                  <div style={{ background: "var(--color-bg-surface)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", padding: "0.75rem", textAlign: "center" }}>
                    <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--color-text-primary)" }}>{totalCases}</div>
                    <div style={{ fontSize: "0.688rem", color: "var(--color-text-muted)", marginTop: "0.25rem" }}>Total Audits</div>
                  </div>
                  <div style={{ background: "var(--color-bg-surface)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", padding: "0.75rem", textAlign: "center" }}>
                    <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--color-success)" }}>{avgCompliance}%</div>
                    <div style={{ fontSize: "0.688rem", color: "var(--color-text-muted)", marginTop: "0.25rem" }}>Avg Score</div>
                  </div>
                  <div style={{ background: "var(--color-bg-surface)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", padding: "0.75rem", textAlign: "center" }}>
                    <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--color-warning)" }}>{inProgressCases}</div>
                    <div style={{ fontSize: "0.688rem", color: "var(--color-text-muted)", marginTop: "0.25rem" }}>In Progress</div>
                  </div>
                </div>
              )}

              {errorMessage && (
                <div className={styles.errorBanner} style={{ maxWidth: "560px", margin: "1rem auto", background: "var(--color-error-muted)", border: "1px solid var(--color-error)", padding: "0.75rem", borderRadius: "var(--radius-md)", color: "var(--color-error-light)", fontSize: "var(--text-sm)" }}>
                  ⚠️ {errorMessage}
                </div>
              )}

              {/* Dynamic inline render of document file cards */}
              {activeDocument && (
                <div className={`${styles.message} ${styles.messageUser}`}>
                  <div className={styles.avatar}>👤</div>
                  <div className={`${styles.bubble} ${styles.bubbleUser}`}>
                    <span>Attached Document for Audit:</span>
                    <div className={styles.fileCard}>
                      <span className={styles.fileIcon}>
                        {activeDocument.fileName.endsWith(".pdf") ? "📕" : activeDocument.fileName.endsWith(".docx") ? "📘" : "📄"}
                      </span>
                      <div className={styles.fileInfo}>
                        <span className={styles.fileName}>{activeDocument.fileName}</span>
                        <span className={styles.fileSize}>{(activeDocument.fileSizeBytes / 1024).toFixed(1)} KB</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Dynamic inline render of running analysis loader */}
              {activeCase && (activeCase.status === "analyzing" || activeCase.status === "processing") && (
                <div className={`${styles.message} ${styles.messageAssistant}`}>
                  <div className={styles.avatar}>⚖️</div>
                  <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                    <div className={styles.loaderBubble}>
                      <span className={styles.loaderText}>⚡ Ingesting & analyzing compliance findings...</span>
                      <div className={styles.loaderProgress}>
                        <div className={`${styles.loaderProgressBar} ${styles.shimmerProgressBar}`} style={{ width: "75%" }} />
                      </div>
                      <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
                        Running hybrid search across 470 Companies Act sections...
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Dynamic inline render of completed report summary card */}
              {report && (
                <div className={`${styles.message} ${styles.messageAssistant}`}>
                  <div className={styles.avatar}>⚖️</div>
                  <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                    <div className={styles.bubbleContent}>
                      Compliance analysis completed for <strong>{activeDocument?.fileName}</strong>! Here is the summary:
                    </div>
                    <div className={styles.summaryCard}>
                      <div className={styles.summaryCardHeader}>
                        <div className={styles.summaryCardScoreCircle}>
                          <svg viewBox="0 0 100 100" className={styles.summaryCardScoreSvg}>
                            <circle cx="50" cy="50" r="42" fill="none" stroke="var(--color-border)" strokeWidth="8" />
                            <circle
                              cx="50" cy="50" r="42" fill="none"
                              stroke={report.compliance_score >= 80 ? "var(--color-success)" : report.compliance_score >= 50 ? "var(--color-warning)" : "var(--color-error)"}
                              strokeWidth="8" strokeLinecap="round"
                              strokeDasharray={`${(report.compliance_score / 100) * 264} 264`}
                              transform="rotate(-90 50 50)"
                            />
                          </svg>
                          <span className={styles.summaryCardScoreValue}>{Math.round(report.compliance_score)}%</span>
                        </div>
                        <div>
                          <span className={styles.summaryCardTitle}>Compliance Score</span>
                          <div className={styles.summaryCardStatus}>
                            {report.compliance_score >= 80 ? "✅ Good Standing" : report.compliance_score >= 50 ? "⚠️ Warning" : "❌ Action Required"}
                          </div>
                        </div>
                      </div>
                      <div className={styles.summaryCardCounts}>
                        <div className={styles.summaryCardMiniStat}>
                          <span className={styles.summaryCardVal} style={{ color: "var(--color-success)" }}>{compliantCount}</span>
                          <span className={styles.summaryCardLabel}>Compliant</span>
                        </div>
                        <div className={styles.summaryCardMiniStat}>
                          <span className={styles.summaryCardVal} style={{ color: "var(--color-error)" }}>{nonCompliantCount}</span>
                          <span className={styles.summaryCardLabel}>Issues</span>
                        </div>
                        <div className={styles.summaryCardMiniStat}>
                          <span className={styles.summaryCardVal} style={{ color: "var(--color-warning)" }}>{warningsCount}</span>
                          <span className={styles.summaryCardLabel}>Warnings</span>
                        </div>
                      </div>
                      <button className={styles.summaryCardCta} onClick={() => setIsDrawerOpen(true)}>
                        Open Findings Dashboard
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Conversational timeline Q&A thread messages */}
              {chatMessages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`${styles.message} ${msg.role === "user" ? styles.messageUser : styles.messageAssistant}`}
                  id={`chat-msg-${idx}`}
                >
                  <div className={styles.avatar}>{msg.role === "user" ? "👤" : "⚖️"}</div>
                  <div className={`${styles.bubble} ${msg.role === "user" ? styles.bubbleUser : styles.bubbleAssistant}`}>
                    <div
                      className={styles.bubbleContent}
                      dangerouslySetInnerHTML={{
                        __html: parseCitationsMarkup(msg.content.replace(/\n/g, "<br />")),
                      }}
                    />
                    
                    {/* Render citation tags at bottom of bubble */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div style={{ marginTop: "0.75rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.5rem", display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                        <span style={{ fontSize: "0.688rem", color: "var(--color-text-muted)" }}>Source Sections:</span>
                        {msg.citations.map((c, ci) => (
                          <span
                            key={ci}
                            className={styles.formCard}
                            style={{
                              fontSize: "0.625rem",
                              padding: "0.15rem 0.4rem",
                              background: c.status === "VERIFIED" ? "var(--color-success-muted)" : c.status === "APPROXIMATE" ? "var(--color-warning-muted)" : "var(--color-error-muted)",
                              color: c.status === "VERIFIED" ? "var(--color-success-light)" : c.status === "APPROXIMATE" ? "var(--color-warning-light)" : "var(--color-error-light)",
                              border: "none",
                            }}
                          >
                            {c.status === "VERIFIED" ? "✓" : c.status === "APPROXIMATE" ? "≈" : "?"} {c.raw_citation}
                          </span>
                        ))}
                      </div>
                    )}
                    <span className={`${styles.msgTime} ${msg.role === "user" ? styles.msgTimeUser : ""}`}>
                      {formatTime(msg.timestamp)}
                    </span>
                  </div>
                </div>
              ))}

              {/* Typing indicator */}
              {chatLoading && (
                <div className={`${styles.message} ${styles.messageAssistant}`}>
                  <div className={styles.avatar}>⚖️</div>
                  <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                    <div style={{ display: "flex", gap: "0.25rem", padding: "0.25rem 0" }}>
                      <span className={styles.pulsingDot} style={{ width: "6px", height: "6px" }} />
                      <span className={styles.pulsingDot} style={{ width: "6px", height: "6px", animationDelay: "0.2s" }} />
                      <span className={styles.pulsingDot} style={{ width: "6px", height: "6px", animationDelay: "0.4s" }} />
                    </div>
                  </div>
                </div>
              )}

              {/* Progress bar overlay during inline chat attachment ingestion */}
              {uploadingFile && (
                <div className={`${styles.message} ${styles.messageAssistant}`}>
                  <div className={styles.avatar}>⚖️</div>
                  <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                    <div className={styles.loaderBubble}>
                      <span className={styles.loaderText}>⚡ Ingesting document: {uploadingFileName}...</span>
                      <div className={styles.loaderProgress}>
                        <div className={styles.loaderProgressBar} style={{ width: `${uploadProgress}%` }} />
                      </div>
                      <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
                        {uploadProgress < 40 ? "Uploading file to server..." : uploadProgress < 85 ? "Parsing text pages..." : "Initializing compliance pipeline..."}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Bottom Input Area */}
            <div className={styles.inputBar}>
              {/* Paperclip upload button */}
              <button
                className={styles.attachBtn}
                onClick={() => fileInputRef.current?.click()}
                disabled={chatLoading || uploadingFile}
                aria-label="Attach document"
                id="chat-attach-btn"
              >
                📎
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                onChange={handleFileSelect}
                style={{ display: "none" }}
                id="chat-file-picker"
              />

              <textarea
                ref={chatInputRef}
                className={styles.textInput}
                placeholder="Type a compliance question or ask about this document..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                disabled={chatLoading || uploadingFile}
                id="chat-message-input"
              />

              <button
                className={styles.sendBtn}
                onClick={handleSend}
                disabled={!chatInput.trim() || chatLoading || uploadingFile}
                id="chat-send-btn"
                aria-label="Send message"
              >
                <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
                  <path
                    d="M18 2L9 11M18 2L12 18L9 11M18 2L2 8L9 11"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </>
      </main>

      {/* ── RIGHT COLUMN: SLIDE-OUT REPORT DRAWER ── */}
      <aside className={`${styles.drawer} ${(!isDrawerOpen || !report) ? styles.drawerClosed : ""}`} aria-label="Detailed report drawer">
        <div className={styles.drawerHeader}>
          <h2 className={styles.drawerTitle}>Compliance Dashboard</h2>
          <button className={styles.drawerCloseBtn} onClick={() => setIsDrawerOpen(false)} aria-label="Close drawer" id="btn-close-drawer">
            ✕
          </button>
        </div>
        <div className={styles.drawerContent}>
          {report && (
            <>
              {/* Score block */}
              <div className={styles.scoreBlock}>
                <div className={styles.scoreRingLarge}>
                  <svg viewBox="0 0 140 140" style={{ width: "100%", height: "100%" }}>
                    <circle cx="70" cy="70" r="58" fill="none" stroke="var(--color-border)" strokeWidth="10" />
                    <circle
                      cx="70"
                      cy="70"
                      r="58"
                      fill="none"
                      stroke={report.compliance_score >= 80 ? "var(--color-success)" : report.compliance_score >= 50 ? "var(--color-warning)" : "var(--color-error)"}
                      strokeWidth="10"
                      strokeLinecap="round"
                      strokeDasharray={`${(report.compliance_score / 100) * 364} 364`}
                      transform="rotate(-90 70 70)"
                    />
                  </svg>
                  <span className={styles.scoreNumber} style={{ fontSize: "var(--text-lg)" }}>{Math.round(report.compliance_score)}%</span>
                </div>
                <div className={styles.statCounts}>
                  <div className={styles.miniStat}>
                    <span className={styles.miniStatIcon}>✅</span>
                    <span className={styles.miniStatVal}>{compliantCount}</span>
                    <span className={styles.miniStatLabel}>Compliant Items</span>
                  </div>
                  <div className={styles.miniStat}>
                    <span className={styles.miniStatIcon}>❌</span>
                    <span className={styles.miniStatVal}>{nonCompliantCount}</span>
                    <span className={styles.miniStatLabel}>Compliance Issues</span>
                  </div>
                  <div className={styles.miniStat}>
                    <span className={styles.miniStatIcon}>⚠️</span>
                    <span className={styles.miniStatVal}>{warningsCount}</span>
                    <span className={styles.miniStatLabel}>Warnings / Reviews</span>
                  </div>
                </div>
              </div>

              {/* Analysis Summary */}
              <div className={styles.summaryText}>
                <h3 className={styles.summaryTitle}>Summary Findings</h3>
                <p className={styles.summaryBody}>{report.summary}</p>
              </div>

              {/* Required Forms Grid */}
              {report.required_forms && report.required_forms.length > 0 && (
                <div className={styles.formsSection}>
                  <h3 className={styles.sectionHeading}>📋 Required MCA Forms</h3>
                  <div className={styles.formsGrid}>
                    {report.required_forms.map((form) => (
                      <span key={form} className={styles.formCard}>
                        {form}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Detailed Findings List */}
              <div className={styles.findingsSection}>
                <h3 className={styles.sectionHeading}>📝 Detailed Audit Findings</h3>
                <div className={styles.findingsList}>
                  {report.items.map((item, idx) => (
                    <article
                      key={idx}
                      className={`${styles.finding} ${
                        item.status?.toUpperCase() === "COMPLIANT" ? styles.findingCompliant :
                        item.status?.toUpperCase() === "NON_COMPLIANT" ? styles.findingNonCompliant :
                        styles.findingWarning
                      }`}
                      id={`finding-detail-${idx}`}
                    >
                      <div className={styles.findingHeader}>
                        <span className={styles.findingIcon}>{statusIcon(item.status)}</span>
                        <div className={styles.findingTitleBlock}>
                          <h4 className={styles.findingTitle}>{item.title}</h4>
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
                      
                      {/* Section References */}
                      {item.references && item.references.length > 0 && (
                        <div className={styles.refsBlock}>
                          <span className={styles.refsLabel}>📖 Legal Citations:</span>
                          <div className={styles.refsList}>
                            {item.references.map((ref, ri) => (
                              <code key={ri} className={styles.refCode}>
                                Section {ref.section} · Page {ref.page} · Lines {ref.line_start}–{ref.line_end}
                              </code>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Corrective suggestions */}
                      {item.suggestion && (
                        <div className={styles.suggestionBlock}>
                          <span className={styles.suggestionIcon}>🔧</span>
                          <div>
                            <span className={styles.suggestionLabel}>Recommended Action</span>
                            <p className={styles.suggestionText}>{item.suggestion}</p>
                          </div>
                        </div>
                      )}

                      {/* Associated forms */}
                      {item.relevant_forms && item.relevant_forms.length > 0 && (
                        <div className={styles.findingForms}>
                          {item.relevant_forms.map((f) => (
                            <span key={f} className={styles.findingFormTag}>
                              {f}
                            </span>
                          ))}
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={
      <div className={styles.workspace} style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <div style={{ textAlign: "center" }}>
          <div className={styles.loaderProgress} style={{ width: "200px", height: "4px", margin: "0 auto 1.5rem" }}>
            <div className={`${styles.loaderProgressBar} ${styles.shimmerProgressBar}`} style={{ width: "100%" }} />
          </div>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>Loading compliance workspace...</p>
        </div>
      </div>
    }>
      <DashboardContent />
    </Suspense>
  );
}
