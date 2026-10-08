# 依赖下载说明

> 本项目**不把 adb 二进制纳入版本控制**（macOS 21MB + Linux 12MB，体积大）。
> 需要编译/运行 photo-sorter 桌面端时，按本文自行下载。

## 为什么排除

- `assets/adb/` 三平台合计 30MB+，且缺 Windows 版
- 二进制不适合进 git（每次更新都会让仓库膨胀）
- 各平台官方都能直接下载

## 下载方式

### 方式一：Android SDK Platform Tools（推荐）

官方地址：https://developer.android.com/tools/releases/platform-tools

下载对应平台压缩包，解压后取 `adb` 可执行文件：

```
platform-tools/
├── adb.exe              → 放到 assets/adb/windows/
├── AdbWinApi.dll        → 放到 assets/adb/windows/
├── AdbWinUsbApi.dll     → 放到 assets/adb/windows/
├── adb                  → 放到 assets/adb/macos/   (chmod +x)
└── adb                  → 放到 assets/adb/linux/   (chmod +x)
```

### 方式二：包管理器

```bash
# macOS
brew install android-platform-tools

# Linux (Debian/Ubuntu)
sudo apt install adb

# Windows (scoop)
scoop install adb

# Windows (choco)
choco install adb
```

装完后从安装位置复制到 `assets/adb/<平台>/`。

## 目录结构（放置后）

```
products/photo-sorter/assets/adb/
├── windows/
│   ├── adb.exe
│   ├── AdbWinApi.dll
│   └── AdbWinUsbApi.dll
├── macos/
│   ├── adb            ← 需要 chmod +x
│   └── lib64/
└── linux/
    ├── adb            ← 需要 chmod +x
    └── lib64/
```

## 权限设置

macOS / Linux 下 adb 需要可执行权限：

```bash
chmod +x products/photo-sorter/assets/adb/macos/adb
chmod +x products/photo-sorter/assets/adb/linux/adb
```

## 平台注意事项

- **macOS**：首次运行 adb 可能被 Gatekeeper 拦截，需右键 → 打开，允许一次
- **Linux**：USB 访问需要 udev 规则，否则识别不到设备
- **Windows**：需要 `.dll` 与 `adb.exe` 同目录，缺一不可

## 验证

```bash
adb version          # 应输出版本号
adb devices          # 连接手机后应列出设备
```

## 相关文档

- 技术方案：[重构方案.md](重构方案.md)
- 开发进展：[开发日志.md](开发日志.md)
