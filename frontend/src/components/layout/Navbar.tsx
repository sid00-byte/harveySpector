"use client";

import { useState, useEffect, useCallback } from "react";
import styles from "./Navbar.module.css";

export function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const handleScroll = useCallback(() => {
    setIsScrolled(window.scrollY > 20);
  }, []);

  useEffect(() => {
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen((prev) => !prev);
  };

  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false);
  };

  return (
    <header
      className={`${styles.navbar} ${isScrolled ? styles.scrolled : ""}`}
      role="banner"
    >
      <nav className={styles.navContainer} aria-label="Main navigation">
        {/* Logo */}
        <a href="/" className={styles.logo} id="navbar-logo">
          <span className={styles.logoIcon} aria-hidden="true">⚖️</span>
          <span className={styles.logoText}>HarveySpecter</span>
        </a>

        {/* Desktop Navigation */}
        <ul className={styles.navLinks} role="list">
          <li>
            <a href="#features" className={styles.navLink} id="nav-features">
              Features
            </a>
          </li>
          <li>
            <a href="#how-it-works" className={styles.navLink} id="nav-how-it-works">
              How It Works
            </a>
          </li>
          <li>
            <a href="#about" className={styles.navLink} id="nav-about">
              About
            </a>
          </li>
        </ul>

        {/* Auth Buttons */}
        <div className={styles.authButtons}>
          <a
            href="/sign-in"
            className={styles.signInBtn}
            id="nav-sign-in"
          >
            Sign In
          </a>
          <a
            href="/sign-up"
            className={styles.getStartedBtn}
            id="nav-get-started"
          >
            Get Started
          </a>
        </div>

        {/* Mobile Menu Toggle */}
        <button
          className={`${styles.hamburger} ${isMobileMenuOpen ? styles.hamburgerOpen : ""}`}
          onClick={toggleMobileMenu}
          id="nav-mobile-toggle"
          type="button"
          aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
          aria-expanded={isMobileMenuOpen}
          aria-controls="mobile-menu"
        >
          <span className={styles.hamburgerLine} />
          <span className={styles.hamburgerLine} />
          <span className={styles.hamburgerLine} />
        </button>
      </nav>

      {/* Mobile Menu */}
      <div
        className={`${styles.mobileMenu} ${isMobileMenuOpen ? styles.mobileMenuOpen : ""}`}
        id="mobile-menu"
        role="dialog"
        aria-label="Mobile navigation"
      >
        <ul className={styles.mobileNavLinks} role="list">
          <li>
            <a
              href="#features"
              className={styles.mobileNavLink}
              id="mobile-nav-features"
              onClick={closeMobileMenu}
            >
              Features
            </a>
          </li>
          <li>
            <a
              href="#how-it-works"
              className={styles.mobileNavLink}
              id="mobile-nav-how-it-works"
              onClick={closeMobileMenu}
            >
              How It Works
            </a>
          </li>
          <li>
            <a
              href="#about"
              className={styles.mobileNavLink}
              id="mobile-nav-about"
              onClick={closeMobileMenu}
            >
              About
            </a>
          </li>
        </ul>
        <div className={styles.mobileAuthButtons}>
          <button
            className={styles.signInBtn}
            id="mobile-nav-sign-in"
            type="button"
          >
            Sign In
          </button>
          <button
            className={styles.getStartedBtn}
            id="mobile-nav-get-started"
            type="button"
          >
            Get Started
          </button>
        </div>
      </div>
    </header>
  );
}
