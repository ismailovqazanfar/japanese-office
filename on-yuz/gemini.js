// No API credentials are requested or persisted in the browser.
export function geminiPanel(demo) {
  const box = document.createElement('section'); box.className = 'not';
  const node = (tag, text) => { const n = document.createElement(tag); if (text) n.textContent = text; return n; };
  box.append(node('h3', 'Gemini · Şəkil studiyası'));
  if (demo) { box.append(node('p', 'Demo rejimində API çağırılmır.')); return box; }
  const info = node('p', 'Bağlantı yoxlanır…');
  const select = node('select'); select.setAttribute('aria-label', 'Kanji seç');
  const prompt = node('textarea'); prompt.rows = 5; prompt.maxLength = 6000; prompt.placeholder = 'Şəkil promptu'; prompt.setAttribute('aria-label', 'Şəkil promptu');
  const negative = node('textarea'); negative.rows = 2; negative.maxLength = 1000; negative.placeholder = 'Şəkildə olmasın…'; negative.setAttribute('aria-label', 'Mənfi prompt');
  for (const n of [select, prompt, negative]) { n.style.width = '100%'; n.style.boxSizing = 'border-box'; n.style.marginBottom = '8px'; }
  const create = node('button', 'Gemini ilə yarat'); create.disabled = true;
  const refresh = node('button', 'Promptları yenilə');
  const copy = node('button', 'Promptu kopyala');
  const result = node('div'); result.setAttribute('aria-live', 'polite');
  box.append(info, select, prompt, negative, create, refresh, copy,
    node('p', 'Bir klik bir şəkil sorğusudur. API istifadəsi ödənişli ola bilər; açarın olması pulsuz kvota demək deyil. Hazır eyni şəkil təkrar yaradılmır.'), result);
  let config = null, batch = null, running = false;
  const json = async (url, options) => {
    const response = await fetch(url, options); const data = await response.json();
    if (!response.ok) throw new Error(data.hata || 'Sorğu alınmadı');
    return data;
  };
  function availability() { create.disabled = running || !config?.configured || !select.value || prompt.value.trim().length < 10; }
  function choose() {
    const brief = config?.briefs.find(b => b.kanji === select.value);
    prompt.value = brief?.image_prompt || ''; negative.value = brief?.negative_prompt || '';
    result.replaceChildren(); availability();
  }
  async function load() {
    try {
      [config, batch] = await Promise.all([json('/api/gemini'), json('/api/kanji')]);
      if (config.partiya !== batch.partiya) throw new Error('Qrup dəyişib. Yenilə düyməsinə bas.');
      info.textContent = config.configured ? `Açar qurulub · ${config.model} · Qrup ${batch.partiya} (API bağlantısı hələ sınaqdan keçirilməyib)` : 'Açar yoxdur. Terminalda py baslat.py ilə başlat və yeni açarı gizli daxil et.';
      select.replaceChildren(...batch.kanjiler.map(k => { const n = node('option', `${k.kanji} · ${k.az}`); n.value = k.kanji; return n; }));
      choose();
    } catch (e) { info.textContent = e.message; config = null; availability(); }
  }
  function show(job) {
    result.replaceChildren();
    if (job.status === 'completed') {
      const img = node('img'); img.src = job.image_url; img.alt = `${job.kanji} üçün yaddaş şəkli`; img.style.width = '100%'; img.style.borderRadius = '12px';
      const link = node('a', 'Şəkli yüklə'); link.href = job.image_url; link.download = `U${job.kanji.codePointAt(0).toString(16).toUpperCase()}${job.extension}`;
      result.append(img, link);
    } else result.append(node('p', job.error || 'Şəkil hazırlanır…'));
  }
  create.onclick = async () => {
    if (running) return;
    running = true; refresh.disabled = true; select.disabled = true; availability();
    try {
      let job = await json('/api/gemini', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({kanji:select.value, partiya:batch.partiya, image_prompt:prompt.value, negative_prompt:negative.value})});
      show(job);
      while (job.status === 'running') {
        await new Promise(resolve => setTimeout(resolve, 1500));
        if (!box.isConnected) break;
        job = await json('/api/gemini/job/' + job.id); show(job);
      }
    } catch (e) { result.replaceChildren(node('p', e.message)); }
    finally { running = false; refresh.disabled = false; select.disabled = false; availability(); }
  };
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(prompt.value + (negative.value ? '\nAvoid: ' + negative.value : '')); copy.textContent = 'Kopyalandı'; }
    catch { prompt.focus(); prompt.select(); copy.textContent = 'Ctrl+C ilə kopyala'; }
  };
  prompt.oninput = availability; select.onchange = choose; refresh.onclick = load;
  load(); return box;
}
