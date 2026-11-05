# 给 AI 的安装说明（Claude Code 等）

你在帮一位音乐老师在 **TA 自己的 Mac** 上装 Coda 课达：Mac 端 + iPhone App。老师多半不懂编程，请：
- 用中文、短句跟老师说话；需要老师动手的事（登录 Apple ID、手机上点按钮）一次只说一件，说清楚点哪里。
- 不要改程序的功能；除了下面写到的地方，不要改代码。
- **不要提交、上传 `mac/我的资料/`**，里面是学生的名字、账本和照片。

---

## 0. 先检查

```bash
sw_vers -productVersion            # 要 12 以上
xcode-select -p                    # 要指向 /Applications/Xcode.app/Contents/Developer
xcodebuild -version                # 没装 Xcode 就请老师去 App Store 装（很大，要等一阵）
/usr/bin/python3 -c 'print("ok")'  # Mac 端只用系统自带的 python3 和标准库，不用 pip 装任何东西
```

`xcode-select -p` 指向 CommandLineTools 时，请老师自己在终端运行（要输开机密码）：
`sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`，然后打开一次 Xcode 让它装完组件。

## 1. Mac 端

1. 编译签课表识别工具（手机拍签课表、Mac 识别要用；只用系统自带框架）：
   ```bash
   cd mac/程序 && ./编译纸质表单识别工具.command
   ```
   成功会打印“已编译”，生成 `mac/程序/纸质表单识别工具`。
2. 启动：
   ```bash
   zsh "Mac 点这里.command"
   ```
   第一次会把 `mac/示例资料/` 复制成 `mac/我的资料/`，然后在后台启动服务并打开浏览器 `http://127.0.0.1:18765/`，进设置向导。请老师自己填老师名字和学生（或先留着示例学生）。
3. 检查：
   ```bash
   lsof -nP -iTCP:18765 -iTCP:18766 -sTCP:LISTEN   # 两个端口都要在听：18765 Mac 网页（只本机），18766 手机通道（https，局域网）
   tail mac/我的资料/运行记录.log                   # 出问题先看这里
   ```
   端口被占用（这台 Mac 上已经有别的程序用 18765/18766）：改 `mac/我的资料/发行版.json` 的 `"port"`（Mac 网页），手机通道用环境变量 `LESSON_PHONE_PORT` 启动；一般不会遇到。

第一次启动时，`mac/我的资料/手机连接/` 里会自动生成这台 Mac 自己的 https 证书和口令，不要拷给别人。

## 2. iPhone App（免费 Apple ID）

工程：`iPhone/课程与签到.xcodeproj`，scheme `课程与签到`，产物 `LessonLedger.app`，iOS 17 以上，SwiftUI，无第三方依赖，无特殊 entitlement（免费账号能签）。

1. **签名**（这一步要老师在 Xcode 里点，命令行做不了登录）：
   - `open iPhone/课程与签到.xcodeproj`
   - 请老师：Xcode → 设置（Settings）→ Accounts → 左下角 + → Apple ID，登录自己的 Apple ID。
   - 左边点蓝色工程图标 → TARGETS 里的 `课程与签到` → **Signing & Capabilities**：勾 Automatically manage signing；**Team** 选“你的名字 (Personal Team)”。
   - **Bundle Identifier** 改成老师自己的，例如 `com.laoshi123.coda`（现在是占位的 `com.example.coda`，免费账号必须用一个别人没注册过的）。
   - 改完 Xcode 会把 `DEVELOPMENT_TEAM` 和 `PRODUCT_BUNDLE_IDENTIFIER` 写进 `project.pbxproj`，Debug 和 Release 两处都要是同一个值（`grep -n "DEVELOPMENT_TEAM\|PRODUCT_BUNDLE_IDENTIFIER" iPhone/课程与签到.xcodeproj/project.pbxproj` 核对）。
2. **手机准备**（请老师在手机上做）：
   - 用数据线连 Mac，手机解锁，弹出“要信任此电脑吗”点**信任**。
   - 设置 → 隐私与安全性 → **开发者模式** 打开（手机会重启）。只有第一次需要。
3. **编译安装**：
   ```bash
   cd iPhone && ./安装到连着的iPhone.command
   ```
   它会找连着的 iPhone，`xcodebuild -allowProvisioningUpdates` 编译（第一次会自动把这部手机登记到老师的免费账号），再用 `xcrun devicectl` 装上。也可以在 Xcode 里选这部手机点运行 ▶︎。
4. 第一次打开 App 提示“不受信任的开发者”：请老师到 设置 → 通用 → **VPN 与设备管理** → 点自己的 Apple ID → 信任。
5. **配对**：Mac 浏览器课程管理右上角点“○ 手机未连接”出二维码（5 分钟有效、只能用一次）；手机打开 App、左滑、点“扫码连接 Mac”扫码；提示“查找本地网络上的设备”点允许。连上后 Mac 右上角变“● 手机已连接”。
   - 连不上：确认手机和 Mac 同一个 Wi-Fi；Mac 的 系统设置 → 网络 → 防火墙 如果开着，要允许 python3 接收连接；手机上的 VPN/代理软件先关掉试试（App 会优先用 Mac 的局域网 IP 直连）。

## 3. 告诉老师这件事（重要）

> 免费苹果账号装的 App **7 天后会打不开**。每周插上线，双击 `iPhone/安装到连着的iPhone.command` 重装一次就好。是覆盖安装，配对和手机里没传完的照片视频都在。

也可以帮老师在“日历”里建一个每周提醒。免费账号一部手机最多同时装 3 个自己编译的 App。

## 4. 装好后自检

```bash
# Mac 端在跑、手机通道在听
lsof -nP -iTCP:18765 -iTCP:18766 -sTCP:LISTEN
# 手机配对过的设备
cat mac/我的资料/手机连接/设备.json | python3 -c 'import json,sys;print([d["name"] for d in json.load(sys.stdin)["devices"]])'
```
请老师在手机上按住一个学生名字 → “请假”，再到 Mac 课时管理里看到这条，就全通了（试完可以在手机上再按住 → 取消请假）。

## 程序结构（需要排查时看）

- `mac/程序/课程连接.py`：主服务，`127.0.0.1:18765`，Mac 网页和所有资料读写。`我的资料/发行版.json` 里 `"phone": true` 时启动手机通道。
- `mac/程序/手机网关.py`：手机通道，`0.0.0.0:18766` https（自签证书，App 按证书指纹认 Mac）；配对后用令牌，只放行看课表、上传、记上课/请假、签课表核对入账这几样，转交给 18765。
- `mac/程序/设备配对.py`：二维码配对、已配对设备。
- `mac/网页/`：课程管理、课时管理、服务管理、设置向导、操作日志页面，和手机网页版（手机浏览器打开 https://Mac地址:18767/m）。
- `mac/我的资料/`：所有资料（JSON 文件 + 照片），程序只认这个文件夹。
- `iPhone/课程与签到/LessonApp.swift`：整个 App；课表页面是 Mac 发来的网页（WKWebView），拍签课表、录语音随记、上传、配对是原生代码。
- `AI接入/`：装好以后，AI 帮老师记录、查课时读这里，入口 `AGENTS.md`。
