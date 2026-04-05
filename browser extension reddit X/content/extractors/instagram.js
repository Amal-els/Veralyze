// ============================================================
// Instagram Post Extractor
// ============================================================

window.TrustGraph = window.TrustGraph || {};

window.TrustGraph.findInstagramPostElement = function (node) {
  const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
  return element?.closest?.('article') || null;
};

window.TrustGraph.extractInstagram = function (info = {}) {
  try {
    const url = window.location.href;
    const article = info.targetElement || window.TrustGraph.findInstagramPostElement(document.activeElement) || document.querySelector('article');

    if (!article) {
      return extractInstagramFallback(url, info);
    }

    const captionEl = article.querySelector(
      'h1._aacl, div._a9zs, span[class*="caption"], [data-testid="post-comment-root"] span, ul > li:first-child span'
    );
    const caption = captionEl?.innerText?.trim() || getMetaContent('og:description') || info.selectionText || '';

    const authorEl = article.querySelector('header span._aacl, header a._acan, header h2, header span, header a');
    const author = authorEl?.innerText?.trim() || getMetaContent('og:site_name') || 'instagram_user';
    const profileLinkEl = article.querySelector('header a[href^="/"]');
    const profileLink = profileLinkEl ? new URL(profileLinkEl.getAttribute('href'), location.origin).href : '';

    const images = [...article.querySelectorAll('img')]
      .filter((img) => img.src && img.naturalWidth > 50 && !img.src.includes('profile'))
      .map((img) => img.src);

    const hashtags = [...(caption.match(/#[\w]+/g) || [])];
    const altTexts = [...article.querySelectorAll('img[alt]')]
      .map((img) => img.alt)
      .filter((alt) => alt && alt.length > 10);

    const timestamp = article.querySelector('time')?.getAttribute('datetime') || '';
    const imageUrl = images[0] || getMetaContent('og:image') || '';
    const videoUrl = article.querySelector('video')?.src || getMetaContent('og:video') || '';
    const reactsCount = extractInstagramReactsCount(article);
    const comments = extractInstagramComments(article, 20);
    const postUrl = findInstagramPostUrl(article, url);
    const topCommenters = comments.items.map((comment) => ({
      username: comment.author || 'unknown',
      reaction_type: 'comment',
      reaction_count: comment.reacts_count ?? 0
    }));

    return buildInstagramPayload({
      caption,
      author,
      profileLink,
      images,
      hashtags,
      altTexts,
      url: postUrl,
      imageUrl,
      videoUrl,
      timestamp,
      reactsCount,
      comments,
      reactions: [
        { type: 'likes', count: reactsCount || 0, top_users: [] },
        { type: 'comments', count: comments.total || comments.items.length, top_users: topCommenters }
      ]
    });
  } catch (err) {
    console.error('[TrustGraph:instagram] Extraction error:', err);
    return null;
  }
};

function extractInstagramFallback(url, info) {
  const caption = getMetaContent('og:description') || info.selectionText || '';
  const author = getMetaContent('og:title') || 'instagram_user';
  const ogImage = getMetaContent('og:image');
  const canonicalUrl = getMetaContent('og:url') || url;

  return buildInstagramPayload({
    caption,
    author,
    profileLink: '',
    images: ogImage ? [ogImage] : [],
    hashtags: [...(caption.match(/#[\w]+/g) || [])],
    altTexts: [],
    url: canonicalUrl,
    imageUrl: ogImage || '',
    videoUrl: getMetaContent('og:video') || '',
    timestamp: '',
    reactsCount: 0,
    comments: { total: 0, items: [] },
    reactions: [
      { type: 'likes', count: 0, top_users: [] },
      { type: 'comments', count: 0, top_users: [] }
    ]
  });
}

function buildInstagramPayload({ caption, author, profileLink, images, hashtags, altTexts, url, imageUrl, videoUrl, timestamp, reactsCount, comments, reactions }) {
  return {
    platform: 'instagram',
    url,
    text: caption,
    author,
    image_url: imageUrl || images?.[0] || '',
    vid_url: videoUrl || '',
    timestamp: timestamp || '',
    user: {
      name: author || '',
      profile_link: profileLink || ''
    },
    nbre_of_reacts: reactsCount || 0,
    comments: comments || { total: 0, items: [] },
    reactions: reactions || [],
    metadata: {
      hashtags,
      altTexts,
      pageUrl: url
    },
    images: images.slice(0, 5)
  };
}

function getMetaContent(property) {
  return document.querySelector(`meta[property="${property}"]`)?.content ||
    document.querySelector(`meta[name="${property}"]`)?.content || '';
}

function findInstagramPostUrl(article, fallbackUrl) {
  const link = article.querySelector('a[href*="/p/"], a[href*="/reel/"], a[href*="/tv/"]');
  const href = link?.getAttribute('href') || getMetaContent('og:url') || fallbackUrl;

  try {
    return new URL(href, location.origin).href;
  } catch (_) {
    return fallbackUrl;
  }
}

function extractInstagramReactsCount(article) {
  const likeTextCandidates = [
    article.querySelector('section span a span')?.textContent,
    article.querySelector('section span span')?.textContent,
    article.querySelector('section button span')?.textContent,
    getMetaContent('og:description')
  ];

  for (const text of likeTextCandidates) {
    const count = parseCountFromText(text || '');
    if (count !== null) return count;
  }
  return 0;
}

function extractInstagramComments(article, limit) {
  const items = [];
  const listItems = [...article.querySelectorAll('ul > li')];

  for (const li of listItems) {
    const timeEl = li.querySelector('time');
    const spans = [...li.querySelectorAll('span')];
    const text = spans.map((span) => span.innerText?.trim()).filter(Boolean).pop() || '';
    if (!text || text.toLowerCase().includes('view all')) continue;

    const likeBtn = li.querySelector('button');
    const likeCount = parseCountFromText(likeBtn?.getAttribute('aria-label') || likeBtn?.innerText || '') ?? 0;
    const author = li.querySelector('h3, a[href^="/"]')?.innerText?.trim() || 'unknown';
    items.push({
      text,
      author,
      reacts_count: likeCount,
      reacts: [],
      react_timestamps: [],
      timestamp: timeEl?.getAttribute('datetime') || ''
    });
  }

  const total = extractInstagramCommentTotal(article, items.length);
  const sorted = items.sort((a, b) => (b.reacts_count || 0) - (a.reacts_count || 0));
  return { total, items: sorted.slice(0, limit) };
}

function extractInstagramCommentTotal(article, fallback) {
  const viewAllEl = [...article.querySelectorAll('a, button, span')]
    .map((el) => el.innerText?.trim())
    .find((text) => text && /view all/i.test(text));

  const count = parseCountFromText(viewAllEl || '');
  return count !== null ? count : fallback;
}

function parseCountFromText(text) {
  if (!text) return null;
  const match = text.replace(/,/g, '').match(/([\d.]+)\s*([kKmM]?)/);
  if (!match) return null;
  let value = parseFloat(match[1]);
  const suffix = match[2].toLowerCase();
  if (suffix === 'k') value *= 1000;
  if (suffix === 'm') value *= 1000000;
  return Math.round(value);
}
