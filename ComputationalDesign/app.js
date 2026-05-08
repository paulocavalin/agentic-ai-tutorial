/**
 * ComputationalDesign/app.js — Pipeline UI controller + Three.js STL viewer
 * ES module, loaded via <script type="module">
 */

import * as THREE from 'three';
import { STLLoader }     from 'three/addons/loaders/STLLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const API = 'http://localhost:8004';

// ── Example buttons ──────────────────────────────────────────────────────────

document.querySelectorAll('.example-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.getElementById('description').value = btn.dataset.text;
  });
});

// ── Form submit ───────────────────────────────────────────────────────────────

document.getElementById('design-btn').addEventListener('click', startPipeline);
document.getElementById('description').addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.ctrlKey) startPipeline();
});

async function startPipeline() {
  const description = document.getElementById('description').value.trim();
  if (!description) return;

  const btn = document.getElementById('design-btn');
  btn.disabled = true;
  btn.textContent = '⬡ Designing…';

  resetPipeline();
  document.getElementById('pipeline').classList.remove('hidden');
  document.getElementById('pipeline').scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await fetch(`${API}/design`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ description }),
    });
    const { id } = await res.json();
    listenToStream(id);
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">⬡</span> Design it';
    alert(`Could not connect to the server: ${err.message}`);
  }
}

// ── Pipeline reset ────────────────────────────────────────────────────────────

function resetPipeline() {
  for (let i = 1; i <= 6; i++) {
    const card = document.getElementById(`stage-${i}`);
    card.className = 'stage-card';
    setBadge(i, 'pending', 'Pending');
    card.querySelector('.stage-placeholder').classList.remove('hidden');
    card.querySelector('.stage-content').classList.add('hidden');
  }
  // Clear stage 3 viewer
  const wrap = document.getElementById('stl-canvas-wrap');
  wrap.innerHTML = '';
  document.getElementById('stl-loading').classList.remove('hidden');
  document.getElementById('stl-unavailable').classList.add('hidden');
  _stlRendered = false;
}

// ── SSE stream handler ────────────────────────────────────────────────────────

function listenToStream(designId) {
  const es = new EventSource(`${API}/design/${designId}/stream`);

  es.onmessage = e => {
    const event = JSON.parse(e.data);

    if (event.type === 'complete') {
      es.close();
      const btn = document.getElementById('design-btn');
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-icon">⬡</span> Design it';
      return;
    }

    if (event.type === 'error') {
      es.close();
      const btn = document.getElementById('design-btn');
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-icon">⬡</span> Design it';
      console.error('Pipeline error:', event.message);
      showError(event.message);
      return;
    }

    const { stage, status, data } = event;
    updateStage(stage, status, data, designId);
  };

  es.onerror = () => {
    es.close();
    const btn = document.getElementById('design-btn');
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">⬡</span> Design it';
  };
}

function showError(message) {
  for (let i = 1; i <= 6; i++) {
    const card = document.getElementById(`stage-${i}`);
    if (card.classList.contains('running')) {
      setBadge(i, 'error', 'Error');
      card.classList.remove('running');
      card.classList.add('error');
      card.querySelector('.stage-placeholder').textContent = `Error: ${message}`;
    }
  }
}

// ── Stage updaters ────────────────────────────────────────────────────────────

function updateStage(stage, status, data, designId) {
  const card = document.getElementById(`stage-${stage}`);

  if (status === 'running') {
    card.classList.add('running');
    setBadge(stage, 'running', 'Running');
    card.querySelector('.stage-placeholder').innerHTML =
      '<span class="spin">⬡</span> Processing…';
    return;
  }

  if (status === 'done') {
    card.classList.remove('running');
    card.classList.add('done');
    setBadge(stage, 'done', 'Done');
    card.querySelector('.stage-placeholder').classList.add('hidden');
    card.querySelector('.stage-content').classList.remove('hidden');

    switch (stage) {
      case 1: renderBrief(data);                    break;
      case 2: renderCode(data, designId);           break;
      case 3: renderPreview(data, designId);        break;
      case 4: renderOptimize(data);                 break;
      case 5: renderPrintSettings(data);            break;
      case 6: renderBOM(data);                      break;
    }
  }
}

function setBadge(stage, cls, text) {
  const badge = document.querySelector(`#stage-${stage} .stage-badge`);
  badge.className = `stage-badge ${cls}`;
  badge.textContent = text;
}

// ── Stage 1: Brief ────────────────────────────────────────────────────────────

function renderBrief(brief) {
  const grid = document.getElementById('brief-grid');
  grid.innerHTML = '';

  const dims = brief.dimensions || {};
  const dimStr = dims.width_mm
    ? `${dims.width_mm} × ${dims.height_mm} × ${dims.depth_mm} mm`
    : 'Not specified';

  const fields = [
    { label: 'Project',     value: brief.project_name || '—' },
    { label: 'Material',    value: brief.material      || '—' },
    { label: 'Dimensions',  value: dimStr },
    { label: 'Purpose',     value: brief.purpose       || '—', full: true },
  ];

  fields.forEach(({ label, value, full }) => {
    const item = el('div', `brief-item${full ? ' full' : ''}`);
    item.innerHTML = `<div class="brief-label">${label}</div><div class="brief-value">${esc(value)}</div>`;
    grid.appendChild(item);
  });

  // Features
  if (brief.features?.length) {
    const item = el('div', 'brief-item full');
    item.innerHTML = `<div class="brief-label">Features</div><div class="brief-value">
      ${brief.features.map(f => `<span class="brief-tag">${esc(f)}</span>`).join('')}
    </div>`;
    grid.appendChild(item);
  }

  // Hardware
  if (brief.hardware?.length) {
    const item = el('div', 'brief-item full');
    item.innerHTML = `<div class="brief-label">Hardware</div><div class="brief-value">
      ${brief.hardware.map(h => `<span class="brief-tag">${esc(h)}</span>`).join('')}
    </div>`;
    grid.appendChild(item);
  }

  // Constraints
  if (brief.constraints?.length) {
    const item = el('div', 'brief-item full');
    item.innerHTML = `<div class="brief-label">Constraints</div><div class="brief-value">
      ${brief.constraints.map(c => `<span class="brief-tag">${esc(c)}</span>`).join('')}
    </div>`;
    grid.appendChild(item);
  }
}

// ── Stage 2: OpenSCAD Code ────────────────────────────────────────────────────

function renderCode(data, designId) {
  const code = document.getElementById('scad-code');
  code.textContent = data.scad_code;
  hljs.highlightElement(code);

  const dl = document.getElementById('scad-download');
  dl.href = `${API}/design/${designId}/scad`;
  dl.classList.remove('hidden');
}

// ── Stage 3: Render ───────────────────────────────────────────────────────────

let _stlRendered = false;

function renderPreview(data, designId) {
  if (data.has_png) {
    const wrap = document.getElementById('render-png-wrap');
    const img  = document.getElementById('render-png');
    img.src = `${API}/design/${designId}/png?t=${Date.now()}`;
    wrap.classList.remove('hidden');
  } else {
    document.getElementById('render-fallback').classList.remove('hidden');
  }

  if (data.has_stl) {
    const dl = document.getElementById('stl-download');
    dl.href = `${API}/design/${designId}/stl`;
    dl.classList.remove('hidden');

    const stlUrl = `${API}/design/${designId}/stl`;
    initSTLViewer(stlUrl);
  } else {
    document.getElementById('stl-loading').classList.add('hidden');
    document.getElementById('stl-unavailable').classList.remove('hidden');
  }
}

function initSTLViewer(stlUrl) {
  if (_stlRendered) return;
  _stlRendered = true;

  const container = document.getElementById('stl-canvas-wrap');
  const w = container.parentElement.clientWidth  || 320;
  const h = container.parentElement.clientHeight || 220;

  // Scene
  const scene    = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a10);

  // Camera
  const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 5000);
  camera.position.set(0, 100, 200);

  // Renderer
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  // Lights
  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(1, 2, 3);
  scene.add(dirLight);

  // Grid
  const grid = new THREE.GridHelper(300, 30, 0x2c3050, 0x1a1d27);
  scene.add(grid);

  // Controls
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  // Load STL
  const loader = new STLLoader();
  loader.load(
    stlUrl,
    geometry => {
      document.getElementById('stl-loading').classList.add('hidden');
      geometry.computeBoundingBox();
      geometry.computeVertexNormals();

      // Centre and scale
      const box    = new THREE.Box3().setFromObject(new THREE.Mesh(geometry));
      const size   = new THREE.Vector3();
      const centre = new THREE.Vector3();
      box.getSize(size);
      box.getCenter(centre);

      const maxDim  = Math.max(size.x, size.y, size.z);
      const scale   = 100 / maxDim;
      geometry.translate(-centre.x, -centre.y, -centre.z);

      const material = new THREE.MeshPhongMaterial({
        color:     0xf97316,
        specular:  0x333333,
        shininess: 60,
        side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.scale.set(scale, scale, scale);
      mesh.position.y = size.z * scale / 2;
      scene.add(mesh);

      camera.position.set(
        size.x * scale * 1.2,
        size.y * scale * 1.2,
        size.z * scale * 1.5,
      );
      controls.update();
    },
    undefined,
    err => {
      console.warn('STL load failed', err);
      document.getElementById('stl-loading').classList.add('hidden');
      document.getElementById('stl-unavailable').classList.remove('hidden');
    }
  );

  // Animate
  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  // Resize
  const resizeObs = new ResizeObserver(() => {
    const nw = container.parentElement.clientWidth;
    const nh = container.parentElement.clientHeight;
    camera.aspect = nw / nh;
    camera.updateProjectionMatrix();
    renderer.setSize(nw, nh);
  });
  resizeObs.observe(container.parentElement);
}

// ── Stage 4: Optimization ─────────────────────────────────────────────────────

function renderOptimize(data) {
  // Issues
  const issuesList = document.getElementById('opt-issues');
  issuesList.innerHTML = '';
  (data.issues || []).forEach(issue => {
    const sev = (issue.severity || 'low').toLowerCase();
    const item = el('div', `issue-item ${sev}`);
    item.innerHTML = `
      <div>
        <span class="issue-sev">${sev}</span>
      </div>
      <div class="issue-text">
        <div>${esc(issue.description)}</div>
        ${issue.fix ? `<div class="issue-fix">→ ${esc(issue.fix)}</div>` : ''}
      </div>
    `;
    issuesList.appendChild(item);
  });

  if (!data.issues?.length) {
    issuesList.innerHTML = '<div class="opt-summary" style="border-color:var(--green)">✅ No printability issues found.</div>';
  }

  // Summary
  if (data.summary) {
    document.getElementById('opt-summary').textContent = data.summary;
  }

  // Optimized code
  const code = document.getElementById('opt-code');
  if (data.optimized_code) {
    code.textContent = data.optimized_code;
    hljs.highlightElement(code);
  } else {
    document.getElementById('opt-code-toolbar').classList.add('hidden');
  }
}

// ── Stage 5: Print Settings ───────────────────────────────────────────────────

function renderPrintSettings(s) {
  const grid = document.getElementById('print-settings-grid');
  grid.innerHTML = '';

  const fields = [
    { label: 'Material',     value: s.material,           unit: '' },
    { label: 'Layer Height', value: s.layer_height_mm,    unit: 'mm' },
    { label: 'Infill',       value: s.infill_percent,     unit: '%' },
    { label: 'Infill Pattern',value: s.infill_pattern,    unit: '' },
    { label: 'Wall Count',   value: s.wall_count,         unit: 'lines' },
    { label: 'Nozzle Temp',  value: s.nozzle_temp_c,      unit: '°C' },
    { label: 'Bed Temp',     value: s.bed_temp_c,         unit: '°C' },
    { label: 'Print Speed',  value: s.print_speed_mms,    unit: 'mm/s' },
    { label: 'Supports',     value: s.supports,           unit: '' },
    { label: 'Cooling',      value: s.cooling,            unit: '' },
    { label: 'Est. Time',    value: s.estimated_time_hours, unit: 'h' },
    { label: 'Filament',     value: s.estimated_filament_g, unit: 'g' },
  ];

  fields.forEach(({ label, value, unit }) => {
    if (value === undefined || value === null) return;
    const item = el('div', 'setting-item');
    item.innerHTML = `
      <div class="setting-label">${label}</div>
      <div class="setting-value">${esc(String(value))}</div>
      ${unit ? `<div class="setting-unit">${unit}</div>` : ''}
    `;
    grid.appendChild(item);
  });

  // Notes
  const notesEl = document.getElementById('print-notes');
  notesEl.innerHTML = '';
  const notes = [...(s.notes || [])];
  if (s.orientation_tip) notes.unshift(`Orientation: ${s.orientation_tip}`);
  notes.forEach(n => {
    const item = el('div', 'print-note-item');
    item.textContent = n;
    notesEl.appendChild(item);
  });
}

// ── Stage 6: BOM ─────────────────────────────────────────────────────────────

function renderBOM(data) {
  const tbody = document.getElementById('bom-tbody');
  tbody.innerHTML = '';
  (data.bom || []).forEach((row, i) => {
    const subtotal = row.qty && row.price_brl
      ? (row.qty * row.price_brl).toFixed(2)
      : '—';
    const inStock  = row.in_stock !== false;
    const tr       = document.createElement('tr');
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${esc(row.item)}</td>
      <td><span class="sku-tag">${esc(row.sku || '—')}</span></td>
      <td>${row.qty ?? '—'}</td>
      <td>${esc(row.unit || '—')}</td>
      <td>R$ ${row.price_brl?.toFixed(2) ?? '—'}</td>
      <td>R$ ${subtotal}</td>
      <td><span class="stock-badge ${inStock ? 'in' : 'out'}">${inStock ? 'In Stock' : 'Check'}</span></td>
    `;
    tbody.appendChild(tr);
  });

  const footer = document.getElementById('bom-footer');
  footer.innerHTML = `
    <div>
      <div class="bom-total-label">Estimated Total</div>
      <div class="bom-total">R$ ${(data.total_estimated_brl || 0).toFixed(2)}</div>
    </div>
    ${data.sourcing_notes ? `<div class="bom-sourcing-note">${esc(data.sourcing_notes)}</div>` : ''}
  `;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function el(tag, className) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  return e;
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
