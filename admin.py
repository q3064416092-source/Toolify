# SPDX-License-Identifier: GPL-3.0-or-later
# Toolify Admin Interface

import os
import yaml
import secrets
import string
import logging
from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

CONFIG_PATH = os.environ.get("TOOLIFY_CONFIG_PATH", "config.yaml")


def _read_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write_config(data: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _verify_admin_key(authorization: str) -> str:
    key = authorization.replace("Bearer ", "")
    config = _read_config()
    allowed = config.get("client_authentication", {}).get("allowed_keys", [])
    if key not in allowed:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return key


# --- API Routes ---

@router.post("/admin/api/login")
async def admin_login(request: Request):
    body = await request.json()
    key = body.get("key", "")
    config = _read_config()
    allowed = config.get("client_authentication", {}).get("allowed_keys", [])
    if key in allowed:
        return {"ok": True}
    raise HTTPException(status_code=401, detail="Invalid key")


@router.get("/admin/api/config")
async def get_config(authorization: str = Header(...)):
    _verify_admin_key(authorization)
    return _read_config()


@router.put("/admin/api/config/server")
async def update_server(request: Request, authorization: str = Header(...)):
    _verify_admin_key(authorization)
    body = await request.json()
    config = _read_config()
    config.setdefault("server", {})
    config["server"]["port"] = int(body.get("port", 8000))
    config["server"]["host"] = body.get("host", "0.0.0.0")
    config["server"]["timeout"] = int(body.get("timeout", 180))
    _write_config(config)
    return {"ok": True}


@router.get("/admin/api/services")
async def get_services(authorization: str = Header(...)):
    _verify_admin_key(authorization)
    config = _read_config()
    return config.get("upstream_services", [])


@router.post("/admin/api/services")
async def add_service(request: Request, authorization: str = Header(...)):
    _verify_admin_key(authorization)
    body = await request.json()
    config = _read_config()
    services = config.get("upstream_services", [])
    for s in services:
        if s["name"] == body["name"]:
            raise HTTPException(status_code=400, detail=f"Service '{body['name']}' already exists")
    services.append(body)
    config["upstream_services"] = services
    _write_config(config)
    return {"ok": True}


@router.put("/admin/api/services/{name}")
async def update_service(name: str, request: Request, authorization: str = Header(...)):
    _verify_admin_key(authorization)
    body = await request.json()
    config = _read_config()
    services = config.get("upstream_services", [])
    for i, s in enumerate(services):
        if s["name"] == name:
            services[i] = body
            config["upstream_services"] = services
            _write_config(config)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Service not found")


@router.delete("/admin/api/services/{name}")
async def delete_service(name: str, authorization: str = Header(...)):
    _verify_admin_key(authorization)
    config = _read_config()
    services = config.get("upstream_services", [])
    config["upstream_services"] = [s for s in services if s["name"] != name]
    if len(config["upstream_services"]) == len(services):
        raise HTTPException(status_code=404, detail="Service not found")
    _write_config(config)
    return {"ok": True}


@router.get("/admin/api/keys")
async def get_keys(authorization: str = Header(...)):
    _verify_admin_key(authorization)
    config = _read_config()
    return config.get("client_authentication", {}).get("allowed_keys", [])


@router.post("/admin/api/keys")
async def add_key(request: Request, authorization: str = Header(...)):
    _verify_admin_key(authorization)
    body = await request.json()
    key = body.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="Key cannot be empty")
    config = _read_config()
    keys = config.get("client_authentication", {}).get("allowed_keys", [])
    if key in keys:
        raise HTTPException(status_code=400, detail="Key already exists")
    keys.append(key)
    config.setdefault("client_authentication", {})["allowed_keys"] = keys
    _write_config(config)
    return {"ok": True}


@router.delete("/admin/api/keys/{index}")
async def delete_key(index: int, authorization: str = Header(...)):
    _verify_admin_key(authorization)
    config = _read_config()
    keys = config.get("client_authentication", {}).get("allowed_keys", [])
    if len(keys) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last key")
    if index < 0 or index >= len(keys):
        raise HTTPException(status_code=404, detail="Key index out of range")
    keys.pop(index)
    config["client_authentication"]["allowed_keys"] = keys
    _write_config(config)
    return {"ok": True}


@router.put("/admin/api/features")
async def update_features(request: Request, authorization: str = Header(...)):
    _verify_admin_key(authorization)
    body = await request.json()
    config = _read_config()
    config["features"] = body
    _write_config(config)
    return {"ok": True}


@router.get("/admin/api/generate-key")
async def generate_key(authorization: str = Header(...)):
    _verify_admin_key(authorization)
    chars = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(32))
    return {"key": f"sk-{random_part}"}


# --- Admin HTML ---

@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return ADMIN_HTML


ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Toolify Admin</title>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0e17;--bg2:#111827;--bg3:#1e293b;--bg4:#283548;
  --text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;
  --primary:#3b82f6;--primary-h:#2563eb;--primary-bg:rgba(59,130,246,.12);
  --green:#22c55e;--green-bg:rgba(34,197,94,.12);
  --red:#ef4444;--red-bg:rgba(239,68,68,.12);
  --yellow:#eab308;--yellow-bg:rgba(234,179,8,.12);
  --orange:#f97316;
  --border:#1e293b;--border2:#334155;
  --radius:10px;--radius-sm:6px;
  --shadow:0 4px 24px rgba(0,0,0,.3);
  --transition:all .2s ease;
}
html{font-size:14px}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;min-height:100vh}
input,textarea,select,button{font:inherit;color:inherit}
a{color:var(--primary);text-decoration:none}

/* Scrollbar */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--bg4);border-radius:3px}

/* Login */
.login-wrap{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:1rem}
.login-card{background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:3rem;width:100%;max-width:400px;box-shadow:var(--shadow)}
.login-card h1{font-size:1.5rem;font-weight:700;margin-bottom:.5rem;display:flex;align-items:center;gap:.5rem}
.login-card p{color:var(--text2);margin-bottom:2rem;font-size:.9rem}

/* Layout */
.layout{display:flex;min-height:100vh}
.sidebar{width:240px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:10}
.sidebar-brand{padding:1.5rem;border-bottom:1px solid var(--border);font-weight:700;font-size:1.15rem;letter-spacing:-.02em}
.sidebar-brand span{color:var(--primary)}
.sidebar-nav{flex:1;padding:.75rem;display:flex;flex-direction:column;gap:2px}
.nav-item{display:flex;align-items:center;gap:.75rem;padding:.7rem 1rem;border-radius:var(--radius-sm);cursor:pointer;transition:var(--transition);color:var(--text2);font-size:.9rem;border:none;background:none;width:100%;text-align:left}
.nav-item:hover{background:var(--bg3);color:var(--text)}
.nav-item.active{background:var(--primary-bg);color:var(--primary);font-weight:600}
.nav-item svg{width:18px;height:18px;flex-shrink:0}
.sidebar-footer{padding:1rem 1.5rem;border-top:1px solid var(--border);font-size:.75rem;color:var(--text3)}
.main{flex:1;margin-left:240px;padding:2rem;max-width:960px}
.page-title{font-size:1.5rem;font-weight:700;margin-bottom:1.5rem}
.page-desc{color:var(--text2);margin:-1rem 0 1.5rem;font-size:.9rem}

/* Cards */
.card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem;margin-bottom:1rem;transition:var(--transition)}
.card:hover{border-color:var(--border2)}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem}
.card-title{font-weight:600;font-size:1rem}

/* Stats */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin-bottom:1.5rem}
.stat-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:1.25rem}
.stat-value{font-size:1.75rem;font-weight:700;margin:.25rem 0}
.stat-label{color:var(--text2);font-size:.8rem;text-transform:uppercase;letter-spacing:.05em}

/* Forms */
.form-group{margin-bottom:1rem}
.form-label{display:block;font-size:.8rem;font-weight:600;color:var(--text2);margin-bottom:.4rem;text-transform:uppercase;letter-spacing:.03em}
.form-input{width:100%;padding:.6rem .8rem;background:var(--bg);border:1px solid var(--border2);border-radius:var(--radius-sm);outline:none;transition:var(--transition);font-size:.9rem}
.form-input:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-bg)}
textarea.form-input{resize:vertical;min-height:100px;font-family:'SF Mono',Monaco,Consolas,monospace;font-size:.82rem}
select.form-input{cursor:pointer;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%2394a3b8' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right .75rem center}
.form-hint{font-size:.75rem;color:var(--text3);margin-top:.25rem}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}

/* Buttons */
.btn{display:inline-flex;align-items:center;gap:.4rem;padding:.55rem 1rem;border-radius:var(--radius-sm);border:1px solid transparent;cursor:pointer;font-size:.85rem;font-weight:500;transition:var(--transition);white-space:nowrap}
.btn-primary{background:var(--primary);color:#fff}
.btn-primary:hover{background:var(--primary-h)}
.btn-ghost{background:transparent;color:var(--text2);border-color:var(--border2)}
.btn-ghost:hover{background:var(--bg3);color:var(--text)}
.btn-danger{background:transparent;color:var(--red);border-color:rgba(239,68,68,.3)}
.btn-danger:hover{background:var(--red-bg)}
.btn-sm{padding:.35rem .7rem;font-size:.8rem}
.btn-group{display:flex;gap:.5rem;flex-wrap:wrap}

/* Toggle */
.toggle-wrap{display:flex;align-items:center;justify-content:space-between;padding:.75rem 0;border-bottom:1px solid var(--border)}
.toggle-wrap:last-child{border-bottom:none}
.toggle-info h4{font-size:.9rem;font-weight:600;margin-bottom:.15rem}
.toggle-info p{font-size:.8rem;color:var(--text3)}
.toggle{position:relative;width:44px;height:24px;flex-shrink:0;cursor:pointer}
.toggle input{display:none}
.toggle-slider{position:absolute;inset:0;background:var(--bg4);border-radius:12px;transition:var(--transition)}
.toggle-slider::after{content:'';position:absolute;top:3px;left:3px;width:18px;height:18px;background:#fff;border-radius:50%;transition:var(--transition)}
.toggle input:checked+.toggle-slider{background:var(--primary)}
.toggle input:checked+.toggle-slider::after{transform:translateX(20px)}

/* Tags */
.tags{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.5rem}
.tag{display:inline-flex;align-items:center;gap:.3rem;padding:.25rem .6rem;background:var(--bg3);border-radius:4px;font-size:.8rem;font-family:'SF Mono',Monaco,Consolas,monospace}
.tag-remove{cursor:pointer;opacity:.5;transition:var(--transition);background:none;border:none;color:var(--text);font-size:1rem;line-height:1;padding:0 0 0 .2rem}
.tag-remove:hover{opacity:1;color:var(--red)}

/* Badge */
.badge{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.badge-green{background:var(--green-bg);color:var(--green)}
.badge-yellow{background:var(--yellow-bg);color:var(--yellow)}
.badge-blue{background:var(--primary-bg);color:var(--primary)}

/* Service cards */
.svc-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:1.25rem;margin-bottom:.75rem;transition:var(--transition)}
.svc-card:hover{border-color:var(--border2)}
.svc-header{display:flex;align-items:center;justify-content:space-between}
.svc-name{font-weight:600;font-size:1rem;display:flex;align-items:center;gap:.5rem}
.svc-url{color:var(--text3);font-size:.8rem;margin-top:.25rem;font-family:'SF Mono',Monaco,Consolas,monospace}
.svc-models{margin-top:.75rem}
.svc-models-label{font-size:.75rem;color:var(--text3);margin-bottom:.3rem}

/* Key list */
.key-item{display:flex;align-items:center;justify-content:space-between;padding:.75rem 1rem;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:.5rem}
.key-value{font-family:'SF Mono',Monaco,Consolas,monospace;font-size:.85rem;color:var(--text2)}

/* Modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;z-index:100;padding:1rem;backdrop-filter:blur(4px)}
.modal{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:2rem;width:100%;max-width:540px;max-height:90vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.modal h3{font-size:1.15rem;font-weight:700;margin-bottom:1.25rem}
.modal-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.5rem}

/* Toast */
.toast-container{position:fixed;top:1rem;right:1rem;z-index:200;display:flex;flex-direction:column;gap:.5rem}
.toast{padding:.75rem 1.25rem;border-radius:var(--radius-sm);font-size:.85rem;animation:slideIn .3s ease;max-width:360px;box-shadow:var(--shadow)}
.toast-success{background:#065f46;color:#a7f3d0;border:1px solid #10b981}
.toast-error{background:#7f1d1d;color:#fca5a5;border:1px solid #ef4444}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}

/* Dot */
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot-green{background:var(--green)}
.dot-red{background:var(--red)}
.dot-yellow{background:var(--yellow)}

/* Responsive */
.mobile-header{display:none;padding:1rem;background:var(--bg2);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:11}
.hamburger{background:none;border:none;color:var(--text);cursor:pointer;padding:.25rem}
@media(max-width:768px){
  .sidebar{transform:translateX(-100%);transition:transform .3s ease}
  .sidebar.open{transform:translateX(0)}
  .main{margin-left:0}
  .mobile-header{display:flex;align-items:center;justify-content:space-between}
  .form-row{grid-template-columns:1fr}
  .stats{grid-template-columns:1fr 1fr}
}

/* Password reveal */
.pw-wrap{position:relative}
.pw-wrap .form-input{padding-right:2.5rem}
.pw-toggle{position:absolute;right:.5rem;top:50%;transform:translateY(-50%);background:none;border:none;color:var(--text3);cursor:pointer;padding:.25rem;font-size:.8rem}
.pw-toggle:hover{color:var(--text)}

.empty-state{text-align:center;padding:3rem;color:var(--text3)}
.empty-state p{margin-top:.5rem;font-size:.9rem}
</style>
</head>
<body x-data="admin()" x-init="init()">

<!-- Toast -->
<div class="toast-container">
  <template x-for="(t,i) in toasts" :key="i">
    <div class="toast" :class="'toast-'+t.type" x-text="t.msg" x-show="t.show"
         x-init="setTimeout(()=>{t.show=false;setTimeout(()=>toasts.splice(i,1),300)},3000)"></div>
  </template>
</div>

<!-- Login -->
<template x-if="!authenticated">
  <div class="login-wrap">
    <div class="login-card">
      <h1><span>Toolify</span> 管理后台</h1>
      <p>输入已配置的客户端密钥以继续</p>
      <div class="form-group">
        <label class="form-label">API 密钥</label>
        <div class="pw-wrap">
          <input :type="showLoginPw?'text':'password'" class="form-input" x-model="loginKey"
                 @keydown.enter="login()" placeholder="sk-...">
          <button class="pw-toggle" @click="showLoginPw=!showLoginPw" x-text="showLoginPw?'隐藏':'显示'"></button>
        </div>
      </div>
      <button class="btn btn-primary" style="width:100%;justify-content:center;margin-top:.5rem" @click="login()">
        登录
      </button>
      <p x-show="loginErr" style="color:var(--red);margin-top:.75rem;font-size:.85rem;text-align:center" x-text="loginErr"></p>
    </div>
  </div>
</template>

<!-- Main -->
<template x-if="authenticated">
  <div>
    <!-- Mobile header -->
    <div class="mobile-header">
      <button class="hamburger" @click="sidebarOpen=!sidebarOpen">
        <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
      </button>
      <span style="font-weight:700"><span style="color:var(--primary)">Toolify</span> 管理后台</span>
      <div></div>
    </div>

    <div class="layout">
      <!-- Sidebar -->
      <aside class="sidebar" :class="{open:sidebarOpen}" @click.outside="sidebarOpen=false">
        <div class="sidebar-brand"><span>Toolify</span> 管理后台</div>
        <nav class="sidebar-nav">
          <button class="nav-item" :class="{active:page==='dashboard'}" @click="page='dashboard';sidebarOpen=false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
            仪表盘
          </button>
          <button class="nav-item" :class="{active:page==='services'}" @click="page='services';sidebarOpen=false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            上游服务
          </button>
          <button class="nav-item" :class="{active:page==='keys'}" @click="page='keys';sidebarOpen=false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
            客户端密钥
          </button>
          <button class="nav-item" :class="{active:page==='features'}" @click="page='features';sidebarOpen=false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
            功能配置
          </button>
          <button class="nav-item" :class="{active:page==='server'}" @click="page='server';sidebarOpen=false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><circle cx="6" cy="6" r="1"/><circle cx="6" cy="18" r="1"/></svg>
            服务器配置
          </button>
        </nav>
        <div class="sidebar-footer">
          <button class="btn btn-ghost btn-sm" style="width:100%;justify-content:center" @click="logout()">退出登录</button>
        </div>
      </aside>

      <!-- Content -->
      <main class="main">

        <!-- Dashboard -->
        <div x-show="page==='dashboard'" x-transition.opacity>
          <h2 class="page-title">仪表盘</h2>
          <div class="stats">
            <div class="stat-card">
              <div class="stat-label">上游服务</div>
              <div class="stat-value" x-text="config?.upstream_services?.length||0"></div>
            </div>
            <div class="stat-card">
              <div class="stat-label">模型数量</div>
              <div class="stat-value" x-text="totalModels"></div>
            </div>
            <div class="stat-card">
              <div class="stat-label">客户端密钥</div>
              <div class="stat-value" x-text="config?.client_authentication?.allowed_keys?.length||0"></div>
            </div>
          </div>
          <div class="card">
            <div class="card-title" style="margin-bottom:1rem">功能状态</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem .75rem">
              <template x-for="f in featureStatusList">
                <div style="display:flex;align-items:center;gap:.5rem;font-size:.85rem">
                  <span class="dot" :class="f.on?'dot-green':'dot-red'"></span>
                  <span x-text="f.label"></span>
                </div>
              </template>
            </div>
          </div>
          <div class="card">
            <div class="card-title" style="margin-bottom:.75rem">服务器</div>
            <div style="font-size:.9rem;color:var(--text2)">
              <span x-text="(config?.server?.host||'0.0.0.0')+':'+(config?.server?.port||8000)"></span>
              &nbsp;&middot;&nbsp; 超时: <span x-text="(config?.server?.timeout||180)+'秒'"></span>
            </div>
          </div>
        </div>

        <!-- Services -->
        <div x-show="page==='services'" x-transition.opacity>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">
            <h2 class="page-title" style="margin:0">上游服务</h2>
            <button class="btn btn-primary" @click="openServiceModal()">+ 添加服务</button>
          </div>
          <template x-if="!config?.upstream_services?.length">
            <div class="empty-state"><p>暂无上游服务配置</p></div>
          </template>
          <template x-for="(svc,i) in (config?.upstream_services||[])" :key="svc.name">
            <div class="svc-card">
              <div class="svc-header">
                <div>
                  <div class="svc-name">
                    <span x-text="svc.name"></span>
                    <span class="badge badge-green" x-show="svc.is_default">默认</span>
                  </div>
                  <div class="svc-url" x-text="svc.base_url"></div>
                  <div x-show="svc.description" style="font-size:.8rem;color:var(--text3);margin-top:.15rem" x-text="svc.description"></div>
                </div>
                <div class="btn-group">
                  <button class="btn btn-ghost btn-sm" @click="openServiceModal(svc)">编辑</button>
                  <button class="btn btn-danger btn-sm" @click="confirmDeleteService(svc.name)">删除</button>
                </div>
              </div>
              <div class="svc-models">
                <div class="svc-models-label">模型 (<span x-text="svc.models?.length||0"></span>)</div>
                <div class="tags">
                  <template x-for="m in (svc.models||[])" :key="m">
                    <span class="tag" x-text="m"></span>
                  </template>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- Keys -->
        <div x-show="page==='keys'" x-transition.opacity>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">
            <h2 class="page-title" style="margin:0">客户端密钥</h2>
            <div class="btn-group">
              <button class="btn btn-ghost" @click="generateKey()">生成随机密钥</button>
              <button class="btn btn-primary" @click="showAddKey=true;newKey=''">+ 添加密钥</button>
            </div>
          </div>
          <template x-if="showAddKey">
            <div class="card" style="margin-bottom:1rem">
              <div class="form-group" style="margin:0">
                <label class="form-label">新密钥</label>
                <div style="display:flex;gap:.5rem">
                  <input class="form-input" x-model="newKey" placeholder="sk-..." @keydown.enter="addKey()">
                  <button class="btn btn-primary" @click="addKey()">添加</button>
                  <button class="btn btn-ghost" @click="showAddKey=false">取消</button>
                </div>
              </div>
            </div>
          </template>
          <template x-for="(k,i) in (config?.client_authentication?.allowed_keys||[])" :key="i">
            <div class="key-item">
              <span class="key-value" x-text="maskKey(k)"></span>
              <div class="btn-group">
                <button class="btn btn-ghost btn-sm" @click="copyText(k)">复制</button>
                <button class="btn btn-danger btn-sm" @click="confirmDeleteKey(i)"
                        :disabled="(config?.client_authentication?.allowed_keys?.length||0)<=1">删除</button>
              </div>
            </div>
          </template>
        </div>

        <!-- Features -->
        <div x-show="page==='features'" x-transition.opacity>
          <h2 class="page-title">功能配置</h2>
          <p class="page-desc">修改将保存到配置文件，需重启服务生效</p>
          <div class="card">
            <div class="toggle-wrap">
              <div class="toggle-info">
                <h4>函数调用</h4>
                <p>为上游模型注入工具/函数调用能力</p>
              </div>
              <label class="toggle"><input type="checkbox" x-model="feat.enable_function_calling" @change="saveFeatures()"><span class="toggle-slider"></span></label>
            </div>
            <div class="toggle-wrap">
              <div class="toggle-info">
                <h4>Developer 转 System 角色</h4>
                <p>将 developer 角色消息转换为 system 角色</p>
              </div>
              <label class="toggle"><input type="checkbox" x-model="feat.convert_developer_to_system" @change="saveFeatures()"><span class="toggle-slider"></span></label>
            </div>
            <div class="toggle-wrap">
              <div class="toggle-info">
                <h4>密钥透传</h4>
                <p>直接转发客户端 API 密钥到上游，而非使用配置的密钥</p>
              </div>
              <label class="toggle"><input type="checkbox" x-model="feat.key_passthrough" @change="saveFeatures()"><span class="toggle-slider"></span></label>
            </div>
            <div class="toggle-wrap">
              <div class="toggle-info">
                <h4>模型透传</h4>
                <p>将所有请求转发到 'openai' 上游服务，忽略模型路由</p>
              </div>
              <label class="toggle"><input type="checkbox" x-model="feat.model_passthrough" @change="saveFeatures()"><span class="toggle-slider"></span></label>
            </div>
            <div class="toggle-wrap">
              <div class="toggle-info">
                <h4>函数调用错误自动重试</h4>
                <p>当函数调用解析失败时自动重试</p>
              </div>
              <label class="toggle"><input type="checkbox" x-model="feat.enable_fc_error_retry" @change="saveFeatures()"><span class="toggle-slider"></span></label>
            </div>
          </div>
          <div class="card">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">日志级别</label>
                <select class="form-input" x-model="feat.log_level" @change="saveFeatures()">
                  <option>DEBUG</option><option>INFO</option><option>WARNING</option><option>ERROR</option><option>CRITICAL</option><option>DISABLED</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">函数调用重试次数</label>
                <div style="display:flex;align-items:center;gap:.75rem">
                  <input type="range" min="1" max="10" x-model.number="feat.fc_error_retry_max_attempts" @change="saveFeatures()" style="flex:1">
                  <span style="font-weight:600;min-width:1.5rem;text-align:center" x-text="feat.fc_error_retry_max_attempts"></span>
                </div>
              </div>
            </div>
          </div>
          <div class="card">
            <div class="form-group">
              <label class="form-label">自定义 Prompt 模板 <span style="color:var(--text3);font-weight:400">(可选，必须包含 {tools_list} 和 {trigger_signal})</span></label>
              <textarea class="form-input" rows="5" x-model="feat.prompt_template" @blur="saveFeatures()" placeholder="留空使用默认 prompt..."></textarea>
            </div>
            <div class="form-group" style="margin:0">
              <label class="form-label">函数调用错误重试 Prompt <span style="color:var(--text3);font-weight:400">(可选，必须包含 {error_details} 和 {original_response})</span></label>
              <textarea class="form-input" rows="4" x-model="feat.fc_error_retry_prompt_template" @blur="saveFeatures()" placeholder="留空使用默认 prompt..."></textarea>
            </div>
          </div>
        </div>

        <!-- Server -->
        <div x-show="page==='server'" x-transition.opacity>
          <h2 class="page-title">服务器配置</h2>
          <p class="page-desc">修改将保存到配置文件，需重启服务生效</p>
          <div class="card">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">主机地址</label>
                <input class="form-input" x-model="srv.host">
              </div>
              <div class="form-group">
                <label class="form-label">端口</label>
                <input type="number" class="form-input" x-model.number="srv.port" min="1" max="65535">
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">超时时间（秒）</label>
              <input type="number" class="form-input" x-model.number="srv.timeout" min="1" style="max-width:200px">
            </div>
            <button class="btn btn-primary" @click="saveServer()">保存</button>
          </div>
        </div>

      </main>
    </div>

    <!-- Service Modal -->
    <template x-if="showSvcModal">
      <div class="modal-overlay" @click.self="showSvcModal=false">
        <div class="modal">
          <h3 x-text="editingSvc?'编辑服务':'添加服务'"></h3>
          <div class="form-group">
            <label class="form-label">名称</label>
            <input class="form-input" x-model="svcForm.name" :disabled="!!editingSvc" placeholder="例如: openai">
          </div>
          <div class="form-group">
            <label class="form-label">Base URL</label>
            <input class="form-input" x-model="svcForm.base_url" placeholder="https://api.openai.com/v1">
          </div>
          <div class="form-group">
            <label class="form-label">API 密钥</label>
            <div class="pw-wrap">
              <input :type="showSvcKey?'text':'password'" class="form-input" x-model="svcForm.api_key" placeholder="sk-...">
              <button class="pw-toggle" @click="showSvcKey=!showSvcKey" x-text="showSvcKey?'隐藏':'显示'"></button>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <input class="form-input" x-model="svcForm.description" placeholder="可选描述">
          </div>
          <div class="toggle-wrap" style="padding:.5rem 0;border:none">
            <div class="toggle-info"><h4>默认服务</h4></div>
            <label class="toggle"><input type="checkbox" x-model="svcForm.is_default"><span class="toggle-slider"></span></label>
          </div>
          <div class="form-group">
            <label class="form-label">模型列表</label>
            <div class="tags" style="margin-bottom:.5rem">
              <template x-for="(m,i) in svcForm.models" :key="i">
                <span class="tag"><span x-text="m"></span><button class="tag-remove" @click="svcForm.models.splice(i,1)">&times;</button></span>
              </template>
            </div>
            <div style="display:flex;gap:.5rem">
              <input class="form-input" x-model="newModel" placeholder="模型名 或 别名:模型名" @keydown.enter="addModel()">
              <button class="btn btn-ghost" @click="addModel()">添加</button>
            </div>
            <div class="form-hint">使用 "别名:真实模型名" 格式定义模型别名</div>
          </div>
          <div class="modal-actions">
            <button class="btn btn-ghost" @click="showSvcModal=false">取消</button>
            <button class="btn btn-primary" @click="saveService()" x-text="editingSvc?'更新':'创建'"></button>
          </div>
        </div>
      </div>
    </template>

    <!-- Confirm Modal -->
    <template x-if="confirmModal.show">
      <div class="modal-overlay" @click.self="confirmModal.show=false">
        <div class="modal" style="max-width:400px">
          <h3 x-text="confirmModal.title"></h3>
          <p style="color:var(--text2);font-size:.9rem" x-text="confirmModal.msg"></p>
          <div class="modal-actions">
            <button class="btn btn-ghost" @click="confirmModal.show=false">取消</button>
            <button class="btn btn-danger" @click="confirmModal.fn();confirmModal.show=false">删除</button>
          </div>
        </div>
      </div>
    </template>

  </div>
</template>

<script>
function admin(){return{
  // State
  authenticated:false,
  page:'dashboard',
  config:null,
  loginKey:'',
  loginErr:'',
  showLoginPw:false,
  sidebarOpen:false,
  toasts:[],
  apiKey:'',

  // Server
  srv:{host:'0.0.0.0',port:8000,timeout:180},

  // Features
  feat:{
    enable_function_calling:true,
    log_level:'INFO',
    convert_developer_to_system:true,
    key_passthrough:false,
    model_passthrough:false,
    enable_fc_error_retry:false,
    fc_error_retry_max_attempts:3,
    prompt_template:null,
    fc_error_retry_prompt_template:null,
  },

  // Service modal
  showSvcModal:false,
  editingSvc:null,
  showSvcKey:false,
  svcForm:{name:'',base_url:'',api_key:'',description:'',is_default:false,models:[]},
  newModel:'',

  // Keys
  showAddKey:false,
  newKey:'',

  // Confirm
  confirmModal:{show:false,title:'',msg:'',fn:()=>{}},

  get totalModels(){
    let n=0;(this.config?.upstream_services||[]).forEach(s=>n+=(s.models||[]).length);return n;
  },
  get featureStatusList(){
    const f=this.config?.features||{};
    return[
      {label:'函数调用',on:f.enable_function_calling!==false},
      {label:'角色转换',on:f.convert_developer_to_system!==false},
      {label:'密钥透传',on:!!f.key_passthrough},
      {label:'模型透传',on:!!f.model_passthrough},
      {label:'错误重试',on:!!f.enable_fc_error_retry},
    ];
  },

  init(){
    const k=localStorage.getItem('toolify_admin_key');
    if(k){this.apiKey=k;this.authenticated=true;this.loadConfig();}
  },

  toast(msg,type='success'){this.toasts.push({msg,type,show:true})},

  async api(method,path,body){
    const opts={method,headers:{'Authorization':'Bearer '+this.apiKey,'Content-Type':'application/json'}};
    if(body)opts.body=JSON.stringify(body);
    const r=await fetch(path,opts);
    if(r.status===401){this.authenticated=false;localStorage.removeItem('toolify_admin_key');throw new Error('未授权');}
    if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'请求失败');}
    return r.json();
  },

  async login(){
    this.loginErr='';
    try{
      const r=await fetch('/admin/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:this.loginKey})});
      if(!r.ok){this.loginErr='密钥无效';return;}
      this.apiKey=this.loginKey;
      localStorage.setItem('toolify_admin_key',this.apiKey);
      this.authenticated=true;
      this.loadConfig();
    }catch(e){this.loginErr='连接失败';}
  },

  logout(){this.authenticated=false;this.apiKey='';localStorage.removeItem('toolify_admin_key');},

  async loadConfig(){
    try{
      this.config=await this.api('GET','/admin/api/config');
      const s=this.config.server||{};
      this.srv={host:s.host||'0.0.0.0',port:s.port||8000,timeout:s.timeout||180};
      const f=this.config.features||{};
      this.feat={
        enable_function_calling:f.enable_function_calling!==false,
        log_level:f.log_level||'INFO',
        convert_developer_to_system:f.convert_developer_to_system!==false,
        key_passthrough:!!f.key_passthrough,
        model_passthrough:!!f.model_passthrough,
        enable_fc_error_retry:!!f.enable_fc_error_retry,
        fc_error_retry_max_attempts:f.fc_error_retry_max_attempts||3,
        prompt_template:f.prompt_template||null,
        fc_error_retry_prompt_template:f.fc_error_retry_prompt_template||null,
      };
    }catch(e){this.toast(e.message,'error');}
  },

  async saveServer(){
    try{await this.api('PUT','/admin/api/config/server',this.srv);await this.loadConfig();this.toast('服务器配置已保存');}
    catch(e){this.toast(e.message,'error');}
  },

  async saveFeatures(){
    try{
      const data={...this.feat};
      if(!data.prompt_template)data.prompt_template=null;
      if(!data.fc_error_retry_prompt_template)data.fc_error_retry_prompt_template=null;
      await this.api('PUT','/admin/api/features',data);
      await this.loadConfig();
      this.toast('功能配置已保存');
    }catch(e){this.toast(e.message,'error');}
  },

  openServiceModal(svc){
    this.showSvcKey=false;this.newModel='';
    if(svc){
      this.editingSvc=svc.name;
      this.svcForm={name:svc.name,base_url:svc.base_url,api_key:svc.api_key,description:svc.description||'',is_default:!!svc.is_default,models:[...(svc.models||[])]};
    }else{
      this.editingSvc=null;
      this.svcForm={name:'',base_url:'',api_key:'',description:'',is_default:false,models:[]};
    }
    this.showSvcModal=true;
  },

  addModel(){
    const m=this.newModel.trim();
    if(m&&!this.svcForm.models.includes(m)){this.svcForm.models.push(m);this.newModel='';}
  },

  async saveService(){
    try{
      if(!this.svcForm.name||!this.svcForm.base_url||!this.svcForm.api_key){this.toast('名称、URL 和密钥为必填项','error');return;}
      if(this.editingSvc){
        await this.api('PUT','/admin/api/services/'+encodeURIComponent(this.editingSvc),this.svcForm);
        this.toast('服务已更新');
      }else{
        await this.api('POST','/admin/api/services',this.svcForm);
        this.toast('服务已创建');
      }
      this.showSvcModal=false;
      await this.loadConfig();
    }catch(e){this.toast(e.message,'error');}
  },

  confirmDeleteService(name){
    this.confirmModal={show:true,title:'删除服务',msg:'确定删除上游服务 "'+name+'"？此操作无法撤销。',fn:async()=>{
      try{await this.api('DELETE','/admin/api/services/'+encodeURIComponent(name));await this.loadConfig();this.toast('服务已删除');}
      catch(e){this.toast(e.message,'error');}
    }};
  },

  maskKey(k){if(k.length<=8)return k;return k.slice(0,6)+'****'+k.slice(-4);},

  async generateKey(){
    try{const r=await this.api('GET','/admin/api/generate-key');this.newKey=r.key;this.showAddKey=true;}
    catch(e){this.toast(e.message,'error');}
  },

  async addKey(){
    const k=this.newKey.trim();
    if(!k){this.toast('密钥不能为空','error');return;}
    try{await this.api('POST','/admin/api/keys',{key:k});this.showAddKey=false;this.newKey='';await this.loadConfig();this.toast('密钥已添加');}
    catch(e){this.toast(e.message,'error');}
  },

  confirmDeleteKey(i){
    this.confirmModal={show:true,title:'删除密钥',msg:'确定删除此客户端密钥？此操作无法撤销。',fn:async()=>{
      try{await this.api('DELETE','/admin/api/keys/'+i);await this.loadConfig();this.toast('密钥已删除');}
      catch(e){this.toast(e.message,'error');}
    }};
  },

  async copyText(t){try{await navigator.clipboard.writeText(t);this.toast('已复制');}catch(e){this.toast('复制失败','error');}},
}}
</script>
</body>
</html>"""
