#!/usr/bin/env python3
"""
HTML 转 PDF 工具 — 高质量转换面试复习资料
用法:
  python3 html2pdf.py                      # 转换当前目录所有 html
  python3 html2pdf.py file.html            # 转换单个文件
  python3 html2pdf.py a.html b.html        # 转换多个文件
  python3 html2pdf.py --dpi=3 file.html    # 指定 DPI（默认2，越高越清晰）
"""

import subprocess
import sys
import os
import glob
import shutil
import tempfile
import re

# ── 配置 ──
DEFAULT_DPI = 2  # 设备缩放倍数，2=Retina清晰度，3=超清（文件更大）
PAGE_WAIT_MS = 10000  # 等待页面渲染时间（毫秒）

# ── 查找浏览器 ──
BROWSER_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]

def find_browser():
    """查找系统上可用的 Chromium 内核浏览器"""
    for path in BROWSER_PATHS:
        if os.path.exists(path):
            return path
    for name in ("google-chrome", "chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None

def get_chrome_version(browser_path):
    """获取 Chrome 版本号"""
    try:
        result = subprocess.run(
            [browser_path, "--version"],
            capture_output=True, text=True, timeout=10
        )
        m = re.search(r'(\d+)\.', result.stdout)
        return int(m.group(1)) if m else 0
    except:
        return 0

# ── 注入 CSS（展开所有折叠卡片 + 强制打印背景色）──
PDF_INJECT_CSS = """
<style id="_pdf_inject">
  /* ── 强制展开所有 Q&A 折叠卡片 ── */
  .qa-body {
    max-height: none !important;
    overflow: visible !important;
    transition: none !important;
  }
  .qa-card .qa-toggle { display: none !important; }
  .qa-card .qa-header { cursor: default !important; }
  /* 标记已展开 */
  .qa-card { /* all open by default for print */ }

  /* ── 打印优化 ── */
  /* 强制打印背景色和渐变 */
  * {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    color-adjust: exact !important;
  }
  /* 移除阴影（打印时阴影会变模糊） */
  .qa-card, .section, .toc, .header {
    box-shadow: none !important;
  }
  /* 避免卡片内容被分页截断 */
  .qa-card {
    page-break-inside: avoid;
    -webkit-column-break-inside: avoid;
  }
  /* 标题不与内容分离 */
  .section-title, .qa-title {
    page-break-after: avoid;
  }
  /* 隐藏不需要打印的元素 */
  .toolbar, .no-print { display: none !important; }
  /* 页面边距 */
  @page {
    margin: 12mm 10mm 15mm 10mm;
  }
  body {
    background: white !important;
    font-size: 14px;
  }
</style>
"""

def inject_print_css(html_content):
    """在 HTML 中注入打印优化 CSS"""
    if '</head>' in html_content:
        return html_content.replace('</head>', PDF_INJECT_CSS + '\n</head>')
    return PDF_INJECT_CSS + html_content

# ── 核心转换函数 ──
def html_to_pdf(input_path, output_path=None, dpi=DEFAULT_DPI):
    """
    将单个 HTML 文件转为 PDF
    返回: True 成功, False 失败
    """
    browser = find_browser()
    if not browser:
        print("  [错误] 未找到 Chrome/Chromium/Edge 浏览器")
        print("  请安装 Google Chrome: https://www.google.com/chrome/")
        return False

    input_path = os.path.abspath(input_path)
    if not os.path.exists(input_path):
        print(f"  [错误] 文件不存在: {input_path}")
        return False

    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + '.pdf'
    output_path = os.path.abspath(output_path)

    # 读取并注入 CSS
    with open(input_path, 'r', encoding='utf-8') as f:
        html = f.read()
    html = inject_print_css(html)

    # 写入临时文件
    tmp_dir = tempfile.mkdtemp(prefix='html2pdf_')
    tmp_html = os.path.join(tmp_dir, '_print.html')
    with open(tmp_html, 'w', encoding='utf-8') as f:
        f.write(html)

    # 判断 Chrome 版本，选择 headless 模式
    version = get_chrome_version(browser)
    headless_flag = '--headless=new' if version >= 112 else '--headless'

    # 使用临时用户数据目录（避免权限问题）
    user_data_dir = os.path.join(tmp_dir, 'chrome_profile')

    # 构建 Chrome 命令
    cmd = [
        browser,
        headless_flag,
        f'--user-data-dir={user_data_dir}',
        '--disable-gpu',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--no-pdf-header-footer',
        f'--force-device-scale-factor={dpi}',
        f'--virtual-time-budget={PAGE_WAIT_MS}',
        f'--print-to-pdf={output_path}',
        f'file://{tmp_html}',
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Chrome headless 即使成功生成 PDF，退出码也可能非 0
        # 所以以 PDF 文件是否生成且有效作为成功标准，不依赖 returncode
        pdf_ok = (os.path.exists(output_path)
                  and os.path.getsize(output_path) > 1000)

        if not pdf_ok and version >= 112:
            # 新版 headless 未生成 PDF 时回退到旧版重试
            cmd[1] = '--headless'
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            pdf_ok = (os.path.exists(output_path)
                      and os.path.getsize(output_path) > 1000)

        shutil.rmtree(tmp_dir, ignore_errors=True)

        if pdf_ok:
            # 验证 PDF 文件头
            with open(output_path, 'rb') as f:
                header = f.read(5)
            if header == b'%PDF-':
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                print(f"  [成功] {os.path.basename(output_path)} ({size_mb:.1f} MB)")
                return True
            else:
                print(f"  [失败] PDF 文件损坏（文件头异常）")
                return False
        else:
            stderr = result.stderr[:300] if result.stderr else '无输出'
            print(f"  [失败] PDF 未生成。浏览器输出: {stderr}")
            return False

    except subprocess.TimeoutExpired:
        # 超时后也检查一下 PDF 是否已生成（Chrome 可能已完成但进程未退出）
        pdf_ok = (os.path.exists(output_path)
                  and os.path.getsize(output_path) > 1000)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if pdf_ok:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  [成功] {os.path.basename(output_path)} ({size_mb:.1f} MB) [超时但已生成]")
            return True
        print(f"  [失败] 转换超时（120秒）且 PDF 未生成")
        return False
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"  [失败] {e}")
        return False

# ── 主入口 ──
def main():
    print("=" * 50)
    print("  HTML 转 PDF 工具 — 高质量转换")
    print("=" * 50)
    print()

    # 解析参数
    dpi = DEFAULT_DPI
    files = []
    for arg in sys.argv[1:]:
        if arg.startswith('--dpi='):
            dpi = int(arg.split('=')[1])
        elif arg.startswith('--'):
            print(f"未知参数: {arg}（支持: --dpi=N）")
            sys.exit(1)
        else:
            files.append(arg)

    # 没有指定文件则扫描当前目录所有 HTML
    if not files:
        files = sorted(glob.glob('*.html'))
        if not files:
            print("当前目录没有 HTML 文件")
            print("用法: python3 html2pdf.py [file.html ...] [--dpi=N]")
            sys.exit(1)
        print(f"找到 {len(files)} 个 HTML 文件，开始转换...\n")

    browser = find_browser()
    if not browser:
        print("[错误] 未找到 Chrome/Chromium/Edge 浏览器")
        print("请安装 Google Chrome: https://www.google.com/chrome/")
        sys.exit(1)

    browser_name = os.path.basename(browser).replace('Google Chrome', 'Chrome')
    version = get_chrome_version(browser)
    print(f"浏览器: {browser_name} v{version}")
    print(f"DPI 倍数: {dpi}x ({'超清' if dpi >= 3 else '高清' if dpi >= 2 else '普通'})")
    print()

    # 逐个转换
    success = 0
    failed = 0
    for f in files:
        if not os.path.exists(f):
            print(f"  [跳过] {f} — 文件不存在")
            failed += 1
            continue
        print(f"  转换: {f}")
        if html_to_pdf(f, dpi=dpi):
            success += 1
        else:
            failed += 1

    # 汇总
    print()
    print("-" * 50)
    print(f"  完成: {success} 成功, {failed} 失败")
    if success > 0:
        output_dir = os.path.dirname(os.path.abspath(files[0])) or '.'
        print(f"  PDF 保存在: {output_dir}/")
    print("-" * 50)

if __name__ == '__main__':
    main()
