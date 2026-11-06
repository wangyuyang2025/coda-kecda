// 素材编辑工具：视频剪头尾 + 旋转，只用 macOS 自带的 AVFoundation，不重新压缩（画质不变、很快）。
// 用法：echo '{"in":"原视频","out":"输出.mov","start":1.5,"end":20.0,"rotate":90}' | 素材编辑工具
//   start / end 是秒（end 可省略＝到结尾），rotate 是顺时针 0/90/180/270。原文件不动。
// 输出一行 JSON：{"ok":true,"duration":18.5} 或 {"error":"…"}。
// 另一个用法：{"probe":"视频"} → {"duration":秒,"width":…,"height":…}
// 再一个：{"covered":"视频"} → {"covered":true/false,"seconds":n}：开头或结尾 6 秒里有没有连续约 1.5 秒以上几乎全黑（拍的时候用手捂住镜头＝这段不要，预删除）。
// 再一个：{"photo":"照片","out":"输出.jpg","rotate":90} → 按屏幕上看到的方向（已套用 EXIF 方向）再顺时针转，存成 JPG。
// 再一个：{"upright":"视频或照片"} → {"rotate":0/90/180/270,"faces":n}：看画面里人脸朝哪边，算出要顺时针转多少度才正（没把握就 0）。
import Foundation
import AVFoundation
import Vision
import ImageIO
import UniformTypeIdentifiers

func reply(_ obj: [String: Any]) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: obj)
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write("\n".data(using: .utf8)!)
    exit(obj["error"] == nil ? 0 : 1)
}
let input = FileHandle.standardInput.readDataToEndOfFile()
guard let job = (try? JSONSerialization.jsonObject(with: input)) as? [String: Any] else { reply(["error": "参数不对"]) }

func load(_ path: String) async -> (AVURLAsset, CMTime, AVAssetTrack?) {
    let asset = AVURLAsset(url: URL(fileURLWithPath: path))
    let duration = (try? await asset.load(.duration)) ?? .zero
    let video = try? await asset.loadTracks(withMediaType: .video).first
    return (asset, duration, video)
}

let done = DispatchSemaphore(value: 0)
var result: [String: Any] = ["error": "没有完成"]
// 发微信用的小视频：{"compress":"原视频","out":"小视频.mp4","maxSide":1280,"bitrate":2500000}
// 长边缩到 maxSide（默认 1280＝720p），H.264 平均码率 bitrate（默认 2.5Mbps，约每分钟 19MB），AAC 128k；方向保持不变。
func compressVideo(_ src: String, _ dst: String, maxSide: Double, bitrate: Int) async throws -> [String: Any] {
    let asset = AVURLAsset(url: URL(fileURLWithPath: src))
    guard let vtrack = try await asset.loadTracks(withMediaType: .video).first else { throw NSError(domain: "c", code: 1, userInfo: [NSLocalizedDescriptionKey: "没有画面"]) }
    let atrack = try await asset.loadTracks(withMediaType: .audio).first
    let natural = try await vtrack.load(.naturalSize), transform = try await vtrack.load(.preferredTransform)
    let scale = min(1, maxSide / max(natural.width, natural.height))
    let w = Int((natural.width * scale / 2).rounded()) * 2, h = Int((natural.height * scale / 2).rounded()) * 2
    let reader = try AVAssetReader(asset: asset)
    let vout = AVAssetReaderTrackOutput(track: vtrack, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange])
    vout.alwaysCopiesSampleData = false; reader.add(vout)
    var aout: AVAssetReaderTrackOutput?
    if let atrack { let o = AVAssetReaderTrackOutput(track: atrack, outputSettings: [AVFormatIDKey: kAudioFormatLinearPCM]); reader.add(o); aout = o }
    let out = URL(fileURLWithPath: dst); try? FileManager.default.removeItem(at: out)
    let writer = try AVAssetWriter(outputURL: out, fileType: .mp4)
    let vin = AVAssetWriterInput(mediaType: .video, outputSettings: [AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: w, AVVideoHeightKey: h, AVVideoScalingModeKey: AVVideoScalingModeResizeAspect,
        AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: bitrate, AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel, AVVideoMaxKeyFrameIntervalKey: 60]])
    vin.transform = transform; vin.expectsMediaDataInRealTime = false; writer.add(vin)
    var ain: AVAssetWriterInput?
    if aout != nil { let i = AVAssetWriterInput(mediaType: .audio, outputSettings: [AVFormatIDKey: kAudioFormatMPEG4AAC, AVNumberOfChannelsKey: 2, AVSampleRateKey: 44100, AVEncoderBitRateKey: 128000]); i.expectsMediaDataInRealTime = false; writer.add(i); ain = i }
    guard reader.startReading(), writer.startWriting() else { throw writer.error ?? reader.error ?? NSError(domain: "c", code: 2, userInfo: [NSLocalizedDescriptionKey: "没法开始压缩"]) }
    writer.startSession(atSourceTime: .zero)
    let group = DispatchGroup()
    func pump(_ input: AVAssetWriterInput, _ output: AVAssetReaderTrackOutput, _ label: String) {
        group.enter(); let q = DispatchQueue(label: label)
        input.requestMediaDataWhenReady(on: q) {
            while input.isReadyForMoreMediaData {
                if let b = output.copyNextSampleBuffer() { input.append(b) } else { input.markAsFinished(); group.leave(); return }
            }
        }
    }
    pump(vin, vout, "v"); if let ain, let aout { pump(ain, aout, "a") }
    await withCheckedContinuation { c in group.notify(queue: .global()) { c.resume() } }
    if reader.status == .failed { writer.cancelWriting(); throw reader.error ?? NSError(domain: "c", code: 3) }
    await writer.finishWriting()
    if writer.status != .completed { throw writer.error ?? NSError(domain: "c", code: 4, userInfo: [NSLocalizedDescriptionKey: "压缩没完成"]) }
    let size = (try? FileManager.default.attributesOfItem(atPath: dst)[.size] as? Int) ?? 0
    return ["ok": true, "width": w, "height": h, "size": size]
}
Task {
    defer { done.signal() }
    if let src = job["compress"] as? String, let dst = job["out"] as? String {
        do { result = try await compressVideo(src, dst, maxSide: job["maxSide"] as? Double ?? 1280, bitrate: job["bitrate"] as? Int ?? 2_500_000) }
        catch { result = ["error": "压缩失败：" + error.localizedDescription] }
        return
    }
    if let path = job["photo"] as? String, let dst = job["out"] as? String {
        let rotate = ((job["rotate"] as? Int ?? 0) % 360 + 360) % 360
        guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil) else { result = ["error": "读不出这张照片"]; return }
        let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 12000]
        guard let img = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { result = ["error": "读不出这张照片"]; return }
        let w = img.width, h = img.height, side = rotate == 90 || rotate == 270
        let ow = side ? h : w, oh = side ? w : h
        guard let ctx = CGContext(data: nil, width: ow, height: oh, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { result = ["error": "内存不够"]; return }
        // 坐标原点在左下：顺时针转 rotate 度
        ctx.translateBy(x: CGFloat(ow) / 2, y: CGFloat(oh) / 2); ctx.rotate(by: -CGFloat(rotate) * .pi / 180); ctx.translateBy(x: -CGFloat(w) / 2, y: -CGFloat(h) / 2)
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
        guard let outImg = ctx.makeImage(), let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: dst) as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else { result = ["error": "存不下"]; return }
        CGImageDestinationAddImage(dest, outImg, [kCGImageDestinationLossyCompressionQuality: 0.92] as CFDictionary)
        result = CGImageDestinationFinalize(dest) ? ["ok": true, "width": ow, "height": oh] : ["error": "存不下"]; return
    }
    if let path = job["covered"] as? String {
        let (asset, duration, _) = await load(path)
        guard duration.seconds > 0 else { result = ["error": "读不出这个视频"]; return }
        let gen = AVAssetImageGenerator(asset: asset); gen.maximumSize = CGSize(width: 64, height: 64)
        gen.requestedTimeToleranceBefore = CMTime(seconds: 0.1, preferredTimescale: 600); gen.requestedTimeToleranceAfter = gen.requestedTimeToleranceBefore
        func dark(_ img: CGImage) -> Bool {
            // 缩成 16×16 灰度：平均亮度很低、而且几乎没有明暗差＝镜头被捂住
            let w = 16, h = 16; var px = [UInt8](repeating: 0, count: w * h)
            guard let ctx = CGContext(data: &px, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w, space: CGColorSpaceCreateDeviceGray(), bitmapInfo: 0) else { return false }
            ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
            let mean = Double(px.reduce(0) { $0 + Int($1) }) / Double(px.count), top = Double(px.max() ?? 0)
            return mean < 22 && top < 60
        }
        let step = 0.25, window = min(6.0, duration.seconds)
        var longest = 0.0
        for (a, b) in [(0.0, window), (max(0, duration.seconds - window), duration.seconds)] {
            var run = 0.0, t = a
            while t < b {
                if let img = try? await gen.image(at: CMTime(seconds: t, preferredTimescale: 600)).image, dark(img) { run += step; longest = max(longest, run) } else { run = 0 }
                t += step
            }
        }
        result = ["covered": longest >= 1.5, "seconds": longest]; return
    }
    if let path = job["upright"] as? String {
        // 取一帧（视频取中间；照片按 EXIF 方向摆好），四个方向各找一次人脸，人脸最多最确定的方向就是“正”的
        var image: CGImage?
        let url = URL(fileURLWithPath: path)
        if ["jpg","jpeg","png","heic","heif","hif"].contains(url.pathExtension.lowercased()) {
            if let src = CGImageSourceCreateWithURL(url as CFURL, nil) {
                let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 1280]
                image = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary)
            }
        } else {
            let (asset, duration, _) = await load(path)
            let gen = AVAssetImageGenerator(asset: asset); gen.appliesPreferredTrackTransform = true; gen.maximumSize = CGSize(width: 1280, height: 1280)
            for f in [0.5, 0.3, 0.7] { if let img = try? await gen.image(at: CMTime(seconds: duration.seconds * f, preferredTimescale: 600)).image { image = img; break } }
        }
        guard let cg = image else { result = ["error": "读不出画面"]; return }
        // Vision 的 orientation：告诉它“这张图要按这个方向看”。.up=不转，.right=顺时针转 90 后看……
        let tries: [(Int, CGImagePropertyOrientation)] = [(0, .up), (90, .right), (180, .down), (270, .left)]
        var best = (rotate: 0, score: 0.0, faces: 0), scores: [String: Double] = [:]
        for (deg, o) in tries {
            let req = VNDetectFaceRectanglesRequest()
            try? VNImageRequestHandler(cgImage: cg, orientation: o).perform([req])
            let faces = (req.results ?? []).filter { $0.confidence > 0.6 && abs(($0.roll?.doubleValue ?? 0)) < 0.6 }
            let score = faces.reduce(0.0) { $0 + Double($1.confidence) * Double($1.boundingBox.width * $1.boundingBox.height).squareRoot() }
            scores[String(deg)] = score
            if score > best.score { best = (deg, score, faces.count) }
        }
        let upScore = scores["0"] ?? 0
        // 只有明显比“不转”好才转（没有人脸、或差不多时都不动）
        let sure = best.rotate != 0 && best.score > 0.05 && best.score > upScore * 2
        result = ["rotate": sure ? best.rotate : 0, "faces": best.faces, "scores": scores]; return
    }
    if let probe = job["probe"] as? String {
        let (_, duration, video) = await load(probe)
        var size = CGSize.zero
        if let v = video, let natural = try? await v.load(.naturalSize), let t = try? await v.load(.preferredTransform) {
            size = natural.applying(t); size = CGSize(width: abs(size.width), height: abs(size.height))
        }
        result = ["duration": duration.seconds, "width": size.width, "height": size.height]; return
    }
    guard let src = job["in"] as? String, let dst = job["out"] as? String else { result = ["error": "缺少输入或输出"]; return }
    let (asset, duration, videoTrack) = await load(src)
    guard duration.seconds > 0 else { result = ["error": "读不出这个视频"]; return }
    let start = max(0, job["start"] as? Double ?? 0)
    let end = min(duration.seconds, job["end"] as? Double ?? duration.seconds)
    guard end - start >= 0.2 else { result = ["error": "剪得太短了"]; return }
    let rotate = ((job["rotate"] as? Int ?? 0) % 360 + 360) % 360
    let range = CMTimeRange(start: CMTime(seconds: start, preferredTimescale: 600), end: CMTime(seconds: end, preferredTimescale: 600))

    // 用一个合成：每条轨道都剪同一段；视频轨在原来的方向上再顺时针转 rotate 度（只改方向标记，不重新压缩）
    let comp = AVMutableComposition()
    do {
        for track in (try await asset.loadTracks(withMediaType: .video)) + (try await asset.loadTracks(withMediaType: .audio)) {
            guard let t = comp.addMutableTrack(withMediaType: track.mediaType, preferredTrackID: kCMPersistentTrackID_Invalid) else { continue }
            try t.insertTimeRange(range, of: track, at: .zero)
            if track.mediaType == .video {
                var transform = (try? await track.load(.preferredTransform)) ?? .identity
                if rotate != 0 {
                    let natural = (try? await track.load(.naturalSize)) ?? .zero
                    let shown = natural.applying(transform), w = abs(shown.width), h = abs(shown.height)
                    let turn: CGAffineTransform
                    switch rotate {
                    case 90: turn = CGAffineTransform(a: 0, b: 1, c: -1, d: 0, tx: h, ty: 0)
                    case 180: turn = CGAffineTransform(a: -1, b: 0, c: 0, d: -1, tx: w, ty: h)
                    default: turn = CGAffineTransform(a: 0, b: -1, c: 1, d: 0, tx: 0, ty: w)
                    }
                    // 先把原来的方向摆正到左上角，再转
                    let r = CGRect(origin: .zero, size: natural).applying(transform)
                    transform = transform.concatenating(CGAffineTransform(translationX: -r.minX, y: -r.minY)).concatenating(turn)
                }
                t.preferredTransform = transform
            }
        }
    } catch { result = ["error": "剪辑失败：\(error.localizedDescription)"]; return }
    _ = videoTrack

    let out = URL(fileURLWithPath: dst)
    try? FileManager.default.removeItem(at: out)
    guard let export = AVAssetExportSession(asset: comp, presetName: AVAssetExportPresetPassthrough) else { result = ["error": "无法导出"]; return }
    do {
        try await export.export(to: out, as: .mov)
        result = ["ok": true, "duration": end - start]
    } catch { result = ["error": "导出失败：\(error.localizedDescription)"] }
}
done.wait()
reply(result)
