import { icon } from './icons.js';
import { lineChart } from './charts.js';

const routes = [
  ['overview', 'Overview', 'grid'], ['catalog', 'Data catalogue', 'box'],
  ['operations', 'Operations', 'pulse'], ['governance', 'Governance', 'shield'],
  ['delivery', 'Delivery roadmap', 'roadmap'],
];
const appearance = {
  'shipment-reliability': ['truck', ''], 'freight-spend': ['chart', 'blue'], 'returns-pulse': ['ret', 'purple'],
};
const main = document.querySelector('#main');
const ctx = {
  actors: {}, products: [], actor: localStorage.getItem('hub-actor') || 'platform-operator',
  query: '', domain: '', period: '', dimension: '', chartRange: 14, renderId: 0,
};
let toastTimer, chart;
const escape = value => String(value ?? '—').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));
const num = value => new Intl.NumberFormat('en-GB').format(value);
const timestamp = value => value ? new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
}).format(new Date(value)) + ' UTC' : '—';
const ageLabel = (status, hours) => {
  if (hours == null) return 'Awaiting first run';
  if (hours < .1) return 'Just published';
  return 'Published ' + num(hours) + 'h ago';
};
const badge = (status, label = status) => `<span class="badge ${escape(status)}">${escape(label.replaceAll('-', ' '))}</span>`;
const tile = (symbol, color = '') => `<span class="tile ${color}">${icon(symbol)}</span>`;
const productLink = id => '#product/' + id;
const runLink = id => '#run/' + id;
const displayName = id => ctx.products.find(p => p.id === id)?.name ?? id;
const actorName = id => ctx.actors[id]?.name ?? id;
const option = (value, label, current) => `<option value="${escape(value)}" ${value === current ? 'selected' : ''}>${escape(label)}</option>`;
const link = (url, name, cls = 'link') => `<a class="${cls}" href="${escape(url)}">${escape(name)}</a>`;
const heading = (title, subtitle, action = '') => `<div class="page-head"><div><h1>${escape(title)}</h1><p>${escape(subtitle)}</p></div>${action}</div>`;
const panel = (title, subtitle, body, action = '', extra = '') => `<section class="panel ${extra}"><div class="panel-head">
  <div><h2>${escape(title)}</h2>${subtitle ? `<p>${escape(subtitle)}</p>` : ''}</div>${action}</div>${body}</section>`;
const dataTable = (headers, rows, empty = 'No records match the current view.') => rows.length ?
  `<div class="table-wrap"><table><thead><tr>${headers.map(item => `<th scope="col">${escape(item)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(row => `<tr>${row.map(item => `<td>${item}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` :
  `<p class="empty">${escape(empty)}</p>`;

async function api(path, payload) {
  const response = await fetch('/api/' + path, payload ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  } : undefined);
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch { detail = null; }
    throw new Error(typeof detail === 'string' ? detail : 'The request could not be completed (' + response.status + ').');
  }
  return response.json();
}

function notify(message, error = false) {
  clearTimeout(toastTimer);
  const toast = document.querySelector('#toast');
  toast.className = error ? 'error' : '';
  toast.textContent = message;
  toastTimer = setTimeout(() => { toast.textContent = ''; }, 6000);
}

function route() {
  const [page, id, tab] = location.hash.slice(1).split('/');
  if (page === 'product') return { page, id, tab: tab || 'data', group: 'catalog', title: displayName(id) };
  if (page === 'run') return { page, id, group: 'operations', title: 'Run #' + id };
  const known = routes.find(row => row[0] === page) || routes[0];
  return { page: known[0], group: known[0], title: known[1] };
}

function renderShell(location) {
  const nav = ([target, label, symbol]) => `<a class="nav-link ${target === location.group ? 'active' : ''}" href="#${target}"
      aria-label="${label}" ${target === location.group ? 'aria-current="page"' : ''} title="${label}">${icon(symbol)}<span class="nav-text">${label}</span></a>`;
  document.querySelector('#sidebar').innerHTML = `<a class="brand" href="#overview" aria-label="Enterprise Data Hub home">
    <span class="brand-icon">${icon('hub')}</span><span><span class="brand-name">Enterprise Data Hub</span>
    <span class="brand-sub" style="display:block">Data Enablement</span></span></a>
    <nav><div class="nav-section"><div class="nav-label">Workspace</div>${routes.slice(0, 3).map(nav).join('')}</div>
    <div class="nav-section"><div class="nav-label">Enablement</div>${routes.slice(3).map(nav).join('')}
      <a class="nav-link" href="/docs" aria-label="API reference" title="API reference" target="_blank" rel="noopener">
      ${icon('code')}<span class="nav-text">API reference</span>${icon('external', 'external')}</a></div></nav>
    <div class="side-bottom"><strong><span class="dot"></span> Synthetic workspace</strong><p>Local data · Demo identities</p></div>`;
  const initials = actorName(ctx.actor).split(' ').slice(0, 2).map(word => word[0]).join('');
  document.querySelector('#topbar').innerHTML = `<div class="breadcrumb"><span>Workspace</span>${icon('next')}<strong>${escape(location.title)}</strong></div>
    <div class="top-actions"><form class="search" id="global-search" role="search">${icon('search')}
      <input id="global-query" name="search" value="${escape(ctx.query)}" type="search" aria-label="Search data products" placeholder="Search products…"><kbd>/</kbd></form>
    <label class="actor"><span class="avatar" aria-hidden="true">${escape(initials)}</span>
      <select id="actor" aria-label="Simulated role" title="Simulated role">${Object.entries(ctx.actors).map(([id, actor]) => option(id, actor.name, ctx.actor)).join('')}</select></label></div>`;
  document.querySelector('#actor').onchange = event => {
    ctx.actor = event.target.value;
    localStorage.setItem('hub-actor', ctx.actor);
    render();
  };
  document.querySelector('#global-search').onsubmit = event => {
    event.preventDefault();
    ctx.query = document.querySelector('#global-query').value.trim();
    if (route().page === 'catalog') render();
    else window.location.hash = 'catalog';
  };
}

function productList(products) {
  return products.map(p => `<div class="list-row"><a class="list-name" href="${productLink(p.id)}">
    ${tile(...appearance[p.id])}<span><strong>${escape(p.name)}</strong><small>${escape(p.domain)} · v${escape(p.publication?.version ?? p.approved_version)}</small></span></a>
    ${badge(p.freshness)}</div>`).join('');
}

function runTable(runs) {
  return dataTable(['Run', 'Product', 'Scenario', 'Status', 'Started'], runs.map(run => [
    link(runLink(run.id), '#' + run.id), escape(displayName(run.product_id)), escape(run.scenario === 'healthy' ? 'Standard refresh' : 'Quality incident'),
    badge(run.status), escape(timestamp(run.started_at)),
  ]), 'Run a refresh to begin collecting quality evidence.');
}

function renderOverview(data) {
  const open = data.active_alerts;
  const activeProduct = data.products[0];
  const recent = data.trend.at(-1);
  const metrics = [
    ['box', '', 'Data products', num(data.products.length), num(new Set(data.products.map(p => p.domain)).size) + ' owning domains'],
    ['clock', 'blue', 'Fresh publications', data.fresh_count + ' / ' + data.products.length, 'Within their published freshness target'],
    ['db', 'purple', 'Serving rows', num(data.published_rows), 'Accepted snapshots across all domains'],
    ['bell', 'amber', 'Open quality alerts', num(open), open ? 'Last accepted datasets still available' : 'No unresolved quality failures'],
  ];
  main.innerHTML = heading('Platform overview', 'Track published data products, reliability and ownership across domains.',
    link('#operations', 'Open operations', 'button')) + `<section class="hero">
      <div class="hero-content"><div class="hero-eyebrow">${icon('shield')} Data Enablement</div>
        <h2>From source events to trusted data</h2><p>Explore reusable datasets with named owners, versioned contracts and an auditable path to publication.</p>
        <a class="button" href="#catalog">Browse data products ${icon('arrow')}</a></div>
      <div class="hero-map" aria-label="Processing layers">
        ${[['db','Bronze'],['filter','Silver'],['stack','Gold'],['stream','Serving']].map(([symbol, label]) => `<a class="hero-step" href="#product/shipment-reliability/lineage">${icon(symbol)}${label}</a>`).join('')}
      </div>
    </section>
    <section class="metrics" aria-label="Platform metrics">${metrics.map(([symbol, color, label, value, note]) => `<article class="metric">
      <div class="metric-top">${tile(symbol, color)}${label}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></article>`).join('')}</section>
    <div class="dashboard-grid">${panel('Shipment reliability', 'Weekly on-time delivery · All carrier lanes',
      recent ? `<div class="chart-stat">${num(recent.value)}% <small>Latest delivery week</small></div>
        <canvas id="overview-chart" class="chart" role="img" aria-label="On-time delivery trends and the 95 percent target. Exact data is available in Shipment Reliability."></canvas>
        <div class="legend"><span><i class="dot"></i> On-time delivery</span><span><i class="dash"></i> 95% target</span></div>` :
        '<p class="empty">Refresh Shipment Reliability to show its trend.</p>',
      recent ? `<select class="pill-select" id="chart-range" aria-label="Chart range">${option('14','Last 14 weeks',String(ctx.chartRange))}
        ${option('6','Last 6 weeks',String(ctx.chartRange))}</select>` : '')}
    ${panel('Data product status', 'Freshness of the current accepted snapshots', productList(data.products) +
      `<div class="list-row">${link(productLink(activeProduct.id) + '/lineage', 'Explore publication lineage')}${icon('arrow')}</div>`,
      link('#catalog', 'View catalogue'))}</div>
    ${panel('Recent pipeline runs', 'Snowflake-first refresh outcomes', runTable(data.runs), link('#operations', 'View run history'), 'after-grid')}`;
  const canvas = document.querySelector('#overview-chart');
  if (canvas) {
    chart = () => lineChart(canvas, data.trend.slice(-ctx.chartRange), { percent: true });
    chart();
    document.querySelector('#chart-range').onchange = event => {
      ctx.chartRange = Number(event.target.value);
      chart();
    };
  }
}

function renderCatalog(products) {
  const domains = [...new Set(products.map(p => p.domain))];
  const query = ctx.query.toLowerCase();
  const matches = products.filter(p => (!ctx.domain || p.domain === ctx.domain) &&
    [p.name, p.domain, p.owner, p.description].some(value => value.toLowerCase().includes(query)));
  main.innerHTML = heading('Data catalogue', 'Find certified aggregates by owning domain and business purpose.') +
    `<form class="toolbar" id="catalog-filters" role="search"><input name="query" type="search" value="${escape(ctx.query)}" placeholder="Search data products" aria-label="Catalogue filter">
      <select name="domain" aria-label="Owning domain">${option('', 'All domains', ctx.domain)}${domains.map(domain => option(domain, domain, ctx.domain)).join('')}</select>
      <button class="button" type="submit">Apply filters</button></form>` +
    (matches.length ? `<section class="cards">${matches.map(p => `<article class="panel product-card">
      <div class="panel-head">${tile(...appearance[p.id])}${badge(p.freshness)}</div>
      <h2>${escape(p.name)}</h2><p>${escape(p.description)}</p>
      <div class="small muted">${escape(p.domain)} · ${escape(p.owner)}</div>
      <div class="card-footer"><span class="tiny">${ageLabel(p.freshness, p.age_hours)}</span>${link(productLink(p.id), 'Open product →')}</div>
    </article>`).join('')}</section>` : '<p class="empty">No products match these filters.</p>');
  const form = document.querySelector('#catalog-filters');
  form.onsubmit = event => {
    event.preventDefault();
    const values = new FormData(form);
    ctx.query = values.get('query').trim();
    ctx.domain = values.get('domain');
    render();
  };
}

function summary(p) {
  return `<dl class="definition"><dt>Domain</dt><dd>${escape(p.domain)}</dd><dt>Data owner</dt><dd>${escape(p.owner)}</dd>
    <dt>Consumers</dt><dd>${escape(p.consumers.join(', '))}</dd><dt>Grain</dt><dd>${escape(p.grain)}</dd>
    <dt>Freshness target</dt><dd>${p.freshness_hours}h between accepted publications</dd>
    <dt>Last publication</dt><dd>${timestamp(p.publication?.finished_at)}</dd></dl>`;
}

function dataView(p, preview) {
  const datasetInfo = panel('Product agreement', '', summary(p) + `<p class="notice" style="margin:15px 0 0">${escape(p.metric_definition)}</p>`);
  const metric = p.id === 'shipment-reliability';
  const chartPanel = panel(p.metric, p.purpose, p.trend.length ? `<div class="chart-stat">
    ${p.id === 'freight-spend' ? '€' : ''}${num(p.trend.at(-1).value)}${metric ? '%' : ''}<small>Latest period</small></div>
    <canvas class="chart" id="product-chart" role="img" aria-label="${escape(p.metric)} by period"></canvas>` : '<p class="empty">Awaiting the first publication.</p>');
  if (!preview) return `<div class="two-col">${datasetInfo}${chartPanel}</div>`;
  const filters = preview.filters;
  const form = `<form class="toolbar" id="preview-filters"><label>${escape(filters.dimension[0].toUpperCase() + filters.dimension.slice(1))}
      <select name="dimension">${option('', 'All', ctx.dimension)}${filters.values.map(value => option(value, value, ctx.dimension)).join('')}</select></label>
    <label>Period start <select name="period">${option('', 'All periods', ctx.period)}${filters.periods.map(value => option(value, value, ctx.period)).join('')}</select></label>
    <button class="button" type="submit">Apply filters</button></form>`;
  const table = dataTable(preview.columns.map(key => key.replaceAll('_', ' ')), preview.rows.map(row => preview.columns.map(key => escape(row[key]))));
  return `<div class="two-col">${chartPanel}${datasetInfo}</div>${panel('Published dataset',
    'Showing ' + preview.rows.length + ' of ' + preview.total + ' matching rows · Publication #' + preview.publication_id,
    form + table, '', 'after-grid')}`;
}

function contractView(p) {
  const c = p.contract;
  const note = p.publication?.version === c.version ? 'This approved version is currently being served.' :
    'The approved version will be served after the next successful refresh. Existing consumers keep the current snapshot until then.';
  return panel('Contract v' + c.version, c.classification, `<p class="notice">${note}</p><p class="small muted" style="margin-bottom:12px">
    Key (${escape(c.primary_key.join(', '))}) · ${escape(c.policy)}</p>` + dataTable(['Field', 'Type', 'Presence', 'Definition'],
    c.fields.map(field => [escape(field.name), escape(field.type), field.required ? 'Required' : 'Nullable', escape(field.description)])),
    link('#governance/' + p.id, 'Review changes', 'button')) +
    panel('Versioned interfaces', '', `<div class="actions">
      ${p.published_contract ? link('/api/products/' + p.id + '/contracts/' + p.published_contract.version, 'Published contract JSON', 'button') : ''}
      ${link('/api/products/' + p.id + '/contracts/' + c.version, 'Approved contract JSON', 'button')}</div>`, '', 'after-grid');
}

function checksView(events) {
  return events.map(event => {
    const checks = event.details.checks || [];
    const detail = checks.length ? checks.map(check => `<div class="check"><b>${escape(check.name)}</b>
      <span>${escape([check.observed].flat().join(', '))} / ${escape([check.expected].flat().join(', '))} ${badge(check.passed ? 'passed' : 'failed')}</span></div>`).join('') :
      `<p class="small muted">${event.details.rows != null ? num(event.details.rows) + ' records' :
        event.details.row_count != null ? num(event.details.row_count) + ' serving rows' :
        event.details.failure ? escape(event.details.failure) : 'Stage recorded'}</p>`;
    return `<div class="audit-row"><h3>${escape(event.stage)} ${badge(event.status)}</h3>${detail}</div>`;
  }).join('');
}

function lineageView(p) {
  const meta = p.publication?.metadata;
  const descriptors = [p.source, 'Original JSONL', 'Typed, latest revisions', p.grain, 'Current Parquet snapshot'];
  return panel('End-to-end lineage', p.lineage_note, `<div class="trace">${p.lineage.stages.map((stage, i) =>
    `<article class="trace-step">${icon(['stream','db','filter','stack','shield'][i])}<h3>${stage}</h3><p>${escape(descriptors[i])}</p></article>`).join('')}</div>
    ${p.lineage.shared_with.length ? `<p class="small muted" style="margin-top:14px">Uses the same source and standardisation as
      ${p.lineage.shared_with.map(other => link(productLink(other.id) + '/lineage', other.name)).join(', ')}.</p>` : ''}`) +
    (meta ? panel('Publication provenance', 'Accepted run #' + p.publication.id + ' · Contract v' + p.publication.version,
      `<dl class="definition"><dt>Source SHA-256</dt><dd class="digest">${escape(meta.source_digest)}</dd>
        <dt>Snapshot SHA-256</dt><dd class="digest">${escape(meta.snapshot_digest)}</dd>
        <dt>Input revisions</dt><dd>${num(meta.bronze_rows)}</dd><dt>Standardised events</dt><dd>${num(meta.silver_rows)}</dd>
        <dt>Serving rows</dt><dd>${num(meta.row_count)}</dd></dl>`, link(runLink(p.publication.id), 'Open execution evidence', 'button'), 'after-grid') +
      panel('Validation evidence', '', checksView(p.lineage.events), '', 'after-grid') : '');
}

function filtersQuery() {
  const values = new URLSearchParams();
  if (ctx.dimension) values.set('dimension', ctx.dimension);
  if (ctx.period) values.set('period', ctx.period);
  return values.toString() ? '?' + values : '';
}

function renderProduct(p, tab, preview) {
  const tabs = [['data','Preview'], ['contract','Contract'], ['lineage','Lineage']];
  const action = p.publication ? `<a class="button primary" href="/api/products/${p.id}/download${tab === 'data' ? filtersQuery() : ''}">${icon('download')} Download CSV</a>` : '';
  const base = productLink(p.id);
  main.innerHTML = heading(p.name, p.description, action) + `<nav class="tab-line" aria-label="Product sections">${tabs.map(([key,label]) =>
    `<a href="${base}/${key}" class="tab ${key === tab ? 'active' : ''}">${label}</a>`).join('')}</nav>` +
    (tab === 'contract' ? contractView(p) : tab === 'lineage' ? lineageView(p) : dataView(p, preview));
  const filter = document.querySelector('#preview-filters');
  if (filter) filter.onsubmit = event => {
    event.preventDefault();
    const values = new FormData(filter);
    ctx.dimension = values.get('dimension');
    ctx.period = values.get('period');
    render();
  };
  const canvas = document.querySelector('#product-chart');
  if (canvas) {
    chart = () => lineChart(canvas, p.trend, { percent: p.id === 'shipment-reliability' });
    chart();
  }
}

function bindForms() {
  for (const form of main.querySelectorAll('form[data-endpoint]')) {
    form.onsubmit = async event => {
      event.preventDefault();
      if (form.dataset.busy) return;
      const data = Object.fromEntries(new FormData(form));
      if (event.submitter?.name) data[event.submitter.name] = event.submitter.value;
      form.dataset.busy = 'true';
      for (const button of form.querySelectorAll('button')) button.disabled = true;
      try {
        const result = await api(form.dataset.endpoint, { ...data, actor: ctx.actor });
        notify({
          published: 'The new snapshot is available in Serving.',
          blocked: 'The change was blocked. See the validation evidence.',
          approved: 'Contract approved. A successful refresh will publish it.',
          acknowledged: 'Alert acknowledged.',
          rejected: 'The proposal was rejected and the decision was recorded.',
        }[result.status] || 'The action was recorded.');
        if (form.dataset.toRun) location.hash = 'run/' + result.id;
        else render();
      } catch (error) {
        notify(error.message, true);
        for (const button of form.querySelectorAll('button')) button.disabled = false;
        delete form.dataset.busy;
      }
    };
  }
}

function renderOperations(runs, alerts) {
  const operator = ctx.actors[ctx.actor]?.role === 'operator';
  const refreshForm = operator ? `<form class="inline" data-endpoint="runs" data-to-run="true">
    <label class="field"><span>Data product</span><select class="form-control" name="product_id">${ctx.products.map(p => option(p.id, p.name)).join('')}</select></label>
    <label class="field"><span>Source scenario</span><select class="form-control" name="scenario">
      ${option('healthy','Standard refresh')}${option('negative-money','Inject negative monetary value')}</select></label>
    <button class="button primary" type="submit">${icon('play')} Run pipeline</button></form>` :
    '<div class="notice">Select Platform Operator to start a run or acknowledge quality alerts.</div>';
  const quality = dataTable(['Product', 'Impact', 'State', 'Run', 'Action'], alerts.quality.map(alert => [
    escape(displayName(alert.product_id)), escape(alert.stage) + ' gate', badge(alert.status), link(runLink(alert.run_id), '#' + alert.run_id),
    operator && alert.status === 'open' ? `<form data-endpoint="alerts/${alert.id}/acknowledge"><button class="button" type="submit">Acknowledge</button></form>` : '—',
  ]), 'No quality alerts have been recorded.');
  const freshness = dataTable(['Product', 'Owner', 'Age', 'Target', 'State'], alerts.freshness.map(a => [
    escape(displayName(a.product_id)), escape(a.owner), a.age_hours == null ? '—' : num(a.age_hours) + 'h',
    a.target_hours + 'h', badge(a.status),
  ]), 'Every product has an accepted snapshot within its freshness target.');
  main.innerHTML = heading('Operations', 'Inspect pipeline evidence, manage alerts and replay the synthetic feeds.') + `<div class="section-stack">
    ${panel('Refresh a data product', 'Snowflake-native architecture with Bronze, Silver, Gold and governed Serving. The local demo reproduces quality gates.', refreshForm)}
    ${panel('Quality alerts', 'Failures leave the last accepted snapshot available. A later successful refresh resolves them.', quality)}
    ${panel('Freshness watch', 'Measured from the latest accepted publication.', freshness)}
    ${panel('Run history', 'Recent quality gates and publication outcomes.', runTable(runs))}
    </div>`;
  bindForms();
}

function renderRun(run) {
  const statusText = {
    blocked: 'The run was blocked. Serving retains the last accepted publication.',
    published: 'The snapshot became current after both quality gates passed.',
    superseded: 'The run completed after a newer run or approved contract took precedence.',
    running: 'The local refresh is processing this batch.',
  }[run.status];
  main.innerHTML = heading('Run #' + run.id, displayName(run.product_id) + ' · ' + timestamp(run.started_at),
    link('#operations', 'Back to operations', 'button')) + `<div class="notice ${run.status === 'blocked' ? 'warning' : ''}">${statusText}</div>` +
    panel('Execution evidence', 'Execution ' + run.execution_id, checksView(run.events), badge(run.status));
}

function renderGovernance(p, requests) {
  const owner = p.owner_actor === ctx.actor;
  const steward = ctx.actors[ctx.actor]?.role === 'steward';
  const picker = `<div class="toolbar"><label for="governance-product">Data product</label><select id="governance-product">
    ${ctx.products.map(other => option(other.id, other.name, p.id)).join('')}</select></div>`;
  const form = owner ? `<form class="inline" data-endpoint="products/${p.id}/changes">
    <label class="field"><span>Candidate change</span><select class="form-control" name="action">
    ${option('add-note', 'Append an optional annotation')}${option('remove-metric', 'Remove a published metric')}</select></label>
    <label class="field wide"><span>Business rationale</span><input class="form-control" name="rationale" required minlength="10" maxlength="500" placeholder="What consumer need does this address?"></label>
    <button class="button primary" type="submit">Submit proposal</button></form>` :
    '<p class="notice">Domain owners submit proposals. A Governance Steward reviews compatible candidates.</p>';
  const items = requests.map(change => `<div class="audit-row">
    <h3>Proposal #${change.id} · v${escape(change.base_version)} → v${escape(change.candidate_version)} ${badge(change.status)}</h3>
    <p>${escape(change.rationale)}</p>
    <p class="small muted">${escape(actorName(change.author))} · ${timestamp(change.submitted_at)}</p>
    ${change.findings.length ? `<ul class="small">${change.findings.map(finding => `<li>${escape(finding)}</li>`).join('')}</ul>` : ''}
    ${change.reviewer ? `<p class="small"><strong>${escape(actorName(change.reviewer))}</strong> · ${escape(change.decision)}</p>` : ''}
    ${steward && change.status === 'pending' ? `<form class="inline" data-endpoint="changes/${change.id}/decision">
      <label class="field wide"><span>Review note</span><input class="form-control" name="note" required minlength="10" maxlength="500" placeholder="Record the independent review rationale"></label>
      <button class="button primary" type="submit" name="decision" value="approve">Approve</button>
      <button class="button danger" type="submit" name="decision" value="reject">Reject</button></form>` : ''}</div>`).join('');
  main.innerHTML = heading('Governance', 'Propose contract changes, check compatibility and record independent decisions.',
    link(productLink(p.id) + '/contract', 'Open contract', 'button')) + picker +
    panel('Propose a change', p.name + ' · Approved contract v' + p.approved_version, form) +
    panel('Contract change history', 'Nullable additions can be reviewed within a major version. Breaking proposals are blocked.',
      items || '<p class="empty">No proposals yet. Choose the owning role to submit a change.</p>', '', 'after-grid');
  document.querySelector('#governance-product').onchange = event => { location.hash = 'governance/' + event.target.value; };
  bindForms();
}

function renderDelivery(delivery) {
  const milestones = delivery.milestones.map(item => `<article class="panel product-card"><div class="panel-head"><h2>${escape(item.title)}</h2>
    ${badge(item.state, item.state.replace('-', ' '))}</div><p>${escape(item.goal)}</p><div class="small muted">Acceptance: ${escape(item.exit)}</div></article>`).join('');
  const issues = dataTable(['ID', 'Work item', 'Owner', 'Score', 'State'], delivery.items.map(item => [
    escape(item.id), `<a href="https://github.com/roger-sans/enterprise-datahub-demo/issues?q=${encodeURIComponent('"' + item.id + '"')}">${escape(item.title)}</a>`,
    escape(item.owner), item.score, badge(item.status),
  ]));
  main.innerHTML = heading('Delivery roadmap', 'Prioritise adoption, interoperability and reliability against explicit release criteria.') +
    `<div class="cards">${milestones}</div>` + panel('Product backlog', 'Scored by value, risk reduction and effort. GitHub Issues hosts the working backlog after initialisation.', issues, '', 'after-grid');
}

let viewedProduct;
async function render() {
  const renderId = ++ctx.renderId;
  chart = null;
  try {
    if (!Object.keys(ctx.actors).length) ctx.actors = await api('actors');
    if (!ctx.actors[ctx.actor]) ctx.actor = 'platform-operator';
    ctx.products = await api('products');
    if (renderId !== ctx.renderId) return;
    const selected = route();
    renderShell(selected);
    let data, extra;
    if (selected.page === 'overview') data = await api('overview');
    if (selected.page === 'product') {
      if (viewedProduct !== selected.id) {
        viewedProduct = selected.id;
        ctx.period = '';
        ctx.dimension = '';
      }
      data = await api('products/' + encodeURIComponent(selected.id));
      if (selected.tab === 'data' && data.publication) extra = await api('products/' + data.id + '/data' + filtersQuery());
    }
    if (selected.page === 'operations') [data, extra] = await Promise.all([api('runs'), api('alerts')]);
    if (selected.page === 'run') data = await api('runs/' + encodeURIComponent(selected.id));
    if (selected.page === 'governance') {
      const wanted = ctx.products.find(p => p.id === location.hash.split('/')[1]) || ctx.products[0];
      data = wanted;
      extra = await api('products/' + wanted.id + '/changes');
    }
    if (selected.page === 'delivery') data = await api('delivery');
    if (renderId !== ctx.renderId) return;
    const views = {
      overview: () => renderOverview(data), catalog: () => renderCatalog(ctx.products),
      product: () => renderProduct(data, selected.tab, extra),
      operations: () => renderOperations(data, extra), run: () => renderRun(data),
      governance: () => renderGovernance(data, extra), delivery: () => renderDelivery(data),
    };
    views[selected.page]();
  } catch (error) {
    if (renderId === ctx.renderId) main.innerHTML = '<p class="notice error">' + escape(error.message) + '</p>';
  }
}

window.addEventListener('hashchange', () => { window.scrollTo(0, 0); render(); });
window.addEventListener('resize', () => chart?.());
document.addEventListener('keydown', event => {
  if (event.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
    event.preventDefault();
    document.querySelector('#global-query')?.focus();
  }
});
document.querySelector('.skip').addEventListener('click', event => {
  event.preventDefault();
  main.focus();
});
render();
