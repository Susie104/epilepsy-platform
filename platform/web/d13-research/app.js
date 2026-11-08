(() => {
  const expectedHash = '60896dd26ae944f2a89aa13b8a910d8cf7a4d01504c0ccc8efe2a032f9976421';
  const groups = [
    ['基本信息', ['age', 'gender', 'nihss']],
    ['既往史与共病', ['uremia','fatty_liver','diabetes','hypertension','coronary_disease','atrial_fibrillation','hyperuricemia','hyperlipidaemia']],
    ['脑影像', ['frontal_lobe','parietal_lobe','temporal_lobe','occipital_lobe','insular_lobe','subcortex_lobe']],
    ['血管与循环', ['aca','mca','pca','va','ba','cca_plaque','ica_plaque','eca_plaque','ant_circle','post_circle','large_ves_as']]
  ];
  const fields = document.getElementById('fields');
  const status = document.getElementById('load-status');
  const result = document.getElementById('result');
  let bundle, exampleLoaded = false;
  const sigmoid = x => x >= 0 ? 1 / (1 + Math.exp(-x)) : Math.exp(x) / (1 + Math.exp(x));

  function createForm() {
    for (const [title, names] of groups) {
      const section = document.createElement('section'); section.className = 'field-group';
      const heading = document.createElement('h3'); heading.textContent = title; section.appendChild(heading);
      const grid = document.createElement('div'); grid.className = 'field-grid';
      for (const name of names) {
        const label = document.createElement('label'); label.className = 'field';
        const text = document.createElement('span'); text.textContent = bundle.labels[name] || name; label.appendChild(text);
        let control;
        if (bundle.binary_fields.includes(name)) {
          control = document.createElement('select');
          for (const [value, caption] of [['','请选择'],['0','0'],['1','1']]) {
            const option = document.createElement('option'); option.value = value; option.textContent = caption; control.appendChild(option);
          }
        } else {
          control = document.createElement('input'); control.type = 'number'; control.step = '1';
          control.min = String(bundle.ranges[name].min); control.max = String(bundle.ranges[name].max);
          control.placeholder = `${control.min}–${control.max}`;
        }
        control.name = name; control.required = true; control.autocomplete = 'off';
        control.addEventListener('change', () => { exampleLoaded = false; result.hidden = true; });
        label.appendChild(control);
        if (name === 'gender') { const note = document.createElement('small'); note.textContent = '仅填原始 D13 编码，方向未明确'; label.appendChild(note); }
        grid.appendChild(label);
      }
      section.appendChild(grid); fields.appendChild(section);
    }
  }

  function predict(values) {
    let logit = bundle.intercept;
    const clippedFields = [];
    for (const name of bundle.feature_order) {
      const raw = values[name];
      const lower = bundle.winsor_lower[name], upper = bundle.winsor_upper[name];
      const clipped = Math.min(upper, Math.max(lower, raw));
      if (clipped !== raw) clippedFields.push(name);
      const transformed = bundle.log1p_fields.includes(name) ? Math.log1p(clipped) : clipped;
      logit += bundle.coefficients[name] * (transformed - bundle.means[name]) / bundle.standard_deviations[name];
    }
    const raw = sigmoid(logit);
    const bounded = Math.max(1e-8, Math.min(1 - 1e-8, raw));
    const calibrated = sigmoid(bundle.calibration.intercept + bundle.calibration.slope * Math.log(bounded / (1 - bounded)));
    return { calibrated, clippedFields };
  }

  document.getElementById('example').addEventListener('click', () => {
    for (const name of bundle.feature_order) document.getElementById('predict-form').elements[name].value = String(bundle.medians[name]);
    exampleLoaded = true; result.hidden = true; status.textContent = '已载入训练中位数示例（非真实患者）';
  });
  document.getElementById('predict-form').addEventListener('submit', event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const values = {};
    for (const name of bundle.feature_order) {
      const value = Number(form.elements[name].value);
      if (!Number.isFinite(value) || form.elements[name].value === '') { status.textContent = `请填写 ${bundle.labels[name] || name}`; return; }
      values[name] = value;
    }
    const output = predict(values);
    result.replaceChildren();
    const title = document.createElement('h2'); title.textContent = exampleLoaded ? '训练中位数示例 · 研究估计' : 'D13 编码输入 · 研究估计';
    const probability = document.createElement('div'); probability.className = 'probability'; probability.textContent = `${(output.calibrated * 100).toFixed(2)}%`;
    const note = document.createElement('p'); note.textContent = '模型输出的是 D13 筛选队列“一年内继发性癫痫”二分类标签的校准估计；不是临床个体风险或治疗建议。';
    const model = document.createElement('p'); model.className = 'model-id'; model.textContent = `${bundle.model_id} · 公开真实数据研究 · 浏览器本地计算`;
    result.append(title, probability, note, model);
    if (output.clippedFields.length) {
      const clipped = document.createElement('p'); clipped.textContent = `以下字段按训练分位范围截断：${output.clippedFields.map(name => bundle.labels[name] || name).join('、')}。`; result.appendChild(clipped);
    }
    result.hidden = false; result.scrollIntoView({ behavior:'smooth', block:'nearest' });
  });

  async function load() {
    try {
      if (!crypto.subtle) throw Error('浏览器不支持模型包校验');
      const response = await fetch('./model_bundle.json', { cache:'no-store' });
      if (!response.ok) throw Error('模型包无法加载');
      const bytes = await response.arrayBuffer();
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2,'0')).join('');
      if (hash !== expectedHash) throw Error('模型包指纹不匹配');
      bundle = JSON.parse(new TextDecoder().decode(bytes));
      if (bundle.model_id !== 'D13-S1-LR-Platt-v0.3' || bundle.feature_order.length !== 28 ||
          groups.flatMap(item => item[1]).some(name => !bundle.feature_order.includes(name))) throw Error('模型字段不匹配');
      createForm();
      document.getElementById('example').disabled = false;
      document.getElementById('predict').disabled = false;
      status.textContent = '冻结模型包已校验 · 仅供研究演示';
    } catch (error) { status.textContent = error.message || '模型包校验失败'; }
  }
  load();
})();
