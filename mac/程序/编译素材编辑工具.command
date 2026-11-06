#!/bin/bash
# 把 素材编辑.swift 编译成 素材编辑工具（视频剪头尾、旋转；Apple 芯片和 Intel 通用，macOS 15 以上）。只有改了源代码才需要运行。
set -e
cd "$(dirname "$0")"
tmp="$(mktemp -d)"
swiftc -O -swift-version 5 -target arm64-apple-macos15 -o "$tmp/arm64" 素材编辑.swift
swiftc -O -swift-version 5 -target x86_64-apple-macos15 -o "$tmp/x86_64" 素材编辑.swift
lipo -create -output 素材编辑工具 "$tmp/arm64" "$tmp/x86_64"
echo "已编译：$(pwd)/素材编辑工具"
