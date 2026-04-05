// ============================================================
// Trust Graph Engine - Background Service Worker (MV3)
// Handles backend analysis requests and popup state
// ============================================================

const DEFAULT_API_URL = 'http://localhost:8000';

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.sync.get(['apiUrl', 'extractionModeEnabled'], (result) => {
    const updates = {};
    if (!result.apiUrl) {
      updates.apiUrl = DEFAULT_API_URL;
    }
    if (typeof result.extractionModeEnabled !== 'boolean') {
      updates.extractionModeEnabled = false;
    }
    if (Object.keys(updates).length > 0) {
      chrome.storage.sync.set(updates);
    }
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'analyzePayload') {
    analyzePayload(message.payload)
      .then((response) => sendResponse({ ok: true, ...response }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message.action === 'getLastResult') {
    chrome.storage.local.get(['lastResult', 'lastPayload'], (data) => {
      sendResponse({
        lastResult: data.lastResult || null,
        lastPayload: data.lastPayload || null
      });
    });
    return true;
  }

  return false;
});

async function analyzePayload(payload) {
  if (!payload || payload.error) {
    throw new Error(payload?.error || 'No extracted payload to analyze.');
  }

  const enrichedPayload = await enrichPayload(payload);

  const { apiUrl } = await chrome.storage.sync.get(['apiUrl']);
  const endpoint = `${(apiUrl || DEFAULT_API_URL).replace(/\/+$/, '')}/analyze`;

  let result;
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(enrichedPayload),
      signal: AbortSignal.timeout(30000)
    });

    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}: ${response.statusText}`);
    }

    result = await response.json();
  } catch (fetchError) {
    console.warn('[TrustGraph] Backend unreachable, using mock response:', fetchError.message);
    result = generateMockResult(enrichedPayload);
  }

  await chrome.storage.local.set({
    lastPayload: enrichedPayload,
    lastResult: {
      ...result,
      platform: enrichedPayload.platform,
      postUrl: enrichedPayload.url,
      timestamp: Date.now()
    }
  });

  return { result, payload: enrichedPayload };
}

async function enrichPayload(payload) {
  if (!shouldHydrateComments(payload)) {
    return payload;
  }

  try {
    const hydrated = await extractPayloadFromTab(payload.url);
    if (!hydrated || hydrated.error || hydrated.platform !== payload.platform) {
      return payload;
    }

    if (payload.platform === 'reddit') {
      return mergeRedditPayload(payload, hydrated);
    }
    if (payload.platform === 'instagram') {
      return mergeInstagramPayload(payload, hydrated);
    }
    return payload;
  } catch (error) {
    console.warn('[TrustGraph] Post hydration failed:', error.message);
    return payload;
  }
}

function shouldHydrateComments(payload) {
  if (!payload?.url) {
    return false;
  }

  const currentTotal = payload.comments?.total ?? payload.comments?.items?.length ?? 0;
  if (payload.platform === 'reddit') {
    return currentTotal < 2;
  }
  if (payload.platform === 'instagram') {
    return currentTotal < 1 && /instagram\.com\/(p|reel|tv)\//.test(payload.url);
  }
  return false;
}

async function extractPayloadFromTab(url) {
  const tab = await chrome.tabs.create({ url, active: false });

  try {
    await waitForTabComplete(tab.id, 20000);
    await delay(1200);
    const extracted = await sendExtractMessage(tab.id);
    return extracted;
  } finally {
    await chrome.tabs.remove(tab.id).catch(() => {});
  }
}

function waitForTabComplete(tabId, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(onUpdated);
      reject(new Error('Timed out waiting for Reddit post tab to load.'));
    }, timeoutMs);

    chrome.tabs.get(tabId).then((tab) => {
      if (tab?.status === 'complete') {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(onUpdated);
        resolve();
      }
    }).catch(() => {});

    function onUpdated(updatedTabId, info) {
      if (updatedTabId !== tabId || info.status !== 'complete') {
        return;
      }
      clearTimeout(timeout);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      resolve();
    }

    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

async function sendExtractMessage(tabId) {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      const response = await chrome.tabs.sendMessage(tabId, {
        action: 'extractPost',
        info: {}
      });
      if (response) {
        return response;
      }
    } catch (_) {
      // Wait for the content script to become available on the new tab.
    }
    await delay(500);
  }

  throw new Error('Could not extract Reddit post from hydrated tab.');
}

function mergeRedditPayload(basePayload, hydratedPayload) {
  const merged = {
    ...basePayload,
    comments: hydratedPayload.comments || basePayload.comments,
    images: hydratedPayload.images?.length ? hydratedPayload.images : basePayload.images,
    metadata: {
      ...(basePayload.metadata || {}),
      ...(hydratedPayload.metadata || {}),
      hydratedFromPostUrl: true
    }
  };

  if (hydratedPayload.reactions?.length) {
    merged.reactions = hydratedPayload.reactions;
  }

  if ((!merged.text || merged.text.length < (hydratedPayload.text || '').length) && hydratedPayload.text) {
    merged.text = hydratedPayload.text;
  }

  if (!merged.title && hydratedPayload.title) {
    merged.title = hydratedPayload.title;
  }

  return merged;
}

function mergeInstagramPayload(basePayload, hydratedPayload) {
  const merged = {
    ...basePayload,
    comments: hydratedPayload.comments || basePayload.comments,
    images: hydratedPayload.images?.length ? hydratedPayload.images : basePayload.images,
    image_url: hydratedPayload.image_url || basePayload.image_url,
    vid_url: hydratedPayload.vid_url || basePayload.vid_url,
    text: hydratedPayload.text || basePayload.text,
    user: {
      ...(basePayload.user || {}),
      ...(hydratedPayload.user || {})
    },
    metadata: {
      ...(basePayload.metadata || {}),
      ...(hydratedPayload.metadata || {}),
      hydratedFromPostUrl: true
    }
  };

  if (hydratedPayload.reactions?.length) {
    merged.reactions = hydratedPayload.reactions;
  }

  if (typeof hydratedPayload.nbre_of_reacts === 'number') {
    merged.nbre_of_reacts = hydratedPayload.nbre_of_reacts;
  }

  return merged;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function generateMockResult(payload) {
  const seed = payload.text?.length || 400;
  const score = Math.min(95, Math.max(10, (seed * 7 + 42) % 90));
  const verdict = score >= 70 ? 'trusted' : score >= 40 ? 'uncertain' : 'suspicious';
  const subscores = {
    authenticity: Math.min(100, score + Math.floor(Math.random() * 15) - 7),
    context: Math.min(100, score + Math.floor(Math.random() * 20) - 10),
    source: Math.min(100, score + Math.floor(Math.random() * 12) - 6)
  };
  const explanations = {
    trusted: 'The content appears credible. The source has a good track record and the claims align with known context.',
    uncertain: 'Some aspects of this post require caution. Cross-check with authoritative sources before sharing.',
    suspicious: 'This post shows multiple red flags, including weak source signals and manipulative framing.'
  };

  return {
    trust_score: score,
    verdict,
    subscores,
    explanation: explanations[verdict],
    graph_nodes: [
      { id: 'post', label: 'Post', score, type: 'post' },
      { id: 'source', label: payload.author || payload.user?.name || 'Author', score: subscores.source, type: 'source' },
      { id: 'claim1', label: 'Claim', score: subscores.authenticity, type: 'claim' },
      { id: 'context', label: 'Context', score: subscores.context, type: 'context' }
    ],
    graph_edges: [
      { from: 'source', to: 'post', weight: 0.8 },
      { from: 'post', to: 'claim1', weight: 0.6 },
      { from: 'post', to: 'context', weight: 0.7 }
    ],
    metadata: { mock: true, platform: payload.platform }
  };
}
