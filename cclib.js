// CCLIB-START
const lib = () => {
  const W_REG = [278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,1015,667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611,278,278,278,469,556,333,556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,556,500,722,500,500,500,334,260,334,584,761,556,761,222,556,333,1000,556,556,333,1000,667,333,1000,761,611,761,761,222,222,333,333,350,556,1000,333,1000,500,333,944,761,500,667,278,333,556,556,556,556,260,556,333,737,370,556,584,333,737,333,400,584,333,333,333,556,537,278,333,333,365,556,834,834,834,611,667,667,667,667,667,667,1000,722,667,667,667,667,278,278,278,278,722,722,778,778,778,778,778,584,778,722,722,722,722,667,667,611,556,556,556,556,556,556,889,500,556,556,556,556,278,278,278,278,556,556,556,556,556,556,556,584,611,556,556,556,556,500,556,500], W_BOLD = [278,333,474,556,556,889,722,238,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,333,333,584,584,584,611,975,722,722,722,722,667,611,778,722,278,556,722,611,833,722,778,667,778,722,667,611,722,667,944,667,667,611,333,278,333,584,556,333,556,611,556,611,556,333,611,611,278,278,556,278,889,611,611,611,611,389,556,333,611,556,778,556,556,500,389,280,389,584,761,556,761,278,556,500,1000,556,556,333,1000,667,333,1000,761,611,761,761,278,278,500,500,350,556,1000,333,1000,556,333,944,761,500,667,278,333,556,556,556,556,280,556,333,737,370,556,584,333,737,333,400,584,333,333,333,611,556,278,333,333,365,556,834,834,834,611,722,722,722,722,722,722,1000,722,667,667,667,667,278,278,278,278,722,722,778,778,778,778,778,584,778,722,722,722,722,667,667,611,556,556,556,556,556,556,889,556,556,556,556,556,278,278,278,278,611,611,611,611,611,611,611,584,611,611,611,611,611,556,611,556], W_ARROW = 987;
  const CP = { 0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84, 0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87, 0x02C6: 0x88, 0x2030: 0x89,
    0x0160: 0x8A, 0x2039: 0x8B, 0x0152: 0x8C, 0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92, 0x201C: 0x93, 0x201D: 0x94, 0x2022: 0x95,
    0x2013: 0x96, 0x2014: 0x97, 0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B, 0x0153: 0x9C, 0x017E: 0x9E, 0x0178: 0x9F };
  const code = ch => { const u = ch.codePointAt(0); if (u < 128 || (u >= 0xA0 && u <= 0xFF)) return u; return CP[u] || 63; };
  const width = (text, bold, size) => { let w = 0; for (const ch of text) { w += ch === '→' ? W_ARROW : ((bold ? W_BOLD : W_REG)[code(ch) - 32] || 556); } return w * size / 1000; };
  const ent = s => s.replace(/\s*→\s*/g, ' to ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/&quot;/g, '"');
  const runs = (html, baseBold) => { const out = []; let bold = !!baseBold; html.split(/(<\/?b>)/).forEach(p => {
    if (p === '<b>') bold = true; else if (p === '</b>') bold = !!baseBold; else if (p) out.push({ t: ent(p), b: bold }); }); return out; };
  const words = rs => { const ws = []; let cur = [];
    rs.forEach(r => r.t.split(/( )/).forEach(piece => { if (piece === ' ') { if (cur.length) ws.push(cur); cur = []; } else if (piece) cur.push({ t: piece, b: r.b }); }));
    if (cur.length) ws.push(cur); return ws; };
  const wlen = (w, size) => w.reduce((a, s) => a + width(s.t, s.b, size), 0);
  const orphans = []; const wrap = (html, size, maxW, baseBold) => { const ws = words(runs(html, baseBold)), sp = width(' ', false, size), lines = []; let line = [], lw = 0;
    ws.forEach(w => { const l = wlen(w, size); if (line.length && lw + sp + l > maxW) { lines.push(line); line = [w]; lw = l; } else { lw += (line.length ? sp : 0) + l; line.push(w); } });
    if (line.length) lines.push(line); if (lines.length > 1 && line.length === 1) orphans.push(line[0].map(x => x.t).join('')); return lines; };
  const esc = s => { let o = ''; for (const ch of s) { const c = code(ch); o += c === 40 ? '\\(' : c === 41 ? '\\)' : c === 92 ? '\\\\' : c < 128 ? ch : '\\' + c.toString(8).padStart(3, '0'); } return o; };

  function layout(d, kind, size, spread = 1) {
    const ops = [], PW = 612, PH = 792; let y;
    const font = (b, i) => (b ? (i ? '/F4' : '/F2') : (i ? '/F3' : '/F1'));
    const drawLine = (line, x, base, sz, ital) => { const sp = width(' ', false, sz);
      line.forEach((w, wi) => { if (wi) x += sp; w.forEach(s => {
        const parts = s.t.split(/(→)/); parts.forEach(pt => { if (!pt) return;
          if (pt === '→') { ops.push(`BT /F5 ${sz} Tf ${x.toFixed(2)} ${base.toFixed(2)} Td (\\256) Tj ET`); x += W_ARROW * sz / 1000; }
          else { ops.push(`BT ${font(s.b, ital)} ${sz} Tf ${x.toFixed(2)} ${base.toFixed(2)} Td (${esc(pt)}) Tj ET`); x += width(pt, s.b, sz); } }); }); });
      return x; };
    const lineW = (line, sz) => line.reduce((a, w, i) => a + wlen(w, sz) + (i ? width(' ', false, sz) : 0), 0);
    if (kind === 'resume') {
      const L = 42, W = 528, lead = size * 1.17 * spread; y = PH - 32;
      const para = (html, sz, ld, opt = {}) => { const ls = wrap(html, sz, opt.w || W, opt.bold);
        ls.forEach(line => { y -= ld; const lw = lineW(line, sz); const x = opt.center ? (PW - lw) / 2 : (opt.x || L); drawLine(line, x, y + ld - sz * 0.93 - (ld - sz) / 2 - 0.0, sz, opt.ital); }); };
      const section = t => { y -= 4; para(t, size + 0.5, lead + 1, { bold: true }); y -= 1; ops.push(`0.8 w ${L} ${y.toFixed(2)} m ${L + W} ${y.toFixed(2)} l S`); y -= 2; };
      const lr = (lhtml, rtxt, ital) => { const y0 = y; const rl = wrap(rtxt, size, 1e6, false)[0] || []; const rw = lineW(rl, size); const ls = wrap(lhtml, size, W - rw - 12, false); let yy = y0;
        ls.forEach(line => { yy -= lead; drawLine(line, L, yy + lead - size * 0.93 - (lead - size) / 2, size, ital); });
        drawLine(rl, L + W - rw, y0 - lead + lead - size * 0.93 - (lead - size) / 2, size, ital);
        y = Math.min(yy, y0 - lead); };
      const bullets = items => items.forEach(b => { const ls = wrap(b, size, W - 11, false);
        ls.forEach((line, i) => { y -= lead; const base = y + lead - size * 0.93 - (lead - size) / 2;
          if (!i) ops.push(`BT /F1 ${size} Tf ${(L + 1).toFixed(2)} ${base.toFixed(2)} Td (\\225) Tj ET`);
          drawLine(line, L + 11, base, size, false); }); });
      const edu = () => { section('EDUCATION'); d.education.forEach((e, i) => { if (i) y -= 3; lr(`<b>${e.school}</b>`, e.dates, false); lr(e.degree, e.place, true); if (e.bullets) bullets(e.bullets); }); };
      para(`<b>${d.name}</b>`, size + 11, size + 14, { center: true });
      para(d.contact, size - 1, lead, { center: true }); y -= 4;
      section('SUMMARY'); para(d.summary, size, lead);
      if (d.layout === 'ext') edu();
      section('TECHNICAL SKILLS'); d.skills.forEach(([k, v]) => para(`<b>${k}:</b> ${v}`, size, lead));
      section('PROJECTS'); d.projects.forEach((p, i) => { if (i) y -= 3; lr(`<b>${p.name}</b>`, p.dates, false); para(p.stack, size - 0.75, lead, { ital: true }); bullets(p.bullets); });
      if (d.layout !== 'ext') edu();
      return { ops, bottom: y };
    } else {
      const L = 66, W = 480, ld = size * 1.35; y = PH - 46;
      const para = (html, sz, lld, opt = {}) => { wrap(html, sz, W, opt.bold).forEach(line => { y -= lld; const lw = lineW(line, sz);
        drawLine(line, opt.center ? (PW - lw) / 2 : L, y + lld - sz * 0.93 - (lld - sz) / 2, sz, false); }); y -= opt.after || 0; };
      para(`<b>${d.name}</b>`, size + 11, size + 14, { center: true }); para(d.contact, size - 1, ld, { center: true, after: 18 });
      d.to.forEach(t => para(t, size, ld)); y -= size; para(d.date, size, ld); y -= size; para(d.greeting, size, ld, { after: size * 0.8 });
      d.paragraphs.forEach(p => para(p, size, ld, { after: size * 0.8 })); para('Best,', size, ld); y -= size * 0.4; para(d.name, size, ld);
      return { ops, bottom: y };
    }
  }

  async function makePdf(d, kind) { orphans.length = 0;
    let size = kind === 'resume' ? 10.5 : 11, min = kind === 'resume' ? 9.25 : 9.75, res;
    const floor = kind === 'resume' ? 28 : 46;
    let firstFit = null; while (true) { orphans.length = 0; res = layout(d, kind, size); const ok = res.bottom >= floor; if (ok && (kind !== 'resume' || !orphans.length)) break; if (ok && !firstFit) firstFit = size; if (size <= min) { if (firstFit) { size = firstFit; orphans.length = 0; res = layout(d, kind, size); } break; } size = Math.round((size - 0.05) * 100) / 100; }
    if (kind === 'resume' && res.bottom >= floor) { let sp = 1; while (sp < 1.08) { const t = layout(d, kind, size, sp + 0.005); if (t.bottom < floor) break; sp += 0.005; res = t; } }
    const content = res.ops.join('\n');
    const raw = new TextEncoder().encode(content);
    let stream = raw, filter = '';
    try { const cs = new CompressionStream('deflate'); const buf = await new Response(new Blob([raw]).stream().pipeThrough(cs)).arrayBuffer(); stream = new Uint8Array(buf); filter = '/Filter /FlateDecode '; } catch (e) {}
    const enc = new TextEncoder(); const parts = []; const offs = []; let len = 0;
    const push = b => { const u = typeof b === 'string' ? enc.encode(b) : b; parts.push(u); len += u.length; };
    push('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n');
    const fontObj = n => `<< /Type /Font /Subtype /Type1 /BaseFont /${n} /Encoding /WinAnsiEncoding >>`;
    const objs = [
      '<< /Type /Catalog /Pages 2 0 R >>',
      '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
      '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R /F4 7 0 R /F5 8 0 R >> >> /Contents 9 0 R >>',
      fontObj('Helvetica'), fontObj('Helvetica-Bold'), fontObj('Helvetica-Oblique'), fontObj('Helvetica-BoldOblique'),
      '<< /Type /Font /Subtype /Type1 /BaseFont /Symbol >>', null,
      `<< /Title (${esc(d.title || d.name || '')}) /Author (${esc(d.name || '')}) >>`
    ];
    objs.forEach((o, i) => { offs.push(len); push(`${i + 1} 0 obj\n`);
      if (o === null) { push(`<< ${filter}/Length ${stream.length} >>\nstream\n`); push(stream); push('\nendstream'); } else push(o);
      push('\nendobj\n'); });
    const xref = len; push(`xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offs.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join(''));
    push(`trailer\n<< /Size ${objs.length + 1} /Root 1 0 R /Info ${objs.length} 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
    return { blob: new Blob(parts, { type: 'application/pdf' }), font: size, fits: res.bottom >= floor, room: Math.round(res.bottom - floor), orphans: [...new Set(orphans)] };
  }

  const toB64 = async blob => { const b = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode(...b.subarray(i, i + 8192)); return btoa(s); };
  const sl = ms => new Promise(r => setTimeout(r, ms));
  async function build(key, d, kind, file) {
    const r = await makePdf(d, kind); sessionStorage['ccdoc_' + key] = JSON.stringify({ d, kind, file });
    return { key, font: r.font, fits: r.fits, room: r.room, orphans: r.orphans, kb: Math.round(r.blob.size / 1024) }; }
  async function show(key) {
    const s = JSON.parse(sessionStorage['ccdoc_' + key] || 'null'); if (!s) return 'no doc ' + key;
    const r = await makePdf(s.d, s.kind); document.getElementById('ccPrev')?.remove();
    const box = document.createElement('div'); box.id = 'ccPrev';
    box.style.cssText = 'position:fixed;inset:3% 10%;z-index:2147483647;background:#fff;border:2px solid #333;box-shadow:0 0 0 100vmax rgba(0,0,0,.45);display:flex;flex-direction:column';
    const bar = document.createElement('div'); bar.style.cssText = 'padding:6px 10px;font:14px sans-serif;display:flex;justify-content:space-between;align-items:center';
    bar.textContent = s.file; const x = document.createElement('button'); x.textContent = 'Close preview'; x.onclick = () => box.remove(); bar.appendChild(x);
    const f = document.createElement('iframe'); f.src = URL.createObjectURL(r.blob); f.style.cssText = 'flex:1;border:0';
    box.append(bar, f); setTimeout(() => document.body.appendChild(box), 400); return 'showing ' + s.file; }
  async function upload(key, docName, btn) {
    const s = JSON.parse(sessionStorage['ccdoc_' + key] || 'null'); if (!s) return { error: 'no doc ' + key };
    const r = await makePdf(s.d, s.kind);
    const b = [...document.querySelectorAll('button')].find(x => x.offsetParent && btn.test(x.innerText)); if (!b) return { error: 'no upload button' };
    b.click(); await sl(1200);
    const f = document.querySelector('#fileUploadForm'); if (!f) return { error: 'no upload form' };
    const nm = f.querySelector('#docName'); nm.value = docName; nm.dispatchEvent(new Event('change', { bubbles: true }));
    const inp = f.querySelector('#fileUpload_docUpload'), dt = new DataTransfer(); dt.items.add(new File([r.blob], s.file, { type: 'application/pdf' }));
    inp.files = dt.files; inp.dispatchEvent(new Event('change', { bubbles: true }));
    let up = ''; for (let i = 0; i < 20 && !up; i++) { await sl(500); up = f.querySelector('#inputFileUpload_docUpload').value; }
    if (!up) return { error: 'file not accepted' };
    await sl(800); document.querySelector('#submitFileUploadFormBtn').click(); await sl(3500);
    if (f.offsetParent) { document.querySelector('#submitFileUploadFormBtn').click(); await sl(3000); }
    return { uploaded: true, modalStillOpen: !!f.offsetParent }; }
  window.cc = Object.assign(window.cc || {}, { makePdf, toB64, build, show, upload, version: 3 });
};
// CCLIB-END
