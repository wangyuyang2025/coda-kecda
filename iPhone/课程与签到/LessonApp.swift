import SwiftUI
import WebKit
import UniformTypeIdentifiers
import CryptoKit
import QuickLook
import AVFoundation
import AVKit
import Speech
import Darwin
import VisionKit

struct Pairing: Codable {
    var serverId: String? = nil
    var role: String? = nil
    let host: String
    let fallbackHost: String?
    let port: Int
    let token: String
    let fingerprint: String
}
final class PinnedSession: NSObject, URLSessionDelegate, @unchecked Sendable {
    let pairing: Pairing
    init(_ pairing: Pairing) { self.pairing = pairing }
    func accepts(_ challenge: URLAuthenticationChallenge) -> Bool {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              [pairing.host, pairing.fallbackHost].compactMap({$0?.lowercased()}).contains(challenge.protectionSpace.host.lowercased()),
              let trust = challenge.protectionSpace.serverTrust,
              let chain = SecTrustCopyCertificateChain(trust) as? [SecCertificate], let certificate = chain.first else { return false }
        let digest = SHA256.hash(data: SecCertificateCopyData(certificate) as Data).map { String(format: "%02x", $0) }.joined()
        return digest == pairing.fingerprint
    }
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge, completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        if accepts(challenge), let trust = challenge.protectionSpace.serverTrust { completionHandler(.useCredential, URLCredential(trust: trust)) }
        else { completionHandler(.cancelAuthenticationChallenge, nil) }
    }
}
/// 0.8 后台上传：把文件交给 iPhone 系统去传，锁屏、切到别的 App 也会继续（往上划掉 App 会被系统取消）。
/// 规矩不变：Mac 回执里的校验码和拍摄编号都对上，才删手机原件。App 睡着时收到的回执先记在 UserDefaults，醒来再处理。
final class BackgroundUploader: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    static let shared = BackgroundUploader()
    static let identifier = "coda.lessonapp.upload"
    static let confirmedKey = "uploadConfirmed", failedKey = "uploadFailed"
    var finishEvents: (() -> Void)?
    var onUpdate: (@Sendable () -> Void)?
    private let lock = NSLock()
    private var bodies: [Int: Data] = [:]
    private var progress: [String: (Int64, Int64)] = [:]   // 拍摄编号 → 已传, 总大小
    private var lastNotify = Date.distantPast
    lazy var session: URLSession = {
        let c = URLSessionConfiguration.background(withIdentifier: Self.identifier)
        c.isDiscretionary = false; c.sessionSendsLaunchEvents = true
        c.timeoutIntervalForResource = 24 * 3600
        return URLSession(configuration: c, delegate: self, delegateQueue: nil)
    }()
    /// 正在传的：拍摄编号 → (已传, 总大小)
    func snapshot() -> [String: (Int64, Int64)] { lock.lock(); defer { lock.unlock() }; return progress }
    /// App 重新打开时，从系统那里找回还在传的任务
    func recover() {
        session.getAllTasks { tasks in
            self.lock.lock()
            for t in tasks where t.state == .running || t.state == .suspended {
                if let id = t.taskDescription?.split(separator: "|").first.map(String.init), self.progress[id] == nil {
                    self.progress[id] = (t.countOfBytesSent, max(t.countOfBytesExpectedToSend, 0))
                }
            }
            self.lock.unlock(); self.notify(force: true)
        }
    }
    func enqueue(_ request: URLRequest, file: URL, captureId: String, checksum: String, size: Int64) {
        lock.lock(); progress[captureId] = (0, size); lock.unlock()
        let task = session.uploadTask(with: request, fromFile: file)
        task.taskDescription = captureId + "|" + checksum
        task.resume(); notify(force: true)
    }
    private func notify(force: Bool = false) {
        lock.lock(); let due = force || Date().timeIntervalSince(lastNotify) > 0.4; if due { lastNotify = Date() }; lock.unlock()
        if due { onUpdate?() }
    }
    // 只认配对时那台 Mac 的证书（App 被系统后台唤醒时模型可能还没建，配对信息直接从存档读）
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge, completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard let data = UserDefaults.standard.data(forKey: "lessonPairedMac"), let p = try? JSONDecoder().decode(Pairing.self, from: data) else { completionHandler(.cancelAuthenticationChallenge, nil); return }
        PinnedSession(p).urlSession(session, didReceive: challenge, completionHandler: completionHandler)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64, totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
        guard let id = task.taskDescription?.split(separator: "|").first.map(String.init) else { return }
        lock.lock(); progress[id] = (totalBytesSent, totalBytesExpectedToSend > 0 ? totalBytesExpectedToSend : (progress[id]?.1 ?? 0)); lock.unlock()
        notify()
    }
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        lock.lock(); bodies[dataTask.taskIdentifier, default: Data()].append(data); lock.unlock()
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        let parts = (task.taskDescription ?? "").split(separator: "|").map(String.init)
        lock.lock(); let body = bodies.removeValue(forKey: task.taskIdentifier) ?? Data(); if parts.count == 2 { progress.removeValue(forKey: parts[0]) }; lock.unlock()
        guard parts.count == 2 else { return }
        let receipt = (try? JSONSerialization.jsonObject(with: body)) as? [String: Any]
        let status = (task.response as? HTTPURLResponse)?.statusCode ?? 0
        let d = UserDefaults.standard
        if error == nil, (200..<300).contains(status), receipt?["sha256"] as? String == parts[1], receipt?["captureId"] as? String == parts[0] {
            d.set((d.stringArray(forKey: Self.confirmedKey) ?? []) + [parts[0]], forKey: Self.confirmedKey)
        } else {
            var failed = d.dictionary(forKey: Self.failedKey) as? [String: String] ?? [:]
            failed[parts[0]] = (receipt?["error"] as? String) ?? (error.map { _ in "连接断了" } ?? "Mac 没确认")
            d.set(failed, forKey: Self.failedKey)
        }
        notify(force: true)
    }
    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        DispatchQueue.main.async { self.finishEvents?(); self.finishEvents = nil }
    }
}
final class LessonAppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, handleEventsForBackgroundURLSession identifier: String, completionHandler: @escaping () -> Void) {
        BackgroundUploader.shared.finishEvents = completionHandler; _ = BackgroundUploader.shared.session
    }
}
/// 1.1 上课拍：App 自己的相机（10-18 用户定）。默认 720p 录像，顶上一键换 1080p / 4K（每次打开都回到 720p）；
/// 中间大红钮＝开始/结束录像，左边小白钮＝拍照；拍完先看一眼，点“重拍”或“保存”。两指捏合＝变焦；点画面对焦，上下滑调亮暗。
struct PreviewFile: Identifiable { let id = UUID(); let url: URL }
@MainActor final class LessonModel: ObservableObject {
    @Published var paired=false
    @Published var showPairScanner=false
    @Published var pairingBusy=false
    @Published var pairingError:String?
    @Published var webIdentity=UUID()
    @Published var status = "正在连接 Mac…"
    @Published var busy = false
    @Published var showSheetScanner = false
    @Published var sheetReviews:[SheetReview] = []
    /// 三页横滑：0 收集（拍签课表、老课表存档）· 1 课表（打开就是这页）· 2 服务（待上传的课堂资料）
    @Published var page = 1
    var showQueue: Bool { get { page==2 } set { page = newValue ? 2 : 1 } }
    enum ScanMode { case sheet, paper }
    var scanMode = ScanMode.sheet
    @Published var showCloudFolder = false
    @Published var captures: [ClassCapture] = []
    /// 0.6 上传：没勾选＝全部上传；勾了＝只传勾的。进度显示第几个、百分比、MB
    @Published var picked: Set<String> = []
    @Published var uploading: Set<String> = []   // 正在后台传的拍摄编号
    @Published var upTotal = 0
    @Published var upSent: Int64 = 0
    @Published var upSize: Int64 = 0
    var offline = false
    var scheduleReady=false
    let captureRoot = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].appendingPathComponent("ClassCaptures",isDirectory:true)
    @Published var noteText=""
    @Published var typingNote=false
    @Published var recordingNote=false
    @Published var startingNote=false
    let recordingHaptic=UIImpactFeedbackGenerator(style:.light)
    @Published var cancellingNote=false
    @Published var showNoteTargets=false
    @Published var noteTargetLabel="按当前时间匹配学生"
    var noteChoices:[NoteTarget]=[]
    /// 0.4：点过谁，随记就记给谁（3 小时内有效）
    var pinnedStudents:[CaptureStudent]?
    var pinnedAt=Date.distantPast
    var pinLessonKey=""
    @Published var focusNote=false
    @Published var renaming:ClassCapture?
    var chosenNoteStudents:[CaptureStudent]=[]
    var chosenNoteAt=Date.distantPast
    var chosenNoteContext=""
    var pendingNoteContext=""
    var noteRecorder:AVAudioRecorder?
    var noteHolding=false
    var noteStarted=Date()
    var noteAudioURL:URL?
    @Published var preview: PreviewFile?
    @Published var error: String?
    var pairing: Pairing
    var pin: PinnedSession
    var session: URLSession
    var web: WKWebView?
    var currentHost: String
    var attemptedFallback = false
    var connectionTask: Task<Void,Never>?
    var connectionWatchdog: Task<Void,Never>?
    @Published var isOnline=false
    @Published var connecting=false
    @Published var lastFailure=""
    var retryTask: Task<Void,Never>?
    var heartbeat: Task<Void,Never>?
    var retryCount=0
    init() {
        let saved=UserDefaults.standard.data(forKey:"lessonPairedMac").flatMap{try? JSONDecoder().decode(Pairing.self,from:$0)}
        pairing=saved ?? Pairing(host:"unpaired.invalid",fallbackHost:nil,port:18766,token:"",fingerprint:"")
        paired=saved != nil
        currentHost = Self.pickHost(pairing)
        try? FileManager.default.createDirectory(at:captureRoot,withIntermediateDirectories:true)
        if let data=try? Data(contentsOf:captureRoot.appendingPathComponent("queue.json")),let items=try? JSONDecoder().decode([ClassCapture].self,from:data){captures=items}
        pin = PinnedSession(pairing)
        session = URLSession(configuration: Self.makeConfig(), delegate: pin, delegateQueue: nil)
        BackgroundUploader.shared.onUpdate={[weak self] in Task{@MainActor in self?.syncUploads()}}
        BackgroundUploader.shared.recover()
    }
    /// 直连配置：不使用系统代理，局域网请求不会被 VPN/代理软件接管。
    static func makeConfig() -> URLSessionConfiguration {
        let config = URLSessionConfiguration.ephemeral
        config.connectionProxyDictionary = [:]
        config.timeoutIntervalForRequest = 180; config.timeoutIntervalForResource = 1800
        return config
    }
    /// 优先用上次连成功的地址；没有就先用 IP（不经过名字解析，VPN 的假 DNS 干扰不到）。
    static func pickHost(_ p: Pairing) -> String {
        let good = UserDefaults.standard.string(forKey: "lessonLastGoodHost") ?? ""
        return [p.host, p.fallbackHost].compactMap { $0 }.contains(good) ? good : (p.fallbackHost ?? p.host)
    }
    var liveLoaded = false
    var baseURL: URL { URL(string: "https://\(currentHost):\(pairing.port)")! }
    @discardableResult func showOfflineSchedule()->Bool {
        guard let cached=try? String(contentsOf:captureRoot.appendingPathComponent("schedule.html"),encoding:.utf8),!cached.isEmpty else{return false}
        scheduleReady=false;web?.scrollView.refreshControl?.isEnabled=false
        offline=true;liveLoaded=false
        web?.loadHTMLString(cached,baseURL:nil)
        status="离线课表 · 资料先存手机，连接 Mac 后上传"
        return true
    }
    func load(quiet:Bool=false) {
        guard paired,web != nil else { return }
        connectionTask?.cancel(); connectionWatchdog?.cancel()
        if !quiet { _ = showOfflineSchedule() }
        connecting=true
        status = "正在连接 Mac…"
        print("Lesson connect starting")
        connectionTask = Task { [weak self] in
            guard let self else { return }
            do {
                var probe = self.request("/state"); probe.httpMethod = "POST"; probe.httpBody = Data("{}".utf8); probe.timeoutInterval = 6
                probe.setValue("application/json",forHTTPHeaderField:"Content-Type")
                let (data,response) = try await self.session.data(for:probe)
                try Task.checkCancellation(); try self.checked(data,response)
                self.learnAddress(data)
                print("Lesson shared ledger reachable")
                self.status = "已连接 Mac，正在读取课表…"
                var pageRequest = self.request("/"); pageRequest.timeoutInterval = 12
                let (html,pageResponse) = try await self.session.data(for:pageRequest)
                try Task.checkCancellation(); try self.checked(html,pageResponse)
                guard let text = String(data:html,encoding:.utf8), text.contains("renderPhoneSchedule") else { throw NSError(domain:"Lesson",code:6,userInfo:[NSLocalizedDescriptionKey:"Mac 没有返回可用课表"]) }
                try? text.write(to:self.captureRoot.appendingPathComponent("schedule.html"),atomically:true,encoding:.utf8)
                self.scheduleReady=false;self.web?.scrollView.refreshControl?.isEnabled=false;self.offline=false;self.liveLoaded=true
                self.web?.loadHTMLString(text,baseURL:nil)
                self.status = "已连接 Mac · 课程表"; self.connected()
            } catch {
                if !Task.isCancelled {self.failed(error)}
            }
        }
    }
    func failed(_ error: Error) {
        connectionWatchdog?.cancel()
        print("Lesson connection failed: \(error.localizedDescription)")
        let other = currentHost == pairing.host ? pairing.fallbackHost : pairing.host
        if !attemptedFallback, let host = other, host != currentHost {
            attemptedFallback = true; currentHost = host; load(quiet:true); return
        }
        isOnline=false; connecting=false
        lastFailure=Self.explain(error)+"（代码 \((error as NSError).code)）"
        let cached = offline || showOfflineSchedule()
        status = cached ? "离线课表 · 资料先存手机，连接 Mac 后上传" : "无法连接 Mac：\(lastFailure)"
        scheduleRetry()
    }
    static func explain(_ error: Error) -> String {
        let e = error as NSError
        if e.domain == "LessonHTTP" { return e.code == 401 ? "这台手机的配对已失效，请点“重新配对”" : e.localizedDescription }
        guard e.domain == NSURLErrorDomain else { return e.localizedDescription }
        switch e.code {
        case NSURLErrorTimedOut: return "Mac 没有回应：可能在睡眠、没启动“课程管理”、不在同一 Wi-Fi，或手机/Mac 上的代理（如 Shadowrocket）拦截了局域网。可先关闭代理再点“重试”"
        case NSURLErrorCannotFindHost, NSURLErrorDNSLookupFailed: return "找不到 Mac：请确认在同一 Wi-Fi、已允许本地网络，并关闭会接管 DNS 的代理（如 Shadowrocket）"
        case NSURLErrorCannotConnectToHost, NSURLErrorNetworkConnectionLost: return "连不上 Mac 的课程管理：请在 Mac 双击“启动课程管理”"
        case NSURLErrorNotConnectedToInternet: return "iPhone 当前没有网络连接"
        case NSURLErrorCancelled, NSURLErrorSecureConnectionFailed, NSURLErrorServerCertificateUntrusted, NSURLErrorClientCertificateRejected: return "安全连接失败：Mac 的证书和配对时不一致，或这个地址上不是你的 Mac（换了网络？），请点“重新配对”"
        default: return e.localizedDescription
        }
    }
    func connected() {
        isOnline=true; connecting=false; lastFailure=""; retryCount=0; retryTask?.cancel()
        UserDefaults.standard.set(currentHost,forKey:"lessonLastGoodHost")
        heartbeat?.cancel()
        heartbeat = Task { [weak self] in
            var misses=0
            while !Task.isCancelled {
                try? await Task.sleep(for:.seconds(20))
                guard !Task.isCancelled, let self, self.isOnline else { return }
                if await self.reachable() { misses=0 } else { misses+=1; if misses>=2 { self.dropped(); return } }
            }
        }
    }
    func reachable() async -> Bool {
        var probe = request("/state"); probe.httpMethod = "POST"; probe.httpBody = Data("{}".utf8); probe.timeoutInterval = 6
        probe.setValue("application/json",forHTTPHeaderField:"Content-Type")
        guard let (data,response) = try? await session.data(for:probe), (try? checked(data,response)) != nil else { return false }
        return true
    }
    func dropped() {
        isOnline=false; lastFailure=Self.explain(URLError(.timedOut)); status="连接已断开，正在重试…"
        scheduleRetry()
    }
    func scheduleRetry() {
        retryTask?.cancel(); heartbeat?.cancel()
        guard paired else { return }
        let delay=[5,10,20,30][min(retryCount,3)]; retryCount+=1
        retryTask = Task { [weak self] in
            try? await Task.sleep(for:.seconds(delay))
            guard !Task.isCancelled, let self, !self.isOnline, self.paired else { return }
            self.reconnect(quiet:true)
        }
    }
    func reconnect(quiet:Bool=false) {
        retryTask?.cancel(); attemptedFallback=false
        currentHost = Self.pickHost(pairing)
        load(quiet:quiet)
    }
    func appBecameActive() {
        syncUploads()
        guard paired, web != nil else { return }
        if isOnline { Task { if !(await reachable()) { dropped() } } }
        else if !connecting { retryCount=0; reconnect(quiet:true) }
    }
    /// Mac 会在 /state 里报告自己当前的局域网 IP；手机据此更新备用地址，路由器重新分配 IP 后仍能连上。
    func learnAddress(_ data: Data) {
        guard let ip=(try? JSONSerialization.jsonObject(with:data) as? [String:Any])?["lanIP"] as? String,
              ip != pairing.fallbackHost, ip.split(separator:".").count == 4, ip.allSatisfy({$0.isNumber || $0=="."}) else { return }
        let updated=Pairing(serverId:pairing.serverId,role:pairing.role,host:pairing.host,fallbackHost:ip,port:pairing.port,token:pairing.token,fingerprint:pairing.fingerprint)
        guard let stored=try? JSONEncoder().encode(updated) else { return }
        UserDefaults.standard.set(stored,forKey:"lessonPairedMac")
        pairing=updated; pin=PinnedSession(updated)
        let config=Self.makeConfig()
        session.finishTasksAndInvalidate(); session=URLSession(configuration:config,delegate:pin,delegateQueue:nil)
    }
    func request(_ path: String) -> URLRequest {
        var r = URLRequest(url: URL(string:path,relativeTo:baseURL)!.absoluteURL)
        r.setValue("Bearer \(pairing.token)", forHTTPHeaderField:"Authorization")
        return r
    }
    func checked(_ data: Data, _ response: URLResponse) throws {
        guard let http=response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let obj = try? JSONSerialization.jsonObject(with:data) as? [String:Any]
            let status=(response as? HTTPURLResponse)?.statusCode
            throw NSError(domain:status != nil ? "LessonHTTP":"Lesson", code:status ?? 1, userInfo:[NSLocalizedDescriptionKey:obj?["error"] as? String ?? "连接失败，请重试"])
        }
    }
    /// 签课表：系统文档扫描拍下的每一页传到 Mac 识别，识别结果在手机上弹出核对单，确认后入账。
    func uploadSheets(_ pages: [UIImage]) async {
        guard !pages.isEmpty else { return }
        if busy { error="手机正在忙（\(status)），等它好了再拍签课表。";return }
        busy=true; defer { busy=false; status="已连接 Mac · 课程表" }
        var found:[SheetReview]=[], skipped=0, archived=0, failed:[String]=[]
        let stamp=Int(Date().timeIntervalSince1970)
        for (i,page) in pages.enumerated() {
            status="正在识别签课表 \(i+1)/\(pages.count)…"
            guard let jpeg=page.jpegData(compressionQuality:0.85) else { failed.append("第 \(i+1) 页无法保存"); continue }
            var r=request("/mobile/sheet"); r.httpMethod="POST"; r.timeoutInterval=240
            r.setValue("image/jpeg",forHTTPHeaderField:"Content-Type")
            r.setValue("手机拍照_\(stamp)_\(i+1).jpg".addingPercentEncoding(withAllowedCharacters:.urlPathAllowed),forHTTPHeaderField:"X-Filename")
            do {
                let (data,response)=try await session.upload(for:r,from:jpeg); try checked(data,response)
                let obj=(try? JSONSerialization.jsonObject(with:data) as? [String:Any]) ?? [:]
                skipped += obj["skipped"] as? Int ?? 0; archived += obj["archived"] as? Int ?? 0
                for sheet in obj["sheets"] as? [[String:Any]] ?? [] { if let review=SheetReview(sheet), !found.contains(where:{$0.id==review.id}) { found.append(review) } }
            } catch { failed.append("第 \(i+1) 页：\(error.localizedDescription)") }
        }
        var notes:[String]=[]
        if archived>0 { notes.append("\(archived) 张不是签课表（比如以前的老课表），已放进 Mac 课时管理的“待归档”，到时在 Mac 上选学生归档。如果其实是签课表，请把四个黑角都拍进去重拍。") }
        if skipped>0 { notes.append("有 \(skipped) 页没认出签课表。") }
        if !failed.isEmpty { notes.append("没成功的：\n"+failed.joined(separator:"\n")) }
        if found.isEmpty && notes.isEmpty { notes.append("没有识别出签课表。") }
        if skipped>0 || !failed.isEmpty || found.isEmpty && archived==0 {
            notes.append("怎么办：\n① 纸放平（压一压别让它弯）、正对着拍、光线均匀，四个黑角都拍进去，再点「拍签课表」重拍；\n② 还不行：用扫描仪扫一下，在 Mac 的课时管理点「导入签字扫描件」；\n③ 照片已经存在 Mac 的“已签扫描件”里，在 Mac 上点「导入签字扫描件」选它也能再试；\n④ 实在认不出：在课表上按住学生名字，直接记上课 / 请假。")
        }
        if !notes.isEmpty { error=notes.joined(separator:"\n\n") }
        sheetReviews=found
    }
    func startScan(_ mode: ScanMode) {
        guard isOnline else { error="请先连上 Mac 再拍（拍完要马上传到 Mac）"; return }
        guard VNDocumentCameraViewController.isSupported else { error="这台设备不支持文档扫描"; return }
        scanMode=mode; showSheetScanner=true
    }
    /// 老课表存档：每页直接传到 Mac 的“待归档”，不做识别。
    func uploadPapers(_ pages: [UIImage]) async {
        guard !pages.isEmpty else { return }
        if busy { error="手机正在忙（\(status)），等它好了再拍老课表。";return }
        busy=true; defer { busy=false; status="已连接 Mac · 课程表" }
        var sent=0, failed:[String]=[]
        let stamp=Int(Date().timeIntervalSince1970)
        for (i,page) in pages.enumerated() {
            status="正在上传老课表 \(i+1)/\(pages.count)…"
            guard let jpeg=page.jpegData(compressionQuality:0.85) else { failed.append("第 \(i+1) 张无法保存"); continue }
            var r=request("/mobile/paper"); r.httpMethod="POST"; r.timeoutInterval=120
            r.setValue("image/jpeg",forHTTPHeaderField:"Content-Type")
            r.setValue("老课表_\(stamp)_\(i+1).jpg".addingPercentEncoding(withAllowedCharacters:.urlPathAllowed),forHTTPHeaderField:"X-Filename")
            do { let (data,response)=try await session.upload(for:r,from:jpeg); try checked(data,response); sent+=1 }
            catch { failed.append("第 \(i+1) 张：\(error.localizedDescription)") }
        }
        var lines:[String]=[]
        if sent>0 { lines.append("已传 \(sent) 张到 Mac。到 Mac 的课时管理点“待归档”，一张张选是谁的。") }
        if !failed.isEmpty { lines.append("没成功的：\n"+failed.joined(separator:"\n")) }
        error=lines.joined(separator:"\n\n")
    }
    func commitSheet(_ review: SheetReview) async {
        busy=true; defer { busy=false }
        var r=request("/mobile/sheet/commit"); r.httpMethod="POST"; r.setValue("application/json",forHTTPHeaderField:"Content-Type")
        var decisions:[String:String]=[:]; for row in review.rows where !row.booked { decisions[row.id]=row.status }
        r.httpBody=try? JSONSerialization.data(withJSONObject:["reviewId":review.id,"decisions":decisions])
        do {
            let (data,response)=try await session.data(for:r); try checked(data,response)
            let obj=(try? JSONSerialization.jsonObject(with:data) as? [String:Any]) ?? [:]
            let saved=obj["saved"] as? Int ?? 0, skipped=obj["skipped"] as? Int ?? 0, pending=obj["pending"] as? Int ?? 0
            sheetReviews.removeAll{$0.id==review.id}
            status="已入账 \(saved) 条"+(skipped>0 ? "，\(skipped) 条以前入过" : "")+(pending>0 ? "，\(pending) 条待确认留在 Mac 的“待核对”" : "")
            error=status
        } catch { self.error="入账没有成功：\(error.localizedDescription)" }
    }
    /// 课表上按住学生名字后的操作：标请假 / 取消（只是标记，签课表核对时参考），或记“上课了”（直接扣课时；编号和签课表那行一样，纸上再签也不会重复扣）。成功后重新读一次课表。
    func setLeave(week:String,course:String,student:String,on:Bool,attend:Bool=false,units:Int=1) async {
        var r=request(attend ? "/mobile/attend" : "/mobile/leave"); r.httpMethod="POST"; r.setValue("application/json",forHTTPHeaderField:"Content-Type")
        r.httpBody=try? JSONSerialization.data(withJSONObject:["week":week,"course":course,"student":student,"on":on])
        do {
            let (data,response)=try await session.data(for:r); try checked(data,response)
            status=attend ? "已记 \(student) 上课，扣 \(units) 节" : on ? "已标 \(student) 请假" : "已取消 \(student) 的请假"
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            reconnect(quiet:true)
        } catch { self.error=(attend ? "上课没记上：" : "请假没标上：")+error.localizedDescription }
    }
    /// 全班上课了：一个个交（和按住名字记上课一样，重复的 Mac 会挡住），全交完再刷新一次课表。
    func attendAll(week:String,course:String,students:[String],units:Int) async {
        var done:[String]=[],failed:[String]=[]
        for student in students {
            var r=request("/mobile/attend"); r.httpMethod="POST"; r.setValue("application/json",forHTTPHeaderField:"Content-Type")
            r.httpBody=try? JSONSerialization.data(withJSONObject:["week":week,"course":course,"student":student,"on":true])
            do { let (data,response)=try await session.data(for:r); try checked(data,response); done.append(student) }
            catch { failed.append(student+"（"+error.localizedDescription+"）") }
        }
        if !done.isEmpty { status="已记上课：\(done.joined(separator:"、"))，各扣 \(units) 节"; UINotificationFeedbackGenerator().notificationOccurred(.success); reconnect(quiet:true) }
        if !failed.isEmpty { self.error="这几位没记上："+failed.joined(separator:"；") }
    }
        func openDocument(path: String) async {
        guard let url=URL(string:path,relativeTo:baseURL)?.absoluteURL, url.host==currentHost else { return }
        busy=true;status="正在读取文件…";defer {busy=false}
        do {
            let (file,response)=try await session.download(for:request(url.absoluteString))
            guard let http=response as? HTTPURLResponse,(200..<300).contains(http.statusCode) else { throw NSError(domain:"Lesson",code:2,userInfo:[NSLocalizedDescriptionKey:"文件读取失败"]) }
            let suffix=UTType(mimeType:response.mimeType ?? "")?.preferredFilenameExtension ?? "pdf"
            let name=(http.value(forHTTPHeaderField:"X-Filename")?.removingPercentEncoding).map { URL(fileURLWithPath:$0).lastPathComponent } ?? "课时资料.\(suffix)"
            let destination=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString,isDirectory:true)
            try FileManager.default.createDirectory(at:destination,withIntermediateDirectories:true)
            let local=destination.appendingPathComponent(name);try FileManager.default.moveItem(at:file,to:local)
            preview=PreviewFile(url:local);status="已连接 Mac · 课程表"
        } catch { self.error=error.localizedDescription }
    }
}
@main struct LessonApp: App {
    @UIApplicationDelegateAdaptor(LessonAppDelegate.self) private var appDelegate
    @StateObject private var model=LessonModel()
    @Environment(\.scenePhase) private var phase
    var body: some Scene { WindowGroup {
        TabView(selection:$model.page) {
            CollectPage(model:model).tag(0)
            VStack(spacing:0){if model.paired {ConnectionBar(model:model);LessonWeb(model:model).id(model.webIdentity);NoteComposer(model:model)}else{Spacer();Text("尚未连接 Mac").font(.title2);Text("连接一次后，课表会保存在手机，离线也能查看").foregroundStyle(.secondary).padding();Button("连接 Mac"){model.showPairScanner=true}.buttonStyle(.borderedProminent);Spacer()}}.tag(1)
            CaptureQueue(model:model).tag(2)
        }.tabViewStyle(.page(indexDisplayMode:.never))
          .onChange(of:phase){_,new in if new == .active {model.appBecameActive()}}
          .task{
              #if DEBUG
              // 开发时预览核对单：模拟器启动参数 -sheetDemo <识别结果 JSON 路径>；模拟器没有摄像头，配对用 -pairCode <二维码里的文字>
              let args=ProcessInfo.processInfo.arguments
              if let i=args.firstIndex(of:"-pairCode"),i+1<args.count { await model.acceptPairCode(args[i+1]) }
              if let i=args.firstIndex(of:"-sheetDemo"),i+1<args.count,let data=try? Data(contentsOf:URL(fileURLWithPath:args[i+1])),
                 let obj=try? JSONSerialization.jsonObject(with:data) as? [String:Any] { model.sheetReviews=(obj["sheets"] as? [[String:Any]] ?? []).compactMap{SheetReview($0)} }
              #endif
          }
          .sheet(isPresented:$model.showPairScanner){PairScannerSheet(model:model)}
          .sheet(isPresented:$model.showNoteTargets){NoteTargetPicker(model:model)}
          .sheet(item:Binding(get:{model.sheetReviews.first},set:{if $0==nil,!model.sheetReviews.isEmpty {model.sheetReviews.removeFirst()}})){review in SheetReviewView(model:model,review:review).interactiveDismissDisabled()}
          .fullScreenCover(isPresented:$model.showSheetScanner){SheetScanner{pages,failure in model.showSheetScanner=false;Task{ try? await Task.sleep(nanoseconds:700_000_000)   // 10-21：等扫描画面关好，提示才弹得出来
            if let failure { model.error="扫描没有完成：\(failure)\n\n请再点一次「\(model.scanMode == .paper ? "老课表存档" : "拍签课表")」重拍。";return }
            if pages.isEmpty { return }   // 自己点了取消
            if model.scanMode == .paper { await model.uploadPapers(pages) } else { await model.uploadSheets(pages) } }}.ignoresSafeArea()}
          .sheet(item:$model.preview){file in FilePreviewSheet(url:file.url){model.preview=nil}}
          .overlay{ if model.busy && (model.status.hasPrefix("正在识别") || model.status.hasPrefix("正在上传老课表")) {   // 10-21：识别要十几秒，整屏写出来，不像卡住
              ZStack{Color.black.opacity(0.55).ignoresSafeArea();VStack(spacing:14){ProgressView().controlSize(.large).tint(.white);Text(model.status).font(.headline).foregroundStyle(.white);Text("照片正在传到 Mac 识别，别切走").font(.footnote).foregroundStyle(.white.opacity(0.8))}.padding(28).background(.ultraThinMaterial,in:RoundedRectangle(cornerRadius:18))} } }
          .alert("提示",isPresented:Binding(get:{model.error != nil && model.page != 2},set:{if !$0 {model.error=nil}})){Button("好"){model.error=nil}} message:{Text(model.error ?? "")}   // 10-27：待上传页自己也有一个提示框，两个同时弹会互相顶掉（提示“跳一下就消失”），所以按当前页只让一个弹

    } }
}

struct SheetScanner:UIViewControllerRepresentable {
    let done:([UIImage],String?)->Void   // 第二个：失败原因（取消时是 nil）
    func makeCoordinator()->Coordinator {Coordinator(done)}
    func makeUIViewController(context:Context)->VNDocumentCameraViewController {let c=VNDocumentCameraViewController();c.delegate=context.coordinator;return c}
    func updateUIViewController(_ c:VNDocumentCameraViewController,context:Context){}
    final class Coordinator:NSObject,VNDocumentCameraViewControllerDelegate {
        let done:([UIImage],String?)->Void
        init(_ done:@escaping([UIImage],String?)->Void){self.done=done}
        func documentCameraViewController(_ c:VNDocumentCameraViewController,didFinishWith scan:VNDocumentCameraScan){done((0..<scan.pageCount).map{scan.imageOfPage(at:$0)},nil)}
        func documentCameraViewControllerDidCancel(_ c:VNDocumentCameraViewController){done([],nil)}
        func documentCameraViewController(_ c:VNDocumentCameraViewController,didFailWithError error:Error){done([],error.localizedDescription)}
    }
}
/// 左页：收集。每周的签课表，以及刚开始用时整理以前的老课表。
struct CollectPage:View {
    @ObservedObject var model:LessonModel
    var body:some View {
        NavigationStack {
            List {
                Section {
                    Button { model.startScan(.sheet) } label: { Label("拍签课表",systemImage:"doc.viewfinder").font(.title3.weight(.semibold)).padding(.vertical,10) }
                } footer: { Text("学生签好的每周签课表。可以连拍几页，拍完马上识别，在手机上核对后入账。四个黑角都要拍进去。") }
                Section {
                    Button { model.startScan(.paper) } label: { Label("老课表存档",systemImage:"archivebox").font(.title3.weight(.semibold)).padding(.vertical,10) }
                } footer: { Text("以前一人一张的纸质课表。拍完传到 Mac 的“待归档”，在 Mac 的课时管理里看图选是谁的；以后在学生的课时单里能复制发给家长。") }
                if model.busy { Section { HStack { ProgressView(); Text(model.status).font(.footnote) } } }
                if !model.isOnline { Section { Text("现在没连上 Mac，连上后才能拍（拍完要马上传过去）。").font(.footnote).foregroundStyle(.secondary) } }
            }
            .navigationTitle("收集").navigationBarTitleDisplayMode(.inline)
            .toolbar{ToolbarItem(placement:.topBarTrailing){Button("课表"){model.page=1}}}
        }
    }
}
struct SheetRow:Identifiable {
    let id,date,day,time,name,reason:String; let units:Int; var status:String; let image:UIImage?; let leaveImage:UIImage?; let booked:Bool
}
struct SheetReview:Identifiable {
    let id,week:String; var rows:[SheetRow]
    init?(_ o:[String:Any]) {
        guard let id=o["reviewId"] as? String, let rows=o["rows"] as? [[String:Any]] else { return nil }
        self.id=id; week=o["week"] as? String ?? ""
        self.rows=rows.map { r in
            let encoded=(r["image"] as? String ?? "").components(separatedBy:",").last ?? ""
            let leave=(r["leaveImage"] as? String ?? "").components(separatedBy:",").last ?? ""
            return SheetRow(id:r["id"] as? String ?? "",date:r["date"] as? String ?? "",day:r["day"] as? String ?? "",time:r["time"] as? String ?? "",name:r["name"] as? String ?? "",
                            reason:r["reason"] as? String ?? "",units:r["units"] as? Int ?? 1,status:r["status"] as? String ?? "待确认",
                            image:Data(base64Encoded:encoded).flatMap{UIImage(data:$0)},leaveImage:Data(base64Encoded:leave).flatMap{UIImage(data:$0)},booked:r["booked"] as? Bool ?? false)
        }
    }
}
/// 手机上的签课表核对单：样子像课表，按天分组；每行 时间、名字、签字截图、上课（扣几节）/请假/待确认，点一下可以改。
struct SheetReviewView:View {
    @ObservedObject var model:LessonModel
    @State var review:SheetReview
    var days:[String] { Array(Set(review.rows.map{$0.date})).sorted() }
    func count(_ s:String)->Int { review.rows.filter{!$0.booked && $0.status==s}.count }  // 停课的行不计入
    var title:String {
        let f=DateFormatter(); f.dateFormat="yyyy-MM-dd"
        guard let d=f.date(from:review.week), let end=Calendar.current.date(byAdding:.day,value:6,to:d) else { return "签课表" }
        f.dateFormat="M/d"; return "\(f.string(from:d))–\(f.string(from:end)) 签课表"
    }
    var body:some View {
        NavigationStack {
            List {
                ForEach(days,id:\.self) { day in
                    Section(header:Text(day.dropFirst(5).replacingOccurrences(of:"-",with:"/")+" "+(review.rows.first{$0.date==day}?.day ?? "")).font(.headline)) {
                        ForEach(review.rows.indices.filter{review.rows[$0].date==day}.sorted{review.rows[$0].time<review.rows[$1].time},id:\.self) { i in row(i) }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement:.cancellationAction) { Button("稍后"){ model.sheetReviews.removeAll{$0.id==review.id} } } }
            .safeAreaInset(edge:.bottom) {
                VStack(spacing:6) {
                    Text("上课 \(count("上课")) · 请假 \(count("请假")) · 待确认 \(count("待确认"))").font(.footnote).foregroundStyle(.secondary)
                    Button { Task{ await model.commitSheet(review) } } label: { Text(model.busy ? "正在入账…" : "确认入账").frame(maxWidth:.infinity).padding(.vertical,6) }
                        .buttonStyle(.borderedProminent).disabled(model.busy || count("上课")+count("请假")==0)
                    Text("“待确认”的这次不入账，以后在 Mac 的“待核对”里补").font(.caption2).foregroundStyle(.secondary)
                }.padding(.horizontal).padding(.vertical,8).background(.bar)
            }
        }
    }
    @ViewBuilder func row(_ i:Int)->some View {
        let r=review.rows[i]
        HStack(spacing:10) {
            VStack(alignment:.leading,spacing:2) {
                Text(r.time).font(.caption).foregroundStyle(.secondary)
                Text(r.name).font(.body.weight(.semibold))
            }.frame(width:96,alignment:.leading)
            if let img=r.image { Image(uiImage:img).resizable().scaledToFit().frame(maxWidth:.infinity,maxHeight:40).background(Color.white).clipShape(RoundedRectangle(cornerRadius:4)) } else { Spacer() }
            if let box=r.leaveImage { Image(uiImage:box).resizable().interpolation(.none).scaledToFit().frame(width:30,height:30).background(Color.white).clipShape(RoundedRectangle(cornerRadius:4)) }
            if r.booked || r.status=="停课" { Text(r.booked ? "已入账" : "停课").font(.caption).foregroundStyle(.secondary).frame(width:84) }
            else {
                Menu {
                    Button("上课 · 扣 \(r.units) 节"){ review.rows[i].status="上课" }
                    Button("请假"){ review.rows[i].status="请假" }
                    Button("待确认"){ review.rows[i].status="待确认" }
                } label: {
                    Text(r.status=="上课" ? "上课 扣\(r.units)" : r.status).font(.callout.weight(.semibold)).frame(width:84).padding(.vertical,6)
                        .background((r.status=="上课" ? Color.blue : r.status=="请假" ? Color.orange : Color.red).opacity(0.14),in:Capsule())
                        .foregroundStyle(r.status=="上课" ? Color.blue : r.status=="请假" ? Color.orange : Color.red)
                }
            }
        }.padding(.vertical,2)
    }
}
struct ConnectionBar: View {
    @ObservedObject var model:LessonModel
    var body: some View {
        if !model.isOnline {
            VStack(alignment:.leading,spacing:6) {
                HStack(spacing:8) {
                    if model.connecting { ProgressView().controlSize(.small) }
                    Text(model.connecting ? "正在连接 Mac…" : "未连接 Mac · 显示离线课表").font(.footnote.bold())
                    Spacer()
                    Button("重试"){model.retryCount=0;model.reconnect(quiet:true)}.buttonStyle(.bordered).controlSize(.small).disabled(model.connecting)
                    Button("重新配对"){model.showPairScanner=true}.buttonStyle(.bordered).controlSize(.small)
                }
                if !model.connecting && !model.lastFailure.isEmpty { Text(model.lastFailure).font(.caption).foregroundStyle(.secondary) }
            }.padding(.horizontal,12).padding(.vertical,8).frame(maxWidth:.infinity,alignment:.leading).background(Color.orange.opacity(0.15))
        }
    }
}
struct LessonWeb: UIViewRepresentable {
    @ObservedObject var model:LessonModel
    func makeCoordinator()->Coordinator {Coordinator(model)}
    func makeUIView(context:Context)->WKWebView {
        let config=WKWebViewConfiguration();config.websiteDataStore = .nonPersistent();config.allowsInlineMediaPlayback=true
        config.userContentController.add(context.coordinator,name:"lessonNative")
        let storedTeacher=UserDefaults.standard.string(forKey:"lessonTeacher") ?? ""
        let safeTeacher=["all","red","blue"].contains(storedTeacher) ? storedTeacher : ""
        config.userContentController.addUserScript(WKUserScript(source:"window.__lessonMobile=true;window.__lessonTeacher='\(safeTeacher)';",injectionTime:.atDocumentStart,forMainFrameOnly:true))
        let pullScript="""
        let nativePullStart=null;
        document.addEventListener('touchstart',e=>{nativePullStart=e.touches.length===1?{x:e.touches[0].clientX,y:e.touches[0].clientY,top:scrollY<=0}:null},true);
        document.addEventListener('touchend',e=>{const p=nativePullStart,t=e.changedTouches[0];nativePullStart=null;if(p&&t&&p.top&&t.clientY-p.y>30&&Math.abs(t.clientX-p.x)<60)e.stopImmediatePropagation()},true);
        """
        config.userContentController.addUserScript(WKUserScript(source:pullScript,injectionTime:.atDocumentStart,forMainFrameOnly:true))
        let web=WKWebView(frame:.zero,configuration:config);web.navigationDelegate=context.coordinator;web.uiDelegate=context.coordinator;web.isInspectable=true
        let pull=UIRefreshControl();pull.attributedTitle=NSAttributedString(string:"下拉切换老师")
        pull.addTarget(context.coordinator,action:#selector(Coordinator.switchTeacher(_:)),for:.valueChanged)
        web.scrollView.refreshControl=pull;web.scrollView.alwaysBounceVertical=true
        web.scrollView.panGestureRecognizer.addTarget(context.coordinator,action:#selector(Coordinator.trackPull(_:)))
        model.web=web;model.load();return web
    }
    func updateUIView(_ uiView:WKWebView,context:Context){}
    @MainActor final class Coordinator:NSObject,WKNavigationDelegate,WKUIDelegate,WKScriptMessageHandler,UIGestureRecognizerDelegate {
        let model:LessonModel
        init(_ model:LessonModel){self.model=model}
        var pullReady=false
        var switchingTeacher=false
        @objc func trackPull(_ gesture:UIPanGestureRecognizer){
            guard let scroll=model.web?.scrollView,let pull=scroll.refreshControl,!pull.isRefreshing else{return}
            if gesture.state == .ended {if pullReady {switchTeacher(pull)};pullReady=false;return}
            if gesture.state == .cancelled {pullReady=false;return}
            let distance = -(scroll.contentOffset.y+scroll.adjustedContentInset.top)
            let next=UserDefaults.standard.string(forKey:"lessonTeacher")=="blue" ? "红老师":"蓝老师"
            let ready=distance>100
            pull.attributedTitle=NSAttributedString(string:ready ? "松开切换到"+next:"继续下拉切换到"+next)
            if ready && !pullReady {UISelectionFeedbackGenerator().selectionChanged()};pullReady=ready
        }
        @objc func switchTeacher(_ pull:UIRefreshControl){
            guard model.scheduleReady,!switchingTeacher else{pull.endRefreshing();return};switchingTeacher=true
            let next=UserDefaults.standard.string(forKey:"lessonTeacher")=="blue" ? "red":"blue"
            let script="if(typeof setPhoneFilter==='function'){setPhoneFilter('"+next+"')}else if(typeof change==='function'){change('"+next+"')}else{throw new Error('Schedule not ready')}"
            model.web?.evaluateJavaScript(script){[weak self] _,error in
                pull.endRefreshing();self?.pullReady=false
                DispatchQueue.main.asyncAfter(deadline:.now()+0.5){self?.switchingTeacher=false}
                if error != nil {self?.model.error="课表尚未加载，请稍后再下拉"}
                else {UserDefaults.standard.set(next,forKey:"lessonTeacher");UIImpactFeedbackGenerator(style:.light).impactOccurred()}
            }
        }
        @objc func openCaptureQueue(_ gesture:UISwipeGestureRecognizer){guard gesture.state == .ended else{return};model.showQueue=true}
        func gestureRecognizer(_ gestureRecognizer:UIGestureRecognizer,shouldRecognizeSimultaneouslyWith otherGestureRecognizer:UIGestureRecognizer)->Bool{return true}

        func webView(_ webView:WKWebView,didReceive challenge:URLAuthenticationChallenge,completionHandler:@escaping(URLSession.AuthChallengeDisposition,URLCredential?)->Void) {
            if model.pin.accepts(challenge),let trust=challenge.protectionSpace.serverTrust {completionHandler(.useCredential,URLCredential(trust:trust))}else{completionHandler(.cancelAuthenticationChallenge,nil)}
        }
        func webView(_ webView:WKWebView,didFinish navigation:WKNavigation!){
            if model.liveLoaded {model.status="已连接 Mac · 课程表"}
            else if webView.url?.scheme == "https" {model.connectionWatchdog?.cancel();model.status="已连接 Mac · 课程表";model.connected()}
            else {model.status="离线课表 · 资料先存手机，连接 Mac 后上传"}
            webView.evaluateJavaScript("typeof setPhoneFilter==='function'||typeof change==='function'"){[weak self] ready,_ in
                self?.model.scheduleReady=(ready as? Bool)==true
                webView.scrollView.refreshControl?.isEnabled=(ready as? Bool)==true
            }
            print("Lesson page finished")
        }
        func webViewWebContentProcessDidTerminate(_ webView:WKWebView){model.connectionTask?.cancel();model.connectionWatchdog?.cancel();if !model.showOfflineSchedule(){model.load()}}
        func webView(_ webView:WKWebView,didFail navigation:WKNavigation!,withError error:Error){if (error as NSError).code != NSURLErrorCancelled {model.failed(error)}}
        func webView(_ webView:WKWebView,didFailProvisionalNavigation navigation:WKNavigation!,withError error:Error){if (error as NSError).code != NSURLErrorCancelled {model.failed(error)}}
        func webView(_ webView:WKWebView,decidePolicyFor action:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void) {
            guard let url=action.request.url else {decisionHandler(.cancel);return}
            if url.scheme=="file" && model.offline {decisionHandler(.allow);return}
            if url.absoluteString=="about:blank" {decisionHandler(.allow);return}
            guard url.host?.lowercased()==model.currentHost.lowercased(),url.scheme=="https" else {decisionHandler(.cancel);return}
            if ["/sheetfile","/scanfile","/studentdoc"].contains(url.path) {decisionHandler(.cancel);Task{await model.openDocument(path:url.absoluteString)};return}
            decisionHandler(.allow)
        }
        func webView(_ webView:WKWebView,createWebViewWith configuration:WKWebViewConfiguration,for navigationAction:WKNavigationAction,windowFeatures:WKWindowFeatures)->WKWebView? {
            if let url=navigationAction.request.url,url.absoluteString != "about:blank" {Task{await model.openDocument(path:url.absoluteString)}};return nil
        }
        func present(_ controller:UIViewController) {
            guard var top=model.web?.window?.rootViewController else {return}
            while let next=top.presentedViewController {top=next}
            if let pop=controller.popoverPresentationController {pop.sourceView=model.web;pop.sourceRect=CGRect(x:20,y:20,width:1,height:1)}
            top.present(controller,animated:true)
        }
        func webView(_ webView:WKWebView,runJavaScriptAlertPanelWithMessage message:String,initiatedByFrame frame:WKFrameInfo,completionHandler:@escaping()->Void){let a=UIAlertController(title:"提示",message:message,preferredStyle:.alert);a.addAction(UIAlertAction(title:"好",style:.default){_ in completionHandler()});present(a)}
        func webView(_ webView:WKWebView,runJavaScriptConfirmPanelWithMessage message:String,initiatedByFrame frame:WKFrameInfo,completionHandler:@escaping(Bool)->Void){let a=UIAlertController(title:"确认",message:message,preferredStyle:.alert);a.addAction(UIAlertAction(title:"取消",style:.cancel){_ in completionHandler(false)});a.addAction(UIAlertAction(title:"确定",style:.default){_ in completionHandler(true)});present(a)}
        func webView(_ webView:WKWebView,runJavaScriptTextInputPanelWithPrompt prompt:String,defaultText:String?,initiatedByFrame frame:WKFrameInfo,completionHandler:@escaping(String?)->Void){let a=UIAlertController(title:prompt,message:nil,preferredStyle:.alert);a.addTextField{$0.text=defaultText};a.addAction(UIAlertAction(title:"取消",style:.cancel){_ in completionHandler(nil)});a.addAction(UIAlertAction(title:"确定",style:.default){_ in completionHandler(a.textFields?.first?.text)});present(a)}
        func userContentController(_ userContentController:WKUserContentController,didReceive message:WKScriptMessage){
            guard message.frameInfo.isMainFrame,let body=message.body as? [String:Any],let action=body["action"] as? String else{return}
            if action=="noteContext",let context=body["context"],JSONSerialization.isValidJSONObject(context){if let data=try? JSONSerialization.data(withJSONObject:context){try? data.write(to:model.captureRoot.appendingPathComponent("note-context.json"),options:.atomic)};return}
            // 0.4：按住名字拖到底部随记栏＝随记换成这个学生
            if action=="pinNote",let name=body["name"] as? String,let id=body["studentId"] as? String {
                // 拖到底部＝换人并打开键盘打字；按住原地（focus:false）＝只换人，直接按住底部说话
                let focus=body["focus"] as? Bool ?? true
                if focus {UIImpactFeedbackGenerator(style:.light).impactOccurred()}
                model.pinNote(CaptureStudent(id:id,name:name),focus:focus);return
            }
            if action=="captureQueue" {return} // Native pager owns horizontal dragging.
            if action=="refreshSchedule" {model.retryCount=0;model.reconnect();return}
            // 按住学生名字：菜单由 Mac 发来的网页画（和 Mac 上一样，改菜单只要刷新）；App 只负责震一下、把选的操作转给 Mac
            // 1.1 手势：按住 0.4 秒轻震（出菜单）、按到 1.2 秒重震（开始录语音）
            if action=="haptic" {let st=body["style"] as? String;UIImpactFeedbackGenerator(style:st=="heavy" ? .heavy : st=="light" ? .light : .medium).impactOccurred();return}
            // 1.1：一直按住名字＝直接录语音给他（班课里可以带上全班），松手保存
            if action=="voiceStart",let name=body["name"] as? String,let id=body["studentId"] as? String {
                let group=(body["group"] as? [[String:String]] ?? []).compactMap{g in g["name"].map{CaptureStudent(id:g["id"] ?? $0,name:$0)}}
                model.pinNote(CaptureStudent(id:id,name:name),group:group,focus:false);model.beginVoiceNote();return
            }
            if action=="voiceStop" {model.endVoiceNote(cancel:body["cancel"] as? Bool ?? false);return}
            if action=="lessonAction",let kind=body["kind"] as? String,["attend","leave"].contains(kind),let week=body["week"] as? String,let course=body["course"] as? String,let student=body["student"] as? String {
                let on=body["on"] as? Bool ?? true,units=body["units"] as? Int ?? 1
                Task{await model.setLeave(week:week,course:course,student:student,on:on,attend:kind=="attend",units:units)};return
            }
            // 1.3（10-24）：全班上课了
            if action=="attendAll",let week=body["week"] as? String,let course=body["course"] as? String,let students=body["students"] as? [String],!students.isEmpty {
                let units=body["units"] as? Int ?? 1;Task{await model.attendAll(week:week,course:course,students:students,units:units)};return
            }
            if action=="leave",let week=body["week"] as? String,let course=body["course"] as? String,let student=body["student"] as? String {let on=body["on"] as? Bool ?? true;Task{await model.setLeave(week:week,course:course,student:student,on:on)};return}
            if action=="cacheSchedule",let html=body["html"] as? String {model.scheduleReady=true;model.web?.scrollView.refreshControl?.isEnabled=true;try? html.write(to:model.captureRoot.appendingPathComponent("schedule.html"),atomically:true,encoding:.utf8);return}
            if action=="setTeacher",let teacher=body["teacher"] as? String,["all","red","blue"].contains(teacher) {UserDefaults.standard.set(teacher,forKey:"lessonTeacher");return}
            if action=="saveFile",let encoded=body["data"] as? String,let data=Data(base64Encoded:encoded),let filename=body["filename"] as? String {
                do {
                    let directory=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
                    try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
                    let file=directory.appendingPathComponent((filename as NSString).lastPathComponent)
                    try data.write(to:file)
                    present(UIActivityViewController(activityItems:[file],applicationActivities:nil))
                } catch {model.error=error.localizedDescription};return
            }
            if action=="document",let path=body["url"] as? String {Task{await model.openDocument(path:path)}}
            if action=="media",let id=body["id"] as? String {Task{await model.openDocument(path:"/mobile/media?id=\(id)")}}
            if ["copyImage","shareImage"].contains(action),let encoded=body["data"] as? String,let data=Data(base64Encoded:encoded),let image=UIImage(data:data){
                if action=="copyImage" {UIPasteboard.general.image=image;model.status="已复制图片，可到微信粘贴"}
                else{present(UIActivityViewController(activityItems:[image],applicationActivities:nil))}
            }
            if action=="print",let web=model.web {let printController=UIPrintInteractionController.shared;let info=UIPrintInfo(dictionary:nil);info.jobName="课时记录";info.orientation = .portrait;printController.printInfo=info;printController.printFormatter=web.viewPrintFormatter();printController.present(animated:true,completionHandler:nil)}
        }
    }
}
struct FilePreviewSheet:View {
    let url:URL
    let close:()->Void
    private var isPhoto:Bool { ["jpg","jpeg","png","heic","heif"].contains(url.pathExtension.lowercased()) }
    var body:some View {
        VStack(spacing:0){
            HStack{Text("资料预览").font(.headline);Spacer();Button("关闭",action:close).buttonStyle(.bordered)}.padding()
            Divider()
            if isPhoto,let image=UIImage(contentsOfFile:url.path){
                Image(uiImage:image).resizable().scaledToFit().frame(maxWidth:.infinity,maxHeight:.infinity).padding(12).contentShape(Rectangle())
            }else{
                DocumentPreview(url:url).id(url).frame(maxWidth:.infinity,maxHeight:.infinity)
            }
        }.presentationDetents([.large]).presentationDragIndicator(.visible)
         .interactiveDismissDisabled(isPhoto)
         .simultaneousGesture(DragGesture(minimumDistance:30).onEnded{value in
             if value.translation.height>120 && value.translation.height>abs(value.translation.width)*1.5 {close()}
         })
    }
}
struct DocumentPreview:UIViewControllerRepresentable {
    let url:URL
    func makeCoordinator()->Coordinator{Coordinator(url)}
    func makeUIViewController(context:Context)->QLPreviewController{let c=QLPreviewController();c.dataSource=context.coordinator;return c}
    func updateUIViewController(_ uiViewController:QLPreviewController,context:Context){}
    final class Coordinator:NSObject,QLPreviewControllerDataSource {let url:URL;init(_ url:URL){self.url=url};func numberOfPreviewItems(in controller:QLPreviewController)->Int{1};func previewController(_ controller:QLPreviewController,previewItemAt index:Int)->QLPreviewItem{url as NSURL}}
}

struct CaptureStudent: Codable {let id:String;let name:String}
struct ClassCapture: Codable, Identifiable {
    let id:String;let student:CaptureStudent;let date:Date;let filename:String
    var cloudName:String?;var message:String?
    var kind:String?=nil;var text:String?=nil;var students:[CaptureStudent]?=nil
    var deviceModel:String?=nil;var teacherFilter:String?=nil
}
extension LessonModel {
    var captureDeviceModel:String {var info=utsname();uname(&info);let count=MemoryLayout.size(ofValue:info.machine);return withUnsafePointer(to:&info.machine){pointer in pointer.withMemoryRebound(to:CChar.self,capacity:count){String(cString:$0)}}}
    func persistCaptures() throws {try JSONEncoder().encode(captures).write(to:captureRoot.appendingPathComponent("queue.json"),options:.atomic)}
    func removeCapture(_ item:ClassCapture) {
        do {
            if preview?.url==captureRoot.appendingPathComponent(item.filename){preview=nil}
            let old=captures;captures.removeAll{$0.id==item.id}
            do{try persistCaptures()}catch{captures=old;throw error}
            try? FileManager.default.removeItem(at:captureRoot.appendingPathComponent(item.filename))
        }catch{self.error=error.localizedDescription}
    }
    func selectCloud(_ url:URL) {
        guard url.startAccessingSecurityScopedResource() else{error="无法访问所选文件夹";return}
        defer{url.stopAccessingSecurityScopedResource()}
        do {
            let values=try url.resourceValues(forKeys:[.isUbiquitousItemKey])
            guard values.isUbiquitousItem==true else{error="请选择 iCloud 云盘里的文件夹，不能选“我的 iPhone”。";return}
            let data=try url.bookmarkData(options:[],includingResourceValuesForKeys:nil,relativeTo:nil)
            UserDefaults.standard.set(data,forKey:"classCaptureCloudFolder");status="已选择 iCloud 文件夹"
        }catch{self.error=error.localizedDescription}
    }
    /// 0.8：算好校验码后交给系统后台传；正在传的不重复交。没勾选＝全部，勾了＝只传勾的
    func uploadCaptures() async {
        guard !busy else{return};busy=true;defer{busy=false}
        let flying=BackgroundUploader.shared.snapshot()
        let list=(picked.isEmpty ? captures : captures.filter{picked.contains($0.id)}).filter{flying[$0.id]==nil}
        status="正在准备上传…"
        for item in list {
            do {
                let local=captureRoot.appendingPathComponent(item.filename)
                let checksum=try await Task.detached {let f=try FileHandle(forReadingFrom:local);defer{try? f.close()};var h=SHA256();while let d=try f.read(upToCount:1024*1024),!d.isEmpty{h.update(data:d)};return h.finalize().map{String(format:"%02x",$0)}.joined()}.value
                let formatter=DateFormatter();formatter.dateFormat="yyyy-MM-dd_HH-mm-ss"
                let name=item.student.name.components(separatedBy:CharacterSet(charactersIn:"/:\\")).joined(separator:"_")+"_"+formatter.string(from:item.date)+"_"+item.id+"."+local.pathExtension
                var r=request("/mobile/upload");r.httpMethod="POST";r.setValue("application/octet-stream",forHTTPHeaderField:"Content-Type")
                r.setValue(name.addingPercentEncoding(withAllowedCharacters:.urlPathAllowed),forHTTPHeaderField:"X-Filename")
                r.setValue(item.id,forHTTPHeaderField:"X-Capture-ID");r.setValue(checksum,forHTTPHeaderField:"X-SHA256")
                r.setValue(try JSONEncoder().encode(item).base64EncodedString(),forHTTPHeaderField:"X-Capture-Metadata")
                let size=Int64((try? local.resourceValues(forKeys:[.fileSizeKey]).fileSize) ?? 0)
                if let i=captures.firstIndex(where:{$0.id==item.id}){captures[i].message="后台上传中…";try? persistCaptures()}
                BackgroundUploader.shared.enqueue(r,file:local,captureId:item.id,checksum:checksum,size:size)
            }catch{
                if let i=captures.firstIndex(where:{$0.id==item.id}){captures[i].message="没能开始上传："+error.localizedDescription;try? persistCaptures()}
            }
        }
        syncUploads()
        status=uploading.isEmpty ? "没有要上传的" : "已交给系统后台上传，可以锁屏或切到别的 App（别往上划掉 App）"
    }
    /// 处理系统传回来的结果：Mac 确认过的删手机原件；失败的写上原因，下次再点上传会重传
    func syncUploads() {
        let d=UserDefaults.standard
        let done=Set(d.stringArray(forKey:BackgroundUploader.confirmedKey) ?? [])
        if !done.isEmpty {for item in captures where done.contains(item.id) {removeCapture(item);picked.remove(item.id)};d.removeObject(forKey:BackgroundUploader.confirmedKey)}
        if let failed=d.dictionary(forKey:BackgroundUploader.failedKey) as? [String:String],!failed.isEmpty {
            for (id,why) in failed {if let i=captures.firstIndex(where:{$0.id==id}){captures[i].message="未上传成功（"+why+"），再点上传重试"}}
            try? persistCaptures();d.removeObject(forKey:BackgroundUploader.failedKey)
            status="有 \(failed.count) 个没传成功，手机原件保留，再点上传重试"
        }
        let flying=BackgroundUploader.shared.snapshot()
        uploading=Set(flying.keys)
        upTotal=flying.count;upSent=flying.values.reduce(0){$0+$1.0};upSize=flying.values.reduce(0){$0+$1.1}
        if flying.isEmpty && !done.isEmpty && captures.isEmpty {status="已上传到 Mac，手机待上传原件已清理"}
    }
}
struct CaptureQueue:View {
    @ObservedObject var model:LessonModel
    @Environment(\.dismiss) var dismiss
    var body:some View {
        NavigationStack {
            List {
                    Section("连接设备") {
                        if model.paired && !model.isOnline { Button("立即重试连接"){model.retryCount=0;model.reconnect(quiet:true)} }
                        Button(model.paired ? "重新扫码连接 Mac":"扫码连接 Mac"){model.showPairScanner=true}
                        Text(model.paired ? "已绑定："+model.pairing.host:"首次使用请扫描 Mac 上的配对二维码").font(.caption)
                        Text(model.status).font(.caption)
                        Text("App 版本 "+((Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "?")+"（"+((Bundle.main.infoDictionary?["CFBundleVersion"] as? String) ?? "?")+"）").font(.caption).foregroundStyle(.secondary)
                    }

                Section {
                    if !model.uploading.isEmpty {
                        VStack(alignment:.leading,spacing:6){
                            let frac=model.upSize>0 ? Double(model.upSent)/Double(model.upSize) : 0
                            Text("后台上传中：还剩 \(model.upTotal) 个 · \(Int(frac*100))%").font(.headline)
                            ProgressView(value:frac)
                            Text(String(format:"已传 %.0f / %.0f MB · 可以锁屏或切走，别往上划掉 App",Double(model.upSent)/1048576,Double(model.upSize)/1048576)).font(.caption).foregroundStyle(.secondary)
                        }
                    } else {
                        Button(model.picked.isEmpty ? "全部上传到 Mac（\(model.captures.count) 个）" : "上传勾选的 \(model.picked.count) 个"){Task{await model.uploadCaptures()}}.disabled(model.busy || model.captures.isEmpty)
                        Text(model.picked.isEmpty ? "点左边圆圈可以只挑几个先传。" : "再点圆圈取消；都不勾＝全部上传。").font(.footnote).foregroundStyle(.secondary)
                    }
                    Text(model.status).font(.footnote)
                }
                if model.captures.isEmpty {Text("暂无待上传资料。随记都会先保存在手机。")}
                ForEach(["文字与语音笔记"],id:\.self){title in
                    let items=model.captures.filter{item in let note=["voice-note","text-note"].contains(item.kind ?? "");return (title=="文字与语音笔记")==note}
                    if !items.isEmpty {Section(title+"（\(items.count)）") {
                ForEach(items){item in
                    HStack(alignment:.top,spacing:12){
                        let on=model.picked.contains(item.id)
                        Image(systemName:on ? "checkmark.circle.fill":"circle").font(.title2).foregroundStyle(on ? Color.accentColor:Color.secondary).padding(.top,4)
                            .onTapGesture{ if !model.busy { if on {model.picked.remove(item.id)} else {model.picked.insert(item.id)} } }
                                                VStack(alignment:.leading,spacing:4){
                            // 点名字改学生（拍错人时用）：先列那时在上的课，再列全部学生
                            Button{model.renaming=item}label:{HStack(spacing:4){Text((item.students ?? [item.student]).map{$0.name}.joined(separator:"、")).font(.headline);Image(systemName:"chevron.down.circle").font(.caption)}}.buttonStyle(.borderless).foregroundStyle(.primary)
                            if item.kind=="voice-note"{InlineVoiceNote(model:model,item:item)}else if let text=item.text{Text(text)}
                            Text(item.date.formatted(date:.omitted,time:.shortened)).font(.caption).foregroundStyle(.secondary)
                            if let message=item.message {Text(message).font(.caption)}
                        }
                    }
                    .swipeActions(edge:.trailing){Button("删除",role:.destructive){model.removeCapture(item)}.disabled(model.busy || model.uploading.contains(item.id))}
                    .contextMenu{  // 按住这一条：删除 / 改学生（和课表上按住名字一样的习惯）
                        Button("改学生"){model.renaming=item}
                        Button("删除",role:.destructive){model.removeCapture(item)}.disabled(model.uploading.contains(item.id))
                    }
                }
                    }}
                }
            }.navigationTitle("待上传资料")
             .alert("提示",isPresented:Binding(get:{model.error != nil && model.page == 2},set:{if !$0{model.error=nil}})){Button("好"){model.error=nil}} message:{Text(model.error ?? "")}
             .toolbar{ToolbarItem(placement:.topBarTrailing){Button("返回课表"){model.showQueue=false}}}
             .sheet(isPresented:$model.showCloudFolder){CloudFolderPicker{url in model.showCloudFolder=false;if let url{model.selectCloud(url)}}}
             .confirmationDialog("改成谁的？",isPresented:Binding(get:{model.renaming != nil},set:{if !$0 {model.renaming=nil}}),titleVisibility:.visible){
                 if let item=model.renaming {
                     ForEach(model.lessonsAt(item.date)){o in Button(o.label){model.reassign(item,to:o.students)}}
                     ForEach(model.rosterStudents(),id:\.id){s in Button(s.name){model.reassign(item,to:[s])}}
                 }
                 Button("取消",role:.cancel){model.renaming=nil}
             }
        }
    }
}
struct CloudFolderPicker:UIViewControllerRepresentable {
    let completed:(URL?)->Void
    func makeCoordinator()->Coordinator{Coordinator(self)}
    func makeUIViewController(context:Context)->UIDocumentPickerViewController{let picker=UIDocumentPickerViewController(forOpeningContentTypes:[.folder],asCopy:false);picker.delegate=context.coordinator;return picker}
    func updateUIViewController(_ uiViewController:UIDocumentPickerViewController,context:Context){}
    final class Coordinator:NSObject,UIDocumentPickerDelegate {
        let parent:CloudFolderPicker;init(_ parent:CloudFolderPicker){self.parent=parent}
        func documentPicker(_ controller:UIDocumentPickerViewController,didPickDocumentsAt urls:[URL]){parent.completed(urls.first)}
        func documentPickerWasCancelled(_ controller:UIDocumentPickerViewController){parent.completed(nil)}
    }
}

struct NoteTarget:Identifiable {let id:String;let label:String;let students:[CaptureStudent]}
extension LessonModel {
    func resolveNoteStudents(forceChoose:Bool=false)->[CaptureStudent]? {
        if !forceChoose,let pinned=pinnedStudents {
            // 拖过来（或点名字）选定的学生：一直有效，直到换了一节课（下一节开始就回到“正在上课的学生”）
            if Date().timeIntervalSince(pinnedAt)<3*3600 && currentLessonKey()==pinLessonKey {return pinned}
            pinnedStudents=nil
        }
        guard let data=try? Data(contentsOf:captureRoot.appendingPathComponent("note-context.json")),let context=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] else{error="请先连接 Mac 刷新一次课表";return nil}
        let now=Date(),cal=Calendar.current,minute=cal.component(.hour,from:now)*60+cal.component(.minute,from:now)
        let weekday=["周日","周一","周二","周三","周四","周五","周六"][cal.component(.weekday,from:now)-1]
        let df=DateFormatter();df.dateFormat="yyyy-MM-dd";let date=df.string(from:now)
        let dates=context["dates"] as? [String:[String:Any]] ?? [:],special=dates[date]
        var lessons=(context["lessons"] as? [[String:Any]] ?? []).filter{($0["day"] as? String)==weekday}
        if special?["replace"] as? Bool == true {lessons=[]}
        lessons += special?["courses"] as? [[String:Any]] ?? []
        let teacher=UserDefaults.standard.string(forKey:"lessonTeacher") ?? "all"
        func students(_ rows:Any?)->[CaptureStudent]{(rows as? [[String:String]] ?? []).compactMap{row in guard let id=row["id"],let name=row["name"] else{return nil};return CaptureStudent(id:id,name:name)}}
        func minutes(_ v:String)->Int? {let p=v.split(separator:":");guard p.count==2,let h=Int(p[0]),let m=Int(p[1]) else{return nil};return h*60+m}
        noteChoices=lessons.compactMap{row in
            guard let time=row["time"] as? String else{return nil};let p=time.replacingOccurrences(of:"–",with:"-").split(separator:"-").map(String.init)
            guard p.count==2,let start=minutes(p[0]),let end=minutes(p[1]),minute>=start,minute<end else{return nil}
            var color=row["teacher"] as? String ?? ""
            if let dual=row["dual"] as? [String:Any],let split=dual["minutes"] as? Int{color=dual[minute<start+split ? "left":"right"] as? String ?? color}
            guard teacher=="all" || color==teacher || color=="both" else{return nil}
            let people=students(row["students"]);guard !people.isEmpty else{return nil}
            return NoteTarget(id:row["id"] as? String ?? time+people.map{$0.id}.joined(separator:","),label:time+" "+people.map{$0.name}.joined(separator:"、"),students:people)
        }
        pendingNoteContext=date+"|"+teacher+"|"+noteChoices.map{$0.id+":"+$0.label}.sorted().joined(separator:"|")
        if !forceChoose && chosenNoteContext==pendingNoteContext && !chosenNoteStudents.isEmpty {return chosenNoteStudents}
        if !forceChoose && noteChoices.count==1 {let selected=noteChoices[0];chosenNoteStudents=selected.students;chosenNoteContext=pendingNoteContext;noteTargetLabel=selected.label;return selected.students}
        if noteChoices.isEmpty || forceChoose {
            let roster=(context["roster"] as? [[String:String]] ?? []).filter{row in teacher=="all" || (row["teachers"] ?? "").split(separator:",").contains(where:{$0==teacher || $0=="both"})}
            noteChoices=students(roster).map{NoteTarget(id:$0.id,label:$0.name,students:[$0])}
        }
        if noteChoices.isEmpty {error="当前老师没有可选的在课学生，请在 Mac 核对排课。";return nil}
        showNoteTargets=true;return nil
    }
    func saveNote(file:URL,people:[CaptureStudent],kind:String,text:String?=nil,date:Date) {
        guard let first=people.first else{return}
        let item=ClassCapture(id:UUID().uuidString,student:first,date:date,filename:file.lastPathComponent,kind:kind,text:text,students:people,deviceModel:captureDeviceModel,teacherFilter:UserDefaults.standard.string(forKey:"lessonTeacher") ?? "all")
        captures.append(item)
        do{try persistCaptures();noteTargetLabel="已保存："+people.map{$0.name}.joined(separator:"、");noteText="";status="随记已保存在手机，左滑后可上传到 Mac"}
        catch{self.error="保存未完成，录音原文件仍保留在手机："+error.localizedDescription}
    }
    func sendTextNote(){
        let text=noteText.trimmingCharacters(in:.whitespacesAndNewlines);guard !text.isEmpty,let people=resolveNoteStudents() else{return}
        do{let file=captureRoot.appendingPathComponent(UUID().uuidString+".txt");try text.write(to:file,atomically:true,encoding:.utf8);saveNote(file:file,people:people,kind:"text-note",text:text,date:Date())}catch{self.error=error.localizedDescription}
    }
    func beginVoiceNote(){
        guard !noteHolding,!recordingNote else{return}
        noteHolding=true;startingNote=true;cancellingNote=false;recordingHaptic.prepare()
        guard let people=resolveNoteStudents() else{noteHolding=false;startingNote=false;return}
        let audio=AVAudioSession.sharedInstance()
        if audio.recordPermission == .granted {startVoiceRecording(people);return}
        audio.requestRecordPermission{allowed in Task{@MainActor in
            guard self.noteHolding else{return}
            guard allowed else{self.noteHolding=false;self.startingNote=false;self.error="请在 iPhone 设置中允许麦克风访问";return}
            self.startVoiceRecording(people)
        }}
    }
    func startVoiceRecording(_ people:[CaptureStudent]) {
        guard noteHolding else{startingNote=false;return}
        do {
            let audio=AVAudioSession.sharedInstance()
            try audio.setCategory(.playAndRecord,mode:.default,options:[.defaultToSpeaker])
            try audio.setAllowHapticsAndSystemSoundsDuringRecording(true)
            try audio.setActive(true)
            let file=captureRoot.appendingPathComponent(UUID().uuidString+".m4a")
            let recorder=try AVAudioRecorder(url:file,settings:[AVFormatIDKey:kAudioFormatMPEG4AAC,AVSampleRateKey:44100,AVNumberOfChannelsKey:1,AVEncoderAudioQualityKey:AVAudioQuality.high.rawValue])
            recorder.isMeteringEnabled=true
            guard recorder.record() else{throw NSError(domain:"Lesson",code:14,userInfo:[NSLocalizedDescriptionKey:"录音未能开始"])}
            noteRecorder=recorder;noteAudioURL=file;chosenNoteStudents=people;noteStarted=Date();recordingNote=true;startingNote=false
            recordingHaptic.impactOccurred()
        }catch{noteHolding=false;startingNote=false;self.error=error.localizedDescription;try? AVAudioSession.sharedInstance().setActive(false)}
    }
    func endVoiceNote(cancel:Bool=false){
        let shouldCancel=cancel || cancellingNote;cancellingNote=false
        noteHolding=false;startingNote=false;guard recordingNote,let file=noteAudioURL else{return}
        let length=noteRecorder?.currentTime ?? 0;noteRecorder?.stop();noteRecorder=nil;recordingNote=false;noteAudioURL=nil
        try? AVAudioSession.sharedInstance().setActive(false,options:.notifyOthersOnDeactivation)
        if shouldCancel || length<0.5 {try? FileManager.default.removeItem(at:file);noteTargetLabel=shouldCancel ? "已取消录音":"录音太短，请按住说话";return}
        saveNote(file:file,people:chosenNoteStudents,kind:"voice-note",date:noteStarted)
    }
}
/// 底部随记栏：一个框，点一下打字，按住说话（松开保存、上滑取消）。
struct NoteComposer:View {
    @ObservedObject var model:LessonModel
    @Environment(\.scenePhase) private var phase
    @FocusState private var typing:Bool
    var body:some View {
        VStack(spacing:5){
            // 0.4：不再有“更换学生”按钮——按住课表上的名字拖到这里就换
            HStack {Text(model.noteTargetLabel).font(.caption).foregroundStyle(.secondary).lineLimit(1);Spacer()}
                .task{while !Task.isCancelled {model.refreshNoteLabel();try? await Task.sleep(for:.seconds(30))}}
            HStack {
                if model.typingNote {
                    TextField("写点课堂随记…",text:$model.noteText,axis:.vertical).textFieldStyle(.roundedBorder).lineLimit(1...4).focused($typing)
                    let empty=model.noteText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty
                    // 没写字时这个键是“收起”，写了字就是“发送”
                    Button(empty ? "收起" : "发送"){ if empty { typing=false; model.typingNote=false } else { model.sendTextNote() } }.frame(minWidth:48,minHeight:44)
                }else{
                    HoldToRecord(model:model){model.typingNote=true;DispatchQueue.main.async{typing=true}}.frame(height:52)
                }
            }
            .onChange(of:typing){_,now in if !now && model.noteText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty {model.typingNote=false}}
            .onChange(of:model.focusNote){_,now in if now {model.typingNote=true;DispatchQueue.main.async{typing=true};model.focusNote=false}}
        }.padding(10).background(.background)
         .overlay(alignment:.top){if model.recordingNote {RecordingNoteIndicator(model:model).offset(y:-140).allowsHitTesting(false)}}
         .onChange(of:phase){_,p in if p != .active {model.endVoiceNote()}}
         .onDisappear{model.endVoiceNote()}
    }
}
struct NoteTargetPicker:View {
    @ObservedObject var model:LessonModel
    var body:some View {
        NavigationStack{List(model.noteChoices){choice in Button(choice.label){model.chosenNoteStudents=choice.students;model.chosenNoteAt=Date();model.chosenNoteContext=model.pendingNoteContext;model.noteTargetLabel=choice.label;model.pinnedStudents=choice.students;model.pinnedAt=Date();model.showNoteTargets=false}}
         .navigationTitle("确认随记属于谁")
         .toolbar{Button("取消"){model.showNoteTargets=false}}}
    }
}

struct RecordingNoteIndicator:View {
    @ObservedObject var model:LessonModel
    var body:some View {
        TimelineView(.animation(minimumInterval:0.08)){context in
            let _ = model.noteRecorder?.updateMeters()
            let power=model.noteRecorder?.averagePower(forChannel:0) ?? -60
            let level=max(0.03,min(1,Double(pow(10,power/30))))
            VStack(spacing:10){
                if model.cancellingNote {
                    Image(systemName:"trash.fill").font(.system(size:30))
                }else{
                    HStack(alignment:.center,spacing:5){ForEach(0..<13,id:\.self){i in
                        let shape=0.35+0.65*abs(sin(Double(i)*1.7+context.date.timeIntervalSinceReferenceDate*7))
                        Capsule().fill(.white).frame(width:5,height:CGFloat(5+level*35*shape))
                    }}.frame(height:40)
                }
                Text(model.cancellingNote ? "松开取消":"正在说话").font(.headline)
                Text(model.cancellingNote ? "滑回按钮继续录音":"上滑取消 · \(Int(context.date.timeIntervalSince(model.noteStarted))) 秒").font(.caption)
            }.foregroundStyle(.white).frame(width:230,height:120)
             .background(model.cancellingNote ? Color.red:Color.green.opacity(0.95),in:RoundedRectangle(cornerRadius:20))
             .shadow(color:.black.opacity(0.15),radius:10,y:4)
             .animation(.easeInOut(duration:0.12),value:model.cancellingNote)
        }
    }
}

@MainActor final class InlineAudio:ObservableObject {
    @Published var playing=false
    @Published var recognitionStatus=""
    var player:AVAudioPlayer?
    var task:SFSpeechRecognitionTask?
    func stop(){player?.stop();player=nil;playing=false;try? AVAudioSession.sharedInstance().setActive(false,options:.notifyOthersOnDeactivation)}
    func toggle(_ url:URL){
        if player?.isPlaying==true {player?.pause();playing=false;return}
        do {try AVAudioSession.sharedInstance().setCategory(.playback);try AVAudioSession.sharedInstance().setActive(true)
            if player==nil {player=try AVAudioPlayer(contentsOf:url)}
            playing=player?.play() ?? false
        }catch{recognitionStatus="无法播放，录音原件仍保留"}
    }
    func transcribe(_ url:URL,completed:@escaping(String)->Void){
        guard task==nil else{return}
        recognitionStatus="正在识别…"
        SFSpeechRecognizer.requestAuthorization{authorization in Task{@MainActor in
            guard authorization == .authorized else{self.recognitionStatus="未允许语音识别，可在设置中开启";return}
            guard let recognizer=SFSpeechRecognizer(locale:Locale(identifier:"zh-CN")),recognizer.supportsOnDeviceRecognition else{self.recognitionStatus="本机暂不支持离线转文字，录音已保留";return}
            let request=SFSpeechURLRecognitionRequest(url:url);request.requiresOnDeviceRecognition=true;request.shouldReportPartialResults=false
            self.task=recognizer.recognitionTask(with:request){result,error in Task{@MainActor in
                if let result,result.isFinal {completed(result.bestTranscription.formattedString);self.recognitionStatus="";self.task=nil}
                else if error != nil {self.recognitionStatus="识别未完成，可点重试";self.task=nil}
            }}
        }}
    }
}
struct InlineVoiceNote:View {
    @ObservedObject var model:LessonModel
    let item:ClassCapture
    @StateObject private var audio=InlineAudio()
    var body:some View {
        VStack(alignment:.leading,spacing:8){
            TimelineView(.periodic(from:.now,by:0.3)){_ in
                Button{audio.toggle(model.captureRoot.appendingPathComponent(item.filename))}label:{
                    Label(audio.player?.isPlaying==true ? "暂停播放":"播放语音",systemImage:audio.player?.isPlaying==true ? "pause.circle.fill":"play.circle.fill")
                        .padding(10).frame(maxWidth:.infinity,alignment:.leading).background(Color.blue.opacity(0.08)).clipShape(RoundedRectangle(cornerRadius:10))
                }.buttonStyle(.borderless)
            }
            if let text=item.text,!text.isEmpty {Text(text).font(.subheadline);Text("自动识别，仅供核对").font(.caption2).foregroundStyle(.secondary)}
            else {Button(audio.recognitionStatus.isEmpty ? "转为文字":audio.recognitionStatus){recognize()}.font(.caption).buttonStyle(.borderless).disabled(audio.task != nil || model.busy)}
        }.onAppear{if item.text==nil && !model.busy {recognize()}}
         .onDisappear{audio.stop();audio.task?.cancel();audio.task=nil}
         .onChange(of:model.busy){_,busy in if busy {audio.stop();audio.task?.cancel();audio.task=nil}}
    }
    private func recognize(){
        audio.transcribe(model.captureRoot.appendingPathComponent(item.filename)){text in
            guard let i=model.captures.firstIndex(where:{$0.id==item.id}) else{return}
            model.captures[i].text=text
            do{try model.persistCaptures()}catch{model.error="识别文字保存失败，录音仍保留"}
        }
    }
}

struct HoldToRecord:UIViewRepresentable {
    @ObservedObject var model:LessonModel
    var onTap:()->Void
    func makeUIView(context:Context)->RecordingTouchControl {
        let control=RecordingTouchControl();control.model=model;control.onTap=onTap;return control
    }
    func updateUIView(_ control:RecordingTouchControl,context:Context){control.model=model;control.onTap=onTap;control.updateTitle()}
}
final class RecordingTouchControl:UIControl {
    weak var model:LessonModel?
    var onTap:(()->Void)?
    private let label=UILabel()
    private var origin=CGPoint.zero
    private var holdStart:DispatchWorkItem?
    private var holding=false
    override init(frame:CGRect){
        super.init(frame:frame);isExclusiveTouch=true;layer.cornerRadius=10
        label.textAlignment = .center;label.font = .preferredFont(forTextStyle:.body);label.isUserInteractionEnabled=false
        addSubview(label);isAccessibilityElement=true;accessibilityTraits = .button;updateTitle()
    }
    required init?(coder:NSCoder){fatalError("init(coder:) has not been implemented")}
    override func layoutSubviews(){super.layoutSubviews();label.frame=bounds.insetBy(dx:14,dy:0)}
    func updateTitle(){
        let recording=model?.recordingNote == true,cancel=model?.cancellingNote == true,active=recording || holding
        label.text=recording ? (cancel ? "松开取消":"松开保存 · 上滑取消") : (holding ? "正在启动录音…":"点一下打字，按住说话")
        label.textAlignment=active ? .center : .left
        label.textColor=active ? .label : .placeholderText
        accessibilityLabel="随记：点一下打字，按住说话"
        backgroundColor=recording ? (cancel ? UIColor.systemRed:UIColor.systemGreen).withAlphaComponent(0.2):UIColor.secondarySystemFill
    }
    override func beginTracking(_ touch:UITouch,with event:UIEvent?)->Bool {
        origin=touch.location(in:window);holding=false
        // 按住 0.3 秒才开始录音；更短的是“点一下”，用来打字。
        let start=DispatchWorkItem{[weak self] in guard let self,self.isTracking else{return};self.holding=true;self.updateTitle();self.model?.beginVoiceNote();self.updateTitle()}
        holdStart=start;DispatchQueue.main.asyncAfter(deadline:.now()+0.3,execute:start)
        return true
    }
    override func continueTracking(_ touch:UITouch,with event:UIEvent?)->Bool {
        guard holding else { return true }
        let cancel=touch.location(in:window).y-origin.y < -60
        if let model,model.cancellingNote != cancel {model.cancellingNote=cancel;UISelectionFeedbackGenerator().selectionChanged()}
        updateTitle();return true
    }
    override func endTracking(_ touch:UITouch?,with event:UIEvent?){
        holdStart?.cancel()
        guard holding else { updateTitle(); onTap?(); return }
        holding=false
        let cancel=touch.map{$0.location(in:window).y-origin.y < -60} ?? true
        model?.endVoiceNote(cancel:cancel);updateTitle()
    }
    override func cancelTracking(with event:UIEvent?){holdStart?.cancel();if holding {holding=false;model?.endVoiceNote(cancel:true)};updateTitle()}
}

struct PairInvitation:Decodable {
    let version:Int;let kind:String;let host:String;let fallbackHost:String?;let port:Int
    let fingerprint:String;let code:String;let serverId:String;let expires:Double
}
extension LessonModel {
    func acceptPairCode(_ value:String) async {
        guard !pairingBusy else{return};pairingBusy=true;pairingError=nil
        defer{pairingBusy=false}
        do {
            let invite=try JSONDecoder().decode(PairInvitation.self,from:Data(value.utf8))
            guard invite.kind=="lesson-pair",invite.version==1,invite.port>0,invite.port<65536,invite.expires>Date().timeIntervalSince1970,invite.fingerprint.count==64,invite.fingerprint.allSatisfy({$0.isHexDigit}),!invite.code.isEmpty else{throw NSError(domain:"Pair",code:1,userInfo:[NSLocalizedDescriptionKey:"二维码无效或已过期，请重新生成"])}
            let hosts=[invite.fallbackHost,invite.host].compactMap{$0}
            guard hosts.allSatisfy({!$0.isEmpty && $0.allSatisfy{$0.isASCII && ($0.isLetter || $0.isNumber || $0=="." || $0=="-")}}) else{throw NSError(domain:"Pair",code:2,userInfo:[NSLocalizedDescriptionKey:"二维码地址无效"])}
            guard captures.isEmpty || pairing.serverId==invite.serverId else{throw NSError(domain:"Pair",code:3,userInfo:[NSLocalizedDescriptionKey:"这个二维码不是原来那台 Mac 的（编号不同）。手机还有待上传资料，为避免传错地方已拦下。请扫原来那台 Mac“服务管理”页里的二维码。"])}
            var candidate=Pairing(serverId:invite.serverId,role:"read-upload",host:invite.host,fallbackHost:invite.fallbackHost,port:invite.port,token:"",fingerprint:invite.fingerprint)
            let candidatePin=PinnedSession(candidate),config=Self.makeConfig()
            config.timeoutIntervalForRequest=10
            let candidateSession=URLSession(configuration:config,delegate:candidatePin,delegateQueue:nil)
            defer{candidateSession.finishTasksAndInvalidate()}
            var result:[String:Any]?,lastError:Error?,workingHost=invite.host
            for host in hosts {
                do {
                    var request=URLRequest(url:URL(string:"https://\(host):\(invite.port)/mobile/pair")!)
                    request.httpMethod="POST";request.setValue("application/json",forHTTPHeaderField:"Content-Type")
                    request.httpBody=try JSONSerialization.data(withJSONObject:["code":invite.code,"name":UIDevice.current.name])
                    let (data,response)=try await candidateSession.data(for:request)
                    try checked(data,response);result=try JSONSerialization.jsonObject(with:data) as? [String:Any];workingHost=host;break
                }catch{lastError=error}
            }
            guard let result,let token=result["token"] as? String,!token.isEmpty,result["serverId"] as? String==invite.serverId else{throw lastError ?? NSError(domain:"Pair",code:4,userInfo:[NSLocalizedDescriptionKey:"配对没有完成"])}
            candidate=Pairing(serverId:invite.serverId,role:"read-upload",host:invite.host,fallbackHost:invite.fallbackHost,port:invite.port,token:token,fingerprint:invite.fingerprint)
            // Fetch and persist the complete timetable before committing the new binding.
            var scheduleRequest=URLRequest(url:URL(string:"https://\(workingHost):\(invite.port)/")!)
            scheduleRequest.setValue("Bearer \(token)",forHTTPHeaderField:"Authorization")
            let (scheduleData,scheduleResponse)=try await candidateSession.data(for:scheduleRequest)
            try checked(scheduleData,scheduleResponse)
            guard let html=String(data:scheduleData,encoding:.utf8),html.contains("renderPhoneSchedule"),html.contains("<script>") else{throw NSError(domain:"Pair",code:5,userInfo:[NSLocalizedDescriptionKey:"Mac 没有返回可用课表，原缓存已保留"])}
            let stored=try JSONEncoder().encode(candidate)
            if pairing.serverId != candidate.serverId {
                let backup=captureRoot.appendingPathComponent("previous-connection-"+UUID().uuidString)
                try FileManager.default.createDirectory(at:backup,withIntermediateDirectories:true)
                for filename in ["schedule.html","note-context.json"] {
                    let existing=captureRoot.appendingPathComponent(filename)
                    if FileManager.default.fileExists(atPath:existing.path){try FileManager.default.copyItem(at:existing,to:backup.appendingPathComponent(filename))}
                }
                try? FileManager.default.removeItem(at:captureRoot.appendingPathComponent("note-context.json"))
                chosenNoteStudents=[];chosenNoteContext=""
            }
            try scheduleData.write(to:captureRoot.appendingPathComponent("schedule.html"),options:.atomic)
            connectionTask?.cancel();connectionWatchdog?.cancel();web?.stopLoading();session.invalidateAndCancel()
            config.timeoutIntervalForRequest=180;config.timeoutIntervalForResource=1800
            pairing=candidate;pin=PinnedSession(candidate);session=URLSession(configuration:config,delegate:pin,delegateQueue:nil)
            currentHost=workingHost;attemptedFallback=false;UserDefaults.standard.set(stored,forKey:"lessonPairedMac")
            paired=true;offline=false;web=nil;webIdentity=UUID();showPairScanner=false;showQueue=false;status="配对成功，正在读取课表…"
        }catch{let ns=error as NSError;pairingError="配对未完成："+(ns.domain==NSURLErrorDomain ? Self.explain(error)+"（代码 \(ns.code)）" : error.localizedDescription)}
    }
}
struct PairScannerSheet:View {
    @ObservedObject var model:LessonModel
    @State private var scanID=UUID()
    var body:some View {NavigationStack{VStack{Text("扫描 Mac“连接设备”里的二维码").padding();QRScanner{value in Task{await model.acceptPairCode(value)}}.id(scanID);if model.pairingBusy{ProgressView("正在连接 Mac…").padding()};if let error=model.pairingError{Text(error).foregroundStyle(.red).padding();Button("重新扫描"){model.pairingError=nil;scanID=UUID()}.padding()}}.navigationTitle("扫码连接 Mac").toolbar{Button("关闭"){model.showPairScanner=false}}}}
}
struct QRScanner:UIViewControllerRepresentable {
    let found:(String)->Void
    func makeUIViewController(context:Context)->QRScanController{let c=QRScanController();c.found=found;return c}
    func updateUIViewController(_ controller:QRScanController,context:Context){}
    static func dismantleUIViewController(_ controller:QRScanController,coordinator:()){controller.stop()}
}
final class QRScanController:UIViewController,AVCaptureMetadataOutputObjectsDelegate {
    let capture=AVCaptureSession();let queue=DispatchQueue(label:"lesson.qr.camera");var layer:AVCaptureVideoPreviewLayer?;var found:((String)->Void)?;var finished=false
    override func viewDidLoad(){super.viewDidLoad();view.backgroundColor = .black
        AVCaptureDevice.requestAccess(for:.video){[weak self] allowed in DispatchQueue.main.async{guard let self else{return};if allowed{self.configure()}else{let l=UILabel();l.text="请在设置中允许相机访问";l.textColor = .white;l.textAlignment = .center;l.frame=self.view.bounds;l.autoresizingMask=[.flexibleWidth,.flexibleHeight];self.view.addSubview(l)}}}
    }
    func configure(){guard let device=AVCaptureDevice.default(for:.video),let input=try? AVCaptureDeviceInput(device:device),capture.canAddInput(input) else{return};capture.addInput(input);let output=AVCaptureMetadataOutput();guard capture.canAddOutput(output) else{return};capture.addOutput(output);output.setMetadataObjectsDelegate(self,queue:.main);output.metadataObjectTypes=[.qr];let preview=AVCaptureVideoPreviewLayer(session:capture);preview.videoGravity = .resizeAspectFill;view.layer.addSublayer(preview);layer=preview;preview.frame=view.bounds;queue.async{self.capture.startRunning()}}
    override func viewDidLayoutSubviews(){super.viewDidLayoutSubviews();layer?.frame=view.bounds}
    func stop(){queue.async{self.capture.stopRunning()}}
    func metadataOutput(_ output:AVCaptureMetadataOutput,didOutput metadataObjects:[AVMetadataObject],from connection:AVCaptureConnection){guard !finished,let value=(metadataObjects.first as? AVMetadataMachineReadableCodeObject)?.stringValue else{return};finished=true;stop();found?(value)}
}

// MARK: - 0.4 点名字写上课内容
extension LessonModel {
    /// 点学生名字：之后的随记（打字或按住说话）都记给这个学生，并直接打开输入框
    func pinNote(_ student:CaptureStudent,group:[CaptureStudent]=[],focus:Bool=true) {
        let who=group.count>1 ? group : [student]
        pinnedStudents=who;pinnedAt=Date();pinLessonKey=currentLessonKey();chosenNoteStudents=who
        noteTargetLabel="随记给："+(who.count>1 ? "全班（"+who.map{$0.name}.joined(separator:"、")+"）" : student.name);if focus {focusNote=true}
    }
    /// 现在正在上的课（按手机上选的老师）——用来判断“换了一节课没有”
    func currentLessonKey()->String {lessonsAt(Date()).map{$0.id}.sorted().joined(separator:"|")}
    /// 随记栏上方那行字：现在记给谁
    func refreshNoteLabel() {
        guard !recordingNote else{return}
        if let pinned=pinnedStudents,Date().timeIntervalSince(pinnedAt)<3*3600,currentLessonKey()==pinLessonKey {noteTargetLabel="随记给："+pinned.map{$0.name}.joined(separator:"、");return}
        pinnedStudents=nil
        let now=lessonsAt(Date())
        noteTargetLabel=now.count==1 ? "随记给（正在上课）："+now[0].students.map{$0.name}.joined(separator:"、") : now.isEmpty ? "现在不是上课时间：按住名字拖到这里选学生" : "现在有 \(now.count) 节课：按住名字拖到这里选学生"
    }
    /// 今天这个时刻在上哪几节课（课前课后 10 分钟也算，但正在上的课优先）
    func lessonsAt(_ date:Date)->[NoteTarget] {
        guard let data=try? Data(contentsOf:captureRoot.appendingPathComponent("note-context.json")),let context=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] else{return []}
        let cal=Calendar.current,minute=cal.component(.hour,from:date)*60+cal.component(.minute,from:date)
        let weekday=["周日","周一","周二","周三","周四","周五","周六"][cal.component(.weekday,from:date)-1]
        let df=DateFormatter();df.dateFormat="yyyy-MM-dd";let day=df.string(from:date)
        let dates=context["dates"] as? [String:[String:Any]] ?? [:],special=dates[day]
        var lessons=(context["lessons"] as? [[String:Any]] ?? []).filter{($0["day"] as? String)==weekday}
        if special?["replace"] as? Bool == true {lessons=[]}
        lessons += special?["courses"] as? [[String:Any]] ?? []
        let teacher=UserDefaults.standard.string(forKey:"lessonTeacher") ?? "all"
        func students(_ rows:Any?)->[CaptureStudent]{(rows as? [[String:String]] ?? []).compactMap{row in guard let id=row["id"],let name=row["name"] else{return nil};return CaptureStudent(id:id,name:name)}}
        func minutes(_ v:String)->Int? {let p=v.split(separator:":");guard p.count==2,let h=Int(p[0]),let m=Int(p[1]) else{return nil};return h*60+m}
        var inside:[NoteTarget]=[],near:[NoteTarget]=[]
        for row in lessons {
            guard let time=row["time"] as? String else{continue};let p=time.replacingOccurrences(of:"–",with:"-").split(separator:"-").map(String.init)
            guard p.count==2,let start=minutes(p[0]),let end=minutes(p[1]),minute>=start-10,minute<end+10 else{continue}
            var color=row["teacher"] as? String ?? ""
            if let dual=row["dual"] as? [String:Any],let split=dual["minutes"] as? Int{color=dual[minute<start+split ? "left":"right"] as? String ?? color}
            guard teacher=="all" || color==teacher || color=="both" else{continue}
            let people=students(row["students"]);guard !people.isEmpty else{continue}
            let t=NoteTarget(id:time+people.map{$0.id}.joined(separator:","),label:time+" "+people.map{$0.name}.joined(separator:"、"),students:people)
            if minute>=start && minute<end {inside.append(t)} else {near.append(t)}
        }
        return inside.isEmpty ? near : inside
    }
    }
// MARK: - 0.5 待上传里改学生
extension LessonModel {
    func rosterStudents()->[CaptureStudent] {
        guard let data=try? Data(contentsOf:captureRoot.appendingPathComponent("note-context.json")),let context=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] else{return []}
        return (context["roster"] as? [[String:String]] ?? []).compactMap{r in guard let id=r["id"],let name=r["name"] else{return nil};return CaptureStudent(id:id,name:name)}
    }
    /// 把待上传里的一条改成别的学生（还没上传，只改手机上的记录）
    func reassign(_ item:ClassCapture,to people:[CaptureStudent]) {
        renaming=nil
        guard let first=people.first,let i=captures.firstIndex(where:{$0.id==item.id}) else{return}
        captures[i]=ClassCapture(id:item.id,student:first,date:item.date,filename:item.filename,cloudName:item.cloudName,message:item.message,kind:item.kind,text:item.text,students:people,deviceModel:item.deviceModel,teacherFilter:item.teacherFilter)
        do{try persistCaptures();status="已改成："+people.map{$0.name}.joined(separator:"、")}catch{self.error="没改成："+error.localizedDescription}
    }
}
