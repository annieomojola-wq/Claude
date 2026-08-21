/* Exchange Drop Monitor - reads data/snapshot.json and renders the dashboard.
   No dependencies, no build step. All text from the snapshot is inserted with
   textContent: company names and sectors are third-party data. */

'use strict';

const SNAPSHOT_URL = '../data/snapshot.json';
const CHART_ROWS = 25;

const state = {
  snapshot: null,
  filters: {
    exchange: 'ALL',
    threshold: 0,
    sector: '',
    search: '',
    sort: 'mom_pct',
    sustained: false,
    includeRisers: false,
  },
  tableSort: { key: 'mom_pct', dir: 'asc' },
};

const $ = (id) => document.getElementById(id);

/* ---------------------------------------------------------------- utils */

function pct(v, digits = 1) {
  if (v === null || v === undefined) return '—';
  const rounded = Number(v.toFixed(digits));
  // -0.04 must not print as "-0.0%"
  const sign = rounded > 0 ? '+' : '';
  return `${sign}${(rounded === 0 ? 0 : rounded).toFixed(digits)}%`;
}

function price(value, currency) {
  if (value === null || value === undefined) return '—';
  if (currency === 'GBX') {
    return `${value.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}p`;
  }
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const arrow = (v) => (v === null || v === undefined ? '' : v < 0 ? '▼' : v > 0 ? '▲' : '■');

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** A round axis step (1, 2, 2.5, 5, 10 x a power of ten) near `raw`. */
function niceStep(raw) {
  if (!(raw > 0)) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(raw)));
  const frac = raw / exp;
  const step = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 2.5 ? 2.5 : frac <= 5 ? 5 : 10;
  return step * exp;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatStamp(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/* ------------------------------------------------------------- selection */

/** Scope from the identity filters: exchange, sector, search. */
function scoped(ignoreExchange = false) {
  const f = state.filters;
  const needle = f.search.trim().toLowerCase();
  return (state.snapshot?.companies || []).filter((c) => {
    if (c.status !== 'ok' || c.mom_pct === null) return false;
    if (!ignoreExchange && f.exchange !== 'ALL' && c.exchange !== f.exchange) return false;
    if (f.sector && c.sector !== f.sector) return false;
    if (needle && !(`${c.ticker} ${c.name}`.toLowerCase().includes(needle))) return false;
    return true;
  });
}

/** The scope plus the movement filters: threshold, sustained, risers. */
function selected() {
  const f = state.filters;
  return scoped().filter((c) => {
    if (f.sustained && !c.sustained) return false;
    if (c.mom_pct >= 0) return f.includeRisers;
    return -c.mom_pct >= f.threshold;
  });
}

function sortRows(rows, key, dir) {
  const factor = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    if (typeof x === 'string' || typeof y === 'string') {
      return String(x).localeCompare(String(y)) * factor;
    }
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    return (x - y) * factor;
  });
}

/* -------------------------------------------------------------- tooltip */

const tooltip = $('tooltip');

function showTooltip(company, event) {
  tooltip.replaceChildren();
  tooltip.appendChild(el('div', 'tt-title', company.ticker));
  tooltip.appendChild(el('div', 'tt-sub', `${company.name} · ${company.exchange}`));

  const rows = [
    ['Last close', price(company.price, company.currency)],
    ['Month on month', `${arrow(company.mom_pct)} ${pct(company.mom_pct)}`],
    ['Previous month', company.prev_mom_pct === null ? '—' : `${arrow(company.prev_mom_pct)} ${pct(company.prev_mom_pct)}`],
    ['3 months', pct(company.chg_3m_pct)],
    ['From 3-month high', pct(company.drawdown_pct)],
    [`vs ${formatDate(company.ref_date)}`, price(company.ref_price, company.currency)],
  ];
  for (const [key, value] of rows) {
    const row = el('div', 'tt-row');
    const k = el('span', 'k');
    if (key === 'Month on month') {
      const line = el('span', 'key-line');
      line.style.background = company.mom_pct < 0 ? 'var(--down)' : 'var(--up)';
      k.appendChild(line);
    }
    k.appendChild(document.createTextNode(key));
    row.appendChild(k);
    row.appendChild(el('span', 'v', value));
    tooltip.appendChild(row);
  }

  tooltip.dataset.open = 'true';
  positionTooltip(event);
}

function positionTooltip(event) {
  const pad = 14;
  const rect = tooltip.getBoundingClientRect();
  let x = (event.clientX ?? 0) + pad;
  let y = (event.clientY ?? 0) + pad;
  if (event.type === 'focus' && event.target.getBoundingClientRect) {
    const target = event.target.getBoundingClientRect();
    x = target.right + pad;
    y = target.top;
  }
  if (x + rect.width > window.innerWidth - 8) x = Math.max(8, x - rect.width - pad * 2);
  if (y + rect.height > window.innerHeight - 8) y = Math.max(8, window.innerHeight - rect.height - 8);
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function hideTooltip() {
  tooltip.dataset.open = 'false';
}

function attachTooltip(node, company) {
  node.addEventListener('pointerenter', (e) => showTooltip(company, e));
  node.addEventListener('pointermove', positionTooltip);
  node.addEventListener('pointerleave', hideTooltip);
  node.addEventListener('focus', (e) => showTooltip(company, e));
  node.addEventListener('blur', hideTooltip);
}

/* --------------------------------------------------------------- render */

function render() {
  if (!state.snapshot) return;
  renderMeta();
  renderKpis();
  renderExchangeBars();
  renderDropChart();
  renderTable();
}

function renderMeta() {
  const meta = state.snapshot.meta;
  const node = $('meta');
  node.replaceChildren();
  const basis =
    meta.basis === 'calendar'
      ? 'last completed calendar month vs the month before'
      : 'latest close vs one month earlier';
  const line1 = el('span');
  line1.appendChild(document.createTextNode('Prices to '));
  line1.appendChild(el('strong', null, formatDate(meta.latest_close)));
  node.appendChild(line1);
  node.appendChild(document.createElement('br'));
  node.appendChild(document.createTextNode(`${basis} · source: ${meta.provider}`));
  node.appendChild(document.createElement('br'));
  node.appendChild(document.createTextNode(`snapshot built ${formatStamp(meta.generated_at)}`));

  $('footer').textContent =
    `${meta.counts.tracked} companies tracked across ${meta.exchanges.join(', ')}. ` +
    `Refresh the numbers with: python3 fetch.py --provider ${meta.is_demo ? 'stooq' : meta.provider}` +
    (meta.basis === 'calendar' ? ' --basis calendar' : '');
}

function renderBanners() {
  const meta = state.snapshot.meta;
  const host = $('banners');
  host.replaceChildren();

  if (meta.is_demo) {
    const banner = el('div', 'banner is-demo');
    const text = el('div');
    text.appendChild(el('strong', null, 'Demo data. '));
    text.appendChild(
      document.createTextNode(
        'These prices are synthetic — generated locally so the dashboard runs with no setup. Nothing here reflects a real market. For live prices run '
      )
    );
    text.appendChild(el('code', null, 'python3 fetch.py --provider stooq'));
    text.appendChild(document.createTextNode(' and reload.'));
    banner.appendChild(text);
    host.appendChild(banner);
  }

  if (meta.counts.errors) {
    const banner = el('div', 'banner is-error');
    const tickers = [...new Set((meta.errors || []).map((e) => e.ticker))].join(', ');
    banner.appendChild(
      el('div', null, `${meta.counts.errors} company${meta.counts.errors === 1 ? '' : 's'} could not be priced and ${meta.counts.errors === 1 ? 'is' : 'are'} missing below: ${tickers}`)
    );
    host.appendChild(banner);
  }
}

function renderKpis() {
  const rows = scoped();
  const decliners = rows.filter((c) => c.mom_pct < 0);
  const worst = decliners.length ? decliners.reduce((a, b) => (a.mom_pct <= b.mom_pct ? a : b)) : null;
  const mid = median(rows.map((c) => c.mom_pct));
  const sustained = rows.filter((c) => c.sustained);
  const scopeNote =
    state.filters.exchange === 'ALL' ? 'all three exchanges' : state.snapshot.exchanges.find((e) => e.code === state.filters.exchange)?.name || state.filters.exchange;

  const tiles = [
    {
      label: 'Falling month on month',
      value: `${decliners.length}`,
      down: false,
      foot: `of ${rows.length} tracked · ${scopeNote}`,
    },
    {
      label: 'Biggest faller',
      value: worst ? pct(worst.mom_pct) : '—',
      down: Boolean(worst),
      foot: worst ? `${worst.ticker} · ${worst.name}` : 'nothing is down',
    },
    {
      label: 'Median move',
      value: mid === null ? '—' : pct(mid),
      down: mid !== null && mid < 0,
      foot: 'typical company in this selection',
    },
    {
      label: 'Falling two months running',
      value: `${sustained.length}`,
      down: false,
      foot: 'down this month and last month',
    },
  ];

  const host = $('kpis');
  host.replaceChildren();
  for (const tile of tiles) {
    const card = el('div', 'kpi');
    card.appendChild(el('div', 'label', tile.label));
    card.appendChild(el('div', `value${tile.down ? ' down' : ''}`, tile.value));
    card.appendChild(el('div', 'foot', tile.foot));
    host.appendChild(card);
  }
}

function renderExchangeBars() {
  const rows = scoped(true); // exchange bars always compare all three
  const host = $('exchange-bars');
  host.replaceChildren();

  for (const exchange of state.snapshot.exchanges) {
    const mine = rows.filter((c) => c.exchange === exchange.code);
    const down = mine.filter((c) => c.mom_pct < 0);
    const share = mine.length ? (down.length / mine.length) * 100 : 0;
    const dimmed = state.filters.exchange !== 'ALL' && state.filters.exchange !== exchange.code;

    const row = el('div', 'ex-row');
    row.style.opacity = dimmed ? '0.45' : '1';

    const head = el('div', 'ex-head');
    const dot = el('span', 'dot');
    dot.style.background = `var(--ex-${exchange.code})`;
    head.appendChild(dot);
    head.appendChild(el('span', 'ex-name', exchange.name));
    head.appendChild(
      el('span', 'ex-val', mine.length ? `${share.toFixed(0)}% falling · ${down.length} of ${mine.length}` : 'no data')
    );
    row.appendChild(head);

    const track = el('div', 'ex-track');
    const fill = el('div', 'ex-fill');
    fill.style.width = `${share}%`;
    fill.style.background = `var(--ex-${exchange.code})`;
    track.appendChild(fill);
    row.appendChild(track);
    host.appendChild(row);
  }
}

const METRICS = {
  mom_pct: {
    falls: 'Biggest month-on-month falls',
    moves: 'Biggest month-on-month moves',
    axis: 'Month-on-month change (%)',
    lead: 'Longer bar means a steeper fall over the month. ',
  },
  drawdown_pct: {
    falls: 'Furthest below the 3-month high',
    moves: 'Furthest below the 3-month high',
    axis: 'Change from the 3-month high (%)',
    lead: 'Longer bar means further below the peak of the last three months. ',
  },
  chg_3m_pct: {
    falls: 'Biggest three-month falls',
    moves: 'Biggest three-month moves',
    axis: 'Three-month change (%)',
    lead: 'Longer bar means a steeper fall over the quarter. ',
  },
};

function renderDropChart() {
  // The chart plots whatever the sort is ranking by, so the bars are always in
  // order. Sorting by ticker has no magnitude, so it falls back to the headline.
  const alphabetical = state.filters.sort === 'ticker';
  const metric = METRICS[state.filters.sort] ? state.filters.sort : 'mom_pct';
  const spec = METRICS[metric];
  const all = sortRows(
    selected().filter((c) => c[metric] !== null && c[metric] !== undefined),
    state.filters.sort,
    'asc'
  );

  // With risers on show, the chart takes both ends of the range - otherwise the
  // steepest 25 falls fill it and no riser is ever visible.
  let rows;
  const risers = all.filter((c) => c[metric] >= 0);
  if (state.filters.includeRisers && risers.length && !alphabetical) {
    const fallers = all.filter((c) => c[metric] < 0);
    const topRisers = risers.slice(-Math.min(10, risers.length));
    rows = sortRows([...fallers.slice(0, CHART_ROWS - topRisers.length), ...topRisers], metric, 'asc');
  } else {
    rows = all.slice(0, CHART_ROWS);
    if (!alphabetical) rows = sortRows(rows, metric, 'asc');
  }

  const host = $('drops-chart');
  const axis = $('drops-axis');
  host.replaceChildren();
  axis.replaceChildren();

  const showsRisers = Boolean(risers.length && state.filters.includeRisers && !alphabetical);
  $('drops-title').textContent = alphabetical
    ? 'Month-on-month change, A to Z'
    : showsRisers
      ? spec.moves
      : spec.falls;
  $('drops-axis-title').textContent = spec.axis;
  $('drops-count').textContent = all.length ? `showing ${rows.length} of ${all.length}` : '';
  $('drops-note').textContent =
    (alphabetical
      ? `The first ${Math.min(CHART_ROWS, all.length)} companies by ticker. `
      : showsRisers
        ? 'The steepest falls and the strongest rises: bars run left of the zero line for falls, right for rises. '
        : spec.lead) +
    '\u25bc\u25bc marks a company down two months running. Every company is also in the table below.';

  if (!rows.length) {
    host.appendChild(el('p', 'empty', 'No company matches these filters. Lower the minimum drop, or clear the search.'));
    return;
  }

  const values = rows.map((c) => c[metric]);
  const worstFall = Math.max(0, ...values.map((v) => (v < 0 ? -v : 0)));
  const bestRise = Math.max(0, ...values);
  const diverging = bestRise > 0;
  // One round step drives both arms, so the ticks read 0, -5, -10 ... not 0, -6.3, -12.5.
  const step = niceStep(Math.max(worstFall, bestRise) / 5);
  const maxDown = Math.ceil(worstFall / step) * step;
  const upSpan = diverging ? Math.ceil(bestRise / step) * step : 0;
  const span = maxDown + upSpan || 1;
  const zeroFrac = maxDown / span; // where 0% sits, as a fraction of the track

  for (const company of rows) {
    const value = company[metric];
    const row = el('div', 'bar-row');
    row.tabIndex = 0;
    row.setAttribute('role', 'listitem');
    row.setAttribute(
      'aria-label',
      `${company.ticker}, ${company.name}, ${company.exchange}, ${pct(value)} ${spec.axis.replace(' (%)', '')}`
    );

    const label = el('div', 'bar-label');
    label.appendChild(el('span', 'tick', company.ticker));
    if (company.sustained) {
      const repeat = el('span', 'repeat', '\u25bc\u25bc');
      repeat.title = 'Down this month and last month';
      label.appendChild(repeat);
    }
    label.appendChild(el('span', 'sub2', company.name));
    row.appendChild(label);

    const track = el('div', 'bar-track');
    const magnitude = Math.abs(value) / span;
    const bar = el('div', `bar${value >= 0 ? ' up' : ''}`);
    bar.style.position = 'absolute';
    bar.style.width = `${Math.max(magnitude * 100, 0.4)}%`;
    if (value < 0) {
      // Falls grow left-to-right when nothing is rising, and leftwards from the
      // zero line when the chart has to show both directions.
      bar.style.left = diverging ? `${Math.max((zeroFrac - magnitude) * 100, 0)}%` : '0';
      bar.style.borderRadius = diverging ? '4px 0 0 4px' : '0 4px 4px 0';
    } else {
      bar.style.left = diverging ? `${zeroFrac * 100}%` : '0';
      bar.style.borderRadius = '0 4px 4px 0';
    }
    track.appendChild(bar);

    if (diverging) {
      const zero = el('div');
      zero.style.cssText =
        `position:absolute;left:${zeroFrac * 100}%;top:0;bottom:0;width:1px;background:var(--axis)`;
      track.appendChild(zero);
    }

    row.appendChild(track);
    // The value sits in its own column, so it can never be clipped by a bar or
    // run off the end of a long one.
    row.appendChild(el('div', 'bar-value', `${arrow(value)} ${pct(value)}`));

    attachTooltip(row, company);
    host.appendChild(row);
  }
  host.setAttribute('role', 'list');

  // Axis: 0 at the zero line, falls to its left, rises to its right.
  const decimals = step % 1 ? 1 : 0;
  const ticks = [];
  for (let value = -maxDown; value <= upSpan + 1e-9; value += step) {
    ticks.push(Number(value.toFixed(4)));
  }
  if (!diverging) ticks.reverse(); // falls run left-to-right when nothing is up
  for (const t of ticks) {
    axis.appendChild(el('span', null, `${t > 0 ? '+' : ''}${t.toFixed(decimals)}%`));
  }
}

function sparkline(company) {
  const points = company.spark || [];
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'spark');
  svg.setAttribute('width', '92');
  svg.setAttribute('height', '26');
  svg.setAttribute('viewBox', '0 0 92 26');
  svg.setAttribute('role', 'img');
  const low = Math.min(...points);
  const high = Math.max(...points);
  svg.setAttribute(
    'aria-label',
    points.length
      ? `Price trend, ${points.length} sessions, low ${low.toFixed(2)}, high ${high.toFixed(2)}`
      : 'No trend data'
  );
  if (points.length < 2) return svg;

  const range = high - low || 1;
  const path = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * 90 + 1;
      const y = 24 - ((value - low) / range) * 22;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  line.setAttribute('d', path);
  line.setAttribute('fill', 'none');
  line.setAttribute('stroke', 'var(--series-1)');
  line.setAttribute('stroke-width', '1.5');
  line.setAttribute('stroke-linejoin', 'round');
  line.setAttribute('stroke-linecap', 'round');
  svg.appendChild(line);
  return svg;
}

function renderTable() {
  const rows = sortRows(selected(), state.tableSort.key, state.tableSort.dir);
  const body = $('tbody');
  body.replaceChildren();
  $('table-empty').hidden = rows.length > 0;

  for (const company of rows) {
    const tr = document.createElement('tr');

    tr.appendChild(el('td', null, company.ticker));
    const name = el('td');
    name.appendChild(el('span', 'name', company.name));
    tr.appendChild(name);

    const exchange = el('td');
    const pill = el('span', 'pill');
    const dot = el('span', 'dot');
    dot.style.background = `var(--ex-${company.exchange})`;
    pill.appendChild(dot);
    pill.appendChild(document.createTextNode(company.exchange));
    exchange.appendChild(pill);
    tr.appendChild(exchange);

    tr.appendChild(el('td', 'num', price(company.price, company.currency)));

    const mom = el('td', 'num');
    const delta = el('span', `delta ${company.mom_pct < 0 ? 'down' : 'up'}`, `${arrow(company.mom_pct)} ${pct(company.mom_pct)}`);
    mom.appendChild(delta);
    if (company.sustained) {
      const badge = el('span', 'badge', '▼▼ 2m');
      badge.style.marginLeft = '8px';
      mom.appendChild(badge);
    }
    tr.appendChild(mom);

    for (const key of ['prev_mom_pct', 'chg_3m_pct', 'drawdown_pct']) {
      const cell = el('td', 'num');
      const v = company[key];
      cell.appendChild(el('span', v === null ? '' : `delta ${v < 0 ? 'down' : 'up'}`, pct(v)));
      tr.appendChild(cell);
    }

    const trend = el('td');
    trend.appendChild(sparkline(company));
    tr.appendChild(trend);

    attachTooltip(tr, company);
    body.appendChild(tr);
  }
}

/* --------------------------------------------------------------- wiring */

function buildExchangeFilter() {
  const host = $('exchange-filter');
  host.replaceChildren();
  const options = [{ code: 'ALL', name: 'All three' }, ...state.snapshot.exchanges];
  for (const option of options) {
    const button = el('button', null);
    button.type = 'button';
    if (option.code !== 'ALL') {
      const dot = el('span', 'dot');
      dot.style.background = `var(--ex-${option.code})`;
      button.appendChild(dot);
    }
    button.appendChild(document.createTextNode(option.code === 'ALL' ? 'All three' : option.code));
    button.setAttribute('aria-pressed', String(state.filters.exchange === option.code));
    button.title = option.name;
    button.addEventListener('click', () => {
      state.filters.exchange = option.code;
      for (const sibling of host.children) sibling.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-pressed', 'true');
      render();
    });
    host.appendChild(button);
  }
}

function buildSectorFilter() {
  const select = $('sector');
  const sectors = [...new Set((state.snapshot.companies || []).map((c) => c.sector))].sort();
  select.replaceChildren();
  select.appendChild(new Option('All sectors', ''));
  for (const sector of sectors) select.appendChild(new Option(sector, sector));
  select.value = state.filters.sector;
}

function wireControls() {
  $('threshold').addEventListener('input', (event) => {
    state.filters.threshold = Number(event.target.value);
    $('threshold-value').textContent =
      state.filters.threshold === 0 ? 'any drop' : `${state.filters.threshold.toFixed(1)}% or more`;
    render();
  });

  $('sector').addEventListener('change', (e) => {
    state.filters.sector = e.target.value;
    render();
  });

  let searchTimer;
  $('search').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    const value = e.target.value;
    searchTimer = setTimeout(() => {
      state.filters.search = value;
      render();
    }, 120);
  });

  $('sort').addEventListener('change', (e) => {
    state.filters.sort = e.target.value;
    state.tableSort = { key: e.target.value, dir: 'asc' };
    syncTableHeaders();
    render();
  });

  $('sustained').addEventListener('change', (e) => {
    state.filters.sustained = e.target.checked;
    render();
  });

  $('include-risers').addEventListener('change', (e) => {
    state.filters.includeRisers = e.target.checked;
    render();
  });

  $('refresh').addEventListener('click', () => load({ keepFrame: true }));

  $('theme').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : current === 'light' ? 'dark' : preferredDark() ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('edm-theme', next);
    } catch (err) {
      /* private mode - the choice just won't persist */
    }
  });

  for (const th of document.querySelectorAll('th[data-sort]')) {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const dir = state.tableSort.key === key && state.tableSort.dir === 'asc' ? 'desc' : 'asc';
      state.tableSort = { key, dir };
      syncTableHeaders();
      renderTable();
    });
  }

  window.addEventListener('scroll', hideTooltip, { passive: true });
}

function syncTableHeaders() {
  for (const th of document.querySelectorAll('th[data-sort]')) {
    if (th.dataset.sort === state.tableSort.key) {
      th.setAttribute('aria-sort', state.tableSort.dir === 'asc' ? 'ascending' : 'descending');
    } else {
      th.removeAttribute('aria-sort');
    }
  }
}

function preferredDark() {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function restoreTheme() {
  try {
    const stored = localStorage.getItem('edm-theme');
    if (stored === 'dark' || stored === 'light') document.documentElement.setAttribute('data-theme', stored);
  } catch (err) {
    /* storage unavailable - fall back to the OS setting */
  }
}

async function load({ keepFrame = false } = {}) {
  const main = document.querySelector('.shell');
  if (keepFrame) main.classList.add('is-loading'); // hold the old render, no skeleton flash
  try {
    const response = await fetch(`${SNAPSHOT_URL}?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.snapshot = await response.json();
    if (!state.snapshot.companies) throw new Error('snapshot has no companies');
    renderBanners();
    buildExchangeFilter();
    buildSectorFilter();
    render();
  } catch (error) {
    const host = $('banners');
    host.replaceChildren();
    const banner = el('div', 'banner is-error');
    const text = el('div');
    text.appendChild(el('strong', null, 'Could not load the snapshot. '));
    text.appendChild(document.createTextNode(`${error.message}. Serve the folder with `));
    text.appendChild(el('code', null, 'python3 serve.py'));
    text.appendChild(document.createTextNode(' and build a snapshot with '));
    text.appendChild(el('code', null, 'python3 fetch.py'));
    text.appendChild(document.createTextNode('.'));
    banner.appendChild(text);
    host.appendChild(banner);
  } finally {
    main.classList.remove('is-loading');
  }
}

restoreTheme();
wireControls();
syncTableHeaders();
load();
