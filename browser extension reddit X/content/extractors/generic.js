/**
 * Generic extractor
 *
 * Catch-all fallback for any unrecognised platform.
 * Prioritises user-selected text, then semantic regions, then body.
 */

window.__genericExtractor = function extract(contextInfo) {
  return {
    platform: "generic",
    url:      window.location.href,
    post: {
      text:       extractText(contextInfo),
      created_at: extractTimestamp(),
      media: {
        images: extractImages(),
        videos: extractVideos(),
      },
    },
    author:     extractAuthor(),
    engagement: { likes: null, comments: null, shares: null },
    comments:   [],
  };
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function extractText(contextInfo) {
  // 1. Selection text passed from the context menu event
  if (contextInfo?.selectionText?.trim()) return contextInfo.selectionText.trim();

  // 2. Live window selection
  const selected = window.getSelection()?.toString().trim();
  if (selected?.length > 10) return selected;

  // 3. Semantic content regions
  const semantic =
    document.querySelector("article") ??
    document.querySelector("main") ??
    document.querySelector("[role='main']");
  if (semantic) return semantic.innerText.trim();

  // 4. Full body fallback
  return document.body.innerText.trim();
}

function extractTimestamp() {
  const time = document.querySelector("time[datetime]");
  if (time) return time.getAttribute("datetime");

  const meta = document.querySelector(
    "meta[property='article:published_time'], meta[name='date']"
  );
  return meta?.getAttribute("content") ?? null;
}

function extractImages() {
  const candidates = [];

  // Open Graph image is the highest-quality signal
  const ogImage = document
    .querySelector("meta[property='og:image']")
    ?.getAttribute("content");
  if (ogImage) candidates.push(ogImage);

  // Visible content images (skip tracking pixels and icons)
  for (const img of document.querySelectorAll("img[src]")) {
    if (candidates.length >= 3) break;
    if (img.naturalWidth > 100 && img.naturalHeight > 100) {
      candidates.push(img.src);
    }
  }

  return [...new Set(candidates)].slice(0, 3);
}

function extractVideos() {
  return Array.from(document.querySelectorAll("video[src]"))
    .map((v) => v.src)
    .filter(Boolean)
    .slice(0, 3);
}

function extractAuthor() {
  const metaAuthor = document
    .querySelector("meta[name='author']")
    ?.getAttribute("content");
  if (metaAuthor) {
    return { name: metaAuthor, handle: null, profile_url: null };
  }

  const schemaName = document
    .querySelector("[itemprop='author'] [itemprop='name']")
    ?.textContent.trim();
  if (schemaName) {
    return { name: schemaName, handle: null, profile_url: null };
  }

  return { name: null, handle: null, profile_url: null };
}
