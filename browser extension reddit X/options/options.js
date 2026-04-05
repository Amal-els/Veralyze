// ============================================================
// Trust Graph — Options Page Script
// Loads/saves settings, tests backend connection
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {

  // ── Elements ──────────────────────────────────────────────────
  const apiUrlEl       = document.getElementById('api-url');
  const apiKeyEl       = document.getElementById('api-key');
  const demoModeEl     = document.getElementById('demo-mode');
  const includeImgEl   = document.getElementById('include-images');
  const showBadgeEl    = document.getElementById('show-badge');
  const enableRedditEl = document.getElementById('enable-reddit');
  const enableInstaEl  = document.getElementById('enable-instagram');
  const btnTest        = document.getElementById('btn-test');
  const btnSave        = document.getElementById('btn-save');
  const statusRow      = document.getElementById('connection-status');
  const statusIcon     = document.getElementById('status-icon');
  const statusText     = document.getElementById('status-text');
  const saveFeedback   = document.getElementById('save-feedback');

  // ── Load saved settings ───────────────────────────────────────
  const defaults = {
    apiUrl: 'http://localhost:8000',
    apiKey: '',
    demoMode: true,
    includeImages: true,
    showBadge: true,
    enableReddit: true,
    enableInstagram: true
  };

  const stored = await chrome.storage.sync.get(Object.keys(defaults));
  const settings = { ...defaults, ...stored };

  apiUrlEl.value           = settings.apiUrl;
  apiKeyEl.value           = settings.apiKey;
  demoModeEl.checked       = settings.demoMode;
  includeImgEl.checked     = settings.includeImages;
  showBadgeEl.checked      = settings.showBadge;
  enableRedditEl.checked   = settings.enableReddit;
  enableInstaEl.checked    = settings.enableInstagram;

  // ── Save ──────────────────────────────────────────────────────
  btnSave.addEventListener('click', async () => {
    const newSettings = {
      apiUrl:          apiUrlEl.value.replace(/\/+$/, '') || defaults.apiUrl,
      apiKey:          apiKeyEl.value,
      demoMode:        demoModeEl.checked,
      includeImages:   includeImgEl.checked,
      showBadge:       showBadgeEl.checked,
      enableReddit:    enableRedditEl.checked,
      enableInstagram: enableInstaEl.checked
    };

    await chrome.storage.sync.set(newSettings);

    saveFeedback.classList.remove('hidden');
    setTimeout(() => saveFeedback.classList.add('hidden'), 2500);
  });

  // ── Test Connection ───────────────────────────────────────────
  btnTest.addEventListener('click', async () => {
    const url = apiUrlEl.value.replace(/\/+$/, '') || defaults.apiUrl;

    statusRow.classList.remove('hidden', 'success', 'error');
    statusRow.classList.add('loading');
    statusIcon.textContent = '⏳';
    statusText.textContent = 'Testing connection…';

    try {
      const response = await fetch(url + '/health', {
        method: 'GET',
        signal: AbortSignal.timeout(8000)
      });

      if (response.ok) {
        statusRow.classList.remove('loading');
        statusRow.classList.add('success');
        statusIcon.textContent = '✅';
        statusText.textContent = `Connected! Server responded ${response.status}`;
      } else {
        throw new Error(`Server responded with ${response.status}`);
      }
    } catch (err) {
      statusRow.classList.remove('loading');
      statusRow.classList.add('error');
      statusIcon.textContent = '❌';
      statusText.textContent = `Failed: ${err.message}`;
    }
  });

});
