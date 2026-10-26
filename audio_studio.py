"""Deterministic local synthesis, no online services or extra dependencies."""
import io,math,random,struct,wave

def synthesize(settings):
    kind=settings.get('kind','tone');seconds=float(settings.get('seconds',2));bpm=float(settings.get('bpm',100));frequency=float(settings.get('frequency',440));volume=float(settings.get('volume',.35))
    if kind not in ('tone','bell','noise','rain','music'):raise ValueError('Неизвестный звук')
    if not .1<=seconds<=120 or not 40<=bpm<=240 or not 30<=frequency<=4000 or not 0<=volume<=1:raise ValueError('Звук: 0.1–120 сек, 40–240 BPM, 30–4000 Гц, громкость 0–1')
    rate=22050;rng=random.Random(int(settings.get('seed',7)));notes=[0,3,7,10,7,3,5,7];out=io.BytesIO();samples=bytearray()
    for i in range(int(rate*seconds)):
        t=i/rate;env=min(1,t/.03,(seconds-t)/.15)
        if kind=='music':
            beat=t*bpm/60;note=frequency*2**(notes[int(beat)%len(notes)]/12);decay=math.exp(-(beat%1)*3)
            v=(math.sin(2*math.pi*note*t)*.5*decay+math.sin(2*math.pi*frequency/2*t)*.2+math.sin(2*math.pi*frequency*.75*t)*.15)
        elif kind=='bell':v=(math.sin(2*math.pi*frequency*t)+.3*math.sin(2*math.pi*frequency*2.76*t))*math.exp(-t*3)
        elif kind in ('noise','rain'):v=rng.uniform(-1,1)*(.25 if kind=='rain' else 1)
        else:v=math.sin(2*math.pi*frequency*t)
        samples.extend(struct.pack('<h',int(max(-1,min(1,v*env*volume))*32767)))
    with wave.open(out,'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(samples)
    return out.getvalue()
