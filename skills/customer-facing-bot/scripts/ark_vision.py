#!/usr/bin/env python3
"""Analyze image/video using ARK Vision API.
Images: direct ARK Chat API call
Videos: 6 evenly-spaced frames + audio transcription for near-complete analysis.
Works with any video size - frames are small jpegs, no file size limit.
"""
import sys, os, base64, json, urllib.request, tempfile, subprocess

def get_b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

def get_env():
    for f in ['/home/ubuntu/.hermes/profiles/customer/.env', '/home/ubuntu/.hermes/.env']:
        if os.path.exists(f):
            with open(f) as fh:
                k, e = '', ''
                for l in fh:
                    l = l.strip()
                    if l.startswith('export ARK_API_KEY='): k = l.split('=',1)[1].strip().strip('"').strip("'")
                    elif l.startswith('export ARK_ENDPOINT='): e = l.split('=',1)[1].strip().strip('"').strip("'")
                if k and e: return k, e
    return '', ''

def extract_frames(path, n=6):
    """Extract n evenly spaced frames."""
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
        'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path],
        capture_output=True, text=True, timeout=10)
    try: dur = float(r.stdout.strip())
    except: dur = 30
    if dur < 1: dur = 30
    interval = dur / (n + 1)
    frames = []
    for i in range(1, n+1):
        t = i * interval
        tmp = tempfile.mktemp(suffix='.jpg')
        r2 = subprocess.run(['ffmpeg', '-y', '-ss', str(t), '-i', path,
            '-vframes', '1', '-q:v', '2', '-vf', 'scale=720:-2', tmp],
            capture_output=True, text=True, timeout=30)
        if r2.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
            frames.append((int(t), tmp))
    return frames, int(dur)

def extract_audio_text(path, api_key):
    """Extract audio and transcribe using ARK API."""
    audio = tempfile.mktemp(suffix='.wav')
    r = subprocess.run(['ffmpeg', '-y', '-i', path, '-vn',
        '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not os.path.exists(audio) or os.path.getsize(audio) < 100:
        if os.path.exists(audio): os.remove(audio)
        return ''
    try:
        with open(audio, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        data = json.dumps({
            'model': 'ep-20260712164025-fph8b',
            'messages': [{'role':'user','content':[
                {'type':'text','text':'转写这段音频里的全部文字内容'},
                {'type':'audio_url','audio_url':{'url':f'data:audio/wav;base64,{b64}'}}
            ]}],
            'max_tokens': 500
        }).encode()
        req = urllib.request.Request(
            'https://ark.cn-beijing.volces.com/api/v3/chat/completions',
            data=data,
            headers={'Content-Type':'application/json','Authorization':f'Bearer {api_key}'})
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        txt = resp.get('choices',[{}])[0].get('message',{}).get('content','')
        os.remove(audio)
        return txt
    except:
        if os.path.exists(audio): os.remove(audio)
        return ''

def call_ark(content, api_key, ep):
    data = json.dumps({'model': ep, 'messages': [{'role':'user','content':content}], 'max_tokens': 1000}).encode()
    req = urllib.request.Request('https://ark.cn-beijing.volces.com/api/v3/chat/completions',
        data=data, headers={'Content-Type':'application/json','Authorization':f'Bearer {api_key}'})
    resp = json.loads(urllib.request.urlopen(req, timeout=90).read())
    return resp.get('choices',[{}])[0].get('message',{}).get('content','')

def main():
    if len(sys.argv) < 2:
        print('请提供文件路径'); sys.exit(1)
    path = sys.argv[1]
    if not os.path.exists(path):
        print('文件不存在'); sys.exit(1)
    ext = os.path.splitext(path)[1].lower()
    is_vid = ext in ('.mp4','.mov','.avi','.mkv','.webm','.flv')
    api_key, ep = get_env()
    if not api_key or not ep:
        print('配置错误'); sys.exit(1)
    if is_vid:
        frames, duration = extract_frames(path, 6)
        if not frames:
            print('无法读取视频'); sys.exit(1)
        audio_text = extract_audio_text(path, api_key)
        prompt = f'这个视频共{duration}秒'
        if audio_text:
            prompt += f'，音频转写文字："{audio_text}"'
        prompt += '。请综合以上画面和音频信息，完整描述这个视频的内容。'
        content = [{'type':'text','text': prompt}]
        for t, fp in frames:
            b64 = get_b64(fp)
            content.append({'type':'image_url','image_url':{'url':f'data:image/jpeg;base64,{b64}'}})
            os.remove(fp)
        result = call_ark(content, api_key, ep)
        print(result if result else '分析无结果')
    else:
        b64 = get_b64(path)
        m = {'.jpg':'jpeg','.jpeg':'jpeg','.png':'png','.webp':'webp'}
        mime = m.get(ext, 'jpeg')
        content = [
            {'type':'text','text':'详细描述这张图片的内容'},
            {'type':'image_url','image_url':{'url':f'data:image/{mime};base64,{b64}'}}
        ]
        result = call_ark(content, api_key, ep)
        print(result if result else '分析无结果')

if __name__ == '__main__':
    main()
