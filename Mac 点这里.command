#!/bin/zsh
# 双击打开 Coda · 课达（开源版）。真正的启动逻辑在 mac/程序/coda_start.py。
cd "$(dirname "$0")" || exit 1
/usr/bin/xattr -dr com.apple.quarantine "$(pwd -P)" 2>/dev/null
if ! /usr/bin/python3 -c '' >/dev/null 2>&1; then
  /usr/bin/osascript -e 'display dialog "Coda 课达 需要苹果的“命令行开发者工具”。" & return & return & "如果刚才弹出了安装提示，请点“安装”，装好后再双击一次。" buttons {"好"} with icon caution' >/dev/null 2>&1
  exit 1
fi
/usr/bin/python3 -X utf8 -B mac/程序/coda_start.py
