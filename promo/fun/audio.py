#!/usr/bin/env python3
"""《18:59》快剪版配乐 + 音效，纯 numpy 合成，无外部素材。

设计：128 BPM 的电子底鼓 + 拍手 + 踩镲 + 贝斯 + 拨弦，
每一个笑点（微信弹窗、滑动、红笔划价、盖章、老虎机）都配独立音效。
"""
import wave

import numpy as np

SR = 48000
DUR = 23.4
N = int(SR * DUR)
rng = np.random.default_rng(11)

BPM = 128.0
BEAT = 60.0 / BPM          # 0.46875s
BAR = BEAT * 4

music = np.zeros(N)
drums = np.zeros(N)
sfx = np.zeros(N)
sub = np.zeros(N)


# ---------------------------------------------------------------- 基元
def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def place(buf, sig, at, gain=1.0):
    i = int(at * SR)
    if i < 0 or i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def exp_env(n, a=0.002, d=0.3, curve=1.0):
    t = np.arange(n) / SR
    atk = np.clip(t / max(a, 1e-5), 0, 1)
    return atk * np.exp(-np.maximum(0, t - a) * curve / max(d, 1e-5))


def one_pole_lp(x, cutoff):
    """时变一极点低通（cutoff 可为标量或逐样本数组）。"""
    if np.isscalar(cutoff):
        a = np.exp(-2 * np.pi * cutoff / SR)
        y = np.empty_like(x)
        acc = 0.0
        for k in range(len(x)):
            acc = (1 - a) * x[k] + a * acc
            y[k] = acc
        return y
    a = np.exp(-2 * np.pi * np.asarray(cutoff) / SR)
    y = np.empty_like(x)
    acc = 0.0
    for k in range(len(x)):
        acc = (1 - a[k]) * x[k] + a[k] * acc
        y[k] = acc
    return y


def hp(x, cutoff):
    return x - one_pole_lp(x, cutoff)


# ---------------------------------------------------------------- 鼓
def kick(dur=0.30, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 46 + 150 * np.exp(-t * 46)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 8.5)
    click = rng.normal(0, 1, n) * np.exp(-t * 480) * 0.25
    return (body + click) * amp


def clap(amp=1.0):
    n = int(0.20 * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    body = one_pole_lp(hp(nz, 900), 4200) * np.exp(-t * 26)
    # 三次快速重触发，模拟多人拍手
    for d in (0.008, 0.017, 0.026):
        m = int(d * SR)
        body[m:] += body[: n - m] * 0.55
    return body * amp * 0.9


def hat(amp=1.0, open_=False):
    d = 0.24 if open_ else 0.05
    n = int(d * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    h = hp(nz, 6500) * np.exp(-t * (24 if open_ else 105))
    return h * amp * 0.5


def snare(amp=1.0):
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    nz = hp(rng.normal(0, 1, n), 1400) * np.exp(-t * 30)
    tone = np.sin(2 * np.pi * 195 * t) * np.exp(-t * 26) * 0.5
    return (nz * 0.8 + tone) * amp


# ---------------------------------------------------------------- 音色
def bass_note(f, dur, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * f * t)
    sig += 0.42 * np.sin(2 * np.pi * f * 2 * t)
    sig += 0.20 * np.sin(2 * np.pi * f * 3 * t)
    sig += 0.09 * np.sin(2 * np.pi * f * 4 * t)
    e = np.clip(t / 0.004, 0, 1) * np.exp(-t * 6.2)
    return sig * e * amp * 0.5


def pluck(f, dur, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * f * t)
    sig += 0.5 * np.sin(2 * np.pi * f * 2 * t)
    sig += 0.28 * np.sin(2 * np.pi * f * 3 * t)
    sig += 0.14 * np.sin(2 * np.pi * f * 5 * t)
    e = np.clip(t / 0.002, 0, 1) * np.exp(-t * 17)
    return sig * e * amp * 0.32


def stab(freqs, dur, amp=1.0, bright=0.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for f in freqs:
        sig += np.sin(2 * np.pi * f * t)
        sig += bright * 0.4 * np.sin(2 * np.pi * f * 2.01 * t)
    e = np.clip(t / 0.006, 0, 1) * np.exp(-t * 7.5)
    return sig * e * amp * 0.10


def pad_tone(f, dur, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * f * t) * 0.5
    sig += 0.26 * np.sin(2 * np.pi * f * 2 * t + 0.6)
    sig += 0.12 * np.sin(2 * np.pi * f * 3 * t + 1.7)
    a = min(0.5, dur * 0.3)
    atk = np.clip(t / a, 0, 1) ** 1.5
    rel = np.clip((dur - t) / min(0.8, dur * 0.4), 0, 1) ** 1.3
    return sig * atk * rel * amp * 0.2


def bell(f, dur=1.2, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = (np.sin(2 * np.pi * f * t) * np.exp(-t * 4.2)
           + 0.42 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 6.5)
           + 0.22 * np.sin(2 * np.pi * f * 5.40 * t) * np.exp(-t * 9.0))
    return sig * amp * 0.4


# ---------------------------------------------------------------- 音效
def tick(amp=1.0):
    n = int(0.02 * SR)
    t = np.arange(n) / SR
    return (rng.normal(0, 1, n) * np.exp(-t * 900)) * amp * 0.5


def pop(amp=1.0):
    """微信消息入：两个上行的软音"""
    out = np.zeros(int(0.26 * SR))
    for i, (f, d) in enumerate([(880, 0.05), (1320, 0.12)]):
        n = int((d + 0.05) * SR)
        t = np.arange(n) / SR
        s = np.sin(2 * np.pi * f * t) * np.exp(-t * 26)
        place(out, s * 0.5, i * 0.055)
    return out * amp


def send_sfx(amp=1.0):
    """发送：短促上行 + 空气"""
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    f = 420 + 900 * (t / t[-1]) ** 2
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t * 13) * 0.5
    air = hp(rng.normal(0, 1, n), 3000) * np.exp(-t * 22) * 0.25
    return (s + air) * amp


def swoosh(dur=0.16, amp=1.0, f0=900, f1=3400, down=False):
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    cut = np.linspace(f1, f0, n) if down else np.linspace(f0, f1, n)
    s = one_pole_lp(nz, cut)
    s = s - one_pole_lp(s, 300)
    env = np.sin(np.linspace(0, np.pi, n)) ** 1.5
    return s * env * amp * 0.55


def slap(amp=1.0):
    """贴纸/盖章的实体感：噪声 + 低频"""
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    nz = hp(rng.normal(0, 1, n), 1200) * np.exp(-t * 60)
    low = np.sin(2 * np.pi * 74 * t) * np.exp(-t * 34) * 0.7
    return (nz * 0.75 + low) * amp


def boom(amp=1.0, f=48, dur=0.7):
    n = int(dur * SR)
    t = np.arange(n) / SR
    fr = f * (1 + 1.4 * np.exp(-t * 16))
    ph = 2 * np.pi * np.cumsum(fr) / SR
    body = np.sin(ph) * np.exp(-t * 2.6)
    nz = one_pole_lp(rng.normal(0, 1, n), 220) * np.exp(-t * 14) * 0.5
    return (body + nz) * amp


def squeak(amp=1.0):
    """马克笔划纸：带颤音的窄带噪声"""
    n = int(0.20 * SR)
    t = np.arange(n) / SR
    f = 780 + 420 * (t / t[-1]) + 40 * np.sin(2 * np.pi * 26 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * 0.35
    s += rng.normal(0, 1, n) * 0.30
    s = one_pole_lp(s, 2600)
    env = np.clip(t / 0.02, 0, 1) * np.clip((t[-1] - t) / 0.03, 0, 1)
    return s * env * amp


def ratchet(dur, amp=1.0, f_end=64):
    """老虎机棘轮：越来越密的咔哒"""
    out = np.zeros(int(dur * SR))
    t = 0.0
    k = 0
    while t < dur:
        g = 0.35 + 0.65 * (t / dur)
        place(out, tick(g), t)
        # 间隔从 62ms 加速到 18ms
        t += 0.062 - (0.044 * (t / dur))
        k += 1
    return out * amp


def riser(dur=0.8, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    cut = np.linspace(400, 9000, n)
    s = one_pole_lp(nz, cut)
    s = s - one_pole_lp(s, 350)
    env = (t / t[-1]) ** 2.2
    tone = np.sin(2 * np.pi * np.cumsum(np.linspace(180, 900, n)) / SR) * 0.15
    return (s * 0.7 + tone) * env * amp


def coin(amp=1.0):
    out = np.zeros(int(0.6 * SR))
    for i, f in enumerate([1568, 2093, 2637]):
        place(out, bell(f, 0.35, 0.5), i * 0.055)
    return out * amp


def typing_click(amp=1.0):
    n = int(0.012 * SR)
    t = np.arange(n) / SR
    return hp(rng.normal(0, 1, n), 2200) * np.exp(-t * 700) * amp * 0.6


# ================================================================ 编排
T = dict(
    s1=0.0, s2=1.9, s3=3.76, s4=6.3, s5=8.9, s6=10.1,
    s7=11.3, s8=15.6, s9=18.0, s10=20.4, end=22.86,
)

# --- 音乐段落
CHORDS = [
    [57, 60, 64, 67],   # Am7
    [53, 57, 60, 64],   # Fmaj7
    [48, 52, 55, 60],   # C
    [55, 59, 62, 65],   # G
]
ROOTS = [45, 41, 36, 43]  # A2 F2 C2 G2

t = 0.0
bar = 0
while t < DUR - 0.3:
    ci = bar % 4
    ch = CHORDS[ci]
    root = ROOTS[ci]

    # 底鼓：1.9s 起，8.9-10.1 空掉，10.1 后回来，20.4 收
    drum_zone = (t >= T["s2"] and t < T["s5"]) or (t >= T["s6"] and t < T["s10"])
    if drum_zone:
        for b in range(4):
            place(drums, kick(1.0), t + b * BEAT, 0.95)
            if b in (1, 3):
                place(drums, clap(0.9), t + b * BEAT, 0.55)
            # 摇摆 8 分音符踩镲
            place(drums, hat(0.9), t + b * BEAT, 0.30)
            place(drums, hat(0.5), t + b * BEAT + BEAT * 0.5, 0.26)
            place(drums, hat(0.85, True), t + b * BEAT + BEAT * 0.75, 0.16)

    # 贝斯：8 分音符
    if t >= T["s2"] and t < T["s10"]:
        for b in range(8):
            tt = t + b * BEAT * 0.5
            if T["s5"] <= tt < T["s6"]:
                continue
            note = root if b % 4 != 3 else root + 12
            place(sub, bass_note(midi(note), BEAT * 0.46, 1.0), tt, 0.62)

    # 拨弦琶音：11.3s 起
    if t >= T["s7"]:
        arp = [0, 2, 1, 3, 2, 0, 3, 1]
        for b in range(8):
            tt = t + b * BEAT * 0.5
            if tt >= DUR - 0.3:
                break
            m = ch[arp[b % 8]] + 12
            place(music, pluck(midi(m), 0.30, 1.0), tt, 0.34)

    # 和声垫：每小节一次，托住高频
    if t >= T["s2"]:
        lv = 0.16 if t < T["s7"] else 0.26
        for m in ch:
            place(music, pad_tone(midi(m + 12), BAR * 1.05, 1.0), t, lv)

    bar += 1
    t += BAR

# --- 段落切换的强拍
for at, amp in [(T["s2"], 0.9), (T["s3"], 0.7), (T["s4"], 0.8),
                (T["s5"], 1.0), (T["s6"], 0.9), (T["s7"], 1.0),
                (T["s8"], 0.85), (T["s9"], 0.7), (T["s10"], 1.0)]:
    place(drums, boom(1.0), at, amp * 0.55)
    place(music, stab([midi(57), midi(64), midi(69)], 0.55, 1.0), at, amp * 0.55)

# ================================================================ 音效点
# S1 时钟
place(sfx, tick(1.0), 0.10, 0.9)
place(sfx, tick(0.85), 0.60, 0.8)
place(sfx, tick(1.0), 0.90, 1.0)
place(sfx, boom(1.0, 62, 0.5), 0.90, 0.35)
place(sfx, slap(0.6), 0.99, 0.55)          # 「下班了」砸出
place(sfx, tick(0.5), 1.33, 0.55)
place(sfx, boom(0.8, 44, 0.6), 1.35, 0.45)  # 「但没人动」
place(sfx, riser(0.45, 1.0), 1.55, 0.28)

# S2 微信
place(sfx, pop(1.0), 2.02, 0.85)           # 老板消息
for i in range(9):                          # 打字
    place(sfx, typing_click(1.0), 2.44 + i * 0.038, 0.45)
place(sfx, send_sfx(1.0), 2.79, 0.7)       # 发「能」
place(sfx, typing_click(0.7), 3.12, 0.4)
place(sfx, typing_click(0.7), 3.20, 0.4)
place(sfx, slap(1.0), 3.34, 0.9)           # 贴纸
place(sfx, boom(0.7, 70, 0.45), 3.34, 0.4)
place(sfx, swoosh(0.22, 1.0, 800, 2600), 3.70, 0.5)

# S3 滑动
for i in range(14):
    at = 3.88 + i * 0.11
    place(sfx, swoosh(0.13, 1.0, 1100, 4200, down=(i % 2 == 1)), at, 0.30)
place(sfx, boom(1.0, 52, 0.55), 5.46, 0.8)     # 停住
place(sfx, slap(0.8), 5.54, 0.6)               # 框住
place(sfx, slap(1.0), 5.82, 0.85)              # 「上个月点过6次」
place(sfx, boom(0.6, 78, 0.4), 5.82, 0.35)
place(sfx, tick(1.0), 6.05, 0.9)               # 按钮变「算了」
place(sfx, tick(0.7), 6.09, 0.7)

# S4 价格
place(sfx, swoosh(0.2, 1.0, 900, 3000), 6.30, 0.45)
place(sfx, slap(0.7), 6.45, 0.5)               # 卡片落位
place(sfx, squeak(1.0), 6.84, 0.85)            # 红笔划掉
place(sfx, boom(1.0, 46, 0.9), 7.01, 1.0)      # 26.50 砸下
place(sfx, stab([midi(69), midi(76)], 0.35, 1.0), 7.01, 0.6)
place(sfx, pop(0.5), 7.35, 0.4)
place(sfx, tick(0.8), 7.62, 0.5)
place(sfx, bell(1318, 0.30, 0.6), 7.88, 0.75)  # 打勾
place(sfx, bell(1760, 0.26, 0.5), 7.93, 0.6)
place(sfx, slap(0.9), 8.14, 0.8)               # 「默认勾选。」
place(sfx, tick(0.6), 8.46, 0.6)

# S5 老三样
place(sfx, boom(1.0, 40, 1.1), 8.90, 1.0)
for i in range(3):
    place(sfx, boom(1.0, 58 - i * 4, 0.50), 9.13 + i * 0.12, 0.95)
    place(sfx, slap(0.8), 9.13 + i * 0.12, 0.6)
place(sfx, riser(0.55, 1.0), 9.55, 0.35)
place(sfx, tick(0.7), 9.66, 0.6)
place(sfx, tick(0.5), 9.82, 0.5)

# S6 老虎机
place(sfx, riser(0.6, 1.0), 9.95, 0.55)
place(sfx, ratchet(0.72, 1.0), 10.28, 0.85)
place(sfx, boom(0.9, 54, 0.6), 10.96, 0.85)
place(sfx, bell(1046, 1.4, 1.0), 10.96, 0.95)   # 叮
place(sfx, bell(1568, 1.1, 0.7), 10.98, 0.7)
place(sfx, coin(1.0), 11.02, 0.55)

# S7 卡片
place(sfx, swoosh(0.34, 1.0, 3600, 500, True), 11.34, 0.75)   # 从天而降
place(sfx, boom(1.0, 42, 1.2), 11.72, 1.0)                    # 落地
place(sfx, slap(1.0), 11.72, 0.9)
place(sfx, stab([midi(57), midi(64), midi(72)], 0.7, 1.0), 11.72, 0.75)
for at, f in [(12.09, 0.9), (12.96, 0.85), (13.85, 1.0)]:     # 三枚印章
    place(sfx, slap(1.0), at, 1.0)
    place(sfx, boom(0.8, 62, 0.45), at, 0.55)
    place(sfx, tick(1.0), at + 0.012, 0.7)
place(sfx, bell(880, 0.5, 0.55), 14.65, 0.5)                  # 「3 秒」

# S8 三连
place(sfx, swoosh(0.18, 1.0, 500, 4000), 15.60, 0.7)
place(sfx, boom(0.9, 50, 0.7), 15.60, 0.8)
for i in range(12):                                            # 12 个 chip
    place(sfx, tick(0.8), 15.77 + i * 0.034, 0.35)
place(sfx, swoosh(0.18, 1.0, 600, 4200), 16.40, 0.7)
place(sfx, boom(0.9, 50, 0.7), 16.40, 0.8)
place(sfx, pop(0.8), 16.59, 0.5)
place(sfx, pop(0.8), 16.72, 0.5)
place(sfx, pop(0.8), 16.85, 0.5)
place(sfx, swoosh(0.18, 1.0, 700, 4500), 17.20, 0.7)
place(sfx, boom(0.9, 50, 0.7), 17.20, 0.8)
place(sfx, coin(0.7), 17.26, 0.35)

# S9 证据
for i, at in enumerate([18.12, 18.64, 19.16]):
    place(sfx, slap(1.0), at, 0.95)
    place(sfx, boom(0.7, 66, 0.4), at, 0.45)
place(sfx, bell(1174, 0.5, 0.5), 19.76, 0.45)

# S10 片尾
place(sfx, boom(1.0, 44, 1.4), 20.40, 0.95)
place(sfx, stab([midi(57), midi(60), midi(67), midi(72)], 1.2, 1.0), 20.40, 0.7)
place(sfx, slap(1.0), 21.12, 1.0)                              # 「加班狗」定格
place(sfx, boom(0.9, 52, 0.7), 21.12, 0.6)
for i in range(6):                                             # 命令行逐字
    place(sfx, typing_click(0.8), 21.80 + i * 0.075, 0.35)
place(sfx, pop(0.6), 22.46, 0.4)


# ================================================================ 混音
def slow_compress(st, thresh_db=-24.0, ratio=2.0, block=480):
    mono = st.mean(axis=1)
    nb = len(mono) // block
    r = np.sqrt(np.mean(mono[: nb * block].reshape(nb, block) ** 2, axis=1) + 1e-12)
    rdb = 20 * np.log10(r)
    over = np.maximum(0.0, rdb - thresh_db)
    gdb = -over * (1 - 1.0 / ratio)
    g = 10 ** (gdb / 20.0)
    sm = np.empty_like(g)
    acc = 1.0
    for i, v in enumerate(g):
        k = 0.40 if v < acc else 0.025
        acc = acc + (v - acc) * k
        sm[i] = acc
    centers = (np.arange(nb) + 0.5) * block
    curve = np.interp(np.arange(len(mono)), centers, sm)
    return st * curve[:, None]


def build():
    global music, drums, sfx, sub

    # 高频清理
    music = music - one_pole_lp(music, 150)
    sub = one_pole_lp(sub, 900)

    # 简单混响：只给 music 与 sfx
    def verb(x, wet=0.16, delays=(0.031, 0.047, 0.071, 0.099)):
        out = x.copy()
        for d in delays:
            k = int(d * SR)
            decay = 0.55
            g = wet * decay
            out[k:] += x[:-k] * g
            wet *= 0.82
        return out

    music_w = verb(music, 0.30)
    sfx_w = verb(sfx, 0.22)

    # 低频收着走：手机外放几乎听不到 60Hz 以下，堆多了只会糊
    dry = music_w * 1.30 + sub * 0.40 + drums * 0.92 + sfx_w * 1.18

    # 倾斜 EQ：砍掉 55Hz 以下，抬起 1.5kHz 以上（清晰度与「脆」感）
    dry = dry - one_pole_lp(dry, 55)
    high = dry - one_pole_lp(dry, 1500)
    dry = dry + high * 0.55

    # 立体声：轻微展宽
    left = dry.copy()
    right = dry.copy()
    d = int(0.006 * SR)
    right[d:] += music_w[:-d] * 0.10
    left[:-d] += music_w[d:] * 0.06
    st = np.stack([left, right], axis=1)

    # 结尾淡出
    fo = int(0.55 * SR)
    st[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.4

    # 先归一化再压，否则压缩器阈值根本触发不到
    st = st * (0.90 / float(np.max(np.abs(st))))
    st = slow_compress(st, -27.0, 3.2)
    st = st * (0.92 / float(np.max(np.abs(st))))
    st = np.tanh(st * 1.9) / np.tanh(1.9)     # 一级软限幅，兜住瞬态
    st = st * (0.96 / float(np.max(np.abs(st))))
    st = np.tanh(st * 1.7) / np.tanh(1.7)     # 二级，把整体推响
    # 留 1dB 余量：AAC 编码会过冲，顶到 0dB 就是削波
    st = st * (0.85 / float(np.max(np.abs(st))))
    return st


def main():
    st = build()
    pcm = np.clip(st, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    path = "promo/fun/audio.wav"
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    rms = 20 * np.log10(np.sqrt(np.mean(st ** 2)) + 1e-12)
    print(f"wrote {path}  dur={DUR}s  rms={rms:.1f} dBFS  peak={20*np.log10(np.max(np.abs(st))):.1f} dBFS")


if __name__ == "__main__":
    main()
