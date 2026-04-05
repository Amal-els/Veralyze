const fs = require('fs');
const path = require('path');

const sizes = [16, 48, 128];
const outDir = path.join(__dirname, '..', 'assets');

sizes.forEach(s => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s}" viewBox="0 0 ${s} ${s}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#6366f1"/>
      <stop offset="1" stop-color="#a855f7"/>
    </linearGradient>
  </defs>
  <rect width="${s}" height="${s}" rx="${s * 0.15}" fill="#0f1123"/>
  <path d="M${s/2} ${s*0.12} Q${s*0.88} ${s*0.2} ${s*0.85} ${s*0.5} Q${s*0.75} ${s*0.82} ${s/2} ${s*0.9} Q${s*0.25} ${s*0.82} ${s*0.15} ${s*0.5} Q${s*0.12} ${s*0.2} ${s/2} ${s*0.12} Z" fill="url(#g)"/>
  <polyline points="${s*0.35},${s*0.52} ${s*0.45},${s*0.64} ${s*0.65},${s*0.38}" fill="none" stroke="#22c55e" stroke-width="${Math.max(1.5, s*0.06)}" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

  const filePath = path.join(outDir, `icon${s}.png`);
  // Chrome MV3 needs PNG icons. We'll save as SVG first, then use the HTML generator.
  // For now, save the SVG data as a workaround — the generate_icons.html can produce PNGs.
  fs.writeFileSync(filePath.replace('.png', '.svg'), svg);
  console.log(`Created icon${s}.svg`);
});

console.log('\nSVG icons created. To get PNGs:');
console.log('1. Open assets/generate_icons.html in Chrome');
console.log('2. Click each download link');
console.log('3. Save to assets/ folder');
