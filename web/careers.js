/* Advice Career Pathways.
 *
 * Reads data/careers.json (or an inlined window.__CAREERS__ when exported as a
 * single file). No dependencies.
 *
 * The company detail opens on hover, which is what was asked for, but hover is
 * only one of three ways in: it also opens on keyboard focus and on tap, and
 * those two pin it open with a backdrop and an Escape handler. A panel that
 * only ever appears on hover is unreachable on a phone and invisible to a
 * screen reader, so the hover is the convenience and the click is the contract.
 */

const CAREERS_URL = '../data/careers.json';

const state = { data: null, country: 'USA', pinned: false, current: null };

const $ = (sel, root = document) => root.querySelector(sel);
const colorOf = (iso3) => `var(--c-${iso3})`;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

const market = (iso3) => state.data.markets.find((m) => m.iso3 === iso3);

/* ── country picker ───────────────────────────────────────────────────── */

function renderCountryFilter() {
  const host = $('#country-filter');
  host.textContent = '';
  for (const entry of state.data.markets) {
    host.append(el('button', {
      type: 'button',
      'aria-pressed': entry.iso3 === state.country ? 'true' : 'false',
      onClick: () => { state.country = entry.iso3; closeModal(); renderAll(); },
    }, el('span', { class: 'swatch', style: `background:${colorOf(entry.iso3)}` }), entry.short));
  }
}

/* ── pathway ──────────────────────────────────────────────────────────── */

function renderPathway() {
  const iso3 = state.country;
  const entry = state.data.countries[iso3];
  const accent = colorOf(iso3);
  document.documentElement.style.setProperty('--accent', accent);

  $('#headline').textContent = entry.headline;

  const facts = $('#facts');
  facts.textContent = '';
  const rows = [
    ['Regulator', entry.regulators, false],
    ['Core designation', entry.designation, true],
    ['Typical time', entry.typical_time, true],
    ['The gate', entry.gate, false],
  ];
  for (const [label, value, mono] of rows) {
    facts.append(el('dl', { class: 'fact' },
      el('dt', {}, label),
      el('dd', { class: mono ? 'mono' : null }, value)));
  }

  const list = $('#pathway');
  list.textContent = '';
  for (const step of entry.steps) {
    list.append(el('li', {},
      el('span', { class: 'step-n', style: `border-color:${accent}` }, String(step.n)),
      el('div', { class: 'step-body' },
        el('p', { class: 'step-title' }, step.title),
        el('p', { class: 'step-detail' }, step.detail),
        step.body ? el('span', { class: 'step-body-tag' }, step.body) : null)));
  }

  const shortcut = $('#shortcut');
  if (entry.shortcut) {
    shortcut.textContent = entry.shortcut;
    shortcut.hidden = false;
    shortcut.style.borderLeftColor = accent;
  } else {
    shortcut.hidden = true;
  }

  $('#cpd').textContent = entry.cpd;

  const bodies = $('#bodies');
  bodies.textContent = '';
  for (const body of entry.bodies) {
    bodies.append(el('li', {},
      el('a', { href: body.url, target: '_blank', rel: 'noopener' }, body.name)));
  }
}

/* ── companies ────────────────────────────────────────────────────────── */

function renderCompanies() {
  const iso3 = state.country;
  const host = $('#companies');
  host.textContent = '';
  const list = state.data.companies[iso3] || [];

  $('#companies-note').textContent =
    `${list.length} firms across ${market(iso3).name}'s advice, asset management and banking industries. `
    + 'Figures carry the date they were reported — treat anything undated as directional.';

  list.forEach((company, index) => {
    const card = el('button', {
      class: 'company',
      type: 'button',
      'aria-expanded': 'false',
      style: `--accent:${colorOf(iso3)}`,
      onClick: (event) => { event.stopPropagation(); togglePinned(card, company, index); },
      onFocus: () => openModal(card, company, index, true),
      onPointerenter: (event) => {
        // Touch fires pointerenter immediately before click; letting it open on
        // hover there would make the first tap open and the second close.
        if (event.pointerType === 'touch' || state.pinned) return;
        if (samePlace(event)) return;   // the panel we just dismissed, reopening itself
        dismissPos = null;
        openModal(card, company, index, false);
      },
      onPointerleave: (event) => {
        if (event.pointerType === 'touch' || state.pinned) return;
        scheduleClose();
      },
    },
      el('span', { class: 'company-name' }, company.name),
      el('span', { class: 'company-ticker' }, company.ticker),
      el('span', { class: 'company-segment' }, company.segment),
      el('span', { class: 'company-scale' }, company.scale));
    host.append(card);
  });
}

/* ── the modal ────────────────────────────────────────────────────────── */

let closeTimer = null;

/* Dismissing a pinned panel hides the backdrop, which changes what sits under
 * the cursor — so the browser fires a fresh pointerenter on the card beneath
 * and the panel springs straight back open.
 *
 * The tell is that the synthetic enter arrives at the exact pixel the dismiss
 * happened at, because the pointer never moved. So we remember where the
 * dismiss was and ignore an enter at that same spot. Suppressing hover
 * wholesale until the next pointermove looks equivalent but is not: enter
 * fires before move, so the first genuine hover after any dismiss — including
 * after switching country — would be swallowed too. */
let pointerPos = { x: -1, y: -1 };
let dismissPos = null;

function samePlace(event) {
  return dismissPos
    && Math.abs(event.clientX - dismissPos.x) < 3
    && Math.abs(event.clientY - dismissPos.y) < 3;
}

const modal = () => $('#company-modal');
const backdrop = () => $('#modal-backdrop');

function scheduleClose() {
  clearTimeout(closeTimer);
  // A gap between card and panel would otherwise close it mid-travel.
  closeTimer = setTimeout(() => { if (!state.pinned) closeModal(); }, 140);
}

function buildModal(company, iso3) {
  const box = modal();
  box.textContent = '';
  box.style.setProperty('--accent', colorOf(iso3));

  box.append(el('h3', { id: 'modal-title' }, company.name));
  // No separator characters: they dangle at the end of a wrapped line and
  // read as a typo. The gap does the same job and survives wrapping.
  box.append(el('p', { class: 'modal-meta' },
    el('span', {}, company.ticker),
    el('span', {}, company.hq),
    el('span', {}, company.scale)));

  for (const [heading, text] of [
    ['What it does', company.what],
    ['Why watch it', company.why_watch],
    ['Getting in', company.entry],
  ]) {
    box.append(el('div', { class: 'modal-section' },
      el('h4', {}, heading), el('p', {}, text)));
  }

  box.append(el('div', { class: 'modal-foot' },
    el('a', { href: company.url, target: '_blank', rel: 'noopener' }, 'Careers site ↗'),
    el('button', {
      class: 'modal-close', type: 'button',
      onClick: (event) => { event.stopPropagation(); closeModal(); },
    }, 'Close')));
}

function position(card) {
  const box = modal();
  // The bottom-sheet breakpoint positions itself in CSS; leave it alone.
  if (window.matchMedia('(max-width: 520px)').matches) return;

  const rect = card.getBoundingClientRect();
  const width = box.offsetWidth;
  const height = box.offsetHeight;
  const margin = 10;

  let left = rect.left + window.scrollX;
  // Keep it on screen: flip to the card's right edge near the viewport edge.
  if (left + width > window.innerWidth - margin) {
    left = rect.right + window.scrollX - width;
  }
  left = Math.max(margin, left);

  // Below the card unless there is no room, in which case above it.
  let top = rect.bottom + window.scrollY + 8;
  if (rect.bottom + height + 8 > window.innerHeight - margin) {
    const above = rect.top + window.scrollY - height - 8;
    if (above > window.scrollY + margin) top = above;
  }
  box.style.left = `${left}px`;
  box.style.top = `${top}px`;
}

function openModal(card, company, index, pinned) {
  clearTimeout(closeTimer);
  dismissPos = null;
  const box = modal();
  buildModal(company, state.country);
  box.hidden = false;
  position(card);

  state.current = index;
  state.pinned = pinned;
  backdrop().hidden = !pinned;
  card.setAttribute('aria-expanded', pinned ? 'true' : 'false');
}

function togglePinned(card, company, index) {
  if (state.pinned && state.current === index) { closeModal(); return; }
  openModal(card, company, index, true);
}

function closeModal() {
  clearTimeout(closeTimer);
  dismissPos = { ...pointerPos };
  modal().hidden = true;
  backdrop().hidden = true;
  state.pinned = false;
  state.current = null;
  document.querySelectorAll('.company[aria-expanded="true"]')
    .forEach((node) => node.setAttribute('aria-expanded', 'false'));
}

/* ── static sections ──────────────────────────────────────────────────── */

function renderMethod() {
  const host = $('#method');
  host.textContent = '';

  host.append(el('div', {},
    el('h3', {}, 'What this is'),
    el('p', {}, 'The regulated route to giving financial advice in each market, taken from the '
      + 'regulator or awarding body that actually sets the rule. Each step links to the body '
      + 'behind it, so you can go straight to the source rather than trusting a summary.'),
    el('p', {}, 'The pathways differ more than you would expect. The UK lets you start with no '
      + 'degree and qualify on the job; the US front-loads exams and then needs a sponsor; '
      + 'Ireland folds everything into one designation; Canada makes you pick a channel first; '
      + 'Nigeria leads with registration.')));

  host.append(el('div', {},
    el('h3', {}, 'What it is not'),
    el('ul', {},
      el('li', {}, 'Not legal or regulatory advice. Rules change, and several of these bodies '
        + 'revise their requirements annually — check the linked source before committing money '
        + 'or time to a route.'),
      el('li', {}, 'Not a ranking. The companies are chosen to span each market’s advice, '
        + 'asset management and banking industries, not to rate them as employers or investments.'),
      el('li', {}, 'Not live data. Company figures carry the date they were reported; the AUM and '
        + 'asset numbers here move quarterly and some will already have moved.'),
      el('li', {}, 'Reciprocity between markets is limited. A UK Level 4 does not transfer to the '
        + 'US, and CFP® is administered separately in each territory even though the mark is '
        + 'the same.'))));
}

function renderMeta() {
  $('#meta').innerHTML =
    `<strong>${state.data.markets.length}</strong> markets · `
    + `<strong>${Object.values(state.data.companies).reduce((n, list) => n + list.length, 0)}</strong> firms · `
    + `checked ${state.data.as_of}`;

  $('#foot').textContent = state.data.note;
}

function renderAll() {
  renderCountryFilter();
  renderPathway();
  renderCompanies();
}

function wire() {
  $('#theme').addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme === 'dark'
      || (!document.documentElement.dataset.theme
        && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
  });

  modal().addEventListener('pointerenter', () => clearTimeout(closeTimer));
  modal().addEventListener('pointerleave', () => { if (!state.pinned) scheduleClose(); });
  backdrop().addEventListener('click', closeModal);
  document.addEventListener('pointermove', (event) => {
    pointerPos = { x: event.clientX, y: event.clientY };
  }, { passive: true });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeModal();
  });
  window.addEventListener('resize', closeModal);
}

async function boot() {
  if (window.__CAREERS__) {
    state.data = window.__CAREERS__;
  } else {
    try {
      const response = await fetch(`${CAREERS_URL}?t=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.data = await response.json();
    } catch (error) {
      $('#banners').append(el('div', { class: 'banner is-error' },
        `Could not load data/careers.json (${error.message}). Serve the folder with `,
        el('code', {}, 'python3 serve.py'), ' rather than opening the file directly.'));
      return;
    }
  }
  state.country = state.data.markets[0].iso3;
  wire();
  renderMeta();
  renderMethod();
  renderAll();
}

boot();
