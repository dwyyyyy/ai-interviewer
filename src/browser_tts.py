from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class BrowserTTSConfig:
    enabled: bool
    autoplay: bool = False
    rate: float = 1.0
    pitch: float = 1.0
    lang: str = "zh-CN"
    height: int = 72


def load_browser_tts_config() -> BrowserTTSConfig:
    load_dotenv()
    return BrowserTTSConfig(
        enabled=os.getenv("BROWSER_TTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        autoplay=os.getenv("BROWSER_TTS_AUTOPLAY", "false").lower() in {"1", "true", "yes", "on"},
        rate=float(os.getenv("BROWSER_TTS_RATE", "1.0")),
        pitch=float(os.getenv("BROWSER_TTS_PITCH", "1.0")),
        lang=os.getenv("BROWSER_TTS_LANG", "zh-CN"),
        height=int(os.getenv("BROWSER_TTS_HEIGHT", "72")),
    )


def build_browser_tts_html(text: str, config: BrowserTTSConfig) -> str:
    safe_text = html.escape(text[:160])
    payload = json.dumps(" ".join(str(text).split()), ensure_ascii=False)
    autoplay = "true" if config.autoplay else "false"
    rate = json.dumps(config.rate)
    pitch = json.dumps(config.pitch)
    lang = json.dumps(config.lang)
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: transparent;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .tts-box {{
      display: flex;
      align-items: center;
      gap: 10px;
      box-sizing: border-box;
      min-height: 56px;
      border: 1px solid #d6dde8;
      border-radius: 8px;
      padding: 10px 12px;
      background: #ffffff;
      color: #18202f;
    }}
    button {{
      border: 1px solid #0f766e;
      border-radius: 8px;
      background: #0f766e;
      color: #ffffff;
      min-height: 36px;
      padding: 0 14px;
      font-weight: 650;
      cursor: pointer;
    }}
    button.secondary {{
      background: #ffffff;
      color: #0f766e;
    }}
    .status {{
      font-size: 13px;
      color: #657084;
      line-height: 1.4;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
  </style>
</head>
<body>
  <div class="tts-box">
    <button id="speak">朗读问题</button>
    <button id="stop" class="secondary">停止</button>
    <div class="status" id="status">TTS 就绪：{safe_text}</div>
  </div>
  <script>
    const text = {payload};
    const status = document.getElementById("status");
    const speakButton = document.getElementById("speak");
    const stopButton = document.getElementById("stop");

    function setStatus(value) {{
      status.textContent = value;
    }}

    function speak() {{
      if (!("speechSynthesis" in window)) {{
        setStatus("当前浏览器不支持 Web Speech TTS。");
        return;
      }}
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = {lang};
      utterance.rate = {rate};
      utterance.pitch = {pitch};
      utterance.onstart = () => setStatus("正在朗读当前问题...");
      utterance.onend = () => setStatus("朗读结束，请回答。");
      utterance.onerror = (event) => setStatus("朗读失败：" + event.error);
      window.speechSynthesis.speak(utterance);
    }}

    speakButton.addEventListener("click", speak);
    stopButton.addEventListener("click", () => {{
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      setStatus("已停止朗读。");
    }});

    if ({autoplay}) {{
      setTimeout(speak, 400);
    }}
  </script>
</body>
</html>
"""
