# Coda · 课达（开源版）

一线老师自己做的排课、课时、签到工具。Mac 上管课表和课时，iPhone 上看课表、记上课、标请假、记随记、拍签课表入账。

**所有资料只存在你自己的 Mac 上**，手机只通过家里/琴房的 Wi-Fi 连你的 Mac，不经过任何服务器。

> English: Coda is a lesson scheduling / attendance tool for private teachers. A Mac app (Python standard library, runs in your browser) plus an iPhone app (SwiftUI) that pairs with your Mac over local Wi-Fi. Non-commercial use only (PolyForm Noncommercial 1.0.0).

---

## 能做什么

**Mac（浏览器里用）**
- 课程管理：把学生拖进周课表；临时调课只改这一周，固定课表不动；两位老师用蓝、红两种颜色。
- 课时管理：每个学生还剩几节；缴费、上课、请假都记成流水，记错了撤销，历史保留。
- 签课表：每周打印一张放琴房，学生签字或打勾请假；拍照/扫描导入后自动认出谁上了课，核对后一键扣课时。
- 课时单：一张图直接粘贴到微信发家长。
- 服务管理：手机随记和相机卡导入的照片视频按学生、按节收好，写上课内容，整理好发给家长。
- 操作日志：Mac 和手机上的每一次改动都有记录。

**iPhone App**
- 看从今天起 7 天的课表（没网时显示上次的）。
- 按住学生名字：记“上课了”（直接扣课时）、标请假、打字或说话记给这个学生。
- 点学生名字：打字或说话记给这个学生，回到 Mac 上传。
- 拍签课表：手机拍完在手机上核对、入账。
- 拍老课表留档。

**手机网页版**：不想编译 App、或者用安卓手机，可以用手机浏览器打开网页版，看课表、记上课、标请假。

**接自己的 AI**：在这个文件夹里打开 Claude Code、Codex 这类 AI，说“请先读 AGENTS.md，然后帮我用课达记课时”。之后说一句“周三小明上了，小红请假”，它查课表、列清单，你说可以它才写。说明在 `AI接入/`。

**这一版没有**：作品管理、演奏录像、手机拍视频（作者另外做成单独的 App）。

## 安卓

从本仓库的 Releases 下载 **coda-android-0.1.apk**，装到手机上（手机会提示允许安装未知来源的应用）。

1. 手机和电脑连同一个 Wi-Fi，电脑上的课达开着。
2. 打开 App，填电脑地址。地址在电脑课达的“服务管理”→“连接手机网页版”的网址里，比如 `192.168.1.20`。
3. 输入电脑上显示的 6 位数，就连上了。以后打开直接进课表。

功能和手机网页版一样：看课表、记上课、请假。App 第一次连接时记下这台电脑的证书，以后别的电脑冒充不了。不想装 App，也可以直接用手机浏览器打开网页版。

源码在 `android/`，可以自己编译。

## Windows

1. 先装 Python：到 python.org 下载，安装时勾选 **Add python.exe to PATH**。
2. 解压后双击 **Windows 点这里.bat**，浏览器会打开课达。防火墙弹窗时点“允许”，手机才连得上。
3. 手机用**手机网页版**（iPhone、安卓都行）。iPhone App 要用 Mac 上的 Xcode 编译，Windows 上做不了。

这些在 Windows 上和 Mac 不一样：
- 剪视频、把大视频压小，只有 Mac 有。
- 拍的签课表在电脑网页里识别，照片要是 JPG 或 PNG（iPhone 的 HEIC 打不开）。
- AI 接入的命令把 `python3` 换成 `py -3`。

文件夹叫 `mac/` 只是历史名字，Windows 也用它。

---

## 需要什么

- 一台 Mac（macOS 12 以上），装 **Xcode**（App Store 免费）。
- 一部 iPhone（iOS 17 以上）。
- 一个 **免费的苹果账号**（就是你平时用的 Apple ID），不用付 ¥688 的开发者费用。
- Mac 和 iPhone 连**同一个 Wi-Fi**。上课时 Mac 要开着。

---

## 怎么装

最省事：在这个文件夹里打开 Claude Code（或别的会写代码的 AI），跟它说：

> 照着 `给AI的安装说明.md` 帮我把 Coda 课达 装好，App 装到我连着的 iPhone 上。

它会一步步带你做，需要你动手的地方（登录 Apple ID、手机上点“信任”）会停下来告诉你。

自己装也可以，三步：

1. **Mac 端**：双击 `Mac 点这里.command`。第一次提示“无法验证开发者”就右键 → 打开。浏览器会打开设置页，填老师名字和学生，一分钟就好。
2. **签课表识别工具**（手机拍签课表要用）：双击 `mac/程序/编译纸质表单识别工具.command`，等它说“已编译”。
3. **iPhone App**：用 Xcode 打开 `iPhone/课程与签到.xcodeproj`，在 Signing & Capabilities 里 Team 选你的 Apple ID（Personal Team），Bundle Identifier 改成你自己的（比如 `com.你的名字.coda`），手机插上线，点运行。详细步骤见 `给AI的安装说明.md`。

---

## 连手机

1. Mac 上打开课程管理，点右上角 **“○ 手机未连接”**，出一个二维码。
2. iPhone 打开 App，左滑，点 **“扫码连接 Mac”**，扫一下。
3. 第一次会问“允许查找本地网络上的设备”，点允许。

连上以后右上角变成“● 手机已连接”。手机传来的照片、视频、随记，点顶栏 **“手机上传”** 在访达里打开。

---

## ⚠️ 免费账号每 7 天要重装一次

用免费苹果账号装的 App，**7 天后就打不开了**（苹果的规定）。到时候：

- iPhone 插上 Mac，双击 `iPhone/安装到连着的iPhone.command`，等它说“装好了”。
- 是覆盖安装：**配对、手机里没传完的照片视频都还在**，不用重新扫码。
- 建议每周固定一天（比如周一上课前）重装一次。

另外免费账号：一部手机最多同时装 3 个这样自己编译的 App；Bundle Identifier 必须是你自己起的、别人没用过的。

---

## 资料在哪

- 你的课表、学生、账本、签课表、手机传来的照片视频都在 `mac/我的资料/`。
- 换电脑：把整个文件夹拷过去就行。
- `mac/我的资料/` 已经写进 `.gitignore`，**不会被 git 提交**。如果你 fork 了这个仓库，也不要把它传上去——里面是学生的名字和照片。

---

## 许可

[PolyForm Noncommercial 1.0.0](LICENSE)：**只能非商业使用**。老师自己教课用、学校内部用、学习研究都可以；拿去卖、做成收费产品或收费服务不行。

用到的第三方代码各自的许可不变：
- `mac/网页/pdf.min.js`、`pdf.worker.min.js`：Mozilla pdf.js，Apache License 2.0。
- `mac/程序/qrcodegen.py`：Project Nayuki QR Code generator，MIT License。
