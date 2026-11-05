// 签课表识别（浏览器版）：Mac、Windows 都能用，不用装任何东西。
// 从 纸质表单识别.swift 一比一翻译过来（门槛、步骤、坐标都一样），10-19 起替代那个只能在 Mac 上跑的小程序。
//   找四角 → 透视校正到 1240×1754 → 读顶部编号条码 → 按版式快照里的 cells 对准框线、逐格量笔迹（墨迹比例），签字格附截图。
// 用法：const r = await CodaScan.scan(图片或画布, token => 取版式快照的 cells)
//   返回 {token, cells:[{id, ink, shift:[dx,dy], image?}]}，和原来小程序的输出一样，交给程序判成 上课 / 请假 / 待确认。
(function () {
  const W = 1240, H = 1754;
  const MARKERS = [{ x: 34, y: 34, size: 24 }, { x: 1206, y: 34, size: 18 }, { x: 1206, y: 1720, size: 21 }, { x: 34, y: 1720, size: 15 }];
  class Fail extends Error {}

  // ---- 位图（RGBA，第 0 行是最上面一行）
  class Raster {
    constructor(w, h, px) { this.w = w; this.h = h; this.px = px || new Uint8ClampedArray(w * h * 4).fill(255); }
    static fromSource(src, w, h) {
      // 先铺白底再画（透明的地方当白纸），高质量缩放
      const c = canvas(w, h), g = c.getContext('2d', { willReadFrequently: true });
      g.fillStyle = '#fff'; g.fillRect(0, 0, w, h); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
      g.drawImage(src, 0, 0, w, h);
      return new Raster(w, h, g.getImageData(0, 0, w, h).data);
    }
    gray(x, y) { const i = (y * this.w + x) * 4, p = this.px; return 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2]; }
    toCanvas() { const c = canvas(this.w, this.h); c.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(this.px), this.w, this.h), 0, 0); return c; }
    resized(nw, nh) { return Raster.fromSource(this.toCanvas(), nw, nh); }
    crop(x0, y0, x1, y1) {
      const a = Math.max(0, Math.min(this.w, x0)), b = Math.max(0, Math.min(this.h, y0)), c = Math.max(a + 1, Math.min(this.w, x1)), d = Math.max(b + 1, Math.min(this.h, y1));
      const out = new Raster(c - a, d - b);
      for (let y = b; y < d; y++) out.px.set(this.px.subarray((y * this.w + a) * 4, (y * this.w + c) * 4), ((y - b) * out.w) * 4);
      return out;
    }
    rotated90() { // 逆时针转 90°（同 PIL 的 rotate(90, expand=True)）
      const out = new Raster(this.h, this.w);
      for (let y = 0; y < this.h; y++) for (let x = 0; x < this.w; x++) { const s = (y * this.w + x) * 4, t = ((this.w - 1 - x) * out.w + y) * 4; for (let k = 0; k < 4; k++) out.px[t + k] = this.px[s + k]; }
      return out;
    }
    rotated180() {
      const out = new Raster(this.w, this.h), n = this.w * this.h;
      for (let i = 0; i < n; i++) { const s = i * 4, t = (n - 1 - i) * 4; for (let k = 0; k < 4; k++) out.px[t + k] = this.px[s + k]; }
      return out;
    }
    darkRatio(x0, y0, x1, y1, below) {
      const a = Math.max(0, x0), b = Math.max(0, y0), c = Math.min(this.w, x1), d = Math.min(this.h, y1);
      if (c <= a || d <= b) return 0;
      let n = 0; for (let y = b; y < d; y++) for (let x = a; x < c; x++) if (this.gray(x, y) < below) n++;
      return n / ((c - a) * (d - b));
    }
    pngDataURL() { return this.toCanvas().toDataURL('image/png'); }
  }
  function canvas(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }

  // ---- 定位与校正
  function components(g, left, top, size, height, maxSide = 60, dark = 100) {
    const ww = Math.min(size, g.w - left), hh = Math.min(height ?? size, g.h - top);
    if (ww <= 0 || hh <= 0) return [];
    const mask = new Uint8Array(ww * hh), seen = new Uint8Array(ww * hh), out = [];
    for (let y = 0; y < hh; y++) for (let x = 0; x < ww; x++) mask[y * ww + x] = g.gray(left + x, top + y) < dark ? 1 : 0;
    for (let start = 0; start < ww * hh; start++) {
      if (!mask[start] || seen[start]) continue;
      const todo = [start]; seen[start] = 1; let n = 0, sx = 0, sy = 0, minx = 1e9, maxx = -1, miny = 1e9, maxy = -1;
      while (todo.length) {
        const p = todo.pop(), y = (p / ww) | 0, x = p % ww;
        n++; sx += x; sy += y; if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y;
        if (x + 1 < ww) { const q = p + 1; if (mask[q] && !seen[q]) { seen[q] = 1; todo.push(q); } }
        if (x > 0) { const q = p - 1; if (mask[q] && !seen[q]) { seen[q] = 1; todo.push(q); } }
        if (y + 1 < hh) { const q = p + ww; if (mask[q] && !seen[q]) { seen[q] = 1; todo.push(q); } }
        if (y > 0) { const q = p - ww; if (mask[q] && !seen[q]) { seen[q] = 1; todo.push(q); } }
      }
      if (n >= 12) {
        const bw = maxx - minx + 1, bh = maxy - miny + 1;
        if (bw / bh > 0.55 && bw / bh < 1.8 && n / (bw * bh) > 0.60 && Math.max(bw, bh) < maxSide) out.push({ x: sx / n, y: sy / n, n });
      }
    }
    return out;
  }
  function solve(a, b) {
    const n = b.length, m = a.map((row, i) => row.concat([b[i]]));
    for (let c = 0; c < n; c++) {
      let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(m[r][c]) > Math.abs(m[p][c])) p = r;
      if (Math.abs(m[p][c]) <= 1e-12) return null;
      [m[c], m[p]] = [m[p], m[c]];
      for (let r = 0; r < n; r++) if (r !== c) { const f = m[r][c] / m[c][c]; for (let k = c; k <= n; k++) m[r][k] -= f * m[c][k]; }
    }
    return m.map((row, i) => row[n] / row[i]);
  }
  // 扫描件：纸张占满整张图，在四个角的固定区域里找黑块
  function cornerMarkers(small) {
    const cands = [];
    for (const mk of MARKERS) {
      const left = mk.x < W / 2 ? 0 : 490, top = mk.y < H / 2 ? 0 : 747;
      const found = components(small, left, top, 130);
      if (!found.length) return null;
      const k = p => Math.abs(Math.sqrt(p.n) - mk.size / 2) + 0.10 * Math.hypot(p.x + left - mk.x / 2, p.y + top - mk.y / 2);
      found.sort((a, b) => k(a) - k(b));
      const f = found[0]; cands.push({ x: 2 * (f.x + left), y: 2 * (f.y + top), n: f.n });
    }
    return cands;
  }
  // 四个标记大小应成比例（24、18、21、15）；明显不成比例的当成没找到
  function saneSizes(c) {
    const scales = c.map((p, i) => p ? Math.sqrt(p.n) / MARKERS[i].size : null).filter(v => v !== null);
    if (scales.length < 3) return c;
    const mid = scales.slice().sort((a, b) => a - b)[Math.floor(scales.length / 2)];
    return c.map((p, i) => !p ? null : (Math.abs(Math.sqrt(p.n) / MARKERS[i].size - mid) / mid > 0.45 ? null : p));
  }
  // 只缺一个角时，用另外三个角按平行四边形补出来，n 记为 0
  function complete(c) {
    const missing = [0, 1, 2, 3].filter(i => !c[i]);
    if (!missing.length) return c.slice();
    if (missing.length !== 1) return null;
    const k = missing[0], a = c[(k + 3) % 4], b = c[(k + 1) % 4], o = c[(k + 2) % 4], out = c.slice();
    out[k] = { x: a.x + b.x - o.x, y: a.y + b.y - o.y, n: 0 };
    return out;
  }
  function checkedCornerMarkers(small) {
    const c = cornerMarkers(small); if (!c) return [];
    return saneSizes(c).some(p => !p) ? [] : [c];
  }
  // 四个都找到时，再准备“去掉最可疑的一个角、用另外三个补”的两种备选
  function variants(c) {
    const scales = c.map((p, i) => Math.sqrt(p.n) / MARKERS[i].size), mid = scales.slice().sort((a, b) => a - b)[2];
    const suspicion = i => { const p = c[i], edge = Math.min(p.x, p.y, W - p.x, H - p.y) < 12 ? 1 : 0; return Math.abs(scales[i] - mid) / mid + edge; };
    const order = [0, 1, 2, 3].sort((a, b) => suspicion(b) - suspicion(a));
    return [c].concat(order.slice(0, 2).map(k => complete(c.map((p, i) => i === k ? null : p))).filter(Boolean));
  }
  // 后备找法：手机拍照时纸只占照片中间，在四个象限里各取最靠外角的黑方块
  function quadrantMarkers(small) {
    const hw = Math.floor(small.w / 2), hh = Math.floor(small.h / 2), cands = [];
    for (const mk of MARKERS) {
      const right = mk.x > W / 2, bottom = mk.y > H / 2, left = right ? hw : 0, top = bottom ? hh : 0;
      let found = components(small, left, top, hw, hh).filter(p => p.n >= 12);
      if (!found.length) found = components(small, left, top, hw, hh, 60, 150).filter(p => p.n >= 12);
      const cx = right ? small.w : 0, cy = bottom ? small.h : 0;
      let best = null, bd = 1e18;
      for (const p of found) { const d = Math.hypot(p.x + left - cx, p.y + top - cy); if (d < bd) { bd = d; best = p; } }
      cands.push(best ? { x: 2 * (best.x + left), y: 2 * (best.y + top), n: best.n } : null);
    }
    const sane = saneSizes(cands);
    if (!sane.some(p => !p)) return variants(sane);
    const done = complete(sane); return done ? [done] : [];
  }
  // 在原图上把缩略图里找到的标记位置再精确一次
  function refine(img, cands) {
    const sx = img.w / W, sy = img.h / H, r = Math.max(16, Math.floor(30 * sx));
    return cands.map(c => {
      if (c.n <= 0) return c;
      const u = Math.floor(c.x * sx), v = Math.floor(c.y * sy), left = Math.max(0, u - r), top = Math.max(0, v - r);
      let found = components(img, left, top, 2 * r, 2 * r, r * 1.6);
      if (!found.length) found = components(img, left, top, 2 * r, 2 * r, r * 1.6, 150);
      let best = null, bd = 1e18;
      for (const p of found) { const d = Math.hypot(p.x + left - u, p.y + top - v); if (d < bd) { bd = d; best = p; } }
      if (!best || bd >= r / 2) return c;
      return { x: (best.x + left + 0.5) / sx, y: (best.y + top + 0.5) / sy, n: c.n };
    });
  }
  function warp(img, cands) {
    const a = [], b = [];
    MARKERS.forEach((mk, i) => {
      const p = cands[i], u = p.x * img.w / W, v = p.y * img.h / H;
      a.push([mk.x, mk.y, 1, 0, 0, 0, -u * mk.x, -u * mk.y]); b.push(u);
      a.push([0, 0, 0, mk.x, mk.y, 1, -v * mk.x, -v * mk.y]); b.push(v);
    });
    const c = solve(a, b); if (!c) throw new Fail('定位标记位置异常，请重扫');
    const out = new Raster(W, H), sw = img.w, sh = img.h, s = img.px, o = out.px;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const X = x + 0.5, Y = y + 0.5, d = c[6] * X + c[7] * Y + 1;
      const u = (c[0] * X + c[1] * Y + c[2]) / d - 0.5, v = (c[3] * X + c[4] * Y + c[5]) / d - 0.5;
      const x0 = Math.floor(u), y0 = Math.floor(v);
      if (x0 < 0 || y0 < 0 || x0 + 1 >= sw || y0 + 1 >= sh) continue;
      const fx = u - x0, fy = v - y0, t = (y * W + x) * 4, i00 = (y0 * sw + x0) * 4, i10 = i00 + 4, i01 = i00 + sw * 4, i11 = i01 + 4;
      for (let k = 0; k < 3; k++) o[t + k] = (s[i00 + k] * (1 - fx) + s[i10 + k] * fx) * (1 - fy) + (s[i01 + k] * (1 - fx) + s[i11 + k] * fx) * fy;
    }
    return out;
  }
  // CRC32（和打印时写进条码的校验字节一致）
  function crc32(bytes) { let crc = 0xFFFFFFFF; for (const b of bytes) { crc ^= b; for (let i = 0; i < 8; i++) crc = (crc & 1) ? (0xEDB88320 ^ (crc >>> 1)) : (crc >>> 1); } return (crc ^ 0xFFFFFFFF) >>> 0; }
  // 读顶部编号条码：在附近小范围里找能通过校验的位置
  function identify(img) {
    const tries = [];
    for (let dy = -8; dy <= 8; dy++) for (let dx = -14; dx <= 14; dx++) tries.push([dx, dy]);
    tries.sort((p, q) => (Math.abs(p[0]) + Math.abs(p[1])) - (Math.abs(q[0]) + Math.abs(q[1])));
    for (const [dx, dy] of tries) {
      const vals = [];
      for (let i = 0; i < 64; i++) { let sum = 0; for (let y = 30 + dy; y < 42 + dy; y++) for (let x = 429 + i * 6 + dx; x < 433 + i * 6 + dx; x++) sum += img.gray(x, y); vals.push(sum / 48); }
      const lo = Math.min(...vals), hi = Math.max(...vals);
      if (hi - lo <= 40) continue;
      const bits = vals.map(v => v < (lo + hi) / 2 ? 1 : 0);
      const raw = []; for (let i = 0; i < 8; i++) { let b = 0; for (let k = 0; k < 8; k++) b = (b << 1) | bits[i * 8 + k]; raw.push(b); }
      if (raw[0] === 0xa6 && raw[1] === 0x5c && raw[7] === (crc32(raw.slice(0, 7)) & 0xff)) return raw.slice(2, 7).map(b => b.toString(16).padStart(2, '0')).join('');
    }
    throw new Fail('表单编号校验失败，请提高扫描清晰度，或使用本系统打印的表单');
  }
  function locate(input) {
    let img = input; if (img.w > img.h) img = img.rotated90();
    let err = new Fail('无法找到四角定位标记。请扫描完整纸张，不要裁掉边缘');
    for (const turned of [img, img.rotated180()]) {
      const small = turned.resized(620, 877), found = [];
      const finders = [checkedCornerMarkers, quadrantMarkers];
      for (let fi = 0; fi < 2; fi++) for (const cands of finders[fi](small)) {
        const sizes = cands.map(p => p.n);
        if (!sizes.includes(0) && sizes.indexOf(Math.max(...sizes)) !== 0) continue; // 最大的黑块应在左上
        try {
          const aligned = warp(turned, refine(turned, cands)), token = identify(aligned);
          if (fi === 0) return [[aligned, token]];
          found.push([aligned, token]);
        } catch (e) { err = e; }
      }
      if (found.length) return found;
    }
    throw err;
  }
  // ---- 量格子
  function grayPlane(r) { const n = r.w * r.h, g = new Float64Array(n), p = r.px; for (let i = 0; i < n; i++) g[i] = 0.299 * p[i * 4] + 0.587 * p[i * 4 + 1] + 0.114 * p[i * 4 + 2]; return g; }
  function edgeDark(g, w, h, x, y, bw, bh) {
    let s = 0, n = 0; const at = (px, py) => { if (px >= 0 && py >= 0 && px < w && py < h) { s += 255 - g[py * w + px]; n++; } };
    for (let i = 0; i <= bw; i++) { at(x + i, y); at(x + i, y + bh); }
    for (let j = 0; j <= bh; j++) { at(x, y + j); at(x + bw, y + j); }
    return n > 0 ? s / n : 0;
  }
  function snap(g, w, h, f, from = [0, 0], limit = 24) {
    const base = edgeDark(g, w, h, f[0] + from[0], f[1] + from[1], f[2], f[3]); let best = from, score = base;
    const ry = Math.min(limit, Math.max(3, Math.min(24, Math.trunc(f[3] * 0.4)))), rx = Math.min(limit, Math.max(3, Math.min(24, Math.trunc(f[2] * 0.4))));
    for (let dy = -ry; dy <= ry; dy++) for (let dx = -rx; dx <= rx; dx++) {
      const v = edgeDark(g, w, h, f[0] + from[0] + dx, f[1] + from[1] + dy, f[2], f[3]);
      if (v > score) { score = v; best = [from[0] + dx, from[1] + dy]; }
    }
    return score > base * 1.15 + 2 ? best : from;
  }
  const ints = v => Array.isArray(v) && v.length === 4 && v.every(n => typeof n === 'number') ? v.map(n => Math.round(n)) : null;
  function fitScore(img, cells) { const g = grayPlane(img); let s = 0, n = 0; for (const c of cells) { const f = ints(c.frame); if (f) { s += edgeDark(g, img.w, img.h, f[0], f[1], f[2], f[3]); n++; } } return n ? s / n : 0; }

  // ---- 入口：source 是 <img>、ImageBitmap 或画布；getCells(token) 返回这张表的 cells（找不到就抛错）
  async function scan(source, getCells, opts = {}) {
    const sw = source.naturalWidth || source.width, sh = source.naturalHeight || source.height;
    const image = Raster.fromSource(source, sw, sh);
    if (image.w < 800 || image.h < 1000) throw new Fail('图片过小，请使用至少 150dpi 扫描');
    const options = locate(image), token = options[0][1];
    const cells = await getCells(token);
    let aligned = options[0][0];
    if (options.length > 1) { let best = -1; for (const [img, t] of options) if (t === token) { const s = fitScore(img, cells); if (s > best) { best = s; aligned = img; } } }
    const plane = grayPlane(aligned), shifts = {}, out = [];
    for (const c of cells) {
      const r = ints(c.rect); if (!r || r[2] <= 0 || r[3] <= 0) continue;
      let shift = [0, 0];
      if (c.follow && shifts[c.follow]) shift = shifts[c.follow];
      const f = ints(c.frame); if (f) shift = snap(plane, aligned.w, aligned.h, f, shift, c.follow == null ? 24 : 8);
      if (c.id) shifts[c.id] = shift;
      r[0] += shift[0]; r[1] += shift[1];
      // 笔迹门槛按这一格的纸色定：比纸色（中位数）深 70 算笔迹，限制在 125–185 之间
      const crop = aligned.crop(r[0], r[1], r[0] + r[2], r[1] + r[3]), n = crop.w * crop.h, tones = new Float64Array(n);
      for (let i = 0; i < n; i++) { const p = crop.px; tones[i] = 0.299 * p[i * 4] + 0.587 * p[i * 4 + 1] + 0.114 * p[i * 4 + 2]; }
      tones.sort(); const paper = n ? tones[Math.floor(n / 2)] : 255;
      const ink = crop.darkRatio(0, 0, crop.w, crop.h, Math.min(185, Math.max(125, paper - 70)));
      const cell = { id: c.id || '', ink: Math.round(ink * 10000) / 10000, shift };
      if (c.image === true) cell.image = crop.pngDataURL();
      out.push(cell);
    }
    const result = { token, cells: out };
    if (opts.preview) result.preview = aligned.resized(620, 877).pngDataURL();
    return result;
  }
  // 打印用：条码的 64 个格子哪些涂黑（和小程序 print 一样）
  function barcodeBits(token) {
    const raw = [0xa6, 0x5c].concat(token.match(/../g).map(h => parseInt(h, 16)));
    raw.push(crc32(raw) & 0xff);
    return raw.flatMap(b => [7, 6, 5, 4, 3, 2, 1, 0].map(i => (b >> i) & 1));
  }
  window.CodaScan = { scan, barcodeBits, MARKERS, W, H, Fail };
})();
