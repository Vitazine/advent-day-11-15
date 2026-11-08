'use strict';
const $ = id => document.getElementById(id);
const form = $('request-form');
let busy = false, ready = false;
const money = nano => '$' + (nano / 1e9).toFixed(nano > 0 && nano < 1000000 ? 6 : 4);
const clockTime = stamp => stamp ? new Date(stamp * 1000).toLocaleTimeString('ru-RU') : 'после завершения запроса';
const names = {API_KEY:'API-ключ', CONFIG_SECRET:'секрет конфигурации', EMAIL:'email', CARD:'карта', PHONE:'телефон', URL:'подозрительный URL', COMMAND:'опасная команда', SYSTEM_PROMPT:'системная инструкция', ENCODING_LIMIT:'сложное кодирование'};
function metric(id, value, cap) {
  const node = $(id); node.replaceChildren(document.createTextNode(value + ' '));
  const small = document.createElement('small'); small.textContent = '/ ' + cap; node.append(small);
}
function updateLimits(data) {
  ready = data.ready === undefined ? ready : data.ready;
  metric('rate', data.rate.remaining, '10 осталось');
  $('rate-info').textContent = 'Использовано: ' + data.rate.used + '. Освобождение: ' + (data.rate.next_release_at ? clockTime(data.rate.next_release_at) : 'лимит доступен');
  metric('remaining', money(data.ip.remaining_nano), '$0.10');
  metric('global', money(data.global_budget.remaining_nano), '$1.00');
  $('budget-meter').value = data.ip.remaining_nano / data.ip.cap_nano * 100;
  $('cost-info').textContent = 'Потрачено: ' + money(data.ip.spent_nano) + ' · резерв: ' + money(data.ip.reserved_nano) + (data.ip.unknown_nano ? ' · из них неопределённо: ' + money(data.ip.unknown_nano) : '');
  $('release').textContent = 'Ближайшее освобождение по IP: ' + (data.ip.next_release_at ? clockTime(data.ip.next_release_at) : 'нет завершённых расходов') + '. Общий резерв: ' + money(data.global_budget.reserved_nano);
  $('service').textContent = ready ? 'Сервис готов. Перед отправкой данные проверяются; исходные секреты не сохраняются в журнал.' : 'Генерация отключена: требуется настройка ключа, проверка тарифов или снятие защитной остановки оператором.';
  $('service').classList.toggle('ready', ready);
  $('send').disabled = busy || !ready;
}
async function refresh() {
  try {
    const response = await fetch('/day13/api/limits', {cache:'no-store'});
    if (!response.ok) throw new Error('limits');
    updateLimits(await response.json());
  } catch {
    ready = false; $('send').disabled = true;
    $('service').textContent = 'Не удалось обновить лимиты. Проверьте соединение и доступ к странице.';
    $('service').classList.remove('ready');
  }
}
function result(message, label, failed, meta = '') {
  const status = document.createElement('p'); status.className = 'result-status' + (failed ? ' error' : ''); status.textContent = label;
  const answer = document.createElement('p'); answer.className = 'answer'; answer.textContent = message;
  $('result').replaceChildren(status, answer); $('result-meta').textContent = meta;
}
$('prompt').addEventListener('input', () => {
  const count = new TextEncoder().encode($('prompt').value).length;
  $('bytes').textContent = count + ' / 8192 байт';
  $('prompt').setCustomValidity(count > 8192 ? 'Не больше 8192 байт.' : '');
});
$('example').addEventListener('click', () => {
  $('prompt').value = 'Объясни, почему адрес demo@example.com относится к персональным данным.';
  $('prompt').dispatchEvent(new Event('input')); $('prompt').focus();
});
form.addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !ready || !form.reportValidity()) return;
  busy = true; $('send').disabled = true; $('result').setAttribute('aria-busy','true');
  result('Проверяем запрос и ожидаем ответ модели. Это может занять до минуты.', 'Выполняется', false);
  try {
    const response = await fetch('/day13/api/generate', {
      method:'POST', headers:{'Content-Type':'application/json','X-Day13-Request':'1'},
      body:JSON.stringify({prompt:$('prompt').value,mode:new FormData(form).get('mode')})
    });
    const data = await response.json();
    const categories = (data.categories || []).map(x => names[x] || x).join(', ');
    const meta = [categories && 'Обнаружено: ' + categories, data.request_id && 'Запрос: ' + data.request_id,
      data.cost_nano !== undefined && 'Стоимость ≤ ' + money(data.cost_nano),
      data.usage && 'Токены: ' + data.usage.total_tokens].filter(Boolean).join(' · ');
    result(data.error ? data.error.message : data.answer, data.error ? 'Запрос остановлен' : data.masked ? 'Данные замаскированы · ответ проверен' : 'Ответ проверен', !response.ok, meta);
  } catch {
    result('Соединение прервалось. Запрос мог быть обработан; проверьте лимиты перед повторной отправкой.', 'Ответ не получен', true);
  } finally {
    busy = false; $('result').removeAttribute('aria-busy'); await refresh();
  }
});
refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 15000);
