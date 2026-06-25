import styles from "./Footer.module.css";

export function Footer() {
  return (
    <footer className={styles.footer} role="contentinfo">
      <div className={styles.container}>
        {/* Top section */}
        <div className={styles.topSection}>
          {/* Brand column */}
          <div className={styles.brandColumn}>
            <a href="/" className={styles.logo} id="footer-logo">
              <span className={styles.logoIcon} aria-hidden="true">⚖️</span>
              <span className={styles.logoText}>HarveySpecter</span>
            </a>
            <p className={styles.tagline}>
              AI-powered compliance analysis for the Companies Act 2013.
              Built to make legal compliance effortless.
            </p>
            <div className={styles.badge}>
              <span className={styles.badgeIcon} aria-hidden="true">🇮🇳</span>
              <span>Built for CAs &amp; CSs in India</span>
            </div>
          </div>

          {/* Links columns */}
          <div className={styles.linksGrid}>
            <div className={styles.linkColumn}>
              <h4 className={styles.linkHeading}>Product</h4>
              <ul className={styles.linkList} role="list">
                <li>
                  <a href="#features" className={styles.link} id="footer-features">
                    Features
                  </a>
                </li>
                <li>
                  <a href="#how-it-works" className={styles.link} id="footer-how-it-works">
                    How It Works
                  </a>
                </li>
                <li>
                  <a href="#pricing" className={styles.link} id="footer-pricing">
                    Pricing
                  </a>
                </li>
              </ul>
            </div>

            <div className={styles.linkColumn}>
              <h4 className={styles.linkHeading}>Legal</h4>
              <ul className={styles.linkList} role="list">
                <li>
                  <a href="/privacy" className={styles.link} id="footer-privacy">
                    Privacy Policy
                  </a>
                </li>
                <li>
                  <a href="/terms" className={styles.link} id="footer-terms">
                    Terms of Service
                  </a>
                </li>
                <li>
                  <a href="/contact" className={styles.link} id="footer-contact">
                    Contact Us
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Divider */}
        <hr className={styles.divider} />

        {/* Bottom section */}
        <div className={styles.bottomSection}>
          <p className={styles.copyright}>
            &copy; 2026 HarveySpecter. All rights reserved.
          </p>
          <p className={styles.disclaimer}>
            Not a substitute for professional legal advice.
          </p>
        </div>
      </div>
    </footer>
  );
}
