// ============================================================
// Trust Graph - Popup Script
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
  const stateIdle = document.getElementById('state-idle');
  const stateResult = document.getElementById('state-result');
  const payloadEl = document.getElementById('result-payload');
  const copyBtn = document.getElementById('btn-copy-payload');
  const summaryEl = document.getElementById('result-summary-title');
  const metaEl = document.getElementById('result-meta');
  const modeToggle = document.getElementById('toggle-extraction-mode');
  const reactionsSection = document.getElementById('result-reactions-section');
  const reactionsList = document.getElementById('result-reactions-list');

  const [localData, syncData] = await Promise.all([
    chrome.storage.local.get(['lastResult', 'lastPayload']),
    chrome.storage.sync.get(['extractionModeEnabled'])
  ]);

  const last = localData.lastResult;
  const payload = localData.lastPayload;
  modeToggle.checked = Boolean(syncData.extractionModeEnabled);

  if (last && last.trust_score !== undefined) {
    showResult(last, payload);
  } else {
    stateIdle.classList.remove('hidden');
  }

  document.getElementById('btn-settings').addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
    window.close();
  });

  modeToggle.addEventListener('change', async () => {
    await chrome.storage.sync.set({ extractionModeEnabled: modeToggle.checked });
  });

  document.getElementById('btn-analyze-again').addEventListener('click', () => {
    stateResult.classList.add('hidden');
    stateIdle.classList.remove('hidden');
  });

  copyBtn.addEventListener('click', async () => {
    const text = payloadEl.textContent || '';
    if (!text || text === '(no extracted payload saved yet)') return;

    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = 'Copied';
    } catch (_) {
      copyBtn.textContent = 'Copy failed';
    }

    setTimeout(() => {
      copyBtn.textContent = 'Copy JSON';
    }, 1500);
  });

  function showResult(result, rawPayload) {
    stateIdle.classList.add('hidden');
    stateResult.classList.remove('hidden');

    const score = Math.round(result.trust_score ?? 0);
    const verdict = result.verdict || (score >= 70 ? 'trusted' : score >= 40 ? 'uncertain' : 'suspicious');
    const icons = { trusted: 'OK', uncertain: '!', suspicious: 'X' };
    const metaItems = result.metadata?.content_meta || [];

    if (result.timestamp) {
      document.getElementById('result-time').textContent = timeAgo(result.timestamp);
    }

    const rawPlatform = result.platform || rawPayload?.platform || 'unknown';
    const platform = platformLabel(rawPlatform);
    const platformBadge = document.getElementById('result-platform-badge');
    platformBadge.textContent = platform;
    platformBadge.className = 'site-chip ' + platformClass(rawPlatform);

    const circle = document.getElementById('result-ring-circle');
    const total = 201;
    const offset = total - (total * score / 100);
    const colorMap = { trusted: '#22c55e', uncertain: '#f59e0b', suspicious: '#ef4444' };
    circle.style.stroke = colorMap[verdict] || '#818cf8';
    circle.style.filter = `drop-shadow(0 0 5px ${colorMap[verdict] || '#818cf8'})`;
    setTimeout(() => {
      circle.style.strokeDashoffset = offset;
    }, 50);

    animateNumber(document.getElementById('result-score-num'), 0, score, 800);

    const chip = document.getElementById('result-verdict-chip');
    chip.textContent = `${icons[verdict] || '?'} ${verdict.toUpperCase()}`;
    chip.className = `verdict-chip ${verdict}`;

    summaryEl.textContent = result.summary_title || defaultSummaryTitle(platform, verdict);
    document.getElementById('result-url').textContent = truncate(result.postUrl || rawPayload?.url || '', 50);
    document.getElementById('result-explanation').textContent = result.explanation || '';
    metaEl.innerHTML = metaItems.map((item) => `<span class="result-meta-pill">${escapeHtml(item)}</span>`).join('');
    renderReactions(result.metadata?.reactions || rawPayload?.reactions || []);

    payloadEl.textContent = rawPayload
      ? JSON.stringify(rawPayload, null, 2)
      : '(no extracted payload saved yet)';

    const sub = result.subscores || {};
    setBar('auth', sub.authenticity ?? 0);
    setBar('ctx', sub.context ?? 0);
    setBar('src', sub.source ?? 0);

    // Render 3D Propagation Graph
    const container = document.getElementById('3d-graph-container');
    container.innerHTML = ''; // Force clear
    
    // Safety: Verify data exists and isn't empty
    if (result.graph_nodes && result.graph_nodes.length > 0) {
      if (!window.ForceGraph3D) {
          container.innerHTML = '<div style="color:#ef4444; padding:20px; text-align:center;">3D Engine not loaded. Check script permissions.</div>';
          return;
      }

      setTimeout(() => {
        try {
          // 1. Clean and stringify nodes first
          const nodes = (result.graph_nodes || [])
              .filter(n => n && n.id !== undefined && n.id !== null)
              .map(n => ({ ...n, id: String(n.id) }));
          
          // 2. Build whitelist from CLEANED nodes only
          const validNodeIds = new Set(nodes.map(n => n.id));
          
          // 3. Filter edges: must exist in whitelist AND have valid source/target
          const edges = (result.graph_edges || [])
              .filter(e => {
                  const s = e && e.source !== undefined ? String(e.source) : null;
                  const t = e && e.target !== undefined ? String(e.target) : null;
                  return s && t && validNodeIds.has(s) && validNodeIds.has(t);
              })
              .map(e => ({ 
                  source: String(e.source), 
                  target: String(e.target) 
              }));

          console.log(`[3D Graph] Rendering ${nodes.length} nodes and ${edges.length} edges.`);

          if (nodes.length === 0) {
             container.innerHTML = '<div style="color:#94a3b8; padding:20px; text-align:center;">No valid propagation nodes.</div>';
             return;
          }

          const width = container.clientWidth || 288;
          const height = container.clientHeight || 250;
          
          // Bulletproof 3D Engine Initialization
          const Graph = ForceGraph3D()(container)
            .width(width)
            .height(height)
            .backgroundColor('#0f172a') // Sleek dark midnight theme
            .nodeId('id')               // Explicitly tell the engine where the ID is
            .linkSource('source')       // Explicitly define source accessor
            .linkTarget('target')       // Explicitly define target accessor
            .showNavInfo(false)
            .nodeRelSize(7)
            .linkWidth(1.5)
            .linkColor(() => 'rgba(255, 255, 255, 0.15)');

          // Delay data injection slightly to ensure the engine is stable
          setTimeout(() => {
            try {
              Graph.graphData({ nodes, links: edges });
              
              // Apply styling after data is loaded
              Graph.nodeLabel(node => {
                const type = (node.type || 'REPLY').toUpperCase();
                const score = typeof node.score === 'number' ? node.score : 0;
                return `<div style="background:rgba(15, 23, 42, 0.95); padding:10px; border-radius:10px; border:1px solid #334155; font-family:Inter, sans-serif; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);">
                          <div style="color:#c084fc; font-weight:700; margin-bottom:4px; font-size:13px;">${node.label}</div>
                          <div style="display:flex; justify-content:space-between; gap:20px; font-size:11px;">
                            <span style="opacity:0.8; color:#94a3b8;">${type}</span>
                            <span style="color:${score > 0.4 ? '#fb7185':'#34d399'}; font-weight:600;">${(score * 100).toFixed(1)}% Risk</span>
                          </div>
                        </div>`;
              })
              .nodeColor(node => {
                  if (node.type === 'root') return '#c084fc';
                  return (node.score || 0) > 0.4 ? '#f43f5e' : '#10b981';
              });
            } catch (innerErr) {
              console.error("[3D Graph] Deferred Data Error:", innerErr);
            }
          }, 50);

          // Subtle auto-rotation
          let angle = 0;
          const rotateInterval = setInterval(() => {
              if (!document.getElementById('3d-graph-container')) {
                  clearInterval(rotateInterval);
                  return;
              }
              Graph.cameraPosition({
                  x: 220 * Math.sin(angle),
                  z: 220 * Math.cos(angle)
              });
              angle += Math.PI / 600;
          }, 20);
        } catch (err) {
          console.error("WebGL 3D Graph Error:", err);
          container.innerHTML = '<div style="color:#94a3b8; padding:20px; text-align:center;">WebGL unavailable or crashed.</div>';
        }
      }, 100);
    }
  }

  function setBar(key, value) {
    const v = Math.round(value);
    const fill = document.getElementById(`bar-${key}`);
    const val = document.getElementById(`val-${key}`);
    if (fill) {
      setTimeout(() => {
        fill.style.width = `${v}%`;
      }, 100);
    }
    if (val) {
      val.textContent = String(v);
    }
  }

  function animateNumber(el, from, to, duration) {
    const start = performance.now();

    function step(now) {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      el.textContent = String(Math.round(from + (to - from) * ease));
      if (t < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
  }

  function timeAgo(timestamp) {
    const diff = Date.now() - timestamp;
    const s = Math.floor(diff / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    return `${Math.floor(s / 3600)}h ago`;
  }

  function platformLabel(platform) {
    if (platform === 'twitter' || platform === 'x') return 'X/Twitter';
    if (platform === 'instagram') return 'Instagram';
    if (platform === 'reddit') return 'Reddit';
    return 'Unknown';
  }

  function platformClass(platform) {
    return platform === 'twitter' ? 'x' : platform;
  }

  function defaultSummaryTitle(platform, verdict) {
    if (verdict === 'trusted') return `${platform} looks fairly credible`;
    if (verdict === 'uncertain') return `${platform} needs a second check`;
    return `${platform} deserves extra caution`;
  }

  function truncate(str, max) {
    return str?.length > max ? `${str.slice(0, max)}...` : (str || '');
  }

  function renderReactions(reactions) {
    if (!Array.isArray(reactions) || reactions.length === 0) {
      reactionsSection.classList.add('hidden');
      reactionsList.innerHTML = '';
      return;
    }

    reactionsSection.classList.remove('hidden');
    reactionsList.innerHTML = reactions.map((reaction) => {
      const users = (reaction.top_users || []).slice(0, 5);
      const usersHtml = users.length
        ? `<div class="reaction-users">${users.map((user) => {
          const username = escapeHtml(user.username || 'unknown');
          const count = user.reaction_count ?? 0;
          const type = escapeHtml(user.reaction_type || reaction.type || 'reaction');
          return `<span class="reaction-user-pill">${username} - ${count} ${type}</span>`;
        }).join('')}</div>`
        : '<div class="reaction-empty">No top users extracted for this reaction.</div>';

      return `
        <div class="reaction-card">
          <div class="reaction-card-header">
            <span class="reaction-card-type">${escapeHtml(formatReactionType(reaction.type || 'reaction'))}</span>
            <span class="reaction-card-count">${formatCount(reaction.count || 0)}</span>
          </div>
          ${usersHtml}
        </div>
      `;
    }).join('');
  }

  function formatReactionType(type) {
    return String(type).replace(/_/g, ' ');
  }

  function formatCount(value) {
    return Number(value || 0).toLocaleString();
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
});
