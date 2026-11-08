(() => {
  const expectedHash = 'fd67d26eb948bff652a19b0822e48e85d8a737d5fb5b7d251e17e8612d2add27';
  const sections = [
    ['基本信息与卒中', ['age', 'stroke_type', 'nihss', 'cortical']],
    ['首次发作与检查', ['interval_gt3', 'multiple_seizures', 'status_epilepticus', 'eeg_epileptic']],
  ];
  const fields = document.getElementById('fields');
  const form = document.getElementById('predict-form');
  const result = document.getElementById('result');
  const status = document.getElementById('load-status');
  let bundle;
  let exampleLoaded = false;
  const sigmoid = x => x >= 0 ? 1 / (1 + Math.exp(-x)) : Math.exp(x) / (1 + Math.exp(x));

  function makeFields() {
    for (const [title, names] of sections) {
      const section = document.createElement('section'); section.className = 'field-group';
      const heading = document.createElement('h3'); heading.textContent = title; section.appendChild(heading);
      const grid = document.createElement('div'); grid.className = 'field-grid';
      for (const name of names) {
        const label = document.createElement('label'); label.className = 'field';
        const text = document.createElement('span'); text.textContent = bundle.labels[name]; label.appendChild(text);
        let control;
        if (bundle.binary_fields.includes(name)) {
          control = document.createElement('select');
          const captions = name === 'stroke_type'
            ? [['', '请选择'], ['0', '出血性卒中'], ['1', '缺血性卒中']]
            : name === 'eeg_epileptic'
              ? [['', '请选择'], ['0', '原始 EEG 编码 0 / 1 / 3'], ['1', '原始 EEG 编码 2']]
              : [['', '请选择'], ['0', '否 / 原始编码 0'], ['1', '是 / 原始编码 1']];
          for (const [value, caption] of captions) {
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
        if (name === 'eeg_epileptic') {
          const note = document.createElement('small');
          note.textContent = '原始 EEG=2 才编码 1；0/1/3 均编码 0，其中 3 为未做 EEG，不能解读为阴性。';
          label.appendChild(note);
        }
        grid.appendChild(label);
      }
      section.appendChild(grid); fields.appendChild(section);
    }
  }

  function estimate(values) {
    let logit = bundle.intercept;
    const clipped = [];
    for (const name of bundle.feature_order) {
      let value = values[name];
      const prep = bundle.continuous_preprocessing[name];
      if (prep) {
        const bounded = Math.min(prep.upper, Math.max(prep.lower, value));
        if (bounded !== value) clipped.push(name);
        value = (bounded - prep.mean) / prep.sd;
      }
      logit += bundle.coefficients[name] * value;
    }
    return { probability: sigmoid(logit), clipped };
  }

  document.getElementById('example').addEventListener('click', () => {
    for (const name of bundle.feature_order) form.elements[name].value = String(bundle.medians[name]);
    exampleLoaded = true; result.hidden = true;
    status.textContent = '已载入训练中位数示例（非真实患者）';
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const values = {};
    for (const name of bundle.feature_order) {
      const input = form.elements[name];
      const value = Number(input.value);
      if (input.value === '' || !Number.isFinite(value)) { status.textContent = `请填写 ${bundle.labels[name]}`; return; }
      values[name] = value;
    }
    const output = estimate(values);
    result.replaceChildren();
    const heading = document.createElement('h2'); heading.textContent = exampleLoaded ? '训练中位数示例 · 研究估计' : '首次发作后 · 研究估计';
    const number = document.createElement('div'); number.className = 'probability'; number.textContent = `${(output.probability * 100).toFixed(2)}%`;
    const note = document.createElement('p'); note.textContent = '这是温州 D 队列随访期间晚期 PSE 二分类结局的模型输出。随访时间不一，不代表固定时间点风险，也不是诊疗建议。';
    const provenance = document.createElement('p'); provenance.className = 'model-id'; provenance.textContent = `${bundle.model_id} · 真实去标识队列 · 浏览器本地计算`;
    result.append(heading, number, note, provenance);
    if (output.clipped.length) {
      const warning = document.createElement('p'); warning.textContent = `连续字段按训练分位截断：${output.clipped.map(name => bundle.labels[name]).join('、')}。`; result.appendChild(warning);
    }
    result.hidden = false; result.scrollIntoView({ behavior:'smooth', block:'nearest' });
  });

  async function load() {
    try {
      if (!crypto.subtle) throw Error('浏览器不支持模型包校验');
      const response = await fetch('./model_bundle.json', { cache:'no-store' });
      if (!response.ok) throw Error('模型包无法加载');
      const bytes = await response.arrayBuffer();
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join('');
      if (hash !== expectedHash) throw Error('模型包指纹不匹配');
      bundle = JSON.parse(new TextDecoder().decode(bytes));
      if (bundle.model_id !== 'WENZHOU-D-CORE8-LR-FULL-2026-11-08' || bundle.feature_order.length !== 8 ||
          sections.flatMap(row => row[1]).some(name => !bundle.feature_order.includes(name))) throw Error('模型字段不匹配');
      makeFields();
      document.getElementById('example').disabled = false;
      document.getElementById('predict').disabled = false;
      status.textContent = 'D 研究模型包已校验 · 仅供研究演示';
    } catch (error) { status.textContent = error.message || '模型包校验失败'; }
  }
  load();
})();
