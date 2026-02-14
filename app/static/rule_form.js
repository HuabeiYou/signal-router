(function () {
  const radios = document.querySelectorAll('input[name="condition_type"]');
  const label = document.getElementById('conditionValueLabel');
  const input = document.getElementById('conditionValueInput');
  const help = document.getElementById('conditionValueHelp');
  if (!radios.length || !label || !input || !help) {
    return;
  }

  function selectedType() {
    const checked = document.querySelector('input[name="condition_type"]:checked');
    return checked ? checked.value : 'contains_text';
  }

  function refreshConditionUI() {
    const t = selectedType();
    if (t === 'always') {
      label.textContent = '匹配内容（无需填写）';
      input.placeholder = '无条件命中，不需要填写';
      input.value = '';
      input.disabled = true;
      help.innerHTML = '已选择“全部消息（无条件命中）”，系统会忽略该输入框。';
      return;
    }

    input.disabled = false;
    if (t === 'contains_text') {
      label.textContent = '关键词内容';
      input.placeholder = '请输入关键词，例如：ETF动量模型推送';
      help.innerHTML = '请输入你要匹配的关键词。示例：填 <code>ETF动量模型推送</code>，消息里出现这段文字就会命中。';
    } else {
      label.textContent = '字段名称';
      input.placeholder = '请输入字段名称，例如：test';
      help.innerHTML = '字段名指 <code>=</code> 左边那部分。示例：消息里有 <code>test=abc</code> 就填 <code>test</code>；消息里有 <code>symbol=501018</code> 就填 <code>symbol</code>。';
    }
  }

  radios.forEach((radio) => radio.addEventListener('change', refreshConditionUI));
  refreshConditionUI();
})();
