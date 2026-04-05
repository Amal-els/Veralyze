// ============================================================
// Trust Graph Engine - Content Script
// Handles hover highlighting, click-to-analyze, and result rendering
// ============================================================

(function () {
  'use strict';

  const HIGHLIGHT_ATTR = 'data-tg-hover-target';
  const CLICKABLE_SELECTOR = 'a, button, input, textarea, select, [role="button"]';

  let overlay = null;
  let badge = null;
  let highlightBox = null;
  let hoverHint = null;
  let activeTarget = null;
  let isAnalyzing = false;
  let extractionModeEnabled = false;

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    switch (message.action) {
      case 'showLoading':
        removeOverlay();
        showLoadingBadge();
        sendResponse({ ok: true });
        break;
      case 'extractPost':
        sendResponse(extractCurrentPost(message.info) || { error: 'No post found at this location.' });
        break;
      case 'showResult':
        removeLoadingBadge();
        renderOverlay(message.result, message.payload);
        sendResponse({ ok: true });
        break;
      case 'showError':
        removeLoadingBadge();
        showErrorToast(message.message);
        sendResponse({ ok: true });
        break;
      default:
        break;
    }
    return true;
  });

  initExtractionMode();
  window.addEventListener('popstate', () => {
    removeOverlay();
    clearHighlight();
  });
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== 'sync' || !changes.extractionModeEnabled) return;
    extractionModeEnabled = Boolean(changes.extractionModeEnabled.newValue);
    if (!extractionModeEnabled) {
      clearHighlight();
      removeLoadingBadge();
    }
  });

  async function initExtractionMode() {
    const data = await chrome.storage.sync.get(['extractionModeEnabled']);
    extractionModeEnabled = Boolean(data.extractionModeEnabled);
    installHoverInspector();
    window.addEventListener('scroll', refreshHighlightPosition, true);
    window.addEventListener('resize', refreshHighlightPosition);
  }

  function installHoverInspector() {
    document.addEventListener('mousemove', onPointerMove, true);
    document.addEventListener('mouseleave', clearHighlight, true);
    document.addEventListener('click', onDocumentClick, true);
  }

  function onPointerMove(event) {
    if (!extractionModeEnabled) {
      clearHighlight();
      return;
    }
    if (isOverlayElement(event.target)) return;

    const candidate = findInspectableTarget(event.target);
    if (!candidate) {
      clearHighlight();
      return;
    }

    if (candidate !== activeTarget) {
      setHighlightTarget(candidate);
    }

    positionHoverHint(event.clientX, event.clientY);
  }

  async function onDocumentClick(event) {
    if (!extractionModeEnabled) return;
    if (isOverlayElement(event.target) || isAnalyzing) return;

    const candidate = findInspectableTarget(event.target);
    if (!candidate) return;

    if (event.target.closest(CLICKABLE_SELECTOR) && !candidate.contains(event.target.closest(CLICKABLE_SELECTOR))) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const payload = extractCurrentPost({ targetElement: candidate });
    if (!payload || payload.error) {
      showErrorToast(payload?.error || 'Could not extract post content.');
      return;
    }

    setHighlightTarget(candidate);
    await analyzePayload(payload);
  }

  function findInspectableTarget(node) {
    const host = window.location.hostname;

    if (host.includes('reddit.com') && window.TrustGraph?.findRedditPostElement) {
      return window.TrustGraph.findRedditPostElement(node);
    }
    if (host.includes('instagram.com') && window.TrustGraph?.findInstagramPostElement) {
      return window.TrustGraph.findInstagramPostElement(node);
    }
    if ((host.includes('x.com') || host.includes('twitter.com')) && window.TrustGraph?.findTwitterPostElement) {
      return window.TrustGraph.findTwitterPostElement(node);
    }

    return null;
  }

  function extractCurrentPost(info) {
    const host = window.location.hostname;

    if (host.includes('reddit.com') && window.TrustGraph?.extractReddit) {
      return window.TrustGraph.extractReddit(info || {});
    }
    if (host.includes('instagram.com') && window.TrustGraph?.extractInstagram) {
      return window.TrustGraph.extractInstagram(info || {});
    }
    if ((host.includes('x.com') || host.includes('twitter.com')) && window.TrustGraph?.extractTwitter) {
      return window.TrustGraph.extractTwitter(info || {});
    }
    return { error: 'Unsupported platform.' };
  }

  async function analyzePayload(payload) {
    isAnalyzing = true;
    removeOverlay();
    showLoadingBadge();

    try {
      const response = await chrome.runtime.sendMessage({
        action: 'analyzePayload',
        payload
      });

      if (!response?.ok) {
        throw new Error(response?.error || 'Analysis failed.');
      }

      renderOverlay(response.result, response.payload);
    } catch (error) {
      showErrorToast(error.message || 'Analysis failed.');
    } finally {
      removeLoadingBadge();
      isAnalyzing = false;
    }
  }

  function setHighlightTarget(element) {
    clearHighlight();
    activeTarget = element;
    activeTarget.setAttribute(HIGHLIGHT_ATTR, 'true');
    ensureHighlightUi();
    refreshHighlightPosition();
  }

  function clearHighlight() {
    if (activeTarget?.isConnected) {
      activeTarget.removeAttribute(HIGHLIGHT_ATTR);
    }
    activeTarget = null;
    highlightBox?.classList.remove('tg-visible');
    hoverHint?.classList.remove('tg-visible');
  }

  function ensureHighlightUi() {
    if (!highlightBox) {
      highlightBox = document.createElement('div');
      highlightBox.id = 'tg-hover-highlight';
      document.documentElement.appendChild(highlightBox);
    }

    if (!hoverHint) {
      hoverHint = document.createElement('div');
      hoverHint.id = 'tg-hover-hint';
      hoverHint.textContent = 'Click to analyze';
      document.documentElement.appendChild(hoverHint);
    }
  }

  function refreshHighlightPosition() {
    if (!activeTarget || !activeTarget.isConnected || !highlightBox) {
      clearHighlight();
      return;
    }

    const rect = activeTarget.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) {
      clearHighlight();
      return;
    }

    highlightBox.classList.add('tg-visible');
    highlightBox.style.left = `${rect.left + window.scrollX}px`;
    highlightBox.style.top = `${rect.top + window.scrollY}px`;
    highlightBox.style.width = `${rect.width}px`;
    highlightBox.style.height = `${rect.height}px`;

    if (hoverHint) {
      hoverHint.classList.add('tg-visible');
      hoverHint.style.left = `${rect.left + window.scrollX + 10}px`;
      hoverHint.style.top = `${Math.max(window.scrollY + 8, rect.top + window.scrollY + 10)}px`;
    }
  }

  function positionHoverHint(clientX, clientY) {
    if (!hoverHint || !activeTarget) return;

    hoverHint.style.left = `${window.scrollX + clientX + 14}px`;
    hoverHint.style.top = `${window.scrollY + clientY + 14}px`;
  }

  function isOverlayElement(node) {
    return !!node?.closest?.('#tg-overlay, #tg-hover-highlight, #tg-hover-hint, #tg-loading-badge, #tg-error-toast');
  }

  function showLoadingBadge() {
    removeLoadingBadge();
    badge = document.createElement('div');
    badge.id = 'tg-loading-badge';
    badge.innerHTML = `
      <div class="tg-spinner"></div>
      <span>Analyzing trust...</span>
    `;
    document.body.appendChild(badge);
  }

  function removeLoadingBadge() {
    badge?.remove();
    badge = null;
  }

  function renderOverlay(result, payload) {
    removeOverlay();

    const score = Math.round(result.trust_score ?? 0);
    const verdict = result.verdict || getVerdict(score);
    const subscores = result.subscores || {};
    const explanation = result.explanation || '';
    const summaryTitle = result.summary_title || defaultSummaryTitle(payload?.platform, verdict);
    const meta = result.metadata?.content_meta || [];
    const isMock = result.metadata?.mock;

    overlay = document.createElement('div');
    overlay.id = 'tg-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', 'Trust Graph Analysis');

    overlay.innerHTML = `
      <div id="tg-panel">
        <div id="tg-header">
          <div id="tg-brand">
            <span id="tg-logo">TG</span>
            <span id="tg-title">Trust Graph</span>
            <span id="tg-platform-badge" class="platform-${platformClass(payload?.platform)}">
              ${platformLabel(payload?.platform).toUpperCase()}
            </span>
          </div>
          <button id="tg-close" aria-label="Close">x</button>
        </div>

        <div id="tg-score-section">
          <div id="tg-ring-wrapper">
            <svg viewBox="0 0 120 120" id="tg-ring-svg">
              <circle cx="60" cy="60" r="50" class="tg-ring-bg"/>
              <circle
                cx="60"
                cy="60"
                r="50"
                class="tg-ring-fill verdict-${verdict}"
                id="tg-ring-circle"
                stroke-dasharray="314"
                stroke-dashoffset="${314 - (314 * score / 100)}"
              />
            </svg>
            <div id="tg-score-inner">
              <span id="tg-score-num">${score}</span>
              <span id="tg-score-label">/100</span>
            </div>
          </div>
          <div id="tg-verdict-block">
            <span id="tg-verdict-chip" class="verdict-chip verdict-${verdict}">
              ${verdictIcon(verdict)} ${verdict.toUpperCase()}
            </span>
            <p id="tg-summary-title">${summaryTitle}</p>
            <p id="tg-post-url">${truncate(payload?.url || '', 55)}</p>
            ${isMock ? '<p class="tg-mock-note">Demo mode - backend unavailable.</p>' : ''}
          </div>
        </div>

        ${meta.length ? `<div id="tg-meta-row">${meta.map((item) => `<span class="tg-meta-pill">${item}</span>`).join('')}</div>` : ''}

        <div id="tg-subscores">
          <h3 class="tg-section-title">Breakdown</h3>
          ${renderSubscore('Authenticity', subscores.authenticity)}
          ${renderSubscore('Context Match', subscores.context)}
          ${renderSubscore('Source Trust', subscores.source)}
        </div>

        <div id="tg-explanation">
          <h3 class="tg-section-title">AI Analysis</h3>
          <p id="tg-explanation-text">${explanation}</p>
        </div>

        <div id="tg-graph-section">
          <h3 class="tg-section-title">Trust Graph</h3>
          <canvas id="tg-graph-canvas" width="360" height="160"></canvas>
        </div>

        <div id="tg-footer">
          <span>Payload sent to backend and saved locally.</span>
          <a href="#" id="tg-open-options">Settings</a>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    requestAnimationFrame(() => {
      overlay.classList.add('tg-visible');
      animateRing(score);
    });

    if (result.graph_nodes && result.graph_edges) {
      setTimeout(() => drawMiniGraph(result.graph_nodes, result.graph_edges), 100);
    }

    overlay.querySelector('#tg-close').addEventListener('click', removeOverlay);
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) removeOverlay();
    });
    overlay.querySelector('#tg-open-options').addEventListener('click', (event) => {
      event.preventDefault();
      chrome.runtime.openOptionsPage();
    });
  }

  function removeOverlay() {
    overlay?.remove();
    overlay = null;
  }

  function animateRing(targetScore) {
    const circle = document.getElementById('tg-ring-circle');
    const numEl = document.getElementById('tg-score-num');
    if (!circle || !numEl) return;

    const total = 314;
    const targetOffset = total - (total * targetScore / 100);
    const start = performance.now();
    const duration = 900;

    function step(now) {
      const progress = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = total - ((total - targetOffset) * ease);
      circle.style.strokeDashoffset = current;
      numEl.textContent = Math.round(targetScore * ease);
      if (progress < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
  }

  function drawMiniGraph(nodes, edges) {
    const canvas = document.getElementById('tg-graph-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const positions = {};
    const cx = w / 2;
    const cy = h / 2;
    const radius = Math.min(w, h) * 0.35;

    nodes.forEach((node, index) => {
      if (index === 0) {
        positions[node.id] = { x: cx, y: cy };
        return;
      }
      const angle = ((index - 1) / Math.max(1, nodes.length - 1)) * 2 * Math.PI - Math.PI / 2;
      positions[node.id] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle)
      };
    });

    ctx.clearRect(0, 0, w, h);

    edges.forEach((edge) => {
      const from = positions[edge.from];
      const to = positions[edge.to];
      if (!from || !to) return;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.strokeStyle = 'rgba(99,102,241,0.4)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });

    nodes.forEach((node) => {
      const pos = positions[node.id];
      if (!pos) return;
      const score = node.score ?? 50;
      const color = scoreToColor(score);
      const r = node.type === 'post' ? 18 : 12;
      const gradient = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, r * 2);
      gradient.addColorStop(0, `${color}55`);
      gradient.addColorStop(1, 'transparent');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r * 2, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.2)';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = '#e2e8f0';
      ctx.font = '9px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(truncate(node.label, 10), pos.x, pos.y + r + 12);
    });
  }

  function renderSubscore(label, value) {
    const v = Math.round(value ?? 0);
    const cls = v >= 70 ? 'trusted' : v >= 40 ? 'uncertain' : 'suspicious';
    return `
      <div class="tg-subscore-row">
        <span class="tg-subscore-label">${label}</span>
        <div class="tg-bar-bg">
          <div class="tg-bar-fill verdict-${cls}" style="width:${v}%"></div>
        </div>
        <span class="tg-subscore-val">${v}</span>
      </div>
    `;
  }

  function showErrorToast(message) {
    const toast = document.createElement('div');
    toast.id = 'tg-error-toast';
    toast.innerHTML = `<span>!</span><span>${message}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }

  function getVerdict(score) {
    if (score >= 70) return 'trusted';
    if (score >= 40) return 'uncertain';
    return 'suspicious';
  }

  function verdictIcon(verdict) {
    return { trusted: 'OK', uncertain: '!', suspicious: 'X' }[verdict] || '?';
  }

  function scoreToColor(score) {
    if (score >= 70) return '#22c55e';
    if (score >= 40) return '#f59e0b';
    return '#ef4444';
  }

  function platformLabel(platform) {
    if (platform === 'twitter' || platform === 'x') return 'X/Twitter';
    if (platform === 'instagram') return 'Instagram';
    if (platform === 'reddit') return 'Reddit';
    return 'Post';
  }

  function platformClass(platform) {
    return platform === 'twitter' ? 'x' : (platform || 'unknown');
  }

  function defaultSummaryTitle(platform, verdict) {
    const subject = platformLabel(platform);
    if (verdict === 'trusted') return `${subject} looks fairly credible`;
    if (verdict === 'uncertain') return `${subject} needs a second check`;
    return `${subject} deserves extra caution`;
  }

  function truncate(str, max) {
    return str?.length > max ? str.slice(0, max) + '...' : (str || '');
  }
})();
