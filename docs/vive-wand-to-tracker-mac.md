# Mac 上将 HTC VIVE 手柄转换为 Tracker

2026 年 11 月 1 日，两只黑色 HTC VIVE Wand 均在 Apple Silicon Mac 上完成 Tracker 配置写入和重启命令后的读回验证。目标是让 SteamVR 将手柄识别为通用追踪器，以便与 VIVE Tracker 3.0 共用 Base Station 1.0。这次写入的是手柄设备配置，范围限于角色和显示标识字段。

## 识别设备并准备工具

一次只接一只待操作手柄，用支持数据传输的 USB 线连接。

```sh
ioreg -p IOUSB -l -w 0 | rg 'USB Product Name|USB Vendor Name|USB Serial Number|idVendor|idProduct'
```

两只手柄均枚举为 HTC `VRC`（`28DE:2012`），序列号形如 `LHR-XXXXXXXX`。第一次经集线器连接时，USB 树里能看到设备，但 HID 接口未能读取。重新连接后，确认 HID 接口和目标序列号再继续。

写入工具 `lighthouse_console` 来自 Valve 历史的 SteamVR macOS depot：App ID `250820`，depot ID `250822`，manifest `8418111908491630065`（用 DepotDownloader 指定 manifest 下载）。虽然文件位于 `osx32` 目录，`lighthouse_console` 实际是 x86_64 Mach-O，在 Apple Silicon 上通过 Rosetta 运行。把它和同一 depot 里的 `libopenvr_api.dylib` 放在同一个目录，启动时设置 `DYLD_LIBRARY_PATH` 指向该目录：

```sh
cd mac-tools && DYLD_LIBRARY_PATH="$PWD" ./lighthouse_console
```

## 备份、转换和写入

1. 用 USB HID 读取原始配置两次，确认字节一致，保留 `original.config.json` 和 `original.config.zlib`。
2. 在 `lighthouse_console` 核对设备序列号，运行 `downloadconfig valve-original.config.json`。确认它与 HID 原始 JSON 逐字节一致。
3. 从本只手柄的原始 JSON 复制生成 `tracker.config.json`。按下表修改四项，保留原有序列号、光学和 IMU 校准以及其他字段。

| 字段 | 原值 | 目标值 |
| --- | --- | --- |
| `device_class` | `controller` | `generic_tracker` |
| `model_number` | `Vive. Controller MV` | `Vive. Tracker PVT` |
| `render_model` | `vr_controller_vive_1_5` | `vr_tracker_vive_1_0` |
| `tracked_controller_role` | 无此字段 | 空字符串 `""` |

在工具的 `lh>` 提示符下执行以下命令。先确认写入成功，再下载读回文件：

```text
uploadconfig tracker.config.json
downloadconfig tracker-readback.config.json
```

解析并比较目标与读回的完整 JSON，同时核对序列号以及原始配置与目标之间的字段差异。通过后执行 `reboot` 和 `quit`，重新打开 USB HID，独立读取到 `tracker-after-reboot.config.json`。

独立读回使用同一序列号的 HID 接口 0。先读取 feature report `0x10` 初始化配置读取，再循环读取 `0x11`。每帧第 2 字节是有效载荷长度，从第 3 字节取数据，长度为零时结束。将载荷拼接后用 zlib 解压，再比较完整 JSON。

## 实测结果

| 验证项 | 手柄 1 | 手柄 2 |
| --- | --- | --- |
| 原始配置两次读取及 Valve 工具备份一致 | 通过 | 通过 |
| 写入后完整配置与目标一致 | 通过 | 通过 |
| 发送重启命令后独立 HID 读回一致 | 通过 | 通过 |
| 设备类别与校准字段核对 | `generic_tracker`，校准保留 | `generic_tracker`，校准保留 |

两只设备的目标 JSON、工具读回和重启命令后读回各自具有相同的 SHA-256。原始配置与 Valve 工具导出的备份也各自具有相同的 SHA-256。

另外，用工具的 `battery` 命令测试了第二只手柄。充电期间先后读取到 63%、72% 和 82%，验证了电量与充电状态读取。按键、光学定位和无线续航未做测试。

## 恢复及 SteamVR 验收

恢复时只连接目标手柄，确认序列号后使用它自己的原始配置：

```text
uploadconfig original.config.json
downloadconfig restore-readback.config.json
```

核对读回 JSON 与原始备份一致，确认类别回到 `controller`，再执行 `reboot`。

实际使用还需在 SteamVR 逐只配对，确认每只都有可用的 Watchman 接收通道，在「管理追踪器」中分配角色，并与 Tracker 3.0 一起检查实际定位。

## 接收器

手柄变成 Tracker 之后，它不再通过头显里的无线接入，需要单独的 Watchman 接收器。用 nRF52840 Dongle 自制接收器时碰到的问题和解法见[本仓库首页](../README.md)：社区固件直接刷到这批板子上是跑不起来的，和操作无关。
