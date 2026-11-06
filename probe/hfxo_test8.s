/* 诊断 8：绿灯 LED1=P0.06 低有效。
   亮1s→灭1s
   第1组：UICR.REGOUT0 电压：2下=3.0V 3下=3.3V 4下=出厂默认(1.8V) 5下=其它
   第2组：HFCLKSTAT：2=晶振已跑 3=只有RC 4=其它
   A: 直接 HFCLKSTART 等1s            成功→慢闪
   U: 先 USBD.ENABLE=1 等50ms 再 START 等1s   成功→五下五下
   D: POWER.DCDCEN=1 再 START 等1s     成功→六下六下
   全失败→快闪 */
    .syntax unified
    .cpu cortex-m4
    .thumb
    .section .text,"ax",%progbits

    .word 0x20040000
    .word reset_handler
    .rept 62
    .word default_handler
    .endr

    .thumb_func
default_handler:
    b default_handler

    .thumb_func
reset_handler:
    ldr r4, =0x50000000
    movs r0, #3
    str r0, [r4, #0x718]
    movs r5, #0x40
    ldr r6, =0x40000000

    bl led_on
    ldr r0, =0x1400000
    bl delay
    bl led_off
    ldr r0, =0x1400000
    bl delay

    /* 第1组 REGOUT0 */
    ldr r0, =0x10001304
    ldr r0, [r0]
    and r0, r0, #7
    cmp r0, #5
    beq v2
    cmp r0, #6
    beq v3
    cmp r0, #7
    beq v4
    movs r7, #5
    b g1
v2: movs r7, #2
    b g1
v3: movs r7, #3
    b g1
v4: movs r7, #4
g1: bl blink_n
    ldr r0, =0x1400000
    bl delay

    /* 第2组 HFCLKSTAT */
    ldr r0, [r6, #0x40C]
    ldr r1, =0x10001
    cmp r0, r1
    beq st2
    cmp r0, #0x10000
    beq st3
    movs r7, #4
    b g2
st2: movs r7, #2
    b g2
st3: movs r7, #3
g2: bl blink_n
    ldr r0, =0x1400000
    bl delay

    /* A */
    movs r0, #1
    str r0, [r6, #0x000]
    bl wait_hfxo
    cbz r0, tryU
    movs r7, #1
    b pattern_forever
tryU:
    ldr r2, =0x40027500         /* USBD.ENABLE */
    movs r0, #1
    str r0, [r2]
    ldr r0, =0x100000
    bl delay
    movs r0, #1
    str r0, [r6, #0x000]
    bl wait_hfxo
    cbz r0, tryD
    movs r7, #5
    b pattern_forever
tryD:
    movs r0, #1
    str r0, [r6, #0x578]        /* POWER.DCDCEN */
    ldr r0, =0x100000
    bl delay
    movs r0, #1
    str r0, [r6, #0x000]
    bl wait_hfxo
    cbz r0, fast_forever
    movs r7, #6
    b pattern_forever

    .thumb_func
wait_hfxo:
    push {r1, r2, lr}
    ldr r1, =0x10001
    ldr r2, =0x200000
1:  ldr r0, [r6, #0x40C]
    cmp r0, r1
    beq 2f
    subs r2, r2, #1
    bne 1b
    movs r0, #0
    pop {r1, r2, pc}
2:  movs r0, #1
    pop {r1, r2, pc}

pattern_forever:
    bl blink_n
    ldr r0, =0xE00000
    bl delay
    b pattern_forever

    .thumb_func
blink_n:
    push {r4, r5, r6, lr}
    mov r6, r7
3:  bl led_on
    ldr r0, =0x300000
    bl delay
    bl led_off
    ldr r0, =0x300000
    bl delay
    subs r6, r6, #1
    bne 3b
    pop {r4, r5, r6, pc}

fast_forever:
    bl led_on
    ldr r0, =0x200000
    bl delay
    bl led_off
    ldr r0, =0x200000
    bl delay
    b fast_forever

    .thumb_func
led_on:
    str r5, [r4, #0x50C]
    bx lr
    .thumb_func
led_off:
    str r5, [r4, #0x508]
    bx lr
    .thumb_func
delay:
5:  subs r0, r0, #1
    bne 5b
    bx lr
    .ltorg
