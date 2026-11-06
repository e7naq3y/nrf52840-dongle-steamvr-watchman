#!/usr/bin/env python
"""往 Valve 固件 main() 的若干 bl 调用点插 LED 进度探针：
探针 k 先让 LED1(P0.06) 闪 k 下（k=10 则常亮 2 秒），再原样跳到原来的目标函数。
看到最后一个闪的次数，就知道卡在哪一段。

用法: python instrument.py <in.bin> <out_prefix>
"""
import struct, subprocess, sys, tempfile, os
from capstone import *
from intelhex import IntelHex

APP = 0x26000
# (调用点地址, 探针编号)  —— 全在 main() 里，按执行顺序
HOOKS = [
    (0x3efd8, 1),   # nrf_drv_clock_init 之前：main 进来了
    (0x3f008, 2),   # LFCLK/HFCLK 两个忙等都过了
    (0x3f020, 3),
    (0x3f042, 4),
    (0x3f080, 5),
    (0x3f0ae, 6),
    (0x3f0d0, 7),
    (0x3f0fc, 8),   # 日志刷完
    (0x3f148, 9),   # 进 USB/模式初始化 (0x2a8cc)
    (0x3f154, 10),  # 初始化全部结束，马上进主循环 → 常亮 2 秒
]

STUB_SRC = r"""
    .syntax unified
    .cpu cortex-m4
    .thumb
    .section .text,"ax",%%progbits
    push {r0-r3, lr}
    ldr r3, =0x50000000
    movs r0, #3
    str r0, [r3, #0x718]
    movs r2, #0x40
    movs r1, #%(k)d
    cmp r1, #10
    beq solid
1:  str r2, [r3, #0x50C]
    ldr r0, =0x300000
2:  subs r0, r0, #1
    bne 2b
    str r2, [r3, #0x508]
    ldr r0, =0x300000
3:  subs r0, r0, #1
    bne 3b
    subs r1, r1, #1
    bne 1b
    b done
solid:
    str r2, [r3, #0x50C]
    ldr r0, =0x2800000
5:  subs r0, r0, #1
    bne 5b
    str r2, [r3, #0x508]
done:
    ldr r0, =0xC00000
4:  subs r0, r0, #1
    bne 4b
    pop {r0-r3, lr}
    ldr pc, =%(target)#x
    .ltorg
"""


def elf_text(path):
    d = open(path, 'rb').read()
    shoff, = struct.unpack_from('<I', d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x2e)
    shs = [struct.unpack_from('<IIIIIIIIII', d, shoff + i * shentsize) for i in range(shnum)]
    strtab = shs[shstrndx]
    name = lambda off: d[strtab[4] + off:d.index(b'\0', strtab[4] + off)].decode()
    assert not any(name(s[0]).startswith('.rel') for s in shs), 'stub has relocations'
    for s in shs:
        if name(s[0]) == '.text':
            return d[s[4]:s[4] + s[5]]
    raise SystemExit('no .text')


def asm(src):
    with tempfile.TemporaryDirectory() as td:
        s = os.path.join(td, 'stub.s'); o = os.path.join(td, 'stub.o')
        open(s, 'w').write(src)
        subprocess.check_call(['xcrun', 'clang', '-target', 'thumbv7em-none-eabi', '-mcpu=cortex-m4', '-mthumb', '-c', s, '-o', o])
        return elf_text(o)


def encode_bl(site, target):
    off = target - (site + 4)
    assert -16777216 <= off < 16777216 and off % 2 == 0
    s = 1 if off < 0 else 0
    off &= 0x1ffffff
    imm10 = (off >> 12) & 0x3ff
    imm11 = (off >> 1) & 0x7ff
    i1 = (off >> 23) & 1
    i2 = (off >> 22) & 1
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = 0xD000 | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack('<HH', hw1, hw2)


def main():
    app = bytearray(open(sys.argv[1], 'rb').read())
    out = sys.argv[2]
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    md.detail = True
    cave = APP + len(app)
    assert cave % 4 == 0
    for site, k in HOOKS:
        ins = next(md.disasm(bytes(app[site - APP:site - APP + 4]), site))
        assert ins.mnemonic == 'bl', (hex(site), ins.mnemonic)
        target = ins.operands[0].imm
        stub = asm(STUB_SRC % {'k': k, 'target': target | 1})
        while len(stub) % 4: stub += b'\0'
        stub_addr = cave + 0  # 当前末尾
        app += stub
        cave = APP + len(app)
        app[site - APP:site - APP + 4] = encode_bl(site, stub_addr)
        chk = next(md.disasm(bytes(app[site - APP:site - APP + 4]), site))
        assert chk.mnemonic == 'bl' and chk.operands[0].imm == stub_addr, (chk.mnemonic, hex(chk.operands[0].imm), hex(stub_addr))
        # 核对 stub 最后的 ldr pc 字面量
        last = list(md.disasm(bytes(stub), stub_addr))
        ldrpc = [i for i in last if i.mnemonic in ('ldr', 'ldr.w') and i.op_str.startswith('pc,')][-1]
        lit = ((ldrpc.address + 4) & ~3) + ldrpc.operands[1].mem.disp
        val = struct.unpack_from('<I', app, lit - APP)[0]
        assert val == (target | 1), (hex(val), hex(target))
        print('hook %2d: site %#x  orig target %#x  -> stub @%#x (%d bytes)' % (k, site, target, stub_addr, len(stub)))
    open(out + '.bin', 'wb').write(app)
    ih = IntelHex(); ih.frombytes(bytes(app), offset=APP); ih.write_hex_file(out + '.hex')
    print('image now %#x..%#x (%d bytes)' % (APP, APP + len(app), len(app)))


if __name__ == '__main__':
    main()
