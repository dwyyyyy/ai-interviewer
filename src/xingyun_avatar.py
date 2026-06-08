from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv


DEFAULT_GATEWAY = "https://nebula-agent.xingyun3d.com/user/v1/ttsa/session"
SDK_URL = "https://media.xingyun3d.com/xingyun3d/general/litesdk/xmovAvatar@latest.js"


@dataclass
class XingyunAvatarConfig:
    enabled: bool
    app_id: str
    app_secret: str
    gateway_server: str = DEFAULT_GATEWAY
    height: int = 520
    debug: bool = False

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.app_id and self.app_secret)


def load_xingyun_avatar_config() -> XingyunAvatarConfig:
    load_dotenv()
    return XingyunAvatarConfig(
        enabled=os.getenv("XINGYUN_AVATAR_ENABLED", "").lower() in {"1", "true", "yes", "on"},
        app_id=os.getenv("XINGYUN_APP_ID", ""),
        app_secret=os.getenv("XINGYUN_APP_SECRET", ""),
        gateway_server=os.getenv("XINGYUN_GATEWAY_SERVER", DEFAULT_GATEWAY),
        height=int(os.getenv("XINGYUN_AVATAR_HEIGHT", "520")),
        debug=os.getenv("XINGYUN_AVATAR_DEBUG", "").lower() in {"1", "true", "yes", "on"},
    )


def build_xingyun_avatar_html(text: str, config: XingyunAvatarConfig) -> str:
    app_id = json.dumps(config.app_id)
    app_secret = json.dumps(config.app_secret)
    gateway_server = json.dumps(config.gateway_server)
    speak_text = json.dumps(_to_ssml_text(text))
    debug = "true" if config.debug else "false"
    safe_text = html.escape(text[:180])
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
    .avatar-shell {{
      width: 100%;
      height: {config.height}px;
      border: 1px solid #d6dde8;
      border-radius: 8px;
      overflow: hidden;
      background: #0f172a;
      position: relative;
    }}
    #xingyun-sdk {{
      width: 100%;
      height: 100%;
    }}
    .status {{
      position: absolute;
      left: 10px;
      right: 10px;
      bottom: 10px;
      padding: 8px 10px;
      border-radius: 6px;
      background: rgba(15, 23, 42, 0.76);
      color: #e5eef9;
      font-size: 12px;
      line-height: 1.45;
      z-index: 10;
    }}
  </style>
</head>
<body>
  <div class="avatar-shell">
    <div id="xingyun-sdk"></div>
    <div class="status" id="xy-status">正在初始化星云数字人...</div>
  </div>
  <script src="{SDK_URL}"></script>
  <script>
    const statusBox = document.getElementById("xy-status");
    const questionText = {speak_text};
    let hasSpoken = false;
    let modelReady = false;

    function setStatus(text) {{
      if (statusBox) statusBox.textContent = text;
    }}

    function speakOnce(sdk) {{
      if (hasSpoken || !questionText) return;
      if (!modelReady) {{
        setStatus("数字人资源加载中，等待渲染完成...");
        return;
      }}
      if (!sdk || typeof sdk.speak !== "function") {{
        setStatus("SDK 已加载，但 speak 方法不可用。");
        return;
      }}
      hasSpoken = true;
      setStatus("数字人播报当前问题：{safe_text}");
      try {{
        sdk.speak(questionText, true, true);
      }} catch (err) {{
        hasSpoken = false;
        setStatus("数字人播报失败：" + (err && err.message ? err.message : String(err)));
      }}
    }}

    function boot() {{
      if (typeof XmovAvatar === "undefined") {{
        setStatus("星云 SDK 加载失败。");
        return;
      }}
      const sdk = new XmovAvatar({{
        containerId: "#xingyun-sdk",
        appId: {app_id},
        appSecret: {app_secret},
        gatewayServer: {gateway_server},
        hardwareAcceleration: "prefer-hardware",
        enableLogger: {debug},
        onDownloadProgress(progress) {{
          setStatus("数字人资源加载进度：" + progress + "%");
          if (Number(progress) >= 100) {{
            modelReady = true;
            setTimeout(() => speakOnce(sdk), 500);
          }}
        }},
        onNetworkInfo(networkInfo) {{
          if ({debug}) console.log("Xingyun network", networkInfo);
        }},
        onMessage(message) {{
          if ({debug}) console.log("Xingyun SDK message", message);
          if (message && message.code) {{
            setStatus("数字人 SDK 消息：" + JSON.stringify(message));
          }}
        }},
        onStatusChange(status) {{
          if ({debug}) console.log("Xingyun status", status);
          if (status === 6 || status === "visible" || status === "online") {{
            modelReady = true;
            setTimeout(() => speakOnce(sdk), 500);
          }}
        }},
        onStateChange(state) {{
          if ({debug}) console.log("Xingyun state", state);
        }},
        onVoiceStateChange(status) {{
          if (status === "start" || status === "voice_start") setStatus("数字人正在播报问题...");
          if (status === "end" || status === "voice_end") setStatus("播报结束，请回答。");
        }},
        onStartSessionWarning(message) {{
          setStatus("数字人会话警告：" + JSON.stringify(message));
        }}
      }});
      window.__xingyunAvatar = sdk;
      setTimeout(() => {{
        if (!modelReady) {{
          setStatus("仍在等待数字人资源。若长时间无画面，请确认访问地址为 localhost 或 HTTPS，并确认星云应用已配置角色/音色。");
        }}
      }}, 5000);
    }}

    if (document.readyState === "complete") boot();
    else window.addEventListener("load", boot);
  </script>
</body>
</html>
"""


def _to_ssml_text(text: str) -> str:
    cleaned = " ".join(str(text).split())
    return f"<speak>{html.escape(cleaned)}</speak>"
