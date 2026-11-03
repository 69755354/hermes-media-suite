const $ = (selector, root = document) => root.querySelector(selector);
// > 执行者：codex
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const idem = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}-request`);
// 部署前缀由服务端注入；页面跳转、请求与动态媒体 URL 共用同一生成器。
const API_BASE = String(window.APP_BASE || '').replace(/\/+$/, '');
const p = (path) => {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) return path;
  if (!API_BASE || path === API_BASE || path.startsWith(`${API_BASE}/`)) return path;
  return `${API_BASE}${path}`;
};
async function api(url, options = {}) {
  if (url.startsWith('/')) url = p(url);
  options.headers = {...(options.headers || {})};
  if (window.CSRF) options.headers['X-CSRF-Token'] = window.CSRF;
  if (options.idempotent) options.headers['Idempotency-Key'] = options.idempotencyKey || idem();
  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  delete options.idempotent;
  delete options.idempotencyKey;
  const response = await fetch(url, options);
  if (response.status === 304) return {notModified: true};
  let data;
  try { data = await response.json(); } catch { data = {message: await response.text()}; }
  if (!response.ok) throw new Error(data.message || '操作失败');
  return data;
}

const login = $('#login-form');
if (login) {
  login.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const data = await api('/api/v1/auth/login', {method: 'POST', body: {account: login.account.value, password: login.password.value, role: login.dataset.role}});
      location.href = p(data.next);
    } catch (error) { $('#login-error').textContent = error.message; }
  });
}

const access = $('#access-form');
if (access) {
  access.addEventListener('submit', async (event) => {
    event.preventDefault();
    $('#access-error').textContent = '';
    try {
      const data = await api('/api/v1/billing/access', {
        method: 'POST',
        body: {customer_id: access.customer_id.value.trim()}
      });
      location.href = p(data.next);
    } catch (error) { $('#access-error').textContent = error.message; }
  });
}

const wizard = $('#wizard');
if (wizard) {
  let step = 1;
  const form = $('#project-form');
  const selectedContentType = () => form.querySelector('[name=content_type]:checked')?.value || '';
  const refreshContentBranch = () => {
    const contentType = selectedContentType();
    $$('[data-content-branch]', form).forEach((section) => {
      const active = section.dataset.contentBranch === contentType;
      section.hidden = !active;
      $$('input, select, textarea', section).forEach((input) => {
        input.disabled = !active;
        input.required = active && input.hasAttribute('data-branch-required');
      });
    });
    if (contentType === 'drama') {
      const direction = form.drama_direction.value;
      form.character_count.value = direction === 'dual' ? '2' : '1';
    }
  };
  const paint = () => {
    $$('.wizard-step').forEach((item, index) => item.classList.toggle('active', index === step - 1));
    $$('.steps span').forEach((item, index) => item.classList.toggle('active', index <= step - 1));
    $('#prev-step').style.visibility = step === 1 ? 'hidden' : 'visible';
    $('#next-step').classList.toggle('hidden', step === 3);
    $('#submit-project').classList.toggle('hidden', step !== 3);
  };
  $('#next-step').onclick = () => {
    const current = $(`.wizard-step[data-step="${step}"]`, form);
    const invalid = $$('input, select, textarea', current).find((input) => !input.disabled && !input.checkValidity());
    if (invalid) {
      invalid.reportValidity();
      return;
    }
    step = Math.min(3, step + 1);
    paint();
  };
  $('#prev-step').onclick = () => { step = Math.max(1, step - 1); paint(); };
  const refreshIndustryCopy = () => {
    const selected = form.industry_path.selectedOptions[0];
    $('#signature-label').textContent = selected.dataset.signatureLabel;
    $('#signature-item').placeholder = selected.dataset.signaturePlaceholder;
    $('#material-hint').textContent = selected.dataset.materialHint;
  };
  form.industry_path.addEventListener('change', refreshIndustryCopy);
  $$('[name=content_type]', form).forEach((input) => input.addEventListener('change', refreshContentBranch));
  form.drama_direction.addEventListener('change', refreshContentBranch);
  let redlineTimer;
  wizard.querySelector('[name=selling_points]').addEventListener('input', (event) => {
    clearTimeout(redlineTimer);
    redlineTimer = setTimeout(async () => {
      try {
        const data = await api('/api/v1/redline-preview', {method: 'POST', body: {text: event.target.value, industry_path: form.industry_path.value}});
        $('#redline-result').textContent = data.findings.length ? data.findings.map((row) => `${row.term}：${row.message}`).join('；') : '尚未发现确定性风险词';
      } catch (_) { $('#redline-result').textContent = '预检暂不可用，提交时仍会再次检查'; }
    }, 300);
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    $('#project-error').textContent = '';
    if (!form.content_authorization.checked) {
      $('#project-error').textContent = '请确认同意拍摄和使用素材制作内容';
      return;
    }
    const contentType = selectedContentType();
    if (!contentType) {
      $('#project-error').textContent = '请先选择探店视频、剧情视频或口播视频';
      return;
    }
    const groupDefinitions = {
      store_visit: [
        ['storefront_assets', 'storefront_photo', '门头照'],
        ['product_assets', 'product_photo', '产品/菜单'],
        ['interior_assets', 'interior_photo', '店内环境'],
        ['price_assets', 'price_board_photo', '价格素材']
      ],
      drama: [
        ['drama_scene_assets', 'drama_scene_reference', '场景参考'],
        ['character_assets', 'character_reference', '人物参考']
      ],
      oral: [['presenter_assets', 'presenter_portrait', '出镜人形象']]
    };
    const requiredGroups = contentType === 'store_visit' ? ['storefront_assets', 'product_assets'] : contentType === 'oral' ? ['presenter_assets'] : [];
    const uploadGroups = groupDefinitions[contentType];
    for (const inputName of requiredGroups) {
      if (!form.elements[inputName].files.length) {
        const label = uploadGroups.find(([name]) => name === inputName)[2];
        $('#project-error').textContent = `请上传${label}`;
        return;
      }
    }
    const plannedUploads = [];
    uploadGroups.forEach(([inputName, evidenceType]) => {
      [...form.elements[inputName].files].forEach((file, index) => {
        plannedUploads.push({file, plannedId: `asset_${evidenceType}_${index + 1}`, evidenceType});
      });
    });
    const evidencePlan = plannedUploads.map((item) => ({
      asset_id: item.plannedId,
      evidence_type: item.evidenceType,
      store_id: 'store_main',
      rights_confirmed: true
    }));
    const body = {
      content_type: contentType,
      industry_path: form.industry_path.value,
      business_name: form.business_name.value.trim(),
      address: form.address.value.trim(),
      contact: form.contact.value.trim(),
      selling_points: form.selling_points.value.split('\n').map((item) => item.trim()).filter(Boolean),
      evidence_assets: evidencePlan,
      content_authorization: {
        accepted: true,
        portrait_confirmed: form.portrait_rights.checked
      },
      prefs: {show_process: form.show_process.value},
      piece_format: 'VIDEO_SHORT',
      platform: '抖音'
    };
    if (contentType === 'store_visit') {
      body.signature_item = form.signature_item.value.trim();
      body.average_spend_fen = Math.round(Number(form.average_spend.value) * 100);
      body.offer = {
        name: form.offer_name.value.trim(),
        specification: form.offer_spec.value.trim(),
        amount_fen: Math.round(Number(form.offer_amount.value) * 100)
      };
    } else if (contentType === 'drama') {
      body.drama_direction = form.drama_direction.value;
      body.character_count = Number(form.character_count.value);
    } else {
      const direction = form.oral_content_direction.value.trim();
      const style = form.reference_style.value.trim();
      if (direction) body.oral_content_direction = direction;
      if (style) body.reference_style = style;
    }
    try {
      const created = await api('/api/v1/projects', {method: 'POST', body, idempotent: true});
      for (const item of plannedUploads) {
        const upload = new FormData();
        upload.append('file', item.file);
        upload.append('store_id', 'store_main');
        upload.append('planned_asset_id', item.plannedId);
        upload.append('evidence_type', item.evidenceType);
        await api(`/api/v1/projects/${created.project_id}/assets`, {method: 'POST', body: upload, idempotent: true});
      }
      location.href = p(`/projects/${created.project_id}`);
    } catch (error) { $('#project-error').textContent = error.message; }
  });
  refreshIndustryCopy();
  refreshContentBranch();
  paint();
}

let progressEtag = null;
async function loadProgress() {
  const headers = progressEtag ? {'If-None-Match': progressEtag} : {};
  const response = await fetch(p(`/api/v1/projects/${window.PROJECT_ID}/progress`), {headers});
  if (response.status === 304) return false;
  if (!response.ok) throw new Error('进度暂不可用');
  progressEtag = response.headers.get('ETag');
  const data = await response.json();
  $('#current-line').textContent = data.current_one_liner;
  $('#order-status').textContent = data.order_status;
  $('#stage-track').innerHTML = data.stages.map((row) => `<article class="stage ${row.status}"><strong>${row.label}</strong><small>${row.status === 'done' ? '已完成' : row.status === 'active' ? '进行中' : '待开始'}</small><small>${row.pct}%</small></article>`).join('');
  if (data.pending_confirmation) {
    $('#pending-confirm').classList.remove('hidden');
    $('#pending-title').textContent = data.pending_confirmation.confirm_id === 'C1' ? '内容方案等你看一下' : '成片等你看一下';
    $('#pending-link').href = p(`/projects/${window.PROJECT_ID}/confirm/${data.pending_confirmation.confirm_id}`);
  } else { $('#pending-confirm').classList.add('hidden'); }
  const artifacts = await api(`/api/v1/projects/${window.PROJECT_ID}/artifacts`);
  $('#artifacts').innerHTML = artifacts.items.map((row) => `<details class="artifact" data-view="${row.client_view_id}"><summary>${row.label}</summary><div class="artifact-content">点击展开加载</div></details>`).join('') || '<div class="card empty">专业产出正在准备。</div>';
  $$('.artifact').forEach((element) => element.addEventListener('toggle', async () => {
    if (element.open && !element.dataset.loaded) {
      const item = await api(`/api/v1/projects/${window.PROJECT_ID}/artifacts/${element.dataset.view}`);
      $('.artifact-content', element).innerHTML = `${item.rendered_html}${item.media_url ? `<video controls playsinline src="${p(item.media_url)}" class="media-preview"></video>` : ''}`;
      element.dataset.loaded = '1';
    }
  }));
  return true;
}

if (window.PAGE === 'progress') {
  loadProgress().catch(() => { $('#current-line').textContent = '暂时不可用，已通知负责人'; });
  let backoff = 5000;
  const poll = async () => {
    try {
      if (!document.hidden) {
        const changed = await loadProgress();
        backoff = changed ? 5000 : Math.min(Math.ceil(backoff * 1.5), 15000);
      } else {
        backoff = 30000;
      }
    } catch (_) { backoff = Math.min(backoff * 2, 30000); }
    setTimeout(poll, backoff + Math.floor(Math.random() * 700));
  };
  setTimeout(poll, backoff);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) loadProgress().catch(() => {});
  });
  $('#process-toggle').addEventListener('change', async (event) => {
    await api(`/api/v1/projects/${window.PROJECT_ID}/preferences`, {method: 'PATCH', body: {show_process: event.target.checked ? 'full' : 'result_only'}});
    await loadProgress();
  });
}

if (window.PAGE === 'confirm') {
  const viewIds = window.CONFIRM_ID === 'C1' ? ['D_CYCLE_TOPICS', 'D_CYCLE_COPY_SET'] : ['D_CYCLE_MEDIA', 'D_CYCLE_PLATFORM_COPY'];
  Promise.all(viewIds.map((id) => api(`/api/v1/projects/${window.PROJECT_ID}/artifacts/${id}`).catch(() => null))).then((items) => {
    $('#confirm-preview').innerHTML = items.filter(Boolean).map((item) => `<section>${item.rendered_html}${item.media_url ? `<video controls playsinline src="${p(item.media_url)}" class="media-preview"></video>` : ''}</section>`).join('') || '<p>内容仍在准备，请稍后刷新。</p>';
  });
  const submitDecision = async (body) => {
    try {
      await api(`/api/v1/projects/${window.PROJECT_ID}/confirmations/${window.CONFIRM_ID}`, {method: 'POST', body: {...body, revision: window.CONFIRM_REVISION}, idempotent: true});
      location.href = p(`/projects/${window.PROJECT_ID}`);
    } catch (error) { $('#confirm-message').textContent = error.message; }
  };
  $('#confirm-ok').onclick = () => submitDecision({decision: 'ok'});
  $('#confirm-pause').onclick = () => submitDecision({decision: 'pause'});
  $('#confirm-revise').onclick = () => $('#revision-form').classList.toggle('hidden');
  $('#revision-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submitDecision({decision: 'revise', note: event.target.note.value, revise_scope: event.target.scope.value, attribution: event.target.attribution.value});
  });
}

if (window.PAGE === 'delivery') {
  Promise.all([api(`/api/v1/projects/${window.PROJECT_ID}/delivery`), api(`/api/v1/projects/${window.PROJECT_ID}/review-reminders`)]).then(([delivery, reminders]) => {
    $('#delivery-list').innerHTML = delivery.items.map((row) => `<div class="page-head"><div><h2>${row.label}</h2><p>${Math.round(row.size / 1024)} KB</p></div><a class="primary button" href="${p(row.download_url || `/api/v1/projects/${window.PROJECT_ID}/delivery/${encodeURIComponent(row.download_token)}`)}">下载 ZIP</a></div>`).join('');
    $('#reminder-cards').innerHTML = reminders.items.map((row) => `<article class="card"><span class="pill">${row.at}</span><h3>${row.what}</h3><p>${row.why}</p><strong>${row.action}</strong></article>`).join('');
  }).catch((error) => { $('#delivery-list').innerHTML = `<p>${error.message}</p>`; });
}

if (window.PAGE === 'ops') {
  $$('.review-row').forEach((row) => {
    const output = $('.ops-output', row);
    const checkButton = $('.ops-check', row);
    const approveButton = $('.ops-approve', row);
    const projectId = row.dataset.project;
    const gateId = row.dataset.gate;
    let checked = null;
    checkButton.addEventListener('click', async () => {
      try {
        checked = await api(`/internal/v1/projects/${projectId}/gates/${gateId}/check`, {method: 'POST'});
        output.textContent = `${checked.output}\n\n审批依据：\n${JSON.stringify(checked.basis, null, 2)}`;
        approveButton.disabled = !(checked.rc === 3 && checked.check_token);
      } catch (error) { output.textContent = error.message; }
    });
    approveButton.addEventListener('click', async () => {
      try {
        const pending = await api('/internal/v1/reviews/pending');
        const item = pending.items.find((candidate) => candidate.project_id === projectId && candidate.gate_id === gateId);
        const result = await api(`/internal/v1/projects/${projectId}/gates/${gateId}/approve`, {method: 'POST', body: {check_token: checked.check_token, evidence_artifact_id: item.evidence_artifact_id}});
        output.textContent = result.output;
        approveButton.disabled = true;
      } catch (error) { output.textContent = error.message; }
    });
    $('.ops-advance', row).addEventListener('click', async () => {
      try {
        const result = await api(`/internal/v1/projects/${projectId}/advance`, {method: 'POST'});
        output.textContent = result.status;
        setTimeout(() => location.reload(), 600);
      } catch (error) { output.textContent = error.message; }
    });
  });
}

if (window.PAGE === 'ops') {
  $$('.remote-row').forEach((row) => {
    const projectId = row.dataset.project;
    const output = $('.remote-output', row);
    $('.remote-execute', row).addEventListener('click', async () => {
      output.textContent = '正在提交新加坡计算节点…';
      try {
        const result = await api(`/internal/v1/projects/${projectId}/media/execute`, {method: 'POST'});
        output.textContent = `已提交：${result.remote_job_id}，状态 ${result.status}`;
      } catch (error) { output.textContent = error.message; }
    });
    $('.remote-status', row).addEventListener('click', async () => {
      output.textContent = '正在查询…';
      try {
        const result = await api(`/internal/v1/projects/${projectId}/media/execute/status`);
        output.textContent = result.error ? `${result.status}：${result.error}` : `当前状态：${result.status}`;
      } catch (error) { output.textContent = error.message; }
    });
  });
}
