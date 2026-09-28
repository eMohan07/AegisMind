/**
 * Intelligence Designed To Evolve
 * Landing Page Interactive Script
 */

document.addEventListener("DOMContentLoaded", () => {
  initStatsCountUp();
  initMobileMenu();
  initNavLinks();
});

/**
 * 1. Count-up animation for stats metrics
 * easeOutCubic, duration: 1500 + i*80ms, start offset: 480 + i*90ms
 * Triggered once via IntersectionObserver threshold 0.25
 */
function initStatsCountUp() {
  const statItems = document.querySelectorAll(".stat-item");
  if (!statItems.length) return;

  const prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

  const startCounter = (el, i) => {
    const valueEl = el.querySelector(".stat-value");
    if (!valueEl) return;

    const target = parseFloat(el.getAttribute("data-target")) || 0;
    const suffix = el.getAttribute("data-suffix") || "";
    const decimals = parseInt(el.getAttribute("data-decimals"), 10) || 0;

    if (prefersReducedMotion) {
      valueEl.textContent = target.toFixed(decimals) + suffix;
      return;
    }

    const duration = 1500 + i * 80;
    const startOffset = 480 + i * 90;

    setTimeout(() => {
      let startTime = null;

      function step(now) {
        if (!startTime) startTime = now;
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = easeOutCubic(progress);
        const current = eased * target;

        valueEl.textContent = current.toFixed(decimals) + suffix;

        if (progress < 1) {
          requestAnimationFrame(step);
        } else {
          valueEl.textContent = target.toFixed(decimals) + suffix;
        }
      }

      requestAnimationFrame(step);
    }, startOffset);
  };

  const observer = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          statItems.forEach((item, index) => {
            startCounter(item, index);
          });
          obs.disconnect();
        }
      });
    },
    { threshold: 0.25 }
  );

  const footer = document.querySelector(".stats-footer");
  if (footer) {
    observer.observe(footer);
  } else {
    statItems.forEach((item, index) => startCounter(item, index));
  }
}

/**
 * 2. Mobile Menu & Drawer Interaction
 * Toggle aria-expanded, hidden attributes, and body.menu-open
 * Close on overlay click, Escape key, link click, or resize > 720px
 */
function initMobileMenu() {
  const burger = document.getElementById("mobile-burger");
  const menu = document.getElementById("mobile-menu");
  const overlay = document.getElementById("mobile-overlay");

  if (!burger || !menu || !overlay) return;

  function openMenu() {
    burger.setAttribute("aria-expanded", "true");
    menu.removeAttribute("hidden");
    overlay.removeAttribute("hidden");
    document.body.classList.add("menu-open");
  }

  function closeMenu() {
    burger.setAttribute("aria-expanded", "false");
    menu.setAttribute("hidden", "");
    overlay.setAttribute("hidden", "");
    document.body.classList.remove("menu-open");
  }

  function isMenuOpen() {
    return burger.getAttribute("aria-expanded") === "true";
  }

  burger.addEventListener("click", () => {
    if (isMenuOpen()) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  overlay.addEventListener("click", () => {
    closeMenu();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isMenuOpen()) {
      closeMenu();
    }
  });

  const mobileLinks = menu.querySelectorAll("a");
  mobileLinks.forEach((link) => {
    link.addEventListener("click", () => {
      closeMenu();
    });
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 720 && isMenuOpen()) {
      closeMenu();
    }
  });
}

/**
 * 3. Nav link active state toggle
 */
function initNavLinks() {
  const desktopLinks = document.querySelectorAll(".nav-pill .nav-link");
  const mobileLinks = document.querySelectorAll(".mobile-menu .mobile-nav-link");

  function setActive(href) {
    desktopLinks.forEach((link) => {
      if (link.getAttribute("href") === href) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    });

    mobileLinks.forEach((link) => {
      if (link.getAttribute("href") === href) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    });
  }

  desktopLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const href = link.getAttribute("href");
      if (href && href.startsWith("#")) {
        setActive(href);
      }
    });
  });

  mobileLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const href = link.getAttribute("href");
      if (href && href.startsWith("#")) {
        setActive(href);
      }
    });
  });
}
