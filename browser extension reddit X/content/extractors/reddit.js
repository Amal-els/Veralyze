// ============================================================
// Reddit Post Extractor
// ============================================================

window.TrustGraph = window.TrustGraph || {};

const REDDIT_SELECTORS = [
  'shreddit-post',
  '[data-testid="post-container"]',
  '.Post',
  '.thing.link',
  '.thing.self'
];

window.TrustGraph.findRedditPostElement = function (node) {
  return findClosest(node, REDDIT_SELECTORS);
};

window.TrustGraph.extractReddit = function (info = {}) {
  try {
    const url = window.location.href;
    const target = info.targetElement || window.TrustGraph.findRedditPostElement(document.activeElement) || document.querySelector(REDDIT_SELECTORS.join(','));

    if (!target) {
      return extractNearestRedditPost(url, info);
    }

    if (target.matches('shreddit-post')) {
      return extractNewReddit(target, url, info);
    }

    if (target.matches('[data-testid="post-container"], .Post')) {
      return extractLegacyReddit(target, url, info);
    }

    if (target.matches('.thing.link, .thing.self')) {
      return extractOldReddit(target, url, info);
    }

    return extractNearestRedditPost(url, info);
  } catch (err) {
    console.error('[TrustGraph:reddit] Extraction error:', err);
    return null;
  }
};

function extractNewReddit(el, url, info) {
  const title = el.getAttribute('post-title') ||
    el.querySelector('h1[slot="title"], [data-testid="post-title"]')?.textContent?.trim() ||
    document.querySelector('h1[slot="title"], [data-testid="post-title"]')?.textContent?.trim() || '';

  const author = el.getAttribute('author') ||
    el.querySelector('[data-testid="post_author_link"], .author')?.textContent?.trim() || 'unknown';

  const subreddit = el.getAttribute('subreddit-prefixed-name') ||
    el.querySelector('[data-testid="subreddit-name"]')?.textContent?.trim() || '';

  const bodyText = el.querySelector('[data-testid="post-rtjson-content"], .RichTextJSON-root, [slot="text-body"]')?.innerText?.trim() || '';
  const externalLink = el.getAttribute('content-href') || info.linkUrl || '';
  const score = el.getAttribute('score') || '0';
  const postUrl = el.getAttribute('permalink') ? `https://www.reddit.com${el.getAttribute('permalink')}` : url;
  const images = collectImages(el, 'img[src*="preview.redd.it"], img[src*="i.redd.it"]');
  const comments = extractRedditComments(document, 8);

  return buildRedditPayload({ title, author, subreddit, bodyText, externalLink, score, postUrl, images, url, comments });
}

function extractLegacyReddit(el, url, info) {
  const title = el.querySelector('h1, h3, [data-testid="post-title"]')?.textContent?.trim() || '';
  const author = el.querySelector('[data-testid="post_author_link"], .author')?.textContent?.trim() || 'unknown';
  const subreddit = el.querySelector('[data-testid="subreddit-name"], .subreddit')?.textContent?.trim() || '';
  const bodyText = el.querySelector('.RichTextJSON-root, .selftext, [data-testid="post-rtjson-content"]')?.innerText?.trim() || '';
  const score = el.querySelector('[data-testid="vote-arrows"] ~ *')?.textContent?.trim() || '0';
  const externalLink = info.linkUrl || '';
  const images = collectImages(el, 'img');
  const comments = extractRedditComments(document, 8);
  const postUrl = findRedditPermalink(el, url);

  return buildRedditPayload({ title, author, subreddit, bodyText, externalLink, score, postUrl, images, url, comments });
}

function extractOldReddit(el, url, info) {
  const title = el.querySelector('a.title')?.textContent?.trim() || document.title || '';
  const author = el.querySelector('.author')?.textContent?.trim() || 'unknown';
  const subreddit = el.querySelector('.subreddit')?.textContent?.trim() || '';
  const bodyText = el.querySelector('.expando .usertext-body')?.innerText?.trim() || '';
  const score = el.querySelector('.score.unvoted, .score.likes')?.textContent?.trim() || '0';
  const externalLink = el.querySelector('a.title')?.href || info.linkUrl || '';
  const images = collectImages(el, 'img');
  const comments = extractRedditComments(document, 8);
  const postUrl = findRedditPermalink(el, url);

  return buildRedditPayload({ title, author, subreddit, bodyText, externalLink, score, postUrl, images, url, comments });
}

function extractNearestRedditPost(url, info) {
  const title = document.title || '';
  const bodyText = info.selectionText || '';
  return buildRedditPayload({
    title,
    author: 'unknown',
    subreddit: '',
    bodyText,
    externalLink: info.linkUrl || '',
    score: '0',
    postUrl: url,
    images: [],
    url,
    comments: extractRedditComments(document, 8)
  });
}

function buildRedditPayload({ title, author, subreddit, bodyText, externalLink, score, postUrl, images, url, comments }) {
  const upvoteCount = parseCount(score);
  const commentCount = comments.total || parseCount(document.querySelector('[data-testid="comment-count"]')?.textContent || '') || comments.items.length;
  const topCommenters = comments.items
    .slice()
    .sort((a, b) => (b.reacts_count || 0) - (a.reacts_count || 0))
    .slice(0, 5)
    .map((comment) => ({
      username: comment.author || 'unknown',
      reaction_type: 'comment',
      reaction_count: comment.reacts_count ?? 0
    }));

  return {
    platform: 'reddit',
    url: postUrl || url,
    text: [title, bodyText].filter(Boolean).join('\n\n'),
    title,
    author,
    comments,
    reactions: [
      {
        type: 'upvotes',
        count: upvoteCount,
        top_users: []
      },
      {
        type: 'comments',
        count: commentCount,
        top_users: topCommenters
      }
    ],
    metadata: {
      subreddit,
      score,
      externalLink,
      pageUrl: url
    },
    images: images.slice(0, 5)
  };
}

function findClosest(node, selectors) {
  const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
  return element?.closest?.(selectors.join(',')) || null;
}

function collectImages(root, selector) {
  return [...root.querySelectorAll(selector)]
    .map((img) => img.src)
    .filter((src) => src && !src.includes('icon'));
}

function findRedditPermalink(root, fallbackUrl) {
  const candidates = [
    root.querySelector('a[data-testid="comments-page-link-num-comments"]'),
    root.querySelector('a[data-click-id="comments"]'),
    root.querySelector('a[href*="/comments/"]'),
    root.querySelector('shreddit-post')?.getAttribute?.('permalink')
  ];

  for (const candidate of candidates) {
    if (!candidate) continue;

    if (typeof candidate === 'string') {
      return candidate.startsWith('http') ? candidate : `https://www.reddit.com${candidate}`;
    }

    const href = candidate.getAttribute?.('href');
    if (!href) continue;
    try {
      return new URL(href, location.origin).href;
    } catch (_) {
      continue;
    }
  }

  return fallbackUrl;
}

function extractRedditComments(root, limit) {
  const selectors = [
    '[data-testid="comment"]',
    'shreddit-comment',
    '.Comment'
  ];
  const seen = new Set();
  const items = [];
  const nodes = selectors.flatMap((selector) => [...root.querySelectorAll(selector)]);

  for (const node of nodes) {
    if (!isCommentRoot(node)) continue;

    const text = node.querySelector('[data-testid="comment"], [data-testid="comment-body"], .md, p')?.innerText?.trim()
      || node.innerText?.trim()
      || '';
    const id = getCommentId(node, items.length);
    const dedupeKey = `${id}:${text}`;
    if (!text || seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);

    const author = node.getAttribute?.('author')
      || node.querySelector('[data-testid="comment_author_link"], .author, a[href*="/user/"]')?.textContent?.trim()
      || 'unknown';
    const scoreText = node.getAttribute?.('score')
      || node.querySelector('[data-testid="vote-arrows"] ~ *')?.textContent?.trim()
      || '0';
    const reactsCount = parseCount(scoreText);
    const parentId = getParentCommentId(node);
    const depth = getCommentDepth(node);
    items.push({
      id,
      parent_id: parentId,
      depth,
      text,
      author,
      reacts_count: reactsCount ?? 0
    });
    if (items.length >= limit) break;
  }

  return {
    total: items.length,
    items,
    thread: buildCommentThread(items)
  };
}

function isCommentRoot(node) {
  return Boolean(node?.matches?.('shreddit-comment, [data-testid="comment"], .Comment'));
}

function getCommentId(node, index) {
  const fallback = `comment-${index + 1}`;
  return node.getAttribute?.('thingid')
    || node.getAttribute?.('id')
    || node.dataset?.commentId
    || node.dataset?.fullname
    || fallback;
}

function getParentCommentId(node) {
  const attrParent = node.getAttribute?.('parent-comment-id')
    || node.getAttribute?.('parentid')
    || node.dataset?.parentCommentId
    || node.dataset?.parentId;
  if (attrParent) return attrParent;

  const parentNode = node.parentElement?.closest?.('shreddit-comment, [data-testid="comment"], .Comment');
  if (!parentNode || parentNode === node) return null;
  return getCommentId(parentNode, -1);
}

function getCommentDepth(node) {
  const attrDepth = node.getAttribute?.('depth') || node.dataset?.depth;
  if (attrDepth !== undefined && attrDepth !== null && attrDepth !== '') {
    const parsed = parseInt(attrDepth, 10);
    if (!Number.isNaN(parsed)) return parsed;
  }

  let depth = 0;
  let current = node.parentElement?.closest?.('shreddit-comment, [data-testid="comment"], .Comment');
  while (current) {
    depth += 1;
    current = current.parentElement?.closest?.('shreddit-comment, [data-testid="comment"], .Comment');
  }
  return depth;
}

function buildCommentThread(items) {
  const nodeMap = new Map();
  const roots = [];

  for (const item of items) {
    nodeMap.set(item.id, {
      ...item,
      replies: []
    });
  }

  for (const item of items) {
    const current = nodeMap.get(item.id);
    const parent = item.parent_id ? nodeMap.get(item.parent_id) : null;
    if (parent) {
      parent.replies.push(current);
    } else {
      roots.push(current);
    }
  }

  return roots;
}

function parseCount(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).replace(/,/g, '').trim();
  const match = text.match(/([\d.]+)\s*([kKmM]?)/);
  if (!match) return null;
  let count = parseFloat(match[1]);
  const suffix = match[2].toLowerCase();
  if (suffix === 'k') count *= 1000;
  if (suffix === 'm') count *= 1000000;
  return Math.round(count);
}
