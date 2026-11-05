// 纸质表单识别工具：通用的“打印 → 填写 → 扫描/拍照 → 识别”工具。只管纸面上的通用部分，表长什么样、每格什么意思由调用它的模板决定。
//   打印 print：画四角定位黑块和顶部编号条码，再按模板给的文字、方框、线条画出整页 PDF。
//   识别 scan：找四角 → 透视校正到 1240×1754 → 读编号 → 按 <版式文件夹>/<编号>.json 里的 cells 逐格量笔迹（墨迹比例），可附格子截图。
//   页数 pages：PDF 有几页。
// 支持多页 PDF、JPG、PNG、HEIC；扫描件、倒放、歪斜、手机斜拍（四角都要拍进去）都可以。
// 只用 macOS 自带框架（CoreGraphics、CoreText、ImageIO、CryptoKit），macOS 12 以上直接运行，不需要 Python 或下载任何东西。
// 用法：echo '{"action":"print|scan|pages","data":{...}}' | ./纸质表单识别工具   （参数见 说明.md）
// 重新编译：运行同目录的 编译纸质表单识别工具.command（需要 Xcode 或命令行工具）
// 来历：定位与编号算法照搬旧系统的 签课识别.py；2026-10-14 改写成 Swift（签课识别工具），同日拆成“通用工具 + 模板”，旧版在 过去资料_暂留/旧程序/签课识别工具_拆分前/。
import Foundation
import CoreGraphics
import CoreText
import ImageIO
import CryptoKit
import Vision

let W = 1240.0, H = 1754.0
let MARKERS: [(x: Double, y: Double, size: Double)] = [(34, 34, 24), (1206, 34, 18), (1206, 1720, 21), (34, 1720, 15)]
struct Fail: Error { let message: String; init(_ m: String) { message = m } }

// MARK: - 小工具
func hex(_ bytes: [UInt8]) -> String { bytes.map { String(format: "%02x", $0) }.joined() }
func sha256Hex(_ data: Data) -> String { hex(Array(SHA256.hash(data: data))) }
func crc32(_ bytes: [UInt8]) -> UInt32 {
    var crc: UInt32 = 0xFFFF_FFFF
    for b in bytes {
        crc ^= UInt32(b)
        for _ in 0..<8 { crc = (crc & 1) != 0 ? 0xEDB8_8320 ^ (crc >> 1) : crc >> 1 }
    }
    return crc ^ 0xFFFF_FFFF
}
func hexBytes(_ s: String) -> [UInt8] {
    var out: [UInt8] = []; var i = s.startIndex
    while i < s.endIndex { let j = s.index(i, offsetBy: 2); out.append(UInt8(s[i..<j], radix: 16)!); i = j }
    return out
}
// MARK: - 位图（RGBA，第 0 行是图片最上面一行，和 PIL 的坐标一致）
final class Raster {
    let w: Int, h: Int
    var px: [UInt8]
    init(w: Int, h: Int) { self.w = w; self.h = h; px = [UInt8](repeating: 255, count: w * h * 4) }
    init(_ cg: CGImage) {
        w = cg.width; h = cg.height; px = [UInt8](repeating: 255, count: w * h * 4)
        let ww = w, hh = h
        px.withUnsafeMutableBytes { buf in
            let ctx = CGContext(data: buf.baseAddress, width: ww, height: hh, bitsPerComponent: 8, bytesPerRow: ww * 4,
                                space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            ctx.setFillColor(CGColor(gray: 1, alpha: 1)); ctx.fill(CGRect(x: 0, y: 0, width: ww, height: hh))
            ctx.interpolationQuality = .high
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: ww, height: hh))
        }
    }
    @inline(__always) func gray(_ x: Int, _ y: Int) -> Double {
        let i = (y * w + x) * 4
        return 0.299 * Double(px[i]) + 0.587 * Double(px[i + 1]) + 0.114 * Double(px[i + 2])
    }
    func cgImage() -> CGImage {
        let data = Data(px) as CFData
        return CGImage(width: w, height: h, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(),
                       bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue), provider: CGDataProvider(data: data)!,
                       decode: nil, shouldInterpolate: true, intent: .defaultIntent)!
    }
    func resized(_ nw: Int, _ nh: Int) -> Raster {
        let out = Raster(w: nw, h: nh); let src = cgImage()
        out.px.withUnsafeMutableBytes { buf in
            let ctx = CGContext(data: buf.baseAddress, width: nw, height: nh, bitsPerComponent: 8, bytesPerRow: nw * 4,
                                space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            ctx.interpolationQuality = .high; ctx.draw(src, in: CGRect(x: 0, y: 0, width: nw, height: nh))
        }
        return out
    }
    func crop(_ x0: Int, _ y0: Int, _ x1: Int, _ y1: Int) -> Raster {
        let a = max(0, min(w, x0)), b = max(0, min(h, y0)), c = max(a + 1, min(w, x1)), d = max(b + 1, min(h, y1))
        let out = Raster(w: c - a, h: d - b)
        for y in b..<d { for x in a..<c { let s = (y * w + x) * 4, t = ((y - b) * out.w + (x - a)) * 4; for k in 0..<4 { out.px[t + k] = px[s + k] } } }
        return out
    }
    /// 逆时针转 90°（同 PIL 的 rotate(90, expand=True)）
    func rotated90() -> Raster {
        let out = Raster(w: h, h: w)
        for y in 0..<h { for x in 0..<w { let s = (y * w + x) * 4, t = ((w - 1 - x) * out.w + y) * 4; for k in 0..<4 { out.px[t + k] = px[s + k] } } }
        return out
    }
    func rotated180() -> Raster {
        let out = Raster(w: w, h: h)
        for y in 0..<h { for x in 0..<w { let s = (y * w + x) * 4, t = ((h - 1 - y) * w + (w - 1 - x)) * 4; for k in 0..<4 { out.px[t + k] = px[s + k] } } }
        return out
    }
    func darkRatio(_ x0: Int, _ y0: Int, _ x1: Int, _ y1: Int, below: Double) -> Double {
        let a = max(0, x0), b = max(0, y0), c = min(w, x1), d = min(h, y1)
        if c <= a || d <= b { return 0 }
        var n = 0
        for y in b..<d { for x in a..<c where gray(x, y) < below { n += 1 } }
        return Double(n) / Double((c - a) * (d - b))
    }
    func pngDataURL() -> String {
        let data = NSMutableData()
        let dest = CGImageDestinationCreateWithData(data, "public.png" as CFString, 1, nil)!
        CGImageDestinationAddImage(dest, cgImage(), nil); CGImageDestinationFinalize(dest)
        return "data:image/png;base64," + (data as Data).base64EncodedString()
    }
}

// MARK: - 读入扫描件
func pageCount(_ url: URL) throws -> Int {
    if url.pathExtension.lowercased() == "pdf" {
        guard let doc = CGPDFDocument(url as CFURL) else { throw Fail("PDF 打不开，请确认文件完整") }
        return doc.numberOfPages
    }
    return 1
}
func loadPage(_ url: URL, page: Int) throws -> Raster {
    if url.pathExtension.lowercased() == "pdf" {
        guard let doc = CGPDFDocument(url as CFURL), let pg = doc.page(at: page + 1) else { throw Fail("PDF 第 \(page + 1) 页打不开") }
        let box = pg.getBoxRect(.mediaBox), rot = ((Int(pg.rotationAngle) % 360) + 360) % 360, s = 2.5
        let pw = rot % 180 == 0 ? box.width : box.height, ph = rot % 180 == 0 ? box.height : box.width
        let out = Raster(w: Int(pw * s), h: Int(ph * s))
        out.px.withUnsafeMutableBytes { buf in
            let ctx = CGContext(data: buf.baseAddress, width: out.w, height: out.h, bitsPerComponent: 8, bytesPerRow: out.w * 4,
                                space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            ctx.setFillColor(CGColor(gray: 1, alpha: 1)); ctx.fill(CGRect(x: 0, y: 0, width: out.w, height: out.h))
            ctx.scaleBy(x: s, y: s)
            switch rot {
            case 90: ctx.translateBy(x: 0, y: box.width); ctx.rotate(by: -.pi / 2)
            case 180: ctx.translateBy(x: box.width, y: box.height); ctx.rotate(by: .pi)
            case 270: ctx.translateBy(x: box.height, y: 0); ctx.rotate(by: .pi / 2)
            default: break
            }
            ctx.translateBy(x: -box.minX, y: -box.minY); ctx.drawPDFPage(pg)
        }
        return out
    }
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { throw Fail("图片打不开") }
    let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] ?? [:]
    let size = max(props[kCGImagePropertyPixelWidth] as? Int ?? 0, props[kCGImagePropertyPixelHeight] as? Int ?? 0)
    let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                                 kCGImageSourceThumbnailMaxPixelSize: max(size, 1)]
    guard let img = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { throw Fail("图片读不出来") }
    return Raster(img)
}

// MARK: - 定位与校正（同旧版 align）
func components(_ g: Raster, left: Int, top: Int, size: Int, height: Int? = nil, maxSide: Double = 60, dark: Double = 100) -> [(x: Double, y: Double, n: Int)] {
    let ww = min(size, g.w - left), hh = min(height ?? size, g.h - top)
    var mask = [Bool](repeating: false, count: ww * hh), seen = [Bool](repeating: false, count: ww * hh)
    for y in 0..<hh { for x in 0..<ww { mask[y * ww + x] = g.gray(left + x, top + y) < dark } }
    var out: [(Double, Double, Int)] = []
    for start in 0..<(ww * hh) where mask[start] && !seen[start] {
        var todo = [start]; seen[start] = true; var pts: [Int] = []
        while let p = todo.popLast() {
            pts.append(p); let y = p / ww, x = p % ww
            for (dy, dx) in [(0, 1), (0, -1), (1, 0), (-1, 0)] {
                let ny = y + dy, nx = x + dx
                if ny >= 0, ny < hh, nx >= 0, nx < ww { let q = ny * ww + nx; if mask[q] && !seen[q] { seen[q] = true; todo.append(q) } }
            }
        }
        if pts.count >= 12 {
            let xs = pts.map { $0 % ww }, ys = pts.map { $0 / ww }
            let bw = Double(xs.max()! - xs.min()! + 1), bh = Double(ys.max()! - ys.min()! + 1)
            if bw / bh > 0.55 && bw / bh < 1.8 && Double(pts.count) / (bw * bh) > 0.60 && max(bw, bh) < maxSide {
                out.append((Double(xs.reduce(0, +)) / Double(pts.count), Double(ys.reduce(0, +)) / Double(pts.count), pts.count))
            }
        }
    }
    return out
}
func solve(_ a: [[Double]], _ b: [Double]) -> [Double]? {
    var m = a.enumerated().map { $0.element + [b[$0.offset]] }; let n = b.count
    for c in 0..<n {
        guard let p = (c..<n).max(by: { abs(m[$0][c]) < abs(m[$1][c]) }), abs(m[p][c]) > 1e-12 else { return nil }
        m.swapAt(c, p)
        for r in 0..<n where r != c { let f = m[r][c] / m[c][c]; for k in c...n { m[r][k] -= f * m[c][k] } }
    }
    return (0..<n).map { m[$0][n] / m[$0][$0] }
}
/// 旧版找法：纸张占满整张图（扫描仪），在四个角的固定区域里找黑块。
func cornerMarkers(_ small: Raster) -> [(x: Double, y: Double, n: Int)]? {
    var cands: [(x: Double, y: Double, n: Int)] = []
    for mk in MARKERS {
        let left = mk.x < W / 2 ? 0 : 490, top = mk.y < H / 2 ? 0 : 747
        var found = components(small, left: left, top: top, size: 130)
        if found.isEmpty { return nil }
        found.sort { a, b in
            func k(_ p: (x: Double, y: Double, n: Int)) -> Double { abs(sqrt(Double(p.n)) - mk.size / 2) + 0.10 * hypot(p.x + Double(left) - mk.x / 2, p.y + Double(top) - mk.y / 2) }
            return k(a) < k(b)
        }
        let f = found[0]; cands.append((2 * (f.x + Double(left)), 2 * (f.y + Double(top)), f.n))
    }
    return cands
}
/// 四个标记的大小应该成比例（24、18、21、15）；明显不成比例的当成没找到（多半是把文字或勾选框当成了标记）。
func saneSizes(_ c: [(x: Double, y: Double, n: Int)?]) -> [(x: Double, y: Double, n: Int)?] {
    let scales = c.enumerated().compactMap { i, p in p.map { sqrt(Double($0.n)) / MARKERS[i].size } }
    guard scales.count >= 3 else { return c }
    let mid = scales.sorted()[scales.count / 2]
    return c.enumerated().map { i, p in
        guard let p else { return nil }
        return abs(sqrt(Double(p.n)) / MARKERS[i].size - mid) / mid > 0.45 ? nil : p
    }
}
/// 只缺一个角时（比如手机文档扫描裁边裁掉了一个黑块），用另外三个角按平行四边形补出来，n 记为 0。
func complete(_ c: [(x: Double, y: Double, n: Int)?]) -> [(x: Double, y: Double, n: Int)]? {
    let missing = (0..<4).filter { c[$0] == nil }
    if missing.isEmpty { return c.map { $0! } }
    guard missing.count == 1 else { return nil }
    let k = missing[0], a = c[(k + 3) % 4]!, b = c[(k + 1) % 4]!, o = c[(k + 2) % 4]!
    var out = c; out[k] = (a.x + b.x - o.x, a.y + b.y - o.y, 0)
    return out.map { $0! }
}
/// 扫描件：在四角的固定位置找；大小不成比例就不用这个结果。
func checkedCornerMarkers(_ small: Raster) -> [[(x: Double, y: Double, n: Int)]] {
    guard let c = cornerMarkers(small) else { return [] }
    let sane = saneSizes(c.map { Optional($0) })
    return sane.contains { $0 == nil } ? [] : [c]
}
/// 四个都找到时，除了原样，再准备“去掉最可疑的一个角、用另外三个补”的两种备选（可疑：大小不成比例、紧贴照片边缘，多半是被裁掉的半个黑块或杂点）。
func variants(_ c: [(x: Double, y: Double, n: Int)]) -> [[(x: Double, y: Double, n: Int)]] {
    let scales = c.enumerated().map { sqrt(Double($0.element.n)) / MARKERS[$0.offset].size }
    let mid = scales.sorted()[2]
    func suspicion(_ i: Int) -> Double {
        let p = c[i], edge = min(p.x, p.y, W - p.x, H - p.y) < 12 ? 1.0 : 0
        return abs(scales[i] - mid) / mid + edge
    }
    let order = (0..<4).sorted { suspicion($0) > suspicion($1) }
    return [c] + order.prefix(2).compactMap { k in complete(c.enumerated().map { $0.offset == k ? nil : $0.element }) }
}
/// 后备找法：纸张只占照片中间（手机拍照），在四个象限里各取最靠外角的黑方块；可以缺一个角。
func quadrantMarkers(_ small: Raster) -> [[(x: Double, y: Double, n: Int)]] {
    let hw = small.w / 2, hh = small.h / 2
    var cands: [(x: Double, y: Double, n: Int)?] = []
    for mk in MARKERS {
        let right = mk.x > W / 2, bottom = mk.y > H / 2, left = right ? hw : 0, top = bottom ? hh : 0
        // 手机文档扫描会把黑块变灰（尤其隔着透明袋）：先按 100 找，找不到放宽到 150
        var found = components(small, left: left, top: top, size: hw, height: hh).filter { $0.n >= 12 }
        if found.isEmpty { found = components(small, left: left, top: top, size: hw, height: hh, dark: 150).filter { $0.n >= 12 } }
        let cx = Double(right ? small.w : 0), cy = Double(bottom ? small.h : 0)
        let f = found.min(by: { hypot($0.x + Double(left) - cx, $0.y + Double(top) - cy) < hypot($1.x + Double(left) - cx, $1.y + Double(top) - cy) })
        cands.append(f.map { (2 * ($0.x + Double(left)), 2 * ($0.y + Double(top)), $0.n) })
    }
    let sane = saneSizes(cands)
    if !sane.contains(where: { $0 == nil }) { return variants(sane.map { $0! }) }
    return complete(sane).map { [$0] } ?? []
}
/// 在原图上把缩略图里找到的标记位置再精确一次（手机照片缩小后误差会让条码读偏）。
func refine(_ img: Raster, _ cands: [(x: Double, y: Double, n: Int)]) -> [(x: Double, y: Double, n: Int)] {
    let sx = Double(img.w) / W, sy = Double(img.h) / H, r = max(16, Int(30 * sx))
    return cands.map { c in
        guard c.n > 0 else { return c }  // 补出来的角没有实物可对
        let u = Int(c.x * sx), v = Int(c.y * sy), left = max(0, u - r), top = max(0, v - r)
        var found = components(img, left: left, top: top, size: 2 * r, height: 2 * r, maxSide: Double(r) * 1.6)
        if found.isEmpty { found = components(img, left: left, top: top, size: 2 * r, height: 2 * r, maxSide: Double(r) * 1.6, dark: 150) }
        guard let f = found.min(by: { hypot($0.x + Double(left - u), $0.y + Double(top - v)) < hypot($1.x + Double(left - u), $1.y + Double(top - v)) }),
              hypot(f.x + Double(left - u), f.y + Double(top - v)) < Double(r) / 2 else { return c }
        return ((f.x + Double(left) + 0.5) / sx, (f.y + Double(top) + 0.5) / sy, c.n)
    }
}
/// 找四角 → 摆正 → 读编号。先按扫描件的固定位置找，读不出编号再按手机照片的方式找；纸张倒放时转 180° 再试。
/// 找四角 → 摆正 → 读编号，返回所有能通过编号校验的摆法。扫描件按固定位置一次找到就直接用；
/// 手机照片会有几种找角方案（原样、去掉可疑的角再补），由调用方按“框线对得最齐”挑一个——
/// 因为编号在顶部，一个角认错时编号仍可能通过，但下半页会错开。
func locate(_ input: Raster) throws -> [(Raster, String)] {
    var img = input
    if img.w > img.h { img = img.rotated90() }
    var err: Error = Fail("无法找到四角定位标记。请扫描完整纸张，不要裁掉边缘")
    for turned in [img, img.rotated180()] {
        let small = turned.resized(620, 877)
        var found: [(Raster, String)] = []
        for (fi, finder) in [checkedCornerMarkers, quadrantMarkers].enumerated() { for cands in finder(small) {
            let sizes = cands.map { $0.n }
            // 最大的黑块应在左上；补过角的方向靠顶部编号校验来确认
            if !sizes.contains(0) && sizes.firstIndex(of: sizes.max()!)! != 0 { continue }
            do {
                let aligned = try warp(turned, refine(turned, cands)), token = try identify(aligned)
                if fi == 0 { return [(aligned, token)] }
                found.append((aligned, token))
            } catch { err = error }
        } }
        if !found.isEmpty { return found }
    }
    throw err
}
/// 摆正后纸上印的框线和版式快照对得有多齐（所有外框四边的平均深度，越大越齐）。
func fitScore(_ img: Raster, _ cells: [[String: Any]]) -> Double {
    let g = grayPlane(img); var s = 0.0, n = 0
    for c in cells { if let f = ints(c["frame"]) { s += edgeDark(g, img.w, img.h, f[0], f[1], f[2], f[3]); n += 1 } }
    return n > 0 ? s / Double(n) : 0
}
func warp(_ img: Raster, _ cands: [(x: Double, y: Double, n: Int)]) throws -> Raster {
    var a: [[Double]] = [], b: [Double] = []
    for (mk, p) in zip(MARKERS, cands) {
        let u = p.x * Double(img.w) / W, v = p.y * Double(img.h) / H
        a.append([mk.x, mk.y, 1, 0, 0, 0, -u * mk.x, -u * mk.y]); b.append(u)
        a.append([0, 0, 0, mk.x, mk.y, 1, -v * mk.x, -v * mk.y]); b.append(v)
    }
    guard let c = solve(a, b) else { throw Fail("定位标记位置异常，请重扫") }
    let out = Raster(w: Int(W), h: Int(H)), sw = img.w, sh = img.h
    for y in 0..<out.h {
        for x in 0..<out.w {
            let X = Double(x) + 0.5, Y = Double(y) + 0.5, d = c[6] * X + c[7] * Y + 1
            let u = (c[0] * X + c[1] * Y + c[2]) / d - 0.5, v = (c[3] * X + c[4] * Y + c[5]) / d - 0.5
            let x0 = Int(floor(u)), y0 = Int(floor(v))
            if x0 < 0 || y0 < 0 || x0 + 1 >= sw || y0 + 1 >= sh { continue }
            let fx = u - Double(x0), fy = v - Double(y0), t = (y * out.w + x) * 4
            for k in 0..<3 {
                let p00 = Double(img.px[(y0 * sw + x0) * 4 + k]), p10 = Double(img.px[(y0 * sw + x0 + 1) * 4 + k])
                let p01 = Double(img.px[((y0 + 1) * sw + x0) * 4 + k]), p11 = Double(img.px[((y0 + 1) * sw + x0 + 1) * 4 + k])
                out.px[t + k] = UInt8(max(0, min(255, (p00 * (1 - fx) + p10 * fx) * (1 - fy) + (p01 * (1 - fx) + p11 * fx) * fy)))
            }
        }
    }
    return out
}
/// 读顶部编号条码。纸不平（比如装在透明袋里、有点鼓）时条码会偏几个像素，所以在附近小范围里找能通过校验的位置；
/// 深浅门槛按这一行条码自己最深和最浅的中间取，照片发灰也能读。校验有 24 位（开头两字节 + 末尾校验字节），找错的可能可以忽略。
func identify(_ img: Raster) throws -> String {
    var tries: [(Int, Int)] = []
    for dy in -8...8 { for dx in -14...14 { tries.append((dx, dy)) } }
    tries.sort { abs($0.0) + abs($0.1) < abs($1.0) + abs($1.1) }
    for (dx, dy) in tries {
        var vals: [Double] = []
        for i in 0..<64 {
            var sum = 0.0
            for y in (30 + dy)..<(42 + dy) { for x in (429 + i * 6 + dx)..<(433 + i * 6 + dx) { sum += img.gray(x, y) } }
            vals.append(sum / 48)
        }
        let lo = vals.min()!, hi = vals.max()!
        guard hi - lo > 40 else { continue }
        let bits = vals.map { $0 < (lo + hi) / 2 ? UInt8(1) : 0 }
        let raw = (0..<8).map { i in bits[(i * 8)..<(i * 8 + 8)].reduce(UInt8(0)) { $0 << 1 | $1 } }
        if raw[0] == 0xa6 && raw[1] == 0x5c && raw[7] == UInt8(crc32(Array(raw[0..<7])) & 0xff) { return hex(Array(raw[2..<7])) }
    }
    // 10-27：纸有点鼓、条码偏得多或有一两条印淡了，严格校验过不了时，和这台电脑打印过的几张表的条码逐个比，
    // 明显最像的那张（相关度高、并且比第二像的高出一截）就认它。只在已知编号里挑，认不出来照旧报错。
    if let tok = ocrToken(img) ?? closestKnown(img, tries) { return tok }
    throw Fail("表单编号校验失败，请提高扫描清晰度，或使用本系统打印的表单")
}
var KNOWN_TOKENS: [String] = []
func barBits(_ token: String) -> [Double] {
    var raw: [UInt8] = [0xa6, 0x5c] + hexBytes(token); raw.append(UInt8(crc32(raw) & 0xff))
    return raw.flatMap { b in (0..<8).map { i in Double((b >> (7 - i)) & 1) } }
}
func pearson(_ a: [Double], _ b: [Double]) -> Double {
    let n = Double(a.count), ma = a.reduce(0, +) / n, mb = b.reduce(0, +) / n
    var sab = 0.0, saa = 0.0, sbb = 0.0
    for i in 0..<a.count { let x = a[i] - ma, y = b[i] - mb; sab += x * y; saa += x * x; sbb += y * y }
    return saa > 0 && sbb > 0 ? sab / (saa * sbb).squareRoot() : 0
}
/// 左上角印着“编号 xxxxxxxxxx”：用系统自带文字识别读出来，和打印过的编号比，最多差 2 个字符、且只有一张对得上才认。
func ocrToken(_ img: Raster) -> String? {
    let known = KNOWN_TOKENS.filter { $0.count == 10 }
    guard !known.isEmpty, let crop = img.cgImage().cropping(to: CGRect(x: 20, y: 70, width: 480, height: 60)) else { return nil }
    let req = VNRecognizeTextRequest(); req.recognitionLevel = .accurate; req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: crop).perform([req])
    let texts = (req.results ?? []).flatMap { $0.topCandidates(3).map { $0.string } }
    let fix: [Character: Character] = ["o": "0", "O": "0", "l": "1", "I": "1", "i": "1", "S": "5", "s": "5", "B": "8", "g": "9", "q": "9", "t": "f", "Z": "2", "z": "2"]
    var seen: [String] = []
    for t in texts {
        let chars = Array(t.replacingOccurrences(of: " ", with: ""))
        let norm = chars.map { c in fix[c] ?? Character(c.lowercased()) }
        if norm.count >= 10 { for start in 0...(norm.count - 10) { seen.append(String(norm[start..<start + 10])) } }
        if norm.count >= 9 { for start in 0...(norm.count - 9) { seen.append(String(norm[start..<start + 9])) } }   // 最后一个字被切掉也认（只比前 9 个）
    }
    if ProcessInfo.processInfo.environment["FORM_DEBUG"] != nil { FileHandle.standardError.write("ocr \(texts)\n".data(using: .utf8)!) }
    let dist = { (a: String, b: String) in zip(a, b).filter { $0 != $1 }.count }
    let hits = Set(known.filter { k in seen.contains { $0.count == 10 ? dist($0, k) <= 2 : dist($0, k) <= 1 } })
    return hits.count == 1 ? hits.first : nil
}
func closestKnown(_ img: Raster, _ tries: [(Int, Int)]) -> String? {
    let known = KNOWN_TOKENS.filter { $0.count == 10 && $0.allSatisfy { $0.isHexDigit } }
    guard !known.isEmpty else { return nil }
    let expected = known.map { barBits($0) }
    var best = [Double](repeating: -1, count: known.count)
    for (dx, dy) in tries {
        var dark: [Double] = []
        for i in 0..<64 {
            var sum = 0.0
            for y in (30 + dy)..<(42 + dy) { for x in (429 + i * 6 + dx)..<(433 + i * 6 + dx) { sum += img.gray(x, y) } }
            dark.append(255 - sum / 48)
        }
        for k in 0..<known.count { best[k] = max(best[k], pearson(dark, expected[k])) }
    }
    let order = best.indices.sorted { best[$0] > best[$1] }, top = best[order[0]], second = order.count > 1 ? best[order[1]] : 0
    if ProcessInfo.processInfo.environment["FORM_DEBUG"] != nil { FileHandle.standardError.write("closestKnown \(zip(known, best).map { "\($0):\(String(format: "%.2f", $1))" })\n".data(using: .utf8)!) }
    return top >= 0.75 && top - second >= 0.15 ? known[order[0]] : nil
}
/// 整页灰度（量框线时反复用，先算一次）。
func grayPlane(_ r: Raster) -> [Double] {
    var g = [Double](repeating: 255, count: r.w * r.h)
    for i in 0..<(r.w * r.h) { g[i] = 0.299 * Double(r.px[i * 4]) + 0.587 * Double(r.px[i * 4 + 1]) + 0.114 * Double(r.px[i * 4 + 2]) }
    return g
}
/// 矩形四条边上的平均深度。
func edgeDark(_ g: [Double], _ w: Int, _ h: Int, _ x: Int, _ y: Int, _ bw: Int, _ bh: Int) -> Double {
    var s = 0.0, n = 0
    func at(_ px: Int, _ py: Int) { if px >= 0, py >= 0, px < w, py < h { s += 255 - g[py * w + px]; n += 1 } }
    for i in 0...bw { at(x + i, y); at(x + i, y + bh) }
    for j in 0...bh { at(x, y + j); at(x + bw, y + j) }
    return n > 0 ? s / Double(n) : 0
}
/// 纸不平（比如在透明袋里鼓起来）时格子会偏十几个像素：在附近找和纸上印的框线最吻合的位置，明显更吻合才移动。
/// 上下最多找到框高的 0.4 倍（不会跳到隔壁一行），左右最多 24。
/// from 是起点偏移（跟随同一行别的格子时用），limit 限制搜索范围（小框只微调）。
func snap(_ g: [Double], _ w: Int, _ h: Int, _ f: [Int], from: (Int, Int) = (0, 0), limit: Int = 24) -> (Int, Int) {
    let base = edgeDark(g, w, h, f[0] + from.0, f[1] + from.1, f[2], f[3]); var best = from, score = base
    let ry = min(limit, max(3, min(24, Int(Double(f[3]) * 0.4)))), rx = min(limit, max(3, min(24, Int(Double(f[2]) * 0.4))))
    for dy in -ry...ry { for dx in -rx...rx {
        let v = edgeDark(g, w, h, f[0] + from.0 + dx, f[1] + from.1 + dy, f[2], f[3])
        if v > score { score = v; best = (from.0 + dx, from.1 + dy) }
    } }
    return score > base * 1.15 + 2 ? best : from
}

func path(_ data: [String: Any], _ key: String) throws -> URL {
    guard let p = data[key] as? String, p.hasPrefix("/") else { throw Fail("缺少参数 \(key)（要用完整路径）") }
    return URL(fileURLWithPath: p)
}
func ints(_ v: Any?) -> [Int]? {
    guard let a = v as? [Any], a.count == 4 else { return nil }
    let n = a.compactMap { ($0 as? NSNumber)?.doubleValue }
    return n.count == 4 ? n.map { Int($0.rounded()) } : nil
}

// MARK: - 识别
/// data: file（扫描件完整路径）、page（第几页，从 0 起）、layouts（版式文件夹，里面是 <编号>.json，含 cells）、preview（要不要整页缩略图）
/// cells: [{"id": 任意字符串, "rect": [x, y, 宽, 高]（1240×1754 页面坐标）, "image": 要不要截图, "frame": 可选，纸上印的外框 [x, y, 宽, 高]，量之前先对准它,
///          "follow": 可选，另一个格子的 id——先用它对准时的偏移（小框跟着同一行的大框走，自己只在 ±8 内微调）}]
func scan(_ data: [String: Any]) throws -> [String: Any] {
    let file = try path(data, "file"), layouts = try path(data, "layouts"), page = data["page"] as? Int ?? 0
    KNOWN_TOKENS = ((try? FileManager.default.contentsOfDirectory(atPath: layouts.path)) ?? []).filter { $0.hasSuffix(".json") }.map { String($0.dropLast(5)) }
    let image = try loadPage(file, page: page)
    if image.w < 800 || image.h < 1000 { throw Fail("图片过小，请使用至少 150dpi 扫描") }
    let options = try locate(image), token = options[0].1
    guard let ldata = try? Data(contentsOf: layouts.appendingPathComponent(token + ".json")),
          let layout = try? JSONSerialization.jsonObject(with: ldata) as? [String: Any],
          let cells = layout["cells"] as? [[String: Any]] else { throw Fail("找不到这张表（编号 \(token)）的版式快照，请确认是本系统打印的表单") }
    let aligned = options.count == 1 ? options[0].0 : options.filter { $0.1 == token }.max { fitScore($0.0, cells) < fitScore($1.0, cells) }!.0
    var out: [[String: Any]] = []
    let plane = grayPlane(aligned)
    var shifts: [String: (Int, Int)] = [:]
    for c in cells {
        guard var r = ints(c["rect"]), r[2] > 0, r[3] > 0 else { continue }
        var shift = (0, 0)
        if let other = c["follow"] as? String, let s = shifts[other] { shift = s }
        if let f = ints(c["frame"]) { shift = snap(plane, aligned.w, aligned.h, f, from: shift, limit: c["follow"] == nil ? 24 : 8) }
        if let id = c["id"] as? String { shifts[id] = shift }
        r[0] += shift.0; r[1] += shift.1
        // 笔迹门槛按这一格的纸色定：比纸色（中位数）深 70 算笔迹，限制在 125–185 之间。扫描件纸是纯白 → 185；手机文档扫描发灰的照片也能量到浅色笔迹。
        let crop = aligned.crop(r[0], r[1], r[0] + r[2], r[1] + r[3])
        var tones: [Double] = []; tones.reserveCapacity(crop.w * crop.h)
        for y in 0..<crop.h { for x in 0..<crop.w { tones.append(crop.gray(x, y)) } }
        tones.sort(); let paper = tones.isEmpty ? 255 : tones[tones.count / 2]
        let ink = crop.darkRatio(0, 0, crop.w, crop.h, below: min(185, max(125, paper - 70)))
        var cell: [String: Any] = ["id": c["id"] ?? "", "ink": (ink * 10000).rounded() / 10000, "shift": [shift.0, shift.1]]
        if c["image"] as? Bool == true { cell["image"] = crop.pngDataURL() }
        out.append(cell)
    }
    var result: [String: Any] = ["token": token, "page": page, "cells": out]
    if data["preview"] as? Bool == true { result["preview"] = aligned.resized(620, 877).pngDataURL() }
    return result
}

// MARK: - 打印
/// data: output（PDF 完整路径）、token（10 位十六进制编号）、title（PDF 标题）、items（模板要画的东西，1240×1754 页面坐标，y 向下）：
///   {"t":"text","x","y"(基线),"s"(文字),"size"} · {"t":"rect","x","y","w","h","fill"} · {"t":"line","x1","y1","x2","y2"}
func printForm(_ data: [String: Any]) throws -> [String: Any] {
    let file = try path(data, "output"), token = data["token"] as? String ?? ""
    guard token.count == 10, token.allSatisfy({ $0.isHexDigit }) else { throw Fail("编号要是 10 位十六进制") }
    var media = CGRect(x: 0, y: 0, width: 595.276, height: 841.89)
    guard let ctx = CGContext(file as CFURL, mediaBox: &media, [kCGPDFContextTitle: data["title"] as? String ?? "表单", kCGPDFContextCreator: "纸质表单识别工具"] as CFDictionary) else { throw Fail("不能写入 PDF") }
    ctx.beginPDFPage(nil); ctx.scaleBy(x: 595.276 / W, y: 841.89 / H); ctx.setLineWidth(1)
    ctx.setStrokeColor(CGColor(gray: 0, alpha: 1)); ctx.setFillColor(CGColor(gray: 0, alpha: 1))
    func rect(_ x: Double, _ y: Double, _ w: Double, _ h: Double, fill: Bool = false) {
        let r = CGRect(x: x, y: H - y - h, width: w, height: h); if fill { ctx.fill(r) } else { ctx.stroke(r) }
    }
    for m in MARKERS { rect(m.x - m.size / 2, m.y - m.size / 2, m.size, m.size, fill: true) }
    var raw = [0xa6, 0x5c] + hexBytes(token.lowercased()); raw.append(UInt8(crc32(raw) & 0xff))
    let bits = raw.flatMap { b in (0..<8).reversed().map { (b >> $0) & 1 } }
    for (i, bit) in bits.enumerated() where bit == 1 { rect(428 + Double(i) * 6, 26, 6, 20, fill: true) }
    func num(_ d: [String: Any], _ k: String) -> Double { (d[k] as? NSNumber)?.doubleValue ?? 0 }
    for it in data["items"] as? [[String: Any]] ?? [] {
        switch it["t"] as? String {
        case "text":
            let font = CTFontCreateWithName("PingFangSC-Regular" as CFString, num(it, "size") > 0 ? num(it, "size") : 18, nil)
            let line = CTLineCreateWithAttributedString(NSAttributedString(string: it["s"] as? String ?? "", attributes: [NSAttributedString.Key(kCTFontAttributeName as String): font,
                                                                                                                         NSAttributedString.Key(kCTForegroundColorAttributeName as String): CGColor(gray: 0, alpha: 1)]))
            ctx.textMatrix = .identity; ctx.textPosition = CGPoint(x: num(it, "x"), y: H - num(it, "y")); CTLineDraw(line, ctx)
        case "rect": rect(num(it, "x"), num(it, "y"), num(it, "w"), num(it, "h"), fill: it["fill"] as? Bool == true)
        case "line":
            ctx.move(to: CGPoint(x: num(it, "x1"), y: H - num(it, "y1"))); ctx.addLine(to: CGPoint(x: num(it, "x2"), y: H - num(it, "y2"))); ctx.strokePath()
        default: throw Fail("不认识的绘制项：\(it["t"] ?? "")")
        }
    }
    ctx.endPDFPage(); ctx.closePDF()
    return ["ok": true]
}

// MARK: - 入口
func emit(_ obj: Any) { FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: obj)) }
do {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    guard let req = try JSONSerialization.jsonObject(with: input) as? [String: Any], let action = req["action"] as? String else { throw Fail("请求无效") }
    let data = req["data"] as? [String: Any] ?? [:]
    switch action {
    case "print": emit(try printForm(data))
    case "scan": emit(try scan(data))
    case "pages": emit(["pages": try pageCount(try path(data, "file"))])
    default: throw Fail("未知操作")
    }
} catch let e as Fail {
    emit(["error": e.message]); exit(1)
} catch {
    emit(["error": "识别工具出错：\(error.localizedDescription)"]); exit(1)
}
