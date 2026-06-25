import styles from "./page.module.css";

const FEATURES = [
  {
    icon: "📄",
    title: "Multi-Format Input",
    description:
      "Upload PDFs, images, DOCX files, or paste text directly. Our AI handles all common document formats used in corporate filings.",
  },
  {
    icon: "🎯",
    title: "100% Act-Referenced",
    description:
      "Every finding cites the exact Section, Chapter, Page, and Line number from the Companies Act 2013. No vague references.",
  },
  {
    icon: "💬",
    title: "Interactive Chat",
    description:
      "Ask follow-up questions about any compliance issue. Get clarifications with precise legal references in real time.",
  },
  {
    icon: "📊",
    title: "Compliance Reports",
    description:
      "Generate detailed compliance reports with compliant/non-compliant status, risk levels, and actionable recommendations.",
  },
];

const STEPS = [
  {
    number: 1,
    icon: "⬆️",
    title: "Upload",
    description:
      "Upload your corporate document — board resolutions, MOA, AOA, annual returns, or any Companies Act filing.",
  },
  {
    number: 2,
    icon: "🔍",
    title: "Analyze",
    description:
      "Our AI cross-references every clause against the full Companies Act 2013 — all 470 sections, 29 chapters, and 7 schedules.",
  },
  {
    number: 3,
    icon: "✅",
    title: "Report",
    description:
      "Receive a comprehensive compliance report with exact references, risk assessments, and recommended remediation steps.",
  },
];

const STATS = [
  { value: "470", label: "Sections Indexed", sublabel: "Companies Act 2013" },
  { value: "29", label: "Chapters Covered", sublabel: "Complete coverage" },
  { value: "7", label: "Schedules Referenced", sublabel: "With all tables" },
];

export default function LandingPage() {
  return (
    <>
      {/* ===== Hero ===== */}
      <section className={styles.hero} aria-labelledby="hero-title">
        <div className={styles.heroBackground}>
          <div className={styles.heroGradient} />
          <div className={styles.heroGrid} aria-hidden="true" />
        </div>

        <div className={styles.heroContent}>
          <span className={styles.heroBadge}>
            <span className={styles.heroBadgePulse} aria-hidden="true" />
            Companies Act 2013 · Full Coverage
          </span>

          <h1 className={styles.heroTitle} id="hero-title">
            Your AI-Powered{" "}
            <span className={styles.heroTitleAccent}>
              Companies Act Compliance
            </span>{" "}
            Partner
          </h1>

          <p className={styles.heroSubtitle}>
            Analyze corporate documents against every section of the Companies Act
            2013 — with exact section, page, and line references. 100% compliance
            coverage for Chartered Accountants &amp; Company Secretaries.
          </p>

          <div className={styles.heroActions}>
            <a
              href="/analyze"
              className={styles.ctaButton}
              id="hero-cta-start"
            >
              Start Analyzing
              <span className={styles.ctaArrow} aria-hidden="true">→</span>
            </a>
            <a
              href="#how-it-works"
              className={styles.secondaryButton}
              id="hero-cta-learn"
            >
              See How It Works
            </a>
          </div>

          <div className={styles.heroTrust}>
            <span className={styles.trustItem}>
              <span className={styles.trustIcon} aria-hidden="true">✓</span>
              Exact Section References
            </span>
            <span className={styles.trustItem}>
              <span className={styles.trustIcon} aria-hidden="true">✓</span>
              AI-Powered Analysis
            </span>
            <span className={styles.trustItem}>
              <span className={styles.trustIcon} aria-hidden="true">✓</span>
              Built for Indian Law
            </span>
          </div>
        </div>
      </section>

      {/* ===== Features ===== */}
      <section
        className={styles.features}
        id="features"
        aria-labelledby="features-title"
      >
        <div className={styles.featuresContainer}>
          <header className={styles.sectionHeader}>
            <span className={styles.sectionBadge}>Features</span>
            <h2 className={styles.sectionTitle} id="features-title">
              Everything You Need for Compliance
            </h2>
            <p className={styles.sectionSubtitle}>
              Purpose-built tools for analyzing corporate documents against the
              Companies Act 2013 with precision and speed.
            </p>
          </header>

          <div className={styles.featuresGrid}>
            {FEATURES.map((feature, index) => (
              <article
                className={styles.featureCard}
                key={feature.title}
                id={`feature-card-${index}`}
              >
                <div className={styles.featureIcon} aria-hidden="true">
                  {feature.icon}
                </div>
                <h3 className={styles.featureTitle}>{feature.title}</h3>
                <p className={styles.featureDescription}>
                  {feature.description}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ===== How It Works ===== */}
      <section
        className={styles.howItWorks}
        id="how-it-works"
        aria-labelledby="how-it-works-title"
      >
        <div className={styles.howItWorksContainer}>
          <header className={styles.sectionHeader}>
            <span className={styles.sectionBadge}>How It Works</span>
            <h2 className={styles.sectionTitle} id="how-it-works-title">
              Three Steps to Full Compliance
            </h2>
            <p className={styles.sectionSubtitle}>
              From document upload to comprehensive report — in minutes, not
              hours.
            </p>
          </header>

          <div className={styles.stepsGrid}>
            {STEPS.map((step) => (
              <div
                className={styles.stepCard}
                key={step.number}
                id={`step-card-${step.number}`}
              >
                <div className={styles.stepNumber} aria-hidden="true">
                  {step.number}
                </div>
                <div className={styles.stepIcon} aria-hidden="true">
                  {step.icon}
                </div>
                <h3 className={styles.stepTitle}>{step.title}</h3>
                <p className={styles.stepDescription}>{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== Stats ===== */}
      <section
        className={styles.stats}
        id="about"
        aria-labelledby="stats-title"
      >
        <div className={styles.statsContainer}>
          <header className={styles.sectionHeader}>
            <span className={styles.sectionBadge}>Coverage</span>
            <h2 className={styles.sectionTitle} id="stats-title">
              Complete Companies Act 2013 Coverage
            </h2>
            <p className={styles.sectionSubtitle}>
              Every section, every chapter, every schedule — indexed and
              cross-referenced for instant compliance analysis.
            </p>
          </header>

          <div className={styles.statsGrid}>
            {STATS.map((stat) => (
              <div
                className={styles.statCard}
                key={stat.label}
                id={`stat-${stat.label.toLowerCase().replace(/\s+/g, "-")}`}
              >
                <div className={styles.statValue}>{stat.value}</div>
                <div className={styles.statLabel}>{stat.label}</div>
                <div className={styles.statSublabel}>{stat.sublabel}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== CTA ===== */}
      <section className={styles.cta} aria-labelledby="cta-title">
        <div className={styles.ctaContainer}>
          <div className={styles.ctaGlow} aria-hidden="true" />
          <div className={styles.ctaContent}>
            <h2 className={styles.ctaTitle} id="cta-title">
              Ready to Streamline Your Compliance Workflow?
            </h2>
            <p className={styles.ctaDescription}>
              Join CAs and CSs across India who use HarveySpecter to analyze
              corporate documents with unmatched precision.
            </p>
            <a
              href="/sign-up"
              className={styles.ctaButton}
              id="cta-get-started"
            >
              Get Started — It&apos;s Free
              <span className={styles.ctaArrow} aria-hidden="true">→</span>
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
