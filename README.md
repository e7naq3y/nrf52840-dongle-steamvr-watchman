# 55 块的 nRF52840 Dongle 刷 SteamVR 接收器：全网教程都说能用，我两块板子都刷不亮，最后发现是 3 个字节的事

> 关键词：nRF52840 Dongle · PCA10059 · SteamVR · Watchman Dongle · Vive Tracker · 全身追踪 · 刷不进去 / 刷完不识别 · nrfutil hw version does not match

你是不是也这样：

- 想把闲置的 Vive 手柄刷成 Tracker 做全身追踪，缺一个 SteamVR 接收器（Watchman Dongle），原厂的又贵又断货；
- 搜到日本大佬的 [watchman-uf2](https://github.com/ugokutennp/watchman-uf2) / [flowing-dongle-ccd](https://github.com/ugokutennp/flowing-dongle-ccd)，说 nRF52840 刷个固件就能当接收器；
- 拼多多 55 块买了块 **nRF52840 Dongle（PCA10059）**，结果：
  - 插上根本没有教程里说的 `FLOW_UF2` 盘；
  - 用 nrfutil 刷 Valve 的固件包报 `Extended Error 0x06: The hardware version of the device does not match`（Steam 论坛 2022 年就有人卡在这一步，至今没人回）；
  - 好不容易刷进去了，拔插一下——**灯不亮、电脑不识别、什么反应都没有**。

我也是。两块板子、十几次刷写、把 Valve 固件反汇编、往里插 LED 探针、手写 Thumb 汇编写小程序一条条试……最后发现社区的固件在这批板子上是**注定跑不起来**的，和你操作没关系。改 **3 个字节**，两块板子都变成了 `Watchman Radio`（Valve Corporation 28DE:2102）。

本文前半部分免费：把能踩的坑全写出来，附排查用的工具；
**根因 + 补丁 + 一键刷写包** 放在私有仓库，**Follow 我 + 给本仓库 Star** 自动解锁（见文末，全自动，几十秒）。

---

## 1. 为什么 PCA10059 不能照教程走

教程用的板子（MS88SF2 模块自制板、nrf52840-x3）预先用 J-Link 刷了 **Adafruit UF2 引导程序**，所以插上是个 U 盘，拖 uf2 就行。

PCA10059 出厂是 **Nordic Open Bootloader**：没有 U 盘，只有一个 `Open DFU Bootloader` 串口（按侧面小 RESET 进入，红灯呼吸）。要换成 UF2 引导必须 SWD 烧录，没有 J-Link 就别想了。

但 Open Bootloader 本身就能刷 SoftDevice + 应用，只是要自己打包：

```bash
# 固件来源：SteamVR\drivers\indexhmd\resources\firmware\radio\gd_1558748372_dfu.zip
#   里面的 s140_nrf52_6.1.1_softdevice.bin（放 0x1000）和 temp_app_stamped.bin（放 0x26000）
# 直接刷 Valve 的 zip 会报 hw version 不匹配 —— 因为 Valve 包里的 hw_version 不是 52。重新打包即可：
nrfutil pkg generate --hw-version 52 --sd-req 0x00 --sd-id 0xB6 \
    --softdevice sd.hex --application app.hex --application-version 1 out.zip
nrfutil dfu usb-serial -pkg out.zip -p /dev/cu.usbmodemXXXX -b 115200
```

坑 1：pip 默认装到的 `nrfutil 5.2.0` 是 Python 2 时代的代码，Python 3 下 `pkg generate` 直接崩。要 `pip install --no-deps --ignore-requires-python nrfutil==6.1.7`，再手动装 `pyserial crcmod ecdsa tqdm pyyaml click piccata libusb1 "protobuf<4" pyspinel`。

坑 2：`--sd-req 0x00 --sd-id 0xB6`（6.1.1 的 FWID 是 0xB6，不是 0xB7）。

刷完 bootloader 会说 `Device programmed.`，一切正常。然后——灯不亮，不识别。

## 2. 没有调试器怎么查一个黑盒固件

Open Bootloader 不能读内存，板子上也没 SWD 调试器。能用的只有：

1. **DFU 协议的隐藏命令**（`tools/dfu_info.py`）：问 bootloader 芯片型号、它看到的 SoftDevice/应用。于是知道了芯片是 nRF52840 **QIAAD0（Rev 2）**，bootloader 在 0xE0000，协议版本 1。
2. **手写 Thumb 汇编的小程序**（`probe/*.s` + `elf2bin.py`，用 Xcode 自带 clang 汇编，不用装交叉工具链），放在 SoftDevice 之后 0x26000，拿板上唯一的绿灯做输出：亮几下代表什么。
3. **LED 探针**（`probe/instrument.py`）：反汇编 Valve 固件找到 `main()`，在它的每个 `bl` 调用点前挂一个小桩，闪 N 下再跳回原函数。固件走到第几步，灯就闪到几。一次刷写就能二分出卡在哪。

LED 探针的结果：固件在 `main()` 开头
`nrf_drv_clock_hfclk_request()` 之后忙等 `HFCLKSTAT == 0x10001`——**在等 32MHz 晶振起振，永远等不到**。

用小程序单独验证：直接 `TASKS_HFCLKSTART`、先 STOP 再 START、改 `HFXODEBOUNCE`、让 SoftDevice 代劳……全部失败。换第二块全新的板（出厂带 SoftDevice 7.2.0）一样。可 bootloader 的 USB DFU 明明工作正常，而 nRF52840 的 USB 是必须用 32MHz 晶振的。

晶振在 bootloader 里起得来，在应用里起不来。差别在哪？

## 3. 排查里踩过的其它坑（省你几小时）

- Valve 固件把低频时钟配成 **SYNTH**（从 HFCLK 合成），所以 SoftDevice 启动也跟着依赖晶振；改成外部 32k 晶振（这板子有）是必要的，但**不够**。
- 想绕开 SoftDevice 测试，把小程序直接放 0x1000 或伪装成 SoftDevice：bootloader 跳转前会关着中断发 SVC（会升级成 HardFault 转给"SoftDevice"），还有残留中断，小程序一进去就进异常。别走这条路。
- `nrfutil pkg generate` 对 SoftDevice 镜像的 `--sd-req` 要写 `0x00`（板上没 SD 时），应用部分自动用 `--sd-id`。
- 用 SoftDevice 前把 `clock_lf_cfg` 从 SYNTH 改成 XTAL 之后，`sd_softdevice_enable` 正常返回了，但 USB 依旧不出来——问题在更前面。
- 板子随时按 RESET 回 DFU，bootloader 在 ACL 保护下应用写不坏，放心折腾。

## 4. 解锁：根因 + 3 字节补丁 + 现成刷写包

私有仓库里有：

- 根因分析（为什么这批板子的晶振在 bootloader 里能起、在应用里不能起，和 USB 外设的关系）；
- 完整补丁表（偏移、原值、新值、含义），以及从你自己的 SteamVR 目录生成补丁固件的脚本 `make_firmware.py`；
- 直接可刷的 `nrfutil` 包（DYX / LYX 两种启动模式，带/不带 SoftDevice）；
- Mac/Linux/Windows 的刷写步骤和 SteamVR 配对方法。

**解锁方式（全自动）**：

1. 先 **Follow** 本仓库作者；
2. 再给本仓库点 **Star**（顺序别反：Star 触发检查，检查时要已经在关注）；
3. 约 1 分钟内 GitHub 会给你发私有仓库的邀请邮件，接受即可。

没收到：确认关注了再取消 Star 重新点一次；或者在 Issues 留言。

---

## 附：手柄那一头怎么变 Tracker（Mac，免费）

接收器只是一半。把 Vive 手柄改成 `generic_tracker`（改 4 个配置字段，用 Valve 历史 macOS depot 里的 `lighthouse_console`，附校验方法）：[docs/vive-wand-to-tracker-mac.md](docs/vive-wand-to-tracker-mac.md)。

## 免责声明

- 固件版权归 Valve，SoftDevice 版权归 Nordic。本仓库只提供分析、脚本和排查工具，使用自担风险。
- 这些板子是拼多多上标 "nRF52840-Dongle PCA10059" 的克隆板，Nordic 原厂板未必有同样的问题。

## 致谢

- [ugokutennp](https://github.com/ugokutennp)：watchman-uf2 / flowing-dongle-ccd / nrf52840-x3
- [m-hayabusa 的 gist](https://gist.github.com/m-hayabusa/378a1dcf168b26b5d0f2cfbe906141c5)
- 排查工作由我和 Claude（Anthropic）一起完成，LED 探针和手写汇编小程序都是现场写的。
