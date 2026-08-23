#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_workshop.py —— 把四个独立工具合并为 tools/workshop.html（真实 DOM 合并，非 iframe）
四个工具：ocr_clean_gui.html / merge_apply.html / detail_rich_gui.html / causal_judge_gui.html

合并策略（解决三个独立单页并存的三大冲突）：
  1) ID 冲突  → 每个工具的所有 id 加前缀（ocr- / mg- / dr-），JS 引用同步改
  2) CSS 冲突 → 每个工具的样式选择器加作用域前缀 `.tool-ocr/.tool-mg/.tool-dr`
               （body/html/:root/* 映射到面板根；@media 递归；@keyframes 改名）
  3) JS 冲突 → 每个工具的脚本包进 initToolX() 函数，首次切到该标签才初始化（懒加载）
标签栏样式参考 index.html「关于」页：.about-tabs / .about-tab（下划线式，红 #b22222 高亮）。

运行：python tools/build_workshop.py   →  重写 tools/workshop.html
"""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS = [
    ("ocr",    "ocr_clean_gui.html"),
    ("mg",     "merge_apply.html"),
    ("dr",     "detail_rich_gui.html"),
    ("cj",     "causal_judge_gui.html"),
]
OUT = os.path.join(ROOT, "workshop.html")


def read_braced(s, i):
    """s[i] 为 '{'，返回 (括号内内容, 匹配的 '}' 之后的下标)"""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return s[i + 1:], len(s)


def split_top(text, sep=","):
    """按 sep 分割，但忽略 () / [] / {} 内部的 sep（用于 CSS 选择器列表）"""
    out, depth, cur = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return out


def scope_selectors(sel, P):
    out = []
    for s in split_top(sel):
        s = s.strip()
        if not s:
            continue
        if s in (":root", "body", "html"):
            out.append(".tool-" + P)
        elif s.startswith("body") or s.startswith("html"):
            out.append(".tool-" + P + s[len("body"):] if s.startswith("body") else "." + P + s[len("html"):])
        elif s == "*":
            out.append(".tool-" + P + " *")
        elif s.startswith("*"):
            out.append(".tool-" + P + " " + s)
        else:
            out.append(".tool-" + P + " " + s)
    return ", ".join(out)


def scope_css(css, P):
    out, i, n = [], 0, len(css)
    while i < n:
        c = css[i]
        if c.isspace() or c == ";":
            out.append(c)
            i += 1
            continue
        if c == "@":
            j = css.find("{", i)
            if j < 0:
                out.append(css[i:])
                break
            head = css[i:j].strip()
            body, k = read_braced(css, j)
            if head.startswith("@media"):
                out.append(head + " {\n" + scope_css(body, P) + "\n}")
            elif head.startswith("@keyframes"):
                parts = head.split()
                if len(parts) >= 2:
                    out.append("@keyframes " + P + "-" + parts[1] + " {\n" + body + "\n}")
                else:
                    out.append(head + " {\n" + body + "\n}")
            else:
                out.append(head + " {\n" + body + "\n}")
            i = k
            continue
        j = css.find("{", i)
        if j < 0:
            out.append(css[i:])
            break
        sel = css[i:j].strip()
        body, k = read_braced(css, j)
        out.append(scope_selectors(sel, P) + " {\n" + body + "\n}")
        i = k
    return "".join(out)


def extract_blocks(html):
    m_style = re.search(r"<style[^>]*>(.*?)</style>", html, re.S)
    m_body = re.search(r"<body[^>]*>(.*?)</body>", html, re.S) or re.search(r"<body[^>]*>(.*)$", html, re.S)
    m_script = re.search(r"<script[^>]*>(.*?)</script>", html, re.S)
    return (m_style.group(1) if m_style else "",
            m_body.group(1) if m_body else "",
            m_script.group(1) if m_script else "")


def prefix_js(script, P, ids):
    for X in sorted(ids, key=len, reverse=True):
        script = script.replace("$('" + X + "')", "$('" + P + "-" + X + "')")
        script = script.replace('$("' + X + '")', '$("' + P + "-" + X + '")')
        script = script.replace("getElementById('" + X + "')", "getElementById('" + P + "-" + X + "')")
        script = script.replace('getElementById("' + X + '")', 'getElementById("' + P + "-" + X + '")')
        script = script.replace("querySelector('#" + X + "')", "querySelector('#" + P + "-" + X + "')")
        script = script.replace('querySelector("#' + X + '")', 'querySelector("#' + P + "-" + X + '")')
        # JS 内动态创建的 id 字符串（如 innerHTML 里的 id="refreshBtn"）
        script = script.replace('id="' + X + '"', 'id="' + P + '-' + X + '"')
        script = script.replace("id='" + X + "'", "id='" + P + '-' + X + "'")
    return script


def main():
    styles, panels, inits = [], [], []
    for P, fn in TOOLS:
        html = open(os.path.join(ROOT, fn), encoding="utf-8").read()
        style, body, script = extract_blocks(html)
        ids = set(re.findall(r'id="([^"]+)"', body)) | set(re.findall(r'id="([^"]+)"', style)) \
            | set(re.findall(r'id=["\']([^"\']+)["\']', script))
        # HTML id 前缀
        for X in sorted(ids, key=len, reverse=True):
            body = re.sub(r'id="' + re.escape(X) + r'"', 'id="' + P + '-' + X + '"', body)
            body = re.sub(r'for="' + re.escape(X) + r'"', 'for="' + P + '-' + X + '"', body)
        # CSS：#id 前缀 + 作用域
        for X in sorted(ids, key=len, reverse=True):
            style = re.sub(r"#" + re.escape(X) + r"(?![-\w])", "#" + P + "-" + X, style)
        style = scope_css(style, P)
        # JS：id 引用前缀
        script = prefix_js(script, P, ids)
        # body 里的 <script>/<style> 已分别提取，剥掉避免面板残留未加前缀的副本
        body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.S)
        body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.S)
        styles.append(style)
        panels.append('<section class="tool-panel tool-' + P + '" id="pan-' + P + '">\n' + body + '\n</section>')
        inits.append("function initTool" + P.upper() + "(){\n" + script + "\n}")

    shell_css = """
/* ===== 工作台外壳：参考 index.html 关于页标签样式 ===== */
body{margin:0;font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
     background:#f7f8fa;color:#1f2329;font-size:14px}
.workshop-head{padding:14px 18px 0;background:#fff;border-bottom:1px solid #e6e8ec}
.head-line{display:flex;align-items:center;gap:10px;margin-bottom:2px}
.workshop-head h1{font-size:17px;margin:0;color:#b22222}
#buildBtn{padding:4px 12px;border:1px solid #d8a0a0;border-radius:6px;background:#fdecec;color:#b22222;
          cursor:pointer;font-size:12px;font-family:inherit}
#buildBtn:hover{background:#f8d8d8}
#buildBtn:disabled{opacity:.55;cursor:not-allowed}
.build-prog{margin:8px 0 10px;padding:8px 12px;border:1px solid #e6e8ec;border-radius:8px;background:#fafbfc}
.bp-bar{height:8px;border-radius:4px;background:#e6e8ec;overflow:hidden}
.bp-fill{height:100%;width:0;background:linear-gradient(90deg,#b22222,#e57373);transition:width .8s ease}
.bp-text{display:block;font-size:12px;color:#6b7280;margin-top:6px}
.bp-text.done{color:#15803d}.bp-text.err{color:#b91c1c}
.hidden{display:none}
.workshop-head .sub{font-size:12px;color:#8a919c;margin-bottom:10px}
.about-tabs{display:flex;gap:8px;border-bottom:1px solid #eee}
.about-tab{flex:1;padding:8px 0;background:none;border:none;border-bottom:2px solid transparent;
           cursor:pointer;font-size:14px;color:#666;font-family:inherit}
.about-tab:hover{color:#b22222}
.about-tab.active{color:#b22222;border-bottom-color:#b22222;font-weight:600}
.tool-panel{display:none}
.tool-panel.active{display:block}
"""
    tab_js = """
/* ===== 标签切换 + 懒加载（参考 index 关于页交互）===== */
(function(){
  var TABS=[['ocr','pan-ocr','initToolOCR'],['merge','pan-mg','initToolMG'],['detail','pan-dr','initToolDR'],['cj','pan-cj','initToolCJ']];
  var inited={};
  function activate(name){
    TABS.forEach(function(t){
      var btn=document.querySelector('.about-tab[data-t="'+t[0]+'"]');
      var pan=document.getElementById(t[1]);
      if(t[0]===name){
        btn.classList.add('active'); pan.classList.add('active');
        if(!inited[t[0]]){
          inited[t[0]]=true;
          try{ window[t[2]](); }catch(err){ console.error('[workshop] init '+t[0]+' 失败:', err); }
        }
      }else{
        btn.classList.remove('active'); pan.classList.remove('active');
      }
    });
  }
  document.querySelectorAll('.about-tab').forEach(function(b){
    b.addEventListener('click', function(){ activate(b.getAttribute('data-t')); });
  });
  activate('detail');
})();

/* ===== 构建按钮 + 进度条：POST /api/build 启动 build_data.py，轮询 /api/build/status ===== */
(function(){
  var btn=document.getElementById('buildBtn');
  var box=document.getElementById('buildProg');
  var fill=document.getElementById('bpFill');
  var text=document.getElementById('bpText');
  var timer=null;
  function mmss(s){ var m=Math.floor(s/60), r=s%60; return m+'分'+(r<10?'0':'')+r+'秒'; }
  function parseProg(log){
    var p=0;
    if(/已重写/.test(log)) p=100;
    else{
      var m=log.match(/布局迭代 (\\d+)\\/640/); if(m) p=25+40*(+m[1])/640;
      else{
        m=log.match(/间距优化 (\\d+)\\/6000/); if(m) p=65+30*(+m[1])/6000;
        else{
          if(/CAUSAL_INFERRED/.test(log)) p=25;
          else if(/CAUSAL\\(verified\\)/.test(log)) p=15;
          else if(/事件总数/.test(log)) p=5;
          else if(/开始力导向/.test(log)) p=20;
        }
      }
    }
    return Math.max(2, Math.min(99, Math.round(p)));
  }
  function stage(log){
    var lines=log.trim().split(/\\r?\\n/); return lines[lines.length-1] || '';
  }
  function poll(){
    fetch('/api/build/status').then(function(r){return r.json();}).then(function(d){
      var p=parseProg(d.log||'');
      fill.style.width = (d.running ? Math.max(p,2) : 100) + '%';
      var st=stage(d.log||'');
      var t=d.running ? ('构建中 ' + p + '% · 已用 ' + mmss(d.elapsed||0)) : '';
      if(!d.running && d.done){
        text.textContent = (d.code===0?'✅ 构建完成，刷新页面查看 index.html':'❌ 构建失败（code '+d.code+'）');
        text.className = 'bp-text ' + (d.code===0?'done':'err');
        btn.disabled=false; clearInterval(timer);
      }else if(!d.running && !d.done && !d.log){
        text.textContent='尚无构建记录，点「⚙️ 构建」开始'; text.className='bp-text';
      }else if(!d.running && d.log){
        text.textContent='上次构建已结束：'+st; text.className='bp-text'; clearInterval(timer); btn.disabled=false;
      }else{
        text.textContent = t + '｜' + st; text.className='bp-text';
      }
    }).catch(function(){ text.textContent='无法连接构建服务（需通过 start_workshop.bat 打开）'; text.className='bp-text err'; clearInterval(timer); btn.disabled=false; });
  }
  btn.addEventListener('click', function(){
    btn.disabled=true; box.classList.remove('hidden'); fill.style.width='2%';
    text.textContent='启动构建…'; text.className='bp-text';
    fetch('/api/build', {method:'POST'}).then(function(r){return r.json();}).then(function(d){
      if(!d.ok){ text.textContent=(d.msg||'启动失败')+(d.error?('：'+d.error):''); text.className='bp-text err'; btn.disabled=false; return; }
      poll(); timer=setInterval(poll, 2000);
    }).catch(function(){ text.textContent='无法连接构建服务（需通过 start_workshop.bat 打开）'; text.className='bp-text err'; btn.disabled=false; });
  });
  // 页面打开时若已有构建在跑，恢复轮询
  fetch('/api/build/status').then(function(r){return r.json();}).then(function(d){
    if(d.running){ btn.disabled=true; box.classList.remove('hidden'); poll(); timer=setInterval(poll, 2000); }
  }).catch(function(){});
})();
"""

    html_out = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>星火日历 · 工具台（OCR 清洗 / 合并应用 / 详情丰富）</title>
<style>
""" + shell_css + "\n" + "\n".join(styles) + """
</style>
</head>
<body>
<header class="workshop-head">
  <div class="head-line">
    <h1>星火日历 · 工具台</h1>
    <button id="buildBtn" title="重跑 build_data.py 重建 index.html（力导向布局较慢，约 5-10 分钟）">⚙️ 构建 index</button>
  </div>
  <div id="buildProg" class="build-prog hidden">
    <div class="bp-bar"><div class="bp-fill" id="bpFill"></div></div>
    <span class="bp-text" id="bpText">准备构建…</span>
  </div>
  <div class="sub">统一服务（8001，双击 start_workshop.bat）＋ 本机 Ollama（OCR 清洗 / 因果裁判用）｜ 四个工具一键切换</div>
  <div class="about-tabs">
    <button class="about-tab" data-t="ocr">🧹 OCR 清洗</button>
    <button class="about-tab" data-t="merge">🔗 合并应用</button>
    <button class="about-tab" data-t="detail">✨ 详情丰富</button>
    <button class="about-tab" data-t="cj">⚖️ 因果裁判</button>
  </div>
</header>
<main>
""" + "\n".join(panels) + """
</main>
<script>
""" + "\n\n".join(inits) + "\n" + tab_js + """
</script>
</body>
</html>
"""
    open(OUT, "w", encoding="utf-8").write(html_out)
    print("已生成", OUT, "|", len(html_out), "字符")
    for P, fn in TOOLS:
        print("  -", P, ":", fn, "合并完成")


if __name__ == "__main__":
    main()
