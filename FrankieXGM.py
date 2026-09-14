#!/usr/bin/env python3
"""FrankieXGM 1.0.0 - Convert Genesis VGM/VGZ (YM2612 + SN76489 + SegaPCM) to XGM 1.01.

- Converts YM2612 port 0/1 writes to XGM FM commands.
- Converts SN76489 writes to XGM PSG commands.
- Converts SegaPCM voices 0..3 to XGM PCM channels 0..3.
- Suppresses all YM2612 channel 6 / DAC activity because XGM uses that DAC
  path for the four software-mixed PCM channels.
- Preserves the VGM GD3 chunk verbatim when present.
"""
from __future__ import annotations
import argparse, gzip, struct, math
from dataclasses import dataclass, field
from pathlib import Path

XGM_RATE = 14000
MAX_XGM_SAMPLES = 63
PCM_AUTO_TARGET_RMS = 0.18       # ~= -14.9 dBFS; a useful Genesis-mix ballpark
PCM_PEAK_CEILING = 0.7071        # -3 dBFS safety ceiling

@dataclass
class Block:
    start: int
    data: bytes

@dataclass
class Voice:
    regs: bytearray = field(default_factory=lambda: bytearray([0xFF]*0x88))
    active: bool = False
    start_addr: int = 0
    loop_addr: int = 0
    end_addr: int = 0xFF
    freq: int = 0xFF
    lvol: int = 0xFF
    rvol: int = 0xFF
    ctrl: int = 0xFF
    chip_rate: int = 4_000_000
    bank_shift: int = 12
    bank_mask: int = 0x70


def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def load_vgm(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
    if raw[:4] != b'Vgm ': raise ValueError('not a VGM/VGZ file')
    return raw

def vgm_version(vgm):
    if len(vgm) < 0x0C:
        raise ValueError("truncated VGM header: need at least 0x0C bytes")
    return u32(vgm, 0x08)

def version_text(ver):
    return f"{(ver >> 8) & 0xFF}.{ver & 0xFF:02X}"

def validate_vgm(vgm):
    """Validate the VGM header/stream before conversion.

    Full YM2612 + SN76489 + SegaPCM conversion requires VGM 1.51 or newer.
    Older VGMs remain usable for YM2612/PSG-only conversion when their command
    stream is otherwise valid; if SegaPCM is actually present, fail explicitly
    instead of silently interpreting a newer command/header field as legacy data.
    """
    if len(vgm) < 0x40:
        raise ValueError("truncated VGM header: file is shorter than 0x40 bytes")
    if vgm[:4] != b'Vgm ':
        raise ValueError("not a VGM/VGZ file")
    ver = vgm_version(vgm)
    if ver == 0:
        raise ValueError("invalid VGM version 0.00")

    eof = eof_offset(vgm)
    if eof < 0x40 or eof > len(vgm):
        raise ValueError(f"invalid VGM EOF offset: 0x{eof:X}")
    data = data_offset(vgm)
    if data < 0x40 or data >= eof:
        raise ValueError(f"invalid VGM data offset: 0x{data:X}")

    # VGM 1.50 introduced the data-offset field. Older files use the fixed
    # 0x40 command-stream start. Reject a non-zero offset in a pre-1.50 file.
    if ver < 0x150 and u32(vgm, 0x34) != 0:
        raise ValueError(f"VGM {version_text(ver)} has a non-zero data offset; expected 0 for pre-1.50 VGM")

    # Parse enough of the stream to validate command boundaries and identify
    # SegaPCM usage. This also catches truncated data blocks before conversion.
    p = data
    has_segapcm = False
    while p < eof:
        c = vgm[p]
        if c == 0x66:
            break
        if c == 0x67:
            if p + 7 > eof or vgm[p+1] != 0x66:
                raise ValueError(f"invalid VGM data block at 0x{p:X}")
            ln = u32(vgm, p+3)
            q = p + 7 + ln
            if q > eof:
                raise ValueError(f"truncated VGM data block at 0x{p:X}")
            if vgm[p+2] == 0x80:
                has_segapcm = True
            p = q
            continue
        if c == 0xC0:
            has_segapcm = True
        try:
            n = command_length(vgm, p)
        except (IndexError, struct.error):
            raise ValueError(f"truncated VGM command 0x{c:02X} at 0x{p:X}")
        if n <= 0 or p + n > eof:
            raise ValueError(f"truncated VGM command 0x{c:02X} at 0x{p:X}")
        p += n

    if p >= eof:
        raise ValueError("VGM command stream has no end command (0x66)")

    if ver < 0x151 and has_segapcm:
        raise ValueError(
            f"VGM {version_text(ver)} contains SegaPCM data, but SegaPCM requires VGM 1.51 or newer; "
            "use a VGM 1.51+ file for SegaPCM conversion"
        )

    return ver, has_segapcm

def data_offset(vgm):
    off = u32(vgm, 0x34)
    return 0x40 if off == 0 else 0x34 + off

def eof_offset(vgm):
    rel = u32(vgm, 0x04)
    return min(0x04 + rel if rel else len(vgm), len(vgm))

def gd3_chunk(vgm, eof):
    if len(vgm) < 0x18: return b''
    rel = u32(vgm, 0x14)
    if not rel: return b''
    pos = 0x14 + rel
    if pos < data_offset(vgm) or pos + 12 > eof or vgm[pos:pos+4] != b'Gd3 ':
        return b''
    size = u32(vgm, pos + 8)
    end = min(eof, pos + 12 + size)
    return bytes(vgm[pos:end])

def command_length(b, p):
    c=b[p]
    if c in (0x00,0x62,0x63,0x66): return 1
    if c in (0x4F,0x50): return 2
    if 0x51 <= c <= 0x5F: return 3
    if 0x30 <= c <= 0x3F: return 2
    if 0x40 <= c <= 0x4E: return 3
    if c == 0x61: return 3
    if 0x70 <= c <= 0x7F: return 1
    if 0x80 <= c <= 0x8F: return 1
    if c == 0x67: return 7 + u32(b,p+3)
    if c == 0x68: return 12
    if 0x90 <= c <= 0x92: return 5
    if 0x93 <= c <= 0x95: return 2
    if 0xA0 <= c <= 0xAF: return 3
    if 0xB0 <= c <= 0xBF: return 3
    if 0xC0 <= c <= 0xCF: return 4
    if 0xD0 <= c <= 0xDF: return 4
    if c == 0xE0: return 5
    if 0xE1 <= c <= 0xFF: return 5
    raise ValueError(f'unsupported/unknown VGM command 0x{c:02X} at 0x{p:X}')

def collect_segapcm_rom(vgm, end):
    blocks=[]; p=data_offset(vgm)
    while p < end:
        c=vgm[p]
        if c==0x67:
            if p+7>end or vgm[p+1]!=0x66: raise ValueError(f'bad data block at 0x{p:X}')
            typ=vgm[p+2]; ln=u32(vgm,p+3); q=p+7
            if q+ln>end: raise ValueError('truncated data block')
            if typ==0x80 and ln>=8:
                blocks.append(Block(u32(vgm,q+4), bytes(vgm[q+8:q+ln])))
            p=q+ln; continue
        p += command_length(vgm,p)
    return blocks

def rom_read(blocks, addr):
    for blk in blocks:
        if blk.start <= addr < blk.start+len(blk.data): return blk.data[addr-blk.start]
    return 0x80

def sega_bank(ctrl, bank_mask=0x70, bank_shift=12):
    return (ctrl & bank_mask) << bank_shift

def clone_voice(v):
    return Voice(bytearray(v.regs),v.active,v.start_addr,v.loop_addr,v.end_addr,v.freq,
                 v.lvol,v.rvol,v.ctrl,v.chip_rate,v.bank_shift,v.bank_mask)

def render_segment(blocks, v, duration_seconds, max_samples=8_000_000):
    # This is intentionally the v0.3.11 PCM renderer: keep the working sample
    # identification/timing behavior unchanged while adding FM/PSG support.
    n=max(1,min(max_samples,int(round(duration_seconds*XGM_RATE))))
    out=bytearray(n)
    chip_tick_rate=v.chip_rate/128.0
    source_rate=chip_tick_rate*max(1,v.freq)/256.0
    source_step=source_rate/XGM_RATE
    pos=float(v.start_addr & 0xFFFFFF)
    loop=float((v.loop_addr & 0xFFFF)<<8)
    scale=((v.lvol&0x7f)+(v.rvol&0x7f))/254.0
    bank=sega_bank(v.ctrl,v.bank_mask,v.bank_shift)
    active=True
    def sample_at(fp):
        a0=int(fp)&0xFFFFFF; frac=(a0&0xFF)/256.0
        s0=rom_read(blocks,bank+((a0>>8)&0xFFFFFF))-128
        a1=(a0+0x100)&0xFFFFFF
        s1=rom_read(blocks,bank+((a1>>8)&0xFFFFFF))-128
        return s0+(s1-s0)*frac
    for i in range(n):
        page=(int(pos)>>16)&0xff
        if page==((v.end_addr+1)&0xff):
            if v.ctrl&0x02: active=False
            else: pos=loop
        if active:
            val=max(-128,min(127,int(round(sample_at(pos)*scale))))
            out[i]=val&0xff
        pos=(pos+source_step*256.0)%0x1000000
    return bytes(out)

def pcm_gain_data(data, mode=None, manual_db=0.0):
    """Apply optional PCM loudness balancing while preserving the 8-bit format.

    Automatic mode first targets a conservative RMS level representative of a
    healthy FM/PSG instrument in a Genesis mix, then limits the resulting peak
    to -3 dBFS. Manual mode applies the requested dB gain and uses the same
    peak ceiling as a safety limiter.
    """
    if not data or mode is None:
        return data, 1.0
    vals=[b-256 if b >= 128 else b for b in data]
    peak=max((abs(x) for x in vals), default=0) / 127.0
    if peak == 0:
        return data, 1.0
    if mode == 'auto':
        mean_sq=sum((x/127.0)*(x/127.0) for x in vals) / len(vals)
        rms=math.sqrt(mean_sq)
        if rms <= 1e-9:
            return data, 1.0
        gain=PCM_AUTO_TARGET_RMS / rms
    elif mode == 'manual':
        gain=10.0 ** (manual_db / 20.0)
    else:
        return data, 1.0
    if peak * gain > PCM_PEAK_CEILING:
        gain=PCM_PEAK_CEILING / peak
    if abs(gain-1.0) < 1e-9:
        return data, gain
    out=bytearray(len(data))
    for i,b in enumerate(vals):
        out[i]=max(-128,min(127,int(round(b*gain)))) & 0xff
    return bytes(out), gain

def native_duration(v):
    start=v.start_addr&0xFFFFFF
    end=((v.end_addr+1)&0xff)<<16
    distance=(end-start)&0xFFFFFF
    if distance==0: distance=0x1000000
    return (distance/max(1,v.freq))/(v.chip_rate/128.0)

def is_ym2612_ch6(port, reg):
    """True for registers belonging to YM2612 channel 6 (port 1, channel 2).
    Also catches channel-6 key on/off via $28 separately elsewhere.
    """
    if port != 1: return False
    # Operator registers: low nibble selects operator, high nibble is group;
    # channel is encoded by the low 2 bits for 0x30..0x9F.
    if 0x30 <= reg <= 0x9F:
        return (reg & 0x03) == 0x02
    if reg in (0xA2,0xA6,0xB2,0xB6):
        return True
    return False

def is_key_for_ch6(port, data):
    # YM2612 $28 encodes the channel in bits 0-1 and the channel bank in
    # bit 2: bank 0 = channels 1-3, bank 1 = channels 4-6.  Thus Genesis
    # channel 3 is data values 0x02/0x06 (OFF/ON), while channel 6 is the
    # same low channel number with bit 2 set.  The old test looked only at
    # the low two bits and accidentally discarded every channel-3 key event.
    return (data & 0x07) == 0x06

def ym_can_ignore(port, reg):
    # Match SGDK YM2612_canIgnore(): only the useful operator/frequency
    # registers and a few port-0 global registers are retained.
    if reg in (0x22,0x24,0x25,0x26,0x27,0x28,0x2B):
        return port == 1
    if 0x30 <= reg < 0xB8:
        return (reg & 3) == 3
    return True

YM_DUALS = ((0x24,0x25),(0xA4,0xA0),(0xA5,0xA1),(0xA6,0xA2),(0xAC,0xA8),(0xAD,0xA9),(0xAE,0xAA))

def collect_loop_state(vgm, data_end, loop_byte_offset):
    ym=[[None]*0x100 for _ in range(2)]; yi=[[False]*0x100 for _ in range(2)]
    psg=[[None,None] for _ in range(4)]; pi=[[False,False] for _ in range(4)]
    pidx=ptype=-1; p=data_offset(vgm)
    while p < loop_byte_offset and p < data_end:
        c=vgm[p]
        if c in (0x52,0x53):
            port=0 if c==0x52 else 1; reg,val=vgm[p+1],vgm[p+2]
            ch6=(port==1 and ((0x30<=reg<=0x9F and (reg&3)==2) or reg in (0xA2,0xA6,0xB2,0xB6)))
            if not ym_can_ignore(port,reg) and reg not in (0x2A,0x2B) and not ch6:
                ym[port][reg]=val; yi[port][reg]=True
            p+=3; continue
        if c==0x50:
            val=vgm[p+1]; x=val&0x7F
            if val&0x80:
                pidx=(x>>5)&3; ptype=(x>>4)&1
                old=psg[pidx][ptype] if psg[pidx][ptype] is not None else 0
                mask=7 if ptype==0 and pidx==3 else 0xF
                psg[pidx][ptype]=(old & ~mask)|(x&mask); pi[pidx][ptype]=True
            elif pidx>=0 and ptype>=0:
                old=psg[pidx][ptype] if psg[pidx][ptype] is not None else 0
                if ptype==0 and pidx==3: psg[pidx][ptype]=(old&~7)|(x&7)
                elif ptype==0: psg[pidx][ptype]=(old&~0x3F0)|((x&0x3F)<<4)
                else: psg[pidx][ptype]=(old&~0xF)|(x&0xF)
                pi[pidx][ptype]=True
            p+=2; continue
        if c==0x67: p+=7+u32(vgm,p+3); continue
        if c==0x68: p+=12; continue
        if c==0x61: p+=3; continue
        if c in (0x62,0x63) or 0x70<=c<=0x7F or 0x80<=c<=0x8F or c==0x66: p+=1; continue
        p+=command_length(vgm,p)
    ye=[]; paired={r for pair in YM_DUALS for r in pair}
    for port,pairs in ((0,YM_DUALS),(1,tuple((a,b) for a,b in YM_DUALS if a>0x30))):
        for a,b in pairs:
            for reg in (a,b):
                if yi[port][reg] and not ym_can_ignore(port,reg): ye.append((port,reg,ym[port][reg]))
    for port in range(2):
        for reg in range(0x100):
            if not yi[port][reg] or ym_can_ignore(port,reg) or (port==0 and reg==0x28) or reg in paired: continue
            if port==1 and ((0x30<=reg<=0x9F and (reg&3)==2) or reg in (0xA2,0xA6,0xB2,0xB6,0x2A,0x2B)): continue
            ye.append((port,reg,ym[port][reg]))
    pe=[]
    for ind in range(4):
        for typ in range(2):
            if not pi[ind][typ]: continue
            val=psg[ind][typ] or 0
            pe.append(0x80|(ind<<5)|(typ<<4)|(val&(7 if ind==3 and typ==0 else 0xF)))
            if typ==0 and ind!=3: pe.append((val>>4)&0x3F)
    return ye,pe

def raw_vgm_command_count(vgm, data_end):
    p=data_offset(vgm); n=0
    while p < data_end:
        c=vgm[p]; n += 1
        if c == 0x66: break
        p += command_length(vgm, p)
    return n

def _ym_state_new():
    return [[None]*0x100 for _ in range(2)]

def _ym_apply(state, port, reg, val):
    if ym_can_ignore(port, reg) or (port == 0 and reg == 0x28):
        return
    if port == 0 and reg == 0x27:
        val &= 0xC0
    state[port][reg] = val

def _ym_get_delta(old, new):
    out=[]
    duals=((0x24,0x25),(0xA4,0xA0),(0xA5,0xA1),(0xA6,0xA2),(0xAC,0xA8),(0xAD,0xA9),(0xAE,0xAA))
    for a,b in duals:
        if old[0][a] != new[0][a] or old[0][b] != new[0][b]:
            if new[0][a] is not None: out.append(('ym',(0,a,new[0][a])))
            if new[0][b] is not None: out.append(('ym',(0,b,new[0][b])))
        if a > 0x30 and (old[1][a] != new[1][a] or old[1][b] != new[1][b]):
            if new[1][a] is not None: out.append(('ym',(1,a,new[1][a])))
            if new[1][b] is not None: out.append(('ym',(1,b,new[1][b])))
    paired={r for pair in duals for r in pair}
    for port in range(2):
        for reg in range(0x100):
            if reg in paired or ym_can_ignore(port,reg) or (port==0 and reg==0x28):
                continue
            if old[port][reg] != new[port][reg] and new[port][reg] is not None:
                out.append(('ym',(port,reg,new[port][reg])))
    return out

def _psg_new():
    return [[None,None] for _ in range(4)]

def _psg_apply(state, latch, val):
    v=val & 0x7F
    if val & 0x80:
        ind=(v>>5)&3; typ=(v>>4)&1
        latch=(ind,typ)
        old=state[ind][typ] if state[ind][typ] is not None else 0
        if typ==0 and ind==3: state[ind][typ]=(old & ~7)|(v&7)
        else: state[ind][typ]=(old & ~0xF)|(v&0xF)
    elif latch[0] >= 0:
        ind,typ=latch; old=state[ind][typ] if state[ind][typ] is not None else 0
        if typ==0 and ind==3: state[ind][typ]=(old&~7)|(v&7)
        elif typ==1: state[ind][typ]=(old&~0xF)|(v&0xF)
        else: state[ind][typ]=(old&~0x3F0)|((v&0x3F)<<4)
    return latch

def _psg_delta(old,new):
    out=[]
    for ind in range(4):
        for typ in range(2):
            ov=old[ind][typ]; nv=new[ind][typ]
            if nv is None or ov == nv: continue
            if typ==0 and ind != 3 and ov is not None and ((ov&0x3F0)==(nv&0x3F0)):
                out.append(('psg',0x80|(ind<<5)|(typ<<4)|(nv&0xF)))
            else:
                out.append(('psg',0x80|(ind<<5)|(typ<<4)|(nv&(7 if ind==3 and typ==0 else 0xF))))
                if typ==0 and ind!=3: out.append(('psg',(nv>>4)&0x3F))
    return out

def clean_chip_events(chip_events, rate, loop_frame, boundaries=None, delay_key_off=True):
    by_frame={}
    for ts,order,f,kind,args in chip_events:
        by_frame.setdefault(f,[]).append((ts,order,kind,args))

    # XGMTool's default delayed-key-off behavior: when a key-on and a later
    # key-off for the same FM channel occur in one frame and the key-off is
    # sufficiently far from the key-on, defer the key-off to the following
    # frame. This avoids an unnecessarily early cut caused by frame packing.
    if delay_key_off:
        max_delta = 44100.0 / rate / 4.0
        for frame in sorted(list(by_frame)):
            evs = sorted(by_frame[frame], key=lambda x:(x[0],x[1]))
            key_on_time = {}
            kept = []
            delayed = []
            for ev in evs:
                ts, order, kind, args = ev
                if kind != 'ymkey':
                    kept.append(ev)
                    continue
                port, val = args
                # YM key command channel is bits 0..2; bit 2 selects channel
                # 6 on the special $28 command encoding.
                ch = val & 0x07
                on = bool(val & 0xF0)
                off = not on
                if on:
                    key_on_time[(port, ch)] = ts
                    kept.append(ev)
                elif off and (port, ch) in key_on_time and (ts - key_on_time[(port, ch)]) > max_delta:
                    delayed.append((0, order, kind, args))
                else:
                    kept.append(ev)
            by_frame[frame] = kept
            if delayed:
                by_frame.setdefault(frame + 1, []).extend(delayed)

    old_ym=_ym_state_new(); old_psg=_psg_new(); latch=(-1,-1); cleaned={}
    for frame in sorted(by_frame):
        is_loop_frame = loop_frame is not None and frame == loop_frame
        # XGMTool resets only the *previous/delta* state when it encounters the
        # loop marker. The current frame state is still copied from the state
        # established before that marker. Thus the loop-target frame emits a
        # complete delta from an empty state, while retaining all register
        # values already active at the jump point.
        cur_ym=[row[:] for row in old_ym]; cur_psg=[row[:] for row in old_psg]
        emitted_ym=_ym_state_new() if is_loop_frame else [row[:] for row in old_ym]
        emitted_psg=_psg_new() if is_loop_frame else [row[:] for row in old_psg]
        if is_loop_frame:
            latch=(-1,-1)
        frame_out=[]
        evs=sorted(by_frame[frame], key=lambda x:(x[0],x[1]))
        for ts,order,kind,args in evs:
            if kind=='ym':
                _ym_apply(cur_ym,*args)
            elif kind=='ymkey':
                for knd,karg in _ym_get_delta(emitted_ym,cur_ym):
                    frame_out.append((ts,order,knd,karg)); _ym_apply(emitted_ym,*karg)
                frame_out.append((ts,order,'ymkey',args))
            elif kind=='psg':
                latch=_psg_apply(cur_psg,latch,args)
        for knd,karg in _ym_get_delta(emitted_ym,cur_ym):
            frame_out.append((0,0,knd,karg))
        for knd,karg in _psg_delta(emitted_psg,cur_psg):
            frame_out.append((0,0,knd,karg))
        frame_out.sort(key=lambda x:(x[0],x[1]))
        cleaned[frame]=frame_out
        old_ym=cur_ym; old_psg=cur_psg
    return cleaned

def parse_timeline(vgm, data_end, chip_rate, bank_shift, bank_mask, rate):
    voices=[Voice() for _ in range(16)]
    for v in voices:
        v.chip_rate=chip_rate; v.bank_shift=bank_shift; v.bank_mask=bank_mask
    pcm=[[] for _ in range(16)]
    chip_events=[]  # (sample_time, order, kind, args)
    samples=0; order=0; p=data_offset(vgm)
    frame=0; sample_cnt=0.0; limit=44100.0/rate; min_limit=limit*0.85
    loop_abs=(0x1C+u32(vgm,0x1C)) if u32(vgm,0x1C) else None
    loop_frame=None
    while p < data_end:
        if loop_frame is None and loop_abs is not None and p >= loop_abs:
            loop_frame=frame
        c=vgm[p]
        if c==0x66: break
        if c==0x61:
            w=vgm[p+1]|vgm[p+2]<<8; samples += w; sample_cnt += w; p+=3
            while sample_cnt > min_limit: sample_cnt -= limit; frame += 1
            continue
        if c==0x62:
            samples += 735; sample_cnt += 735; p+=1
            while sample_cnt > min_limit: sample_cnt -= limit; frame += 1
            continue
        if c==0x63:
            samples += 882; sample_cnt += 882; p+=1
            while sample_cnt > min_limit: sample_cnt -= limit; frame += 1
            continue
        if 0x70<=c<=0x7F:
            w=(c&0x0f)+1; samples += w; sample_cnt += w; p+=1
            while sample_cnt > min_limit: sample_cnt -= limit; frame += 1
            continue
        if 0x80<=c<=0x8F:
            # YM2612 DAC byte + wait: deliberately suppress DAC data because
            # XGM reserves FM channel 6 for its PCM mixer, but retain timing.
            w=c&0x0f; samples += w; sample_cnt += w; p+=1
            while sample_cnt > min_limit: sample_cnt -= limit; frame += 1
            continue
        if c==0x67: p+=7+u32(vgm,p+3); continue
        if c==0x68: p+=12; continue
        if c==0x50:
            chip_events.append((samples,order,frame,'psg',vgm[p+1])); order+=1; p+=2; continue
        if c in (0x52,0x53):
            port=0 if c==0x52 else 1; reg=vgm[p+1]; val=vgm[p+2]
            if reg==0x2B or reg==0x2A or is_ym2612_ch6(port,reg):
                p+=3; continue
            if reg==0x28:
                if is_key_for_ch6(port,val):
                    p+=3; continue
                chip_events.append((samples,order,frame,'ymkey',(port,val))); order+=1
            else:
                chip_events.append((samples,order,frame,'ym',(port,reg,val))); order+=1
            p+=3; continue
        if c==0xC0:
            addr=vgm[p+1]|vgm[p+2]<<8; val=vgm[p+3]
            # SegaPCM second chip is bit 7 of the high address byte.
            if vgm[p+2]&0x80: p+=4; continue
            ch=(addr&0x78)>>3; reg=addr&7; upper=bool(addr&0x80)
            if ch<16:
                v=voices[ch]
                if not upper:
                    if reg==2: v.lvol=val
                    elif reg==3: v.rvol=val
                    elif reg==4: v.loop_addr=(v.loop_addr&0xff00)|val
                    elif reg==5: v.loop_addr=(v.loop_addr&0x00ff)|(val<<8)
                    elif reg==6: v.end_addr=val
                    elif reg==7: v.freq=val
                else:
                    if reg==4: v.start_addr=(v.start_addr&0xffff00)|(val<<8)
                    elif reg==5: v.start_addr=(v.start_addr&0x00ffff)|(val<<16)
                    elif reg==6:
                        was=v.active; v.ctrl=val; v.active=not(val&1)
                        if v.active and not was: pcm[ch].append((samples,'start',clone_voice(v)))
                        elif was and not v.active: pcm[ch].append((samples,'stop',None))
            p+=4; continue
        p+=command_length(vgm,p)
    return pcm,chip_events,samples,loop_frame,frame

def sgdk_frame_boundaries(vgm, data_end, rate):
    """Reproduce XGMTool's VGM_convertWaits frame placement.

    Returns (event_sample_time -> frame index) boundaries as a list of
    (start_sample, frame_index). The conversion accumulates waits and emits a
    frame wait whenever the accumulator exceeds 85% of one frame.
    """
    limit=44100.0/rate; min_limit=limit*0.85
    p=data_offset(vgm); sample_cnt=0.0; time=0.0; frame=0; boundaries=[(0,0)]
    while p < data_end:
        c=vgm[p]
        if c==0x66: break
        if c==0x61: wait=vgm[p+1]|(vgm[p+2]<<8); p+=3
        elif c==0x62: wait=735; p+=1
        elif c==0x63: wait=882; p+=1
        elif 0x70<=c<=0x7F: wait=(c&0x0F)+1; p+=1
        elif 0x80<=c<=0x8F: wait=c&0x0F; p+=1
        elif c==0x67: p+=7+u32(vgm,p+3); wait=0
        elif c==0x68: p+=12; wait=0
        else: p+=command_length(vgm,p); wait=0
        if wait:
            sample_cnt += wait
            while sample_cnt > min_limit:
                frame += 1; sample_cnt -= limit
                boundaries.append((time,frame))
            time += wait
    return boundaries, frame

def frame_for_time(time, boundaries):
    # boundaries are emitted at the command-stream time where XGMTool inserts
    # the frame wait. The command following that boundary belongs to the next
    # frame.
    lo=0; hi=len(boundaries)
    while lo+1 < hi:
        mid=(lo+hi)//2
        if boundaries[mid][0] <= time: lo=mid
        else: hi=mid
    return boundaries[lo][1]

def sgdk_frame_for_sample(sample_time, rate):
    frame_samples=44100.0/rate; min_limit=frame_samples*0.85
    if sample_time <= min_limit: return 0
    return max(0,int(math.ceil((sample_time-min_limit)/frame_samples)))

def sgdk_converted_frame_count(total_samples, rate):
    frame_samples=44100.0/rate; min_limit=frame_samples*0.85
    if total_samples <= min_limit: return 0
    return max(0,int(math.ceil((total_samples-min_limit)/frame_samples)))

def loop_frame_for(vgm, data_end, rate):
    rel = u32(vgm, 0x1C)
    if not rel:
        return None
    target = 0x1C + rel
    if target < data_offset(vgm) or target >= data_end:
        return None
    p = data_offset(vgm); ts = 0
    while p < target:
        c = vgm[p]
        if c == 0x61:
            ts += vgm[p+1] | vgm[p+2] << 8; p += 3
        elif c == 0x62:
            ts += 735; p += 1
        elif c == 0x63:
            ts += 882; p += 1
        elif 0x70 <= c <= 0x7F:
            ts += (c & 15) + 1; p += 1
        elif c == 0x66:
            break
        elif c == 0x67:
            p += 7 + u32(vgm, p+3)
        elif c == 0x68:
            p += 12
        else:
            p += command_length(vgm, p)
    return sgdk_frame_for_sample(ts, rate)

def convert(vgm, ntsc=None, pcm_normalize=False, pcm_gain_db=None, delay_key_off=True):
    ver, has_segapcm = validate_vgm(vgm)
    print(f"VGM version: {version_text(ver)}")
    if ver < 0x151:
        print("SegaPCM support: unavailable for this VGM version (YM2612/PSG only)")
    else:
        print("SegaPCM support: available")
    rate=60 if ntsc is not False else 50
    chip=u32(vgm,0x38)&0x7fffffff or 4_000_000
    spcm_if=u32(vgm,0x3c) if len(vgm)>=0x40 else 0
    bank_shift=(spcm_if&0x0f) if spcm_if else 12
    bank_mask=(0x70|((spcm_if>>16)&0xfc)) if spcm_if else 0x70
    eof=eof_offset(vgm); gd3=gd3_chunk(vgm,eof); data_end=eof
    if gd3:
        pos=vgm.find(gd3, data_offset(vgm), eof); data_end=pos if pos>=0 else eof
    blocks=collect_segapcm_rom(vgm,data_end)
    raw_count=raw_vgm_command_count(vgm,data_end)
    print("Optimizing VGM...")
    print(f"VGM duration: {u32(vgm,0x18)} samples ({u32(vgm,0x18)//44100} seconds)")
    pcm_timeline, chip_events, total_samples, loop_frame, converted_frames=parse_timeline(vgm,data_end,chip,bank_shift,bank_mask,rate)
    if not any(pcm_timeline[ch] for ch in range(4)) and not chip_events:
        raise ValueError('no YM2612/PSG/SegaPCM playback data found')
    print(f"Number of command: {raw_count}")
    print(f"Computed VGM duration: {total_samples} samples ({total_samples//44100} seconds)")
    frame_len=int(44100/rate)
    print(f"VGM duration after wait command conversion: {converted_frames*frame_len} samples ({converted_frames*frame_len//44100} seconds)")
    print(f"Number of command: {converted_frames + len(chip_events) + sum(len(pcm_timeline[ch]) for ch in range(4))}")
    cleaned_chip=clean_chip_events(chip_events,rate,loop_frame,[],delay_key_off)
    clean_count=converted_frames + sum(len(v) for v in cleaned_chip.values())
    print(f"Computed VGM duration: {converted_frames*frame_len} samples ({converted_frames*frame_len//44100} seconds)")
    print(f"Number of command after commands clean: {clean_count}")
    print(f"Number of command after PCM command remove: {clean_count}")

    rendered={}; sample_ids={}; xgm_samples=[]; frame_cmds={}; start_count=0
    state_duration={}; starts=[]
    for ch in range(4):
        evs=pcm_timeline[ch]
        for i,(t,kind,v) in enumerate(evs):
            if kind!='start': continue
            t2=evs[i+1][0] if i+1<len(evs) else total_samples
            dur=max(0,(t2-t)/44100.0); dur=min(dur,native_duration(v))
            key=(v.start_addr,v.loop_addr,v.end_addr,v.freq,v.lvol&127,v.rvol&127,v.ctrl&0x72)
            state_duration[key]=max(state_duration.get(key,0),dur); starts.append((ch,t,v,key))
    for ch,t,v,key in starts:
        frame=sgdk_frame_for_sample(t,rate); start_count+=1; dur=state_duration[key]
        if dur<=1/XGM_RATE: continue
        if key not in rendered:
            data=render_segment(blocks,v,dur)
            balance_mode = 'auto' if pcm_normalize else ('manual' if pcm_gain_db is not None else None)
            data, applied_gain = pcm_gain_data(data, balance_mode, pcm_gain_db or 0.0)
            rendered[key]=data; sample_ids[key]=len(xgm_samples)+1; xgm_samples.append(data)
            if len(xgm_samples)>MAX_XGM_SAMPLES: raise ValueError('more than 63 XGM PCM samples required')
        frame_cmds.setdefault(frame,[]).append((t,0x50|ch,sample_ids[key]))
    for ch in range(4):
        for t,kind,_ in pcm_timeline[ch]:
            if kind=='stop': frame_cmds.setdefault(sgdk_frame_for_sample(t,rate),[]).append((t,0x50|ch,0))

    # Add cleaned FM/PSG events, mirroring the important state-delta behavior
    # of XGMTool's VGM_cleanCommands().
    for frame, evs in cleaned_chip.items():
        for ts,order,kind,args in evs:
            if kind=='psg': frame_cmds.setdefault(frame,[]).append((ts,0x10,args))
            elif kind=='ymkey':
                port,val=args; frame_cmds.setdefault(frame,[]).append((ts,0x40,val))
            else:
                port,reg,val=args; frame_cmds.setdefault(frame,[]).append((ts,0x20 if port==0 else 0x30,(reg,val)))

    # Resolve same-channel PCM stop+play collisions exactly like v0.3.11.
    # Retriggers can generate both events at one frame; the play must win.
    resolved = {}
    for frame, evs in frame_cmds.items():
        chip_evs = []
        pcm_latest = {}
        for idx, e in enumerate(evs):
            if e[1] in (0x50, 0x51, 0x52, 0x53):
                ch = e[1] & 3
                prev = pcm_latest.get(ch)
                # A play/retrigger and stop can land on the same XGM frame.
                # Prefer the play command so the retrigger is not immediately
                # cancelled by a stop command.
                if prev is None or e[2] != 0 or prev[1][2] == 0:
                    pcm_latest[ch] = (idx, e)
            else:
                chip_evs.append((idx, e))
        merged = chip_evs + list(pcm_latest.values())
        merged.sort(key=lambda x: x[0])
        resolved[frame] = [e for _, e in merged]
    frame_cmds = resolved

    # XGM command stream. PCM command priority is 0.
    # Follow SGDK XGMTool's frame conversion and, importantly, keep the final
    # frame wait before the loop command. The loop command is zero-time, so it
    # must come AFTER the last 0x00 belonging to the loop. Otherwise the loop
    # is exactly one frame too short.
    music=bytearray(); frame_offsets={}
    has_loop=loop_frame is not None and 0 <= loop_frame < converted_frames

    # Every converted frame has one frame wait.
    #
    # SGDK's XGMTool puts the loop command AFTER the final frame wait. This is
    # subtle: putting 0x7E before that 0x00 makes the 0x00 unreachable and
    # shortens every loop by one complete frame.
    loop_inserted = False
    # Do NOT inject a reconstructed YM/PSG state at the loop target.
    # The loop may point into the middle of a track, and prepending a synthetic
    # state makes the first occurrence of that frame differ from subsequent
    # looped occurrences. The XGM stream must instead contain exactly the
    # events belonging to the target frame.

    for frame in range(converted_frames):
        frame_offsets[frame]=len(music)
        evs=frame_cmds.get(frame,[])
        evs=sorted(enumerate(evs), key=lambda x:(x[1][0],x[0]))
        for _,e in evs:
            _,op,val=e
            if op==0x10: music += bytes([op,val])
            elif op in (0x20,0x30): music += bytes([op,val[0],val[1]])
            else: music += bytes([op,val])
        music.append(0)

    if has_loop:
        off=frame_offsets[loop_frame]
        music += bytes([0x7E,off&255,(off>>8)&255,(off>>16)&255])
        loop_inserted = True

    music += b'\x7F'

    print("Converting VGM to XGM...")
    print(f"XGM duration: {converted_frames} frames ({converted_frames//rate} seconds)")

    sample_blob=bytearray(); table=[]
    for data in xgm_samples:
        while len(sample_blob)%256: sample_blob.append(0)
        a=len(sample_blob)//256; padded=data+b'\x00'*((-len(data))%256)
        sample_blob.extend(padded); table.append((a,len(padded)//256))
    hdr=bytearray(b'XGM ')
    for i in range(63):
        hdr += struct.pack('<HH',*(table[i] if i<len(table) else (0xffff,1)))
    flags=0 if rate==60 else 1
    if gd3: flags|=2
    hdr += struct.pack('<HBB',len(sample_blob)//256,1,flags)
    out=bytes(hdr)+bytes(sample_blob)+struct.pack('<I',len(music))+bytes(music)+gd3
    frame_count = converted_frames
    return out, {'frames':frame_count,'seconds':frame_count/rate,'samples':len(xgm_samples),
                 'sample_bytes':len(sample_blob),'rate':rate,'fm_psg_events':sum(len(v) for v in cleaned_chip.values()),
                 'pcm_starts':start_count,'gd3':bool(gd3)}

def main():
    ap=argparse.ArgumentParser(description='FrankieXGM - Convert Genesis YM2612+SN76489+SegaPCM VGM/VGZ to XGM 1.01')
    ap.add_argument('input'); ap.add_argument('output'); ap.add_argument('--ntsc',action='store_true'); ap.add_argument('--pal',action='store_true')
    ap.add_argument('--dd', action='store_true', help='disable delayed YM key-off (XGMTool-compatible default is enabled)')
    pcm_group=ap.add_mutually_exclusive_group()
    pcm_group.add_argument('--pcm-normalize', action='store_true', help='automatically balance PCM loudness using RMS targeting with a -3 dBFS peak ceiling')
    pcm_group.add_argument('--pcm-gain', type=float, metavar='DB', help='apply a fixed PCM gain in dB, with a -3 dBFS peak ceiling')
    a=ap.parse_args()
    if a.ntsc and a.pal: ap.error('--ntsc and --pal are mutually exclusive')
    out,info=convert(load_vgm(Path(a.input)), True if a.ntsc else False if a.pal else None, a.pcm_normalize, a.pcm_gain, not a.dd)
    Path(a.output).write_bytes(out)
    print(f"Converted: {a.input} -> {a.output}")
    print(f"XGM: {info['frames']} frames ({info['seconds']:.2f}s), {info['samples']} PCM samples, {info['sample_bytes']} bytes PCM")
    print(f"YM2612/PSG events: {info['fm_psg_events']}; SegaPCM starts: {info['pcm_starts']}; GD3: {'yes' if info['gd3'] else 'no'}")

if __name__=='__main__': main()
