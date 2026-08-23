/* Five-Market Economic Tracker.
 *
 * Reads data/econ.json (or an inlined window.__ECON__ when exported as one
 * self-contained file) and renders it. No dependencies, no build step.
 *
 * Charting conventions, applied throughout:
 *   - one y-axis, never two: two measures of different scale get two charts
 *   - colour follows the country, never its rank or its position in a filter
 *   - a legend whenever more than one series is drawn, plus a table view,
 *     which is also the relief for the light-mode contrast warning
 *   - crosshair and tooltip on every line chart
 */

const SNAPSHOT_URL = '../data/econ.json';

const ERAS = [
  { from: 1980, to: 1982, label: 'Volcker shock' },
  { from: 1990, to: 1991, label: 'Early-90s recession' },
  { from: 2008, to: 2009, label: 'Financial crisis' },
  { from: 2020, to: 2020, label: 'COVID' },
];

const state = {
  data: null,
  indicator: 'NY.GDP.MKTP.KD.ZG',
  startYear: 1975,
  country: 'USA',
  pulseView: 'chart',
  smooth: 'raw',
  explorerView: 'chart',
  hidden: new Set(),
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const colorOf = (iso3) => `var(--c-${iso3})`;

/* ── formatting ────────────────────────────────────────────────────────── */

function fmtNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('en-GB', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtCompact(value) {
  const abs = Math.abs(value);
  const units = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'k']];
  for (const [size, suffix] of units) {
    if (abs >= size) return `${(value / size).toFixed(abs / size >= 100 ? 0 : 1)}${suffix}`;
  }
  return fmtNumber(value, 0);
}

/** Format one reading for its unit. `short` drops the trailing unit words so
 *  the number still fits inside a chart axis or a tooltip column. */
function fmtValue(value, unit, short = false) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  switch (unit) {
    case 'pct': return `${fmtNumber(value, 1)}%`;
    case 'pct_gdp': return short ? `${fmtNumber(value, 1)}%` : `${fmtNumber(value, 1)}% of GDP`;
    case 'usd': return value < 0 ? `-$${fmtCompact(-value)}` : `$${fmtCompact(value)}`;
    case 'count': return fmtCompact(value);
    case 'score': return fmtNumber(value, 2);
    case 'ratio': return fmtNumber(value, 1);
    case 'months': return short ? fmtNumber(value, 1) : `${fmtNumber(value, 1)} months`;
    case 'rate': return fmtNumber(value, value >= 100 ? 0 : 2);
    case 'score0': return fmtNumber(value, 0);   // the 0-100 pulse axis
    default: return fmtNumber(value, 1);
  }
}

function fmtSigned(value, unit) {
  if (value === null || value === undefined) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${fmtValue(value, unit, true)}`;
}

const bandOf = (score) => {
  if (score === null || score === undefined) return 'unknown';
  if (score >= 75) return 'strong';
  if (score >= 55) return 'firm';
  if (score >= 45) return 'middling';
  if (score >= 25) return 'soft';
  return 'weak';
};

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

const svgEl = (tag, attrs = {}) => {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    node.setAttribute(key, value);
  }
  return node;
};

const swatch = (iso3) => el('span', { class: 'swatch', style: `background:${colorOf(iso3)}` });

/** Round tick values, and a domain that ends on them.
 *  An axis reading 79.0% / 61.1% / 43.2% is arithmetically correct and
 *  useless — the reader cannot hold those numbers in their head. */
function niceScale(lo, hi, count = 5) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const rawStep = (hi - lo) / count;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalised = rawStep / magnitude;
  const step = (normalised <= 1 ? 1
    : normalised <= 2 ? 2
      : normalised <= 2.5 ? 2.5
        : normalised <= 5 ? 5 : 10) * magnitude;
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks = [];
  // Guard the accumulation against binary-float drift, or 0.1 steps wander.
  for (let i = 0; start + i * step <= end + step * 1e-9; i += 1) {
    ticks.push(Math.round((start + i * step) * 1e6) / 1e6);
  }
  return { lo: start, hi: end, ticks };
}

/* ── line chart ────────────────────────────────────────────────────────── */

/**
 * One y-axis, N series, crosshair tooltip.
 * series: [{ iso3, name, points: [[year, value], ...] }]
 */
function lineChart(container, { series, unit, yMin, yMax, eras = false, height = 360 }) {
  container.textContent = '';
  const live = series.filter((s) => s.points.length && !state.hidden.has(s.iso3));
  if (!live.length) {
    container.append(el('p', { class: 'card-note' }, 'Nothing to draw — every series is hidden or empty.'));
    return;
  }

  const W = 900;
  const H = height;
  const M = { top: 16, right: 18, bottom: 34, left: 56 };
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;

  const years = live.flatMap((s) => s.points.map(([year]) => year));
  const values = live.flatMap((s) => s.points.map(([, value]) => value));
  const x0 = Math.min(...years);
  const x1 = Math.max(...years);
  let lo = yMin !== undefined ? yMin : Math.min(...values);
  let hi = yMax !== undefined ? yMax : Math.max(...values);
  if (yMin === undefined && yMax === undefined) {
    const pad = (hi - lo) * 0.06;
    // Never pad a strictly-positive series below zero: an axis offering
    // "-2,000 listed companies" or "-$50k GDP per capita" is nonsense.
    lo = Math.min(...values) >= 0 ? Math.max(0, lo - pad) : lo - pad;
    hi = Math.max(...values) <= 0 ? Math.min(0, hi + pad) : hi + pad;
  }
  const scale = niceScale(lo, hi, 5);
  lo = scale.lo;
  hi = scale.hi;

  const sx = (year) => M.left + (x1 === x0 ? plotW / 2 : ((year - x0) / (x1 - x0)) * plotW);
  const sy = (value) => M.top + plotH - ((value - lo) / (hi - lo)) * plotH;

  const figure = el('div', { class: 'figure' });
  const svg = svgEl('svg', {
    viewBox: `0 0 ${W} ${H}`,
    role: 'img',
    'aria-label': `Line chart, ${live.map((s) => s.name).join(', ')}, ${x0} to ${x1}`,
  });

  // Era shading sits underneath everything, at 4.5% ink — present, recessive.
  if (eras) {
    for (const era of ERAS) {
      if (era.to < x0 || era.from > x1) continue;
      const left = sx(Math.max(era.from, x0));
      const right = sx(Math.min(era.to, x1));
      svg.append(svgEl('rect', {
        class: 'era-band', x: left, y: M.top,
        width: Math.max(right - left, 4), height: plotH,
      }));
      const label = svgEl('text', {
        class: 'era-label', x: left + 3, y: M.top + 11,
      });
      label.textContent = era.label;
      svg.append(label);
    }
  }

  // y gridlines, on the round values niceScale picked
  for (const value of scale.ticks) {
    const y = sy(value);
    svg.append(svgEl('line', { class: 'grid-line', x1: M.left, x2: W - M.right, y1: y, y2: y }));
    const text = svgEl('text', { class: 'tick-text', x: M.left - 8, y: y + 4, 'text-anchor': 'end' });
    text.textContent = fmtValue(value, unit, true);
    svg.append(text);
  }

  // A zero line only where zero is meaningful and actually inside the range.
  if (lo < 0 && hi > 0) {
    svg.append(svgEl('line', { class: 'zero-line', x1: M.left, x2: W - M.right, y1: sy(0), y2: sy(0) }));
  }

  // x ticks: decade marks, plus the final year
  const step = x1 - x0 > 30 ? 10 : x1 - x0 > 12 ? 5 : 2;
  const xTicks = [];
  for (let year = Math.ceil(x0 / step) * step; year <= x1; year += step) xTicks.push(year);
  if (xTicks[xTicks.length - 1] !== x1) xTicks.push(x1);
  for (const year of xTicks) {
    const text = svgEl('text', {
      class: 'tick-text', x: sx(year), y: H - M.bottom + 18, 'text-anchor': 'middle',
    });
    text.textContent = String(year);
    svg.append(text);
  }
  svg.append(svgEl('line', {
    class: 'axis-line', x1: M.left, x2: W - M.right, y1: M.top + plotH, y2: M.top + plotH,
  }));

  // series
  for (const entry of live) {
    const d = entry.points
      .map(([year, value], i) => `${i ? 'L' : 'M'}${sx(year).toFixed(2)},${sy(value).toFixed(2)}`)
      .join(' ');
    svg.append(svgEl('path', { class: 'series-line', d, style: `stroke:${colorOf(entry.iso3)}` }));
  }

  const crosshair = svgEl('line', { class: 'crosshair', y1: M.top, y2: M.top + plotH, opacity: 0 });
  svg.append(crosshair);
  const dots = live.map((entry) => {
    const dot = svgEl('circle', { class: 'hover-dot', r: 4.5, opacity: 0, fill: colorOf(entry.iso3) });
    svg.append(dot);
    return dot;
  });

  figure.append(svg);
  const tooltip = el('div', { class: 'tooltip', hidden: true });
  const hit = el('div', { class: 'chart-hit' });
  figure.append(tooltip, hit);
  container.append(figure);

  const valueAt = (entry, year) => {
    const found = entry.points.find(([y]) => y === year);
    return found ? found[1] : null;
  };

  function move(event) {
    const box = hit.getBoundingClientRect();
    const scale = box.width / W;
    const px = (event.clientX - box.left) / scale;
    const ratio = Math.min(Math.max((px - M.left) / plotW, 0), 1);
    const year = Math.round(x0 + ratio * (x1 - x0));

    crosshair.setAttribute('x1', sx(year));
    crosshair.setAttribute('x2', sx(year));
    crosshair.setAttribute('opacity', 1);

    const rows = [];
    live.forEach((entry, i) => {
      const value = valueAt(entry, year);
      if (value === null) { dots[i].setAttribute('opacity', 0); return; }
      dots[i].setAttribute('cx', sx(year));
      dots[i].setAttribute('cy', sy(value));
      dots[i].setAttribute('opacity', 1);
      rows.push({ entry, value });
    });
    rows.sort((a, b) => b.value - a.value);

    tooltip.textContent = '';
    tooltip.append(el('div', { class: 'tt-year' }, String(year)));
    if (!rows.length) {
      tooltip.append(el('div', { class: 'tt-row' }, el('span', { class: 'tt-name' }, 'no data')));
    }
    for (const { entry, value } of rows) {
      tooltip.append(el('div', { class: 'tt-row' },
        el('span', { class: 'tt-name' }, swatch(entry.iso3), entry.name),
        el('span', { class: 'tt-val' }, fmtValue(value, unit, true))));
    }
    tooltip.hidden = false;

    // Flip the tooltip to the other side of the cursor near the right edge.
    const tipW = tooltip.offsetWidth;
    const localX = (sx(year) * box.width) / W;
    const left = localX + 14 + tipW > box.width ? localX - tipW - 14 : localX + 14;
    tooltip.style.left = `${Math.max(0, left)}px`;
    tooltip.style.top = `${Math.max(0, Math.min(event.clientY - box.top - 10, box.height - tooltip.offsetHeight))}px`;
  }

  function leave() {
    tooltip.hidden = true;
    crosshair.setAttribute('opacity', 0);
    dots.forEach((dot) => dot.setAttribute('opacity', 0));
  }

  hit.addEventListener('pointermove', move);
  hit.addEventListener('pointerleave', leave);
}

/** Tiny trend line, no axes — used inside cards where the shape is the point. */
function sparkline(container, points, { color, height = 40, fill = false } = {}) {
  container.textContent = '';
  if (!points.length) {
    container.append(el('p', { class: 'mini-sub' }, 'no data'));
    return;
  }
  const W = 200;
  const H = height;
  const pad = 3;
  const years = points.map(([year]) => year);
  const values = points.map(([, value]) => value);
  const x0 = Math.min(...years);
  const x1 = Math.max(...years);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (lo === hi) { lo -= 1; hi += 1; }
  const sx = (year) => (x1 === x0 ? W / 2 : ((year - x0) / (x1 - x0)) * W);
  const sy = (value) => H - pad - ((value - lo) / (hi - lo)) * (H - pad * 2);

  const svg = svgEl('svg', {
    viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none',
    role: 'img', 'aria-label': `Trend from ${x0} to ${x1}`,
  });
  const d = points.map(([year, value], i) => `${i ? 'L' : 'M'}${sx(year).toFixed(1)},${sy(value).toFixed(1)}`).join(' ');
  if (fill) {
    svg.append(svgEl('path', {
      d: `${d} L${sx(x1).toFixed(1)},${H} L${sx(x0).toFixed(1)},${H} Z`,
      fill: color, opacity: 0.12, stroke: 'none',
    }));
  }
  svg.append(svgEl('path', { d, fill: 'none', stroke: color, 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke' }));
  const [lastYear, lastValue] = points[points.length - 1];
  svg.append(svgEl('circle', { cx: sx(lastYear), cy: sy(lastValue), r: 2.5, fill: color }));
  container.append(svg);
}

/* ── section: pulse cards ──────────────────────────────────────────────── */

function renderPulseCards() {
  const grid = $('#pulse-grid');
  grid.textContent = '';
  const { pulse, context } = state.data;

  for (const country of state.data.countries) {
    const entry = pulse[country.iso3];
    const band = entry.band;
    const trend = entry.trend;
    const ctx = (context.countries || {})[country.iso3] || {};

    const card = el('div', {
      class: 'pulse-card',
      style: `--accent:${colorOf(country.iso3)}`,
    });

    card.append(el('div', { class: 'pulse-top' },
      el('span', { class: 'pulse-name' }, country.flag, country.short),
      el('span', { class: 'pulse-band', 'data-band': band }, band)));

    card.append(el('div', { style: 'display:flex;align-items:baseline;gap:8px' },
      el('span', { class: 'pulse-score' }, entry.latest === null ? '—' : fmtNumber(entry.latest, 0)),
      el('span', { class: 'meta' }, `/ 100 · ${entry.latest_year || ''}`)));

    const read = entry.latest === null
      ? 'Not enough history to score.'
      : `Better than ${fmtNumber(entry.latest, 0)}% of its years since ${state.data.meta.start_year}. `
        + (trend
          ? `${trend.direction[0].toUpperCase()}${trend.direction.slice(1)} since ${trend.from_year} `
            + `(${trend.change > 0 ? '+' : ''}${fmtNumber(trend.change, 1)} pts).`
          : '');
    card.append(el('p', { class: 'pulse-read' }, read));

    const spark = el('div', { class: 'pulse-spark' });
    card.append(spark);
    sparkline(spark, entry.history, { color: colorOf(country.iso3), height: 40, fill: true });

    if (ctx.policy_rate) {
      card.append(el('div', { class: 'pulse-rate' },
        el('span', {}, 'Policy rate'),
        el('span', { class: 'val' }, ctx.policy_rate.short || ctx.policy_rate.display)));
    }
    grid.append(card);
  }

  const years = state.data.countries
    .map((c) => pulse[c.iso3].latest_year)
    .filter(Boolean);
  const lo = Math.min(...years);
  const hi = Math.max(...years);
  $('#pulse-asof').textContent = years.length
    ? `latest scored year: ${lo === hi ? lo : `${lo}–${hi}`}`
    : '';
}

/* ── section: fifty-year pulse ─────────────────────────────────────────── */

/** Centred rolling mean. The composite is jumpy year to year - a single bad
 *  harvest or a one-off export surge moves it - so smoothing is the difference
 *  between reading the noise and reading the trend. */
function rollingMean(points, window) {
  if (window <= 1) return points;
  const half = Math.floor(window / 2);
  return points.map(([year], i) => {
    const slice = points.slice(Math.max(0, i - half), i + half + 1);
    const mean = slice.reduce((sum, [, value]) => sum + value, 0) / slice.length;
    return [year, Math.round(mean * 10) / 10];
  });
}

function pulseSeries() {
  const window = state.smooth === 'avg3' ? 3 : state.smooth === 'avg5' ? 5 : 1;
  return state.data.countries.map((country) => ({
    iso3: country.iso3,
    name: country.short,
    points: rollingMean(state.data.pulse[country.iso3].history, window),
  }));
}

function renderPulseChart() {
  const chart = $('#pulse-chart');
  const table = $('#pulse-table');
  const isChart = state.pulseView === 'chart';
  chart.hidden = !isChart;
  table.hidden = isChart;

  if (isChart) {
    lineChart(chart, { series: pulseSeries(), unit: 'score0', yMin: 0, yMax: 100, eras: true, height: 380 });
    chart.append(legend(() => renderPulseChart()));
  } else {
    renderYearTable(table, pulseSeries(), 'score0');
  }
}

/** Legend doubles as a series toggle. Colour stays bound to the country, so
 *  hiding one never repaints the others. */
function legend(rerender) {
  const list = el('ul', { class: 'legend' });
  for (const country of state.data.countries) {
    const off = state.hidden.has(country.iso3);
    list.append(el('li', {},
      el('button', {
        type: 'button',
        'aria-pressed': off ? 'false' : 'true',
        onClick: () => {
          if (off) state.hidden.delete(country.iso3); else state.hidden.add(country.iso3);
          rerender();
        },
      }, swatch(country.iso3), country.short)));
  }
  return list;
}

function renderYearTable(container, series, unit) {
  container.textContent = '';
  const years = Array.from(new Set(series.flatMap((s) => s.points.map(([y]) => y)))).sort((a, b) => b - a);
  const lookup = series.map((s) => new Map(s.points));

  const table = el('table', { class: 'data-table' });
  const head = el('tr', {}, el('th', {}, 'Year'));
  series.forEach((s) => head.append(el('th', {}, s.name)));
  table.append(el('thead', {}, head));

  const body = el('tbody');
  for (const year of years) {
    const row = el('tr', {}, el('td', {}, String(year)));
    lookup.forEach((map) => {
      const value = map.get(year);
      row.append(el('td', { class: 'num' }, value === undefined ? '—' : fmtValue(value, unit, true)));
    });
    body.append(row);
  }
  table.append(body);
  container.append(el('div', { class: 'table-wrap scroll-y' }, table));
}

/* ── section: indicator explorer ───────────────────────────────────────── */

function buildIndicatorSelect() {
  const select = $('#indicator');
  select.textContent = '';
  for (const family of state.data.families) {
    const group = el('optgroup', { label: family.label });
    const members = state.data.indicators.filter((i) => i.family === family.id);
    if (!members.length) continue;
    for (const indicator of members) {
      group.append(el('option', { value: indicator.code }, indicator.label));
    }
    select.append(group);
  }
  select.value = state.indicator;
}

function explorerSeries() {
  return state.data.countries.map((country) => ({
    iso3: country.iso3,
    name: country.short,
    points: (state.data.series[country.iso3][state.indicator] || [])
      .filter(([year]) => year >= state.startYear),
  }));
}

function renderExplorer() {
  const meta = state.data.indicators.find((i) => i.code === state.indicator);
  const chart = $('#explorer-chart');
  const table = $('#explorer-table');
  const isChart = state.explorerView === 'chart';
  chart.hidden = !isChart;
  table.hidden = isChart;

  const covered = state.data.countries
    .filter((c) => (state.data.series[c.iso3][state.indicator] || []).length)
    .map((c) => c.short);
  const missing = state.data.countries
    .filter((c) => !(state.data.series[c.iso3][state.indicator] || []).length)
    .map((c) => c.short);

  $('#indicator-note').textContent = `${meta.note}`
    + (missing.length ? `  Not reported for ${missing.join(', ')}.` : '')
    + (covered.length ? `  Source: World Bank (${meta.code}).` : '');

  const series = explorerSeries();
  if (isChart) {
    lineChart(chart, { series, unit: meta.unit, eras: true, height: 360 });
    chart.append(legend(() => renderExplorer()));
  } else {
    renderYearTable(table, series, meta.unit);
  }

  renderRanking(meta);
}

function renderRanking(meta) {
  const host = $('#explorer-ranking');
  host.textContent = '';
  const ranked = state.data.rankings[meta.code] || [];
  if (!ranked.length) return;

  host.append(el('h3', {
    style: 'font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:20px 0 4px;font-weight:600',
  }, 'Latest reading, scored against each country’s own history'));
  host.append(el('p', { class: 'card-note', style: 'margin-bottom:12px' },
    'The bar is the percentile, not the raw value — so a long bar means "good for this country", '
    + 'not "bigger than the others".'));

  const list = el('div', { class: 'rank-list' });
  for (const row of ranked) {
    const country = state.data.countries.find((c) => c.iso3 === row.iso3);
    const score = row.score;
    const track = el('div', { class: 'rank-track' });
    if (score !== null) {
      track.append(el('div', {
        class: 'rank-fill',
        style: `width:${Math.max(score, 1.5)}%;background:${colorOf(row.iso3)}`,
      }));
    }
    list.append(el('div', { class: 'rank-row' },
      el('span', { class: 'rank-name' }, swatch(row.iso3), `${country.short}`),
      track,
      el('span', { class: 'rank-value' }, fmtValue(row.value, meta.unit, true),
        el('span', { class: 'meta', style: 'margin-left:5px' }, `'${String(row.year).slice(2)}`))));
  }
  host.append(list);
}

/* ── section: country detail ───────────────────────────────────────────── */

function renderCountryFilter() {
  const host = $('#country-filter');
  host.textContent = '';
  for (const country of state.data.countries) {
    host.append(el('button', {
      type: 'button',
      'aria-pressed': country.iso3 === state.country ? 'true' : 'false',
      onClick: () => { state.country = country.iso3; renderCountryFilter(); renderCountryDetail(); },
    }, el('span', { class: 'swatch', style: `background:${colorOf(country.iso3)}` }), country.short));
  }
}

function renderCountryDetail() {
  const host = $('#country-detail');
  host.textContent = '';
  const iso3 = state.country;
  const country = state.data.countries.find((c) => c.iso3 === iso3);
  const readings = state.data.readings[iso3];
  const entry = state.data.pulse[iso3];

  $('#country-note').textContent =
    `${country.name}: every series on file, each scored against its own record. `
    + (entry.latest !== null
      ? `Pulse ${fmtNumber(entry.latest, 0)}/100 — best year ${entry.best_year}, worst ${entry.worst_year}.`
      : '');

  for (const family of state.data.families) {
    const members = state.data.indicators
      .filter((i) => i.family === family.id && readings[i.code]);
    if (!members.length) continue;

    const block = el('div', { class: 'family-block' }, el('h3', {}, family.label));
    const grid = el('div', { class: 'mini-grid' });

    for (const indicator of members) {
      const reading = readings[indicator.code];
      const band = bandOf(reading.score);
      const card = el('div', { class: 'mini' });

      card.append(el('div', { class: 'mini-head' },
        el('span', { class: 'mini-label' }, indicator.short),
        reading.score === null
          ? el('span', { class: 'pct-badge', 'data-band': 'unknown' }, 'n/s')
          : el('span', { class: 'pct-badge', 'data-band': band, title: `${fmtNumber(reading.score, 0)}th percentile of this country's own history` },
            `${fmtNumber(reading.score, 0)}`)));

      card.append(el('div', { class: 'mini-value' }, fmtValue(reading.value, indicator.unit, true)));
      const changeText = reading.change !== undefined
        ? `${fmtSigned(reading.change, indicator.unit)} vs ${reading.prev_year}`
        : 'no earlier reading';
      card.append(el('div', { class: 'mini-sub' }, `${reading.year} · ${changeText}`));

      const spark = el('div', { class: 'mini-spark' });
      card.append(spark);
      sparkline(spark, state.data.series[iso3][indicator.code] || [], {
        color: colorOf(iso3), height: 34,
      });

      const stats = reading.stats || {};
      card.append(el('div', { class: 'mini-foot' },
        el('span', {}, `${stats.first_year ?? '?'}–${stats.last_year ?? '?'}`),
        el('span', {}, `range ${fmtValue(stats.min, indicator.unit, true)} … ${fmtValue(stats.max, indicator.unit, true)}`)));

      grid.append(card);
    }
    block.append(grid);
    host.append(block);
  }
}

/* ── section: the curated "right now" panel ────────────────────────────── */

function renderContext() {
  const context = state.data.context || {};
  const card = $('#context-card');
  if (!context.countries) { card.hidden = true; return; }

  $('#context-asof').textContent = `hand-checked ${context.as_of}`;
  $('#context-note').textContent = context.note || '';

  const host = $('#context-body');
  host.textContent = '';

  if (context.global) {
    if (context.global.themes) {
      const list = el('ul', { class: 'themes' });
      context.global.themes.forEach((theme) => list.append(el('li', {}, theme)));
      host.append(list);
    }
    if (context.global.ipo) {
      host.append(el('p', { class: 'ctx-block', style: 'margin-bottom:18px' },
        el('strong', {}, 'IPOs, globally: '), context.global.ipo));
    }
  }

  const grid = el('div', { class: 'ctx-grid' });
  for (const country of state.data.countries) {
    const ctx = context.countries[country.iso3];
    if (!ctx) continue;
    const card2 = el('div', { class: 'ctx-card', style: `--accent:${colorOf(country.iso3)}` });
    card2.append(el('h3', {}, country.flag, country.name));

    if (ctx.policy_rate) {
      card2.append(el('p', { class: 'ctx-rate' },
        el('strong', {}, ctx.policy_rate.display), ` · ${country.policy_rate_name}`,
        el('br'), `${ctx.policy_rate.action} ${ctx.policy_rate.as_of}`,
        ctx.policy_rate.note ? ` — ${ctx.policy_rate.note}` : ''));
    }

    if (ctx.signals) {
      const list = el('ul', { class: 'ctx-signals' });
      for (const signal of ctx.signals) {
        list.append(el('li', {},
          el('span', { class: 'sig-label' }, signal.label),
          el('span', { class: 'sig-value', 'data-tone': signal.tone }, signal.value),
          el('span', { class: 'sig-note' }, `${signal.as_of}${signal.note ? ` — ${signal.note}` : ''}`)));
      }
      card2.append(list);
    }

    if (ctx.politics) {
      card2.append(el('p', { class: 'ctx-block' },
        el('strong', {}, 'Politics: '), ctx.politics.summary,
        ctx.politics.next_election ? el('br') : null,
        ctx.politics.next_election ? `Next: ${ctx.politics.next_election}.` : null));
      if (ctx.politics.watch) {
        card2.append(el('p', { class: 'ctx-block', style: 'margin-bottom:2px' }, el('strong', {}, 'What to watch:')));
        const watch = el('ul', { class: 'ctx-watch' });
        ctx.politics.watch.forEach((item) => watch.append(el('li', {}, item)));
        card2.append(watch);
      }
    }

    if (ctx.markets_business) {
      if (ctx.markets_business.ipo) {
        card2.append(el('p', { class: 'ctx-block' }, el('strong', {}, 'IPOs & listings: '), ctx.markets_business.ipo));
      }
      if (ctx.markets_business.note) {
        card2.append(el('p', { class: 'ctx-block' }, ctx.markets_business.note));
      }
    }

    if (ctx.sources) {
      const sources = el('p', { class: 'ctx-sources' }, 'Sources: ');
      ctx.sources.forEach((source, i) => {
        if (i) sources.append(document.createTextNode(' · '));
        sources.append(el('a', { href: source.url, target: '_blank', rel: 'noopener' }, source.label));
      });
      card2.append(sources);
    }
    grid.append(card2);
  }
  host.append(grid);
}

/* ── section: method & coverage ────────────────────────────────────────── */

function renderMethod() {
  const host = $('#method-body');
  host.textContent = '';
  const { meta } = state.data;
  const pulseNames = state.data.pulse_codes
    .map((code) => state.data.indicators.find((i) => i.code === code))
    .filter(Boolean)
    .map((i) => i.short);

  const cols = el('div', { class: 'method-cols' });

  cols.append(el('div', {},
    el('h3', {}, 'How the score works'),
    el('p', {}, 'A raw number means nothing on its own — 3% inflation is good in Lagos and bad in Ottawa. '
      + 'So every reading is turned into a percentile against that same country’s own record over the '
      + 'tracked period. 90 means better than 90% of its own years.'),
    el('p', {}, 'Direction is set per indicator, which is what lets unemployment falling and investment '
      + 'rising both count as an improvement. Inflation is scored on distance from that central bank’s '
      + 'own target, so deflation is penalised too.'),
    el('p', {}, `The composite averages ${pulseNames.length} components, equally weighted: ${pulseNames.join(', ')}. `
      + 'Equal weights because any other weighting would be a hidden opinion about which part of an '
      + 'economy matters most.')));

  cols.append(el('div', {},
    el('h3', {}, 'What it will not tell you'),
    el('ul', {},
      el('li', {}, 'It is not a cross-country league table. A 70 in Nigeria and a 70 in Canada both mean '
        + '"good by its own standards", not that the two economies are equally comfortable to live in.'),
      el('li', {}, 'Ireland’s headline GDP and FDI are distorted by multinational balance-sheet moves. '
        + 'Modified domestic demand, in the panel above, is the honest read.'),
      el('li', {}, 'Business closure has no comparable 50-year cross-country series. New business density '
        + 'starts in 2006, and insolvency counts are national. The curated panel carries those.'),
      el('li', {}, 'IPO counts are not published as a World Bank series. Listed-company count is the '
        + 'long-run proxy: falling means delistings are outpacing floats.'),
      el('li', {}, 'The most recent year is often incomplete or revised. Governance scores start in 1996.'))));

  const rows = state.data.indicators.map((indicator) => {
    const covered = state.data.countries.map((country) => {
      const cov = (state.data.coverage[country.iso3] || {})[indicator.code];
      return { country, cov };
    });
    return { indicator, covered };
  });

  const table = el('table', { class: 'data-table' });
  const head = el('tr', {}, el('th', {}, 'Indicator'));
  state.data.countries.forEach((c) => head.append(el('th', {}, c.short)));
  table.append(el('thead', {}, head));
  const body = el('tbody');
  for (const { indicator, covered } of rows) {
    const row = el('tr', {}, el('td', {}, indicator.label));
    for (const { cov } of covered) {
      row.append(el('td', { class: 'num' },
        cov && cov.count ? `${cov.first_year}–${cov.last_year}` : '—'));
    }
    body.append(row);
  }
  table.append(body);

  host.append(cols);
  host.append(el('h3', {
    style: 'font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:22px 0 8px;font-weight:600',
  }, 'Coverage — the years each series actually has'));
  host.append(el('div', { class: 'table-wrap scroll-y' }, table));

  $('#foot').textContent =
    `Indicator data: World Bank Open Data (${meta.indicators} series, ${meta.observations.toLocaleString('en-GB')} observations, `
    + `${meta.start_year}–${meta.end_year}). Governance: Worldwide Governance Indicators. `
    + `Policy rates, politics, insolvencies and IPO activity are hand-curated and dated in the panel above. `
    + `Snapshot generated ${meta.generated_at.replace('T', ' ').replace('+00:00', ' UTC')}.`;
}

/* ── banners, meta, wiring ─────────────────────────────────────────────── */

function renderBanners() {
  const host = $('#banners');
  host.textContent = '';
  const { meta } = state.data;

  if (meta.is_demo) {
    host.append(el('div', { class: 'banner is-demo' },
      el('span', {}, 'Showing synthetic demo data — these are not real economic figures. Run '),
      el('code', {}, 'python3 fetch_econ.py --provider worldbank'), el('span', {}, ' for the real thing.')));
  }
  if (meta.errors && meta.errors.length) {
    host.append(el('div', { class: 'banner is-error' },
      `${meta.errors.length} series did not come back in the last refresh: `
      + `${meta.errors.map((e) => e.label).join(', ')}. Everything else is current.`));
  }
}

function renderMeta() {
  const { meta } = state.data;
  $('#meta').innerHTML =
    `<strong>${meta.observations.toLocaleString('en-GB')}</strong> observations · `
    + `<strong>${meta.start_year}–${meta.end_year}</strong> · `
    + `${meta.is_demo ? 'demo' : 'World Bank'}`;
}

function segment(selector, key, attr, after) {
  const host = $(selector);
  if (!host) return;
  host.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    const raw = button.dataset[attr];
    state[key] = attr === 'start' ? Number(raw) : raw;
    $$('button', host).forEach((b) => b.setAttribute('aria-pressed', b === button ? 'true' : 'false'));
    after();
  });
}

function renderAll() {
  renderBanners();
  renderMeta();
  renderPulseCards();
  renderPulseChart();
  renderExplorer();
  renderCountryFilter();
  renderCountryDetail();
  renderContext();
  renderMethod();
}

function wire() {
  buildIndicatorSelect();
  $('#indicator').addEventListener('change', (event) => {
    state.indicator = event.target.value;
    renderExplorer();
  });
  segment('#pulse-view', 'pulseView', 'view', renderPulseChart);
  segment('#pulse-smooth', 'smooth', 'smooth', renderPulseChart);
  segment('#explorer-view', 'explorerView', 'view', renderExplorer);
  segment('#range-filter', 'startYear', 'start', renderExplorer);

  $('#theme').addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme === 'dark'
      || (!document.documentElement.dataset.theme
        && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
  });

  // The charts are drawn to a viewBox, but the tooltip maths reads pixels.
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { renderPulseChart(); renderExplorer(); }, 150);
  });
}

async function boot() {
  if (window.__ECON__) {
    state.data = window.__ECON__;
  } else {
    try {
      const response = await fetch(`${SNAPSHOT_URL}?t=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.data = await response.json();
    } catch (error) {
      $('#banners').append(el('div', { class: 'banner is-error' },
        `Could not load data/econ.json (${error.message}). Serve the folder with `,
        el('code', {}, 'python3 serve.py'), ' rather than opening the file directly.'));
      return;
    }
  }
  state.country = state.data.countries[0].iso3;
  wire();
  renderAll();
}

boot();
