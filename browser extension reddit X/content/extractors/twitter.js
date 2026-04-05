window.TrustGraph = window.TrustGraph || {};

function parseCount(el) {
  if (!el) return null;

  const text = (el.innerText || '').replace(/,/g, '').trim();
  if (!text) return null;

  if (/k$/i.test(text)) return Math.round(parseFloat(text) * 1000);
  if (/m$/i.test(text)) return Math.round(parseFloat(text) * 1000000);

  const n = parseInt(text, 10);
  return Number.isNaN(n) ? null : n;
}

const TWITTER_POST_SELECTOR = [
  'article[data-testid="tweet"]',
  'article'
].join(', ');

window.TrustGraph.findTwitterPostElement = function (node) {
  const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
  if (!element) return null;

  const directArticle = element.closest?.(TWITTER_POST_SELECTOR);
  if (directArticle && isUsableTweet(directArticle)) {
    return directArticle;
  }

  const composedPath = typeof element.getRootNode === 'function' ? element.getRootNode() : document;
  const visibleTweets = [...document.querySelectorAll(TWITTER_POST_SELECTOR)].filter(isUsableTweet);
  const fallback = visibleTweets.find((tweet) => tweet.contains(element));
  if (fallback) return fallback;

  return visibleTweets[0] || null;
};

window.TrustGraph.extractTwitter = function (info = {}) {
  const root = info.targetElement || window.TrustGraph.findTwitterPostElement(document.activeElement) || document.querySelector(TWITTER_POST_SELECTOR);
  if (!root) return null;

  const authorLink = root.querySelector('[data-testid="User-Name"] a[href^="/"], a[href^="/"][role="link"]');
  const authorName = authorLink?.innerText?.trim() || null;
  const profileUrl = authorLink?.getAttribute('href') ? new URL(authorLink.getAttribute('href'), location.origin).href : null;

  const handle = [...root.querySelectorAll('a[href^="/"] span')]
    .map((el) => el.innerText?.trim())
    .find((value) => value?.startsWith('@')) || null;

  const timeEl = root.querySelector('time');
  const createdAt = timeEl?.getAttribute('datetime') || null;

  const textEl = root.querySelector('[data-testid="tweetText"]');
  const text = textEl?.innerText?.trim() || root.innerText?.trim() || null;

  const images = Array.from(root.querySelectorAll('img'))
    .map((img) => img.src)
    .filter((src) => src && src.includes('pbs.twimg.com/media'))
    .slice(0, 4);

  const likeEl = root.querySelector('[data-testid="like"] span');
  const replyEl = root.querySelector('[data-testid="reply"] span');
  const retweetEl = root.querySelector('[data-testid="retweet"] span');

  const likes = parseCount(likeEl);
  const commentsCount = parseCount(replyEl);
  const shares = parseCount(retweetEl);
  const comments = extractComments(root);
  const topReplyUsers = comments
    .slice()
    .sort((a, b) => (b.reaction_count || 0) - (a.reaction_count || 0))
    .slice(0, 5)
    .map((comment) => ({
      username: comment.author?.handle || comment.author?.name || 'unknown',
      reaction_type: 'reply',
      reaction_count: comment.reaction_count ?? 0
    }));

  return {
    platform: 'twitter',
    url: window.location.href,
    post: {
      text,
      created_at: createdAt,
      media: {
        images,
        videos: []
      }
    },
    author: {
      name: authorName,
      handle,
      profile_url: profileUrl
    },
    engagement: {
      likes,
      comments: commentsCount,
      shares
    },
    reactions: [
      { type: 'likes', count: likes || 0, top_users: [] },
      { type: 'replies', count: commentsCount || comments.length, top_users: topReplyUsers },
      { type: 'reposts', count: shares || 0, top_users: [] }
    ],
    comments
  };
};

function extractComments(root) {
  const allTweets = Array.from(document.querySelectorAll(TWITTER_POST_SELECTOR)).filter(isUsableTweet);
  const comments = [];

  if (window.location.pathname.includes('/status/')) {
    for (let i = 1; i < allTweets.length && comments.length < 20; i += 1) {
      const comment = extractCommentFromArticle(allTweets[i]);
      if (comment) comments.push(comment);
    }
    return comments;
  }

  const index = allTweets.indexOf(root);
  if (index === -1) return comments;

  for (let i = index + 1; i < allTweets.length && comments.length < 10; i += 1) {
    const el = allTweets[i];
    if (el.querySelector('[data-testid="socialContext"]')) break;
    if (el.innerText.includes('Promoted')) break;

    const comment = extractCommentFromArticle(el);
    if (comment) comments.push(comment);
  }

  return comments;
}

function extractCommentFromArticle(el) {
  const textEl = el.querySelector('[data-testid="tweetText"]');
  const text = textEl?.innerText?.trim();
  if (!text) return null;

  const nameEl = el.querySelector('[data-testid="User-Name"] span');
  const handle = [...el.querySelectorAll('a[href^="/"] span')]
    .map((node) => node.innerText?.trim())
    .find((value) => value?.startsWith('@')) || null;

  return {
    text,
    author: {
      name: nameEl?.innerText?.trim() || null,
      handle
    },
    reaction_count: parseCount(el.querySelector('[data-testid="like"] span')) ?? 0
  };
}

function isUsableTweet(el) {
  if (!el) return false;
  if (el.closest('[aria-label="Timeline: Trending now"]')) return false;
  if (el.innerText?.includes('Who to follow')) return false;
  if (el.innerText?.includes('Relevant people')) return false;
  if (el.querySelector('[data-testid="placementTracking"]') && !el.querySelector('[data-testid="tweetText"], time')) {
    return false;
  }

  return Boolean(
    el.querySelector('[data-testid="tweetText"]') ||
    el.querySelector('time') ||
    el.querySelector('[data-testid="User-Name"]')
  );
}
