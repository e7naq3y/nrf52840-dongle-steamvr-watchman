# 把 clang 产出的单段 ELF .o 变成放在 BASE 的裸二进制：自己处理 R_ARM_ABS32 重定位（Thumb 函数符号保留 bit0）
import struct, sys
BASE=int(sys.argv[3],16)
d=open(sys.argv[1],'rb').read()
shoff,=struct.unpack_from('<I',d,0x20); shentsize,shnum,shstrndx=struct.unpack_from('<HHH',d,0x2e)
shs=[struct.unpack_from('<IIIIIIIIII',d,shoff+i*shentsize) for i in range(shnum)]
def name(off,tab): return d[tab[4]+off:d.index(b'\0',tab[4]+off)].decode()
shstr=shs[shstrndx]
sec={name(s[0],shstr):s for s in shs}
text=bytearray(d[sec['.text'][4]:sec['.text'][4]+sec['.text'][5]])
symtab=sec['.symtab']; strtab=shs[symtab[6]]
syms=[struct.unpack_from('<IIIBBH',d,symtab[4]+i*16) for i in range(symtab[5]//16)]
rel=sec.get('.rel.text')
n=0
if rel:
    for i in range(rel[5]//8):
        r_off,r_info=struct.unpack_from('<II',d,rel[4]+i*8)
        rtype=r_info&0xff; symi=r_info>>8
        st_name,st_value,st_size,st_info,st_other,st_shndx=syms[symi]
        assert rtype==2, ('unsupported reloc type',rtype)
        addend,=struct.unpack_from('<I',text,r_off)
        val=(BASE+st_value+addend)&0xffffffff
        if (st_info&0xf)==2 and not (val&1): val|=1     # STT_FUNC → Thumb
        struct.pack_into('<I',text,r_off,val); n+=1
        print('  reloc @%#x sym=%-16s st_value=%#x addend=%#x -> %#x'%(r_off,name(st_name,strtab) or '<sec>',st_value,addend,val))
print('relocs applied:',n)
open(sys.argv[2],'wb').write(text)
