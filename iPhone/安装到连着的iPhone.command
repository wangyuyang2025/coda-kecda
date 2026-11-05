#!/bin/zsh
# 把“课程与签到”App 装到用数据线连着这台 Mac 的每一部 iPhone / iPad（覆盖安装，配对和手机里的资料都保留）。
# 新设备第一次装：手机上要先“信任这台电脑”，并打开 设置 → 隐私与安全性 → 开发者模式；装完第一次打开若提示“未受信任的开发者”，到 设置 → 通用 → VPN 与设备管理 里信任。
cd "$(dirname "$0")" || exit 1
OUT="$HOME/Library/Caches/课程与签到-安装"
LIST="$OUT/devices.json"; mkdir -p "$OUT"
xcrun devicectl list devices --json-output "$LIST" >/dev/null 2>&1
IDS=($(/usr/bin/python3 -c "
import json;d=json.load(open('$LIST'))
for x in d['result']['devices']:
  c=x.get('connectionProperties',{})
  if c.get('transportType')=='wired' and x['hardwareProperties'].get('reality')=='physical':print(x['hardwareProperties']['udid'])"))
if (( ${#IDS} == 0 )); then echo "没有找到用数据线连着的 iPhone。请插上线、解锁手机、点“信任”后再试。"; read -k1 "?按任意键关闭"; exit 1; fi
VER=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" 课程与签到/Info.plist)
BUILD=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" 课程与签到/Info.plist)
echo "准备安装 App 版本 $VER（$BUILD）到 ${#IDS} 部设备"
for ID in $IDS; do
  echo "\n== $ID：编译（新设备会自动登记到开发者账号）"
  if ! xcodebuild -project 课程与签到.xcodeproj -scheme 课程与签到 -configuration Release -destination "id=$ID" -derivedDataPath "$OUT/build" -allowProvisioningUpdates -allowProvisioningDeviceRegistration build -quiet; then echo "编译失败（上面有原因）"; continue; fi
  echo "== $ID：安装"
  xcrun devicectl device install app --device "$ID" "$OUT/build/Build/Products/Release-iphoneos/LessonLedger.app" >/dev/null && echo "装好了：版本 $VER（$BUILD）" || echo "安装失败：手机要解锁、信任这台电脑、打开开发者模式"
done
read -k1 "?全部完成，按任意键关闭"
