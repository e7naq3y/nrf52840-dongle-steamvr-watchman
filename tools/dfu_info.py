#!/usr/bin/env python
"""查询处于 Open DFU Bootloader 模式的 nRF52840 Dongle：芯片型号/版本、引导程序版本、当前有没有 SoftDevice / 应用。

用法: python dfu_info.py /dev/cu.usbmodemXXXX
依赖 ~/.venvs/nrf 里的 nrfutil 6.1.7（借用它的 SLIP/串口传输层）。
"""
import struct
import sys

from nordicsemi.dfu.dfu_transport_serial import DfuTransportSerial

OP_PROTOCOL_VERSION = 0x00
OP_HARDWARE_VERSION = 0x0A
OP_FIRMWARE_VERSION = 0x0B
OP_RESPONSE = 0x60

RESULT = {0x00: 'InvalidCode', 0x01: 'Success', 0x02: 'NotSupported', 0x03: 'InvalidParameter',
          0x04: 'InsufficientResources', 0x05: 'InvalidObject', 0x07: 'UnsupportedType',
          0x08: 'OperationNotPermitted', 0x0A: 'OperationFailed', 0x0B: 'ExtendedError'}
IMG_TYPE = {0: 'SoftDevice', 1: 'Application', 2: 'Bootloader', 3: 'Unknown'}


def cmd(t, payload):
    t.dfu_adapter.send_message(list(payload))
    resp = t.dfu_adapter.get_message()
    if resp is None or resp[0] != OP_RESPONSE or resp[1] != payload[0]:
        raise RuntimeError('bad response %r' % (resp,))
    if resp[2] != 0x01:
        return None, RESULT.get(resp[2], hex(resp[2])) + (' ext=0x%02x' % resp[3] if resp[2] == 0x0B and len(resp) > 3 else '')
    return bytes(resp[3:]), 'Success'


def main():
    port = sys.argv[1]
    t = DfuTransportSerial(com_port=port, baud_rate=115200, flow_control=False, timeout=5.0)
    t.open()
    try:
        data, st = cmd(t, [OP_PROTOCOL_VERSION])
        print('DFU protocol version:', data[0] if data else st)
        data, st = cmd(t, [OP_HARDWARE_VERSION])
        if data:
            part, variant, rom, ram, page = struct.unpack('<IIIII', data[:20])
            print('chip: part=nRF%X variant=%s rom=%dK ram=%dK page=%d' % (part, struct.pack('>I', variant).decode('ascii', 'replace'), rom // 1024, ram // 1024, page))
        else:
            print('hardware version:', st)
        for img in range(0, 4):
            data, st = cmd(t, [OP_FIRMWARE_VERSION, img])
            if not data:
                print('image #%d: %s' % (img, st))
                break
            typ, ver, addr, length = struct.unpack('<BIII', data[:13])
            print('image #%d: %-11s version=0x%08X (%d) addr=0x%05X len=%d' % (img, IMG_TYPE.get(typ, typ), ver, ver, addr, length))
            if typ == 3:
                break
    finally:
        t.close()


if __name__ == '__main__':
    main()
