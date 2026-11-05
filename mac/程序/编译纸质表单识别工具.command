#!/bin/bash
# 把 纸质表单识别.swift 编译成 纸质表单识别工具（Apple 芯片和 Intel 通用，macOS 12 以上）。只有改了源代码才需要运行。
set -e
cd "$(dirname "$0")"
tmp="$(mktemp -d)"
swiftc -O -swift-version 5 -target arm64-apple-macos12 -o "$tmp/arm64" 纸质表单识别.swift
swiftc -O -swift-version 5 -target x86_64-apple-macos12 -o "$tmp/x86_64" 纸质表单识别.swift
lipo -create -output 纸质表单识别工具 "$tmp/arm64" "$tmp/x86_64"
echo "已编译：$(pwd)/纸质表单识别工具"
