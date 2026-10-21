#!/usr/bin/env python3
"""为宣传片合成一条极简氛围bed + 关键节点音效（纯程序生成，无外部素材）。

设计原则：不抢画面。低频只做支撑，中频留给“读字”，
音效只出现在镜头切换和卡片逐项高亮的位置。
"""
import os
import wave

import numpy as np

SR = 48000
DUR = 33.6
N = int(SR * DUR)

# 与视频时间轴对齐（秒）
T_LIGHT = 7.48
T_CARD = 11.58
T_STEP = [13.18, 14.96, 16.84]
T_NOTE = 17.32
T_MODES = 20.16
T_DATA = 24.88
T_END = 29.24

BPM = 92.0
BEAT = 60.0 / BPM
BAR = BEAT * 4

rng = np.random.default_rng(7)


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def env_ad(n, a, d, curve=3.0):
    """attack / exp decay 包络"""
    t = np.arange(n) / SR
    atk = np.clip(t / max(a, 1e-4), 0, 1)
    dec = np.exp(-np.maximum(0, t - a) * curve / max(d, 1e-4))
    return atk * dec


def pad_tone(f, dur, amp, detune=0.0, bright=0.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    ff = f * (1 + detune)
    sig = np.sin(2 * np.pi * ff * t) * 0.44
    sig += bright * 0.34 * np.sin(2 * np.pi * ff * 2 * t + 0.7)
    sig += bright * 0.20 * np.sin(2 * np.pi * ff * 3 * t + 1.9)
    sig += bright * 0.12 * np.sin(2 * np.pi * ff * 5 * t + 3.1)
    a = min(0.55, dur * 0.35)
    atk = np.clip(t / a, 0, 1) ** 1.6
    rel = np.clip((dur - t) / min(0.9, dur * 0.45), 0, 1) ** 1.4
    return sig * atk * rel * amp


def place(buf, sig, at, gain=1.0):
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for k in range(len(x)):
        acc = (1 - a) * x[k] + a * acc
        y[k] = acc
    return y


CHORDS = [
    [50, 53, 57, 60, 64],   # Dm9
    [46, 50, 53, 57],       # Bbmaj7
    [41, 45, 48, 52],       # Fmaj7
    [45, 48, 52, 55],       # Am7
]


def slow_compress(st, thresh_db=-26.0, ratio=2.1, block=480):
    """分块 RMS + 一极点平滑的慢压缩，避免逐采样循环。"""
    mono = st.mean(axis=1)
    nb = len(mono) // block
    r = np.sqrt(np.mean(mono[: nb * block].reshape(nb, block) ** 2, axis=1) + 1e-12)
    rdb = 20 * np.log10(r)
    over = np.maximum(0.0, rdb - thresh_db)
    gdb = -over * (1 - 1.0 / ratio)
    # 平滑增益曲线（起音快、释放慢）
    g = 10 ** (gdb / 20.0)
    sm = np.empty_like(g)
    acc = 1.0
    ka, kr = 0.35, 0.03
    for i, v in enumerate(g):
        k = ka if v < acc else kr
        acc = acc + (v - acc) * k
        sm[i] = acc
    centers = (np.arange(nb) + 0.5) * block
    curve = np.interp(np.arange(len(mono)), centers, sm)
    return st * curve[:, None]


def build():
    pad = np.zeros(N)
    sub = np.zeros(N)
    drums = np.zeros(N)
    sfx = np.zeros(N)

    # ---------- 和声垫 + 低音 ----------
    nb = int(np.ceil(DUR / BAR)) + 1
    for b in range(nb):
        t0 = b * BAR
        if t0 >= DUR:
            break
        ch = CHORDS[b % 4]
        # 越到后面越亮
        bright = 0.30 + 0.55 * min(1.0, t0 / 24.0)
        level = 0.044 if t0 < T_LIGHT else 0.050
        # pad 抬一个八度，避开 100-300Hz 的糊区
        for j, m in enumerate(ch):
            f = midi(m + 12)
            for det in (-0.0021, 0.0, 0.0022):
                place(pad, pad_tone(f, BAR * 1.12, level / 3.0, det, bright), t0)
        # 高八度微光：给亮度和“贵”的质感
        if t0 >= T_LIGHT - 0.1:
            sh = 0.0042 + 0.006 * min(1.0, (t0 - T_LIGHT) / 18.0)
            for m in ch[:3]:
                place(pad, pad_tone(midi(m + 24), BAR * 1.2, sh, 0.0009, 0.5), t0)

        # 低音：只留根音，负责托底
        root = midi(ch[0] - 12)
        n = int(BAR * 1.05 * SR)
        t = np.arange(n) / SR
        s = np.sin(2 * np.pi * root * t) + 0.22 * np.sin(2 * np.pi * root * 3 * t)
        e = np.clip(t / 0.02, 0, 1) * np.exp(-t * 1.5)
        place(sub, s * e * 0.24, t0)

    # ---------- 时钟滴答（前段独有） ----------
    n = int(0.045 * SR)
    t = np.arange(n) / SR
    tick = np.sin(2 * np.pi * 2100 * t) * np.exp(-t * 95) * 0.5
    tick += rng.normal(0, 1, n) * np.exp(-t * 220) * 0.18
    k = 1.3
    while k < T_LIGHT - 0.4:
        place(sfx, tick, k, 0.075)
        k += 1.3

    # ---------- 鼓组（进卡后进入） ----------
    def kick(amp=0.5):
        n = int(0.34 * SR)
        t = np.arange(n) / SR
        f = 118 * np.exp(-t * 26) + 44
        ph = 2 * np.pi * np.cumsum(f) / SR
        return np.sin(ph) * np.exp(-t * 7.5) * amp

    def hat(amp=0.2):
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        nz = rng.normal(0, 1, n)
        nz = np.diff(np.concatenate([[0], nz]))  # 粗糙高通
        return nz * np.exp(-t * 70) * amp

    kb = kick()
    hb = hat()
    tt = T_CARD
    beat_i = 0
    while tt < T_END:
        bar_pos = (tt - T_CARD) % BAR
        if abs(bar_pos) < 1e-6 or abs(bar_pos - 2 * BEAT) < 1e-6:
            place(drums, kb, tt, 0.55 if tt < T_DATA else 0.42)
        if tt >= T_CARD:
            place(drums, hb, tt, 1.0 if beat_i % 2 else 0.6)
        tt += BEAT / 2
        beat_i += 1

    # ---------- 音效 ----------
    # 开灯：噪声上扬 + 高音泛光
    n = int(1.5 * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    dark = lowpass(nz, 900)
    bright = np.diff(np.concatenate([[0], nz]))
    w = np.clip(t / 0.9, 0, 1) ** 2
    riser = (dark * (1 - w) + bright * w * 0.5) * np.clip(t / 0.75, 0, 1) * np.exp(-np.maximum(0, t - 1.0) * 5)
    place(sfx, riser, T_LIGHT - 0.95, 0.11)
    for f, a in ((1320, 0.05), (1980, 0.032), (2640, 0.02)):
        n2 = int(2.0 * SR)
        t2 = np.arange(n2) / SR
        s = np.sin(2 * np.pi * f * t2) * np.exp(-t2 * 2.4) * np.clip(t2 / 0.06, 0, 1)
        place(sfx, s, T_LIGHT + 0.04, a)

    # 卡片入场：低频 whoosh
    n = int(0.85 * SR)
    t = np.arange(n) / SR
    nz = lowpass(rng.normal(0, 1, n), 420)
    e = np.clip(t / 0.25, 0, 1) * np.exp(-np.maximum(0, t - 0.18) * 6)
    place(sfx, nz * e, T_CARD - 0.16, 0.5)

    # 三步高亮：短促 blip
    for k, ts in enumerate(T_STEP):
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        f = 1180 + k * 130
        s = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2 * t)) * np.exp(-t * 42)
        place(sfx, s, ts - 0.02, 0.075)

    # 核价说明出现：确认音
    for f, a, d in ((880, 0.06, 0.55), (1320, 0.045, 0.5), (1760, 0.022, 0.42)):
        n = int(1.4 * SR)
        t = np.arange(n) / SR
        s = np.sin(2 * np.pi * f * t) * np.exp(-t * (3.0 / d)) * np.clip(t / 0.005, 0, 1)
        place(sfx, s, T_NOTE, a)

    # 切到双模式：轻扫
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    nz = np.diff(np.concatenate([[0], rng.normal(0, 1, n)]))
    place(sfx, nz * np.exp(-t * 9) * np.clip(t / 0.05, 0, 1), T_MODES - 0.1, 0.05)

    # 数据段：一次低频冲击
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    f = 90 * np.exp(-t * 8) + 38
    ph = 2 * np.pi * np.cumsum(f) / SR
    place(sfx, np.sin(ph) * np.exp(-t * 4.2), T_DATA - 0.05, 0.34)

    # 片尾：一个干净的和弦长音
    for m, a in ((62, 0.055), (69, 0.04), (74, 0.03), (50, 0.05)):
        n = int(3.2 * SR)
        t = np.arange(n) / SR
        f = midi(m)
        s = np.sin(2 * np.pi * f * t) * np.clip(t / 0.02, 0, 1) * np.exp(-t * 1.3)
        place(sfx, s, T_END + 0.05, a)

    # ---------- 空气层 ----------
    air_n = int(DUR * SR)
    air = rng.normal(0, 1, air_n)
    air = air - lowpass(air, 3200)              # 只留 3kHz 以上
    te = np.arange(air_n) / SR
    air_env = np.interp(te, [0, T_LIGHT, T_CARD, T_DATA, T_END, DUR],
                        [0.5, 1.0, 1.2, 1.35, 0.9, 0.2])
    air = air * air_env * 0.012
    drums = drums + air

    # ---------- 混响（只给 pad 与 sfx） ----------
    ir_n = int(1.7 * SR)
    ti = np.arange(ir_n) / SR
    ir = [rng.normal(0, 1, ir_n) * np.exp(-ti * 3.1) for _ in range(2)]
    for i in range(2):
        ir[i] = lowpass(ir[i], 5200)
        ir[i] /= np.max(np.abs(ir[i])) + 1e-9

    def conv(x, h):
        n = len(x) + len(h) - 1
        nfft = 1 << (n - 1).bit_length()
        y = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(h, nfft), nfft)[: len(x)]
        return y

    wet_l = conv(pad, ir[0]) * 0.5 + conv(sfx, ir[0]) * 0.38
    wet_r = conv(pad, ir[1]) * 0.5 + conv(sfx, ir[1]) * 0.38

    pad = pad - lowpass(pad, 190)   # 一阶高通，清掉 200Hz 以下的互调堆积
    dry = pad + sub + drums + sfx
    L = dry + wet_l
    R = dry + wet_r

    # 轻微宽度：pad 左右微错位
    sh = int(0.008 * SR)
    R = R + np.concatenate([np.zeros(sh), pad[:-sh]]) * 0.12

    st = np.stack([L, R], axis=1)
    # 淡入淡出
    fi = int(0.25 * SR)
    fo = int(1.6 * SR)
    st[:fi] *= np.linspace(0, 1, fi)[:, None] ** 1.5
    st[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.2

    # 软限幅 + 归一
    # 总线慢压缩：把整体响度提到可用水平，同时保住瞬态
    st = slow_compress(st, thresh_db=-26.0, ratio=2.1)
    peak = float(np.max(np.abs(st)))
    st = st * (0.86 / peak)
    return st


def main():
    st = build()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio.wav")
    pcm = (np.clip(st, -1, 1) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    rms = float(np.sqrt(np.mean(st ** 2)))
    print(f"audio.wav  {len(st) / SR:.1f}s  peak={np.max(np.abs(st)):.2f}  rms={20 * np.log10(rms):.1f} dBFS")


if __name__ == "__main__":
    main()
