// Renders the title card, end card and caption overlays as PNGs.
// Usage: node render_cards.js OUT_DIR ICON_SVG   (needs the playwright package)
const { chromium } = require('playwright');
const fs = require('fs');
const dir = process.argv[2];
const icon = fs.readFileSync(process.argv[3], 'utf8');
const base = `
  * { box-sizing: border-box; margin: 0; }
  body { font-family: Cantarell, "DejaVu Sans", sans-serif; color: #f4f4f8; }
  kbd { font: 600 0.82em "DejaVu Sans Mono", monospace; padding: 3px 9px; border-radius: 7px;
        background: #2b2f3f; border: 1px solid #454a5e; border-bottom-width: 3px; margin: 0 2px; }
  .arrow { color: #8b90a8; padding: 0 4px; }
  b { color: #fff; }
`;
const card = (inner) => `<html><head><style>${base}
  body { width: 1280px; height: 800px; display: grid; place-items: center; text-align: center;
         background: radial-gradient(1200px 700px at 20% 110%, #1f5a3d55, transparent 60%),
                     radial-gradient(900px 600px at 95% -10%, #7a1e3a66, transparent 60%),
                     radial-gradient(900px 700px at 80% 110%, #4b2a6e66, transparent 60%),
                     linear-gradient(180deg, #161333, #0b1020); }
  .logo svg { width: 132px; height: 132px; filter: drop-shadow(0 18px 30px #0008); }
  h1 { font-size: 84px; font-weight: 800; letter-spacing: -2px; margin-top: 10px; }
  .tag { font-size: 34px; font-weight: 700; margin-top: 6px;
         background: linear-gradient(90deg, #62a0ea, #c061cb 45%, #ed333b 75%, #f6a03b);
         -webkit-background-clip: text; color: transparent; }
  .sub { font-size: 21px; color: #b8bbcc; margin-top: 18px; }
  .pills { display: flex; gap: 12px; justify-content: center; margin-top: 30px; }
  .pill { font-size: 18px; padding: 8px 16px; border-radius: 99px; background: #ffffff14; border: 1px solid #ffffff22; }
  .url { font: 600 22px "DejaVu Sans Mono", monospace; margin-top: 26px; color: #e6e6ef; }
</style></head><body><div>${inner}</div></body></html>`;

const captions = {
  A: 'Your files in Files. Roue waits quietly in the background.',
  B: 'Press <kbd>Super</kbd> + <kbd>Shift</kbd> + <kbd>D</kbd>: the wheel opens at your pointer',
  C: 'Drop a photo on a slice. <b>HEIC</b><span class="arrow">→</span><b>JPG</b>, saved right next to it.',
  D: 'Or right-click in Files<span class="arrow">→</span><b>Convert with Roue…</b>',
  E: 'The wheel shows what fits. <b>Under 10 MB</b> sizes a video for chat.',
  G: 'On X11, hold <kbd>Shift</kbd> while dragging: the wheel comes to you',
  H: 'Release <kbd>Shift</kbd> and drop on a slice',
  I: 'The same presets work from the terminal',
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.setContent(card(`
    <div class="logo">${icon}</div>
    <h1>Roue</h1>
    <div class="tag">Drop a file. Get the file you wanted.</div>
    <div class="sub">A drag-and-drop file converter for the Linux desktop</div>`));
  await page.screenshot({ path: `${dir}/title.png` });
  await page.setContent(card(`
    <div class="logo">${icon}</div>
    <h1>Roue</h1>
    <div class="tag">Drop a file. Get the file you wanted.</div>
    <div class="pills"><span class="pill">100% local</span><span class="pill">No uploads, no telemetry</span>
      <span class="pill">27 presets</span><span class="pill">GPL-3.0</span></div>
    <div class="url">github.com/guilyx/roue</div>`));
  await page.screenshot({ path: `${dir}/end.png` });

  const cap = await browser.newPage({ viewport: { width: 1280, height: 80 } });
  for (const [id, html] of Object.entries(captions)) {
    await cap.setContent(`<html><head><style>${base}
      body { background: transparent; }
      #c { display: inline-block; font-size: 25px; font-weight: 600; padding: 8px 4px; white-space: nowrap; }
    </style></head><body><span id="c">${html}</span></body></html>`);
    await cap.locator('#c').screenshot({ path: `${dir}/cap-${id}.png`, omitBackground: true });
  }
  // Small wordmark for the left of the caption band.
  await cap.setContent(`<html><head><style>${base} body{background:transparent}
    #w{display:inline-flex;align-items:center;gap:10px;font-size:22px;font-weight:800;padding:4px}
    #w svg{width:38px;height:38px}</style></head><body><span id="w">${icon}Roue</span></body></html>`);
  await cap.locator('#w').screenshot({ path: `${dir}/mark.png`, omitBackground: true });
  await browser.close();
})();
