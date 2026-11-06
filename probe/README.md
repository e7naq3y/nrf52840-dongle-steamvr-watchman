# 没有调试器时怎么看一个黑盒固件卡在哪

工具都是在 Mac 上现写的，只依赖 Xcode 自带的 clang（当汇编器用）和 Python 的 `capstone`、`intelhex`。

- `elf2bin.py <obj> <out.bin> <base>`：把 `clang -target thumbv7em-none-eabi -c x.s` 产出的 .o 变成放在 `base` 地址的裸二进制，自己处理 `R_ARM_ABS32` 重定位（Thumb 函数保留 bit0）。不用链接器、不用 arm-none-eabi 工具链。
- `hfxo_test8.s`：示例小程序。放在 SoftDevice 之后（0x26000），用板上绿灯"闪几下"当输出：读 UICR、读 `HFCLKSTAT`、按不同条件尝试起振。
- `instrument.py <app.bin> <out_prefix>`：LED 探针。往固件 `main()` 的若干 `bl` 调用点前插桩（桩先闪 N 下再 `ldr pc` 跳回原目标，保留 r0-r3），一次刷写就能知道固件跑到了第几步。`HOOKS` 表按自己反汇编出来的地址改。

打包刷写：

```bash
python elf2bin.py test.o test.bin 0x26000
python -c "from intelhex import IntelHex; ih=IntelHex(); ih.frombytes(open('test.bin','rb').read(), offset=0x26000); ih.write_hex_file('test.hex')"
nrfutil pkg generate --hw-version 52 --sd-req 0xB6 --application test.hex --application-version 2 test.zip
nrfutil dfu usb-serial -pkg test.zip -p /dev/cu.usbmodemXXXX -b 115200
```

注意：小程序**不要**放 0x1000 或伪装成 SoftDevice 去绕开真 SoftDevice——bootloader 跳转前关着中断发 SVC（升级为 HardFault 转发过来）、还有残留中断，没有完整异常处理的小程序一进去就死。放在真 SoftDevice 后面最省事。
