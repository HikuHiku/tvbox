# -*- coding: utf-8 -*-
import requests
import re
import os
import json
import base64
import codecs
from pathlib import Path
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

AllSource = []
class TvboxDownloader:
    def __init__(self, my_repo, source_url, output_dir=Path("tvbox_output"), source_name="default", remove_list=[]):
        self.my_repo = my_repo
        self.source_url = source_url.strip()
        self.output_dir = output_dir
        self.source_name = source_name
        self.remove_list = remove_list
        self.jar_dir = self.output_dir / "jar"
        self.headers = {
            "user-agent": "okhttp/3.15",
            "accept": "application/json, text/plain, */*"
        }
        self.s = requests.Session()
        self.timeout = (10, 30)
        
        # 创建目录
        self.output_dir.mkdir(exist_ok=True)
        self.jar_dir.mkdir(exist_ok=True)

    def download_file(self, url, save_path):
        """通用下载，自动清洗 URL"""
        try:
            clean_url = url.split(';')[0].strip()
            print(f"  正在下载: {clean_url}")
            
            r = self.s.get(clean_url, headers=self.headers, timeout=self.timeout, verify=False)
            r.raise_for_status()
            with open(save_path, 'wb') as f:
                f.write(r.content)
            print(f"  ✓ 已保存: {save_path.name} ({len(r.content)} bytes)")
            return True
        except Exception as e:
            print(f"  ✗ 下载失败: {e}")
            return False

    def clean_json_content(self, text):
        """只删除以 // 开头的注释行，保留 URL 中的 //"""
        lines = text.splitlines()
        cleaned_lines = []
        
        for line in lines:
            # 检查是否以 // 开头（允许前导空格）
            stripped = line.strip()
            if stripped.startswith('//'):
                print(f"  删除注释行: {line[:50]}...")
                continue  # 跳过注释行
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def picparse(self, url):
        """从图片解析隐藏内容（Base64 解码）"""
        try:
            print("  检测到图片伪装，尝试 Base64 解码...")
            r = self.s.get(url, headers=self.headers, timeout=self.timeout, verify=False)
            
            # 提取所有 Base64 块
            pattern = r'([A-Za-z0-9+/]+={0,2})'
            matches = re.findall(pattern, r.text)
            
            if not matches:
                print("  ✗ 未找到 Base64 内容")
                return None
            
            # 尝试每个匹配项（取最长的）
            decoded = None
            for match in sorted(matches, key=len, reverse=True):
                try:
                    decoded = base64.b64decode(match).decode('utf-8')
                    if 'searchable' in decoded or 'sites' in decoded:
                        print("  ✓ Base64 解码成功")
                        break
                except:
                    continue
            
            if not decoded:
                print("  ✗ 所有 Base64 块解码失败")
                return None
            
            # 只清理 // 注释
            cleaned = self.clean_json_content(decoded)
            
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                print(f"  ✗ 清理后 JSON 仍无效: {e}")
                print(f"  错误位置附近内容: {cleaned[e.pos-30:e.pos+30]}")
                return None
                
        except Exception as e:
            print(f"  ✗ Base64 解码失败: {e}")
            return None

    def fetch_json(self, url):
        """增强版 JSON 获取"""
        try:
            r = self.s.get(url, headers=self.headers, timeout=self.timeout, verify=False)
            
            # 调试信息
            print(f"  HTTP状态码: {r.status_code}")
            print(f"  Content-Type: {r.headers.get('content-type', 'unknown')}")
            
            # 处理 BOM
            content = r.content
            if content.startswith(codecs.BOM_UTF8):
                content = content[len(codecs.BOM_UTF8):]
            
            # 检测图片伪装
            content_type = r.headers.get('content-type', '')
            if 'image' in content_type or content.startswith(b'\xff\xd8') or content.startswith(b'BM'):
                return self.picparse(url)
            
            # 普通文本处理
            text = content.decode('utf-8', errors='ignore')
            cleaned = self.clean_json_content(text)
            
            try:
                return json.loads(cleaned)
            except:
                # 如果失败，尝试 GBK 编码
                text = content.decode('gbk', errors='ignore')
                cleaned = self.clean_json_content(text)
                return json.loads(cleaned)
                
        except Exception as e:
            print(f"✗ 请求失败: {e}")
            return None

    def run(self):
        """主流程"""
        print(f"\n{'='*60}")
        print(f"开始处理线路: {self.source_name}")
        print(f"源地址: {self.source_url}")
        print(f"{'='*60}\n")
        
        # 1. 下载并解析线路 JSON
        line_data = self.fetch_json(self.source_url)
        if not line_data:
            print("✗ 无法获取有效的线路数据")
            return
        
        # 2. 过滤站点
        if self.remove_list and 'sites' in line_data:
            original_count = len(line_data['sites'])
            line_data['sites'] = [
                site for site in line_data['sites'] 
                if not any(substr in site['name'] for substr in self.remove_list)
            ]
            filtered_count = len(line_data['sites'])
            print(f"站点过滤: {original_count} → {filtered_count} (移除了 {original_count - filtered_count} 个)\n")
        
        # 3. 下载 jar
        spider_url = line_data.get('spider')
        if spider_url:
            jar_name = f"{self.source_name}.jar"
            jar_path = self.jar_dir / jar_name
            
            if self.download_file(spider_url, jar_path):
                line_data['spider'] = f"{self.my_repo}/jar/{jar_name}"
        else:
            print("⚠ 未找到 spider 字段，跳过 jar 下载\n")
        
        # 4. 保存 JSON
        json_path = self.output_dir / f"{self.source_name}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(line_data, f, ensure_ascii=False, indent=4)
        
        print(f"\n✓ 线路 JSON 已保存: {json_path}")
        print(f"{'='*60}")
        print(f"完成！文件在: {self.output_dir.absolute()}")
        print(f"{'='*60}")
        AllSource.append({
            "name": self.source_name,
            "url": f"{self.my_repo}/{self.source_name}.json"
        })

if __name__ == '__main__':
    # 这里填写你的仓库地址，镜像源可以随便换你想用的，或者可以直连github就直接去掉镜像
    MY_REPO = "https://gh-proxy.com/https://raw.githubusercontent.com/YOUR_NAME/tvbox/main"
    # 这里填写下载配置文件的地址，该脚本将会把线路的json和jar文件下载至你的电脑硬盘中
    OUTPUT_DIR = Path("D:/TvboxSource")
    
    # 这里填写你要下载的线路信息，REMOVE_LIST用于匹配并删除包含这些关键词的站点
    # 比方说我不喜欢用各种网盘，想把那些用不到的各类网盘站点去掉，那么在REMOVE_LIST中填入'4K'即可去掉大部分网盘站点
    # 该脚本仅支持下载单仓线路，且没有增加其它功能的打算，下载后自行push到你的仓库即可
    Sources = [
        {
            "SOURCE_NAME": "王二小",
            "SOURCE_URL": "http://tvbox.xn--4kq62z5rby2qupq9ub.top/",
            "REMOVE_LIST": ['4K', '我的','哔哩','哔哔','配置中心','网盘','给力','推送','综合']
        },
        {
            "SOURCE_NAME": "饭太硬",
            "SOURCE_URL": "http://www.饭太硬.com/tv",
            "REMOVE_LIST": ['4K','预告片','三盘','搜搜','优夸','夸父','推送','哔哔','我的']
        },
        {
            "SOURCE_NAME": "jack老师",
            "SOURCE_URL": "https://ok321.top/tv",
            "REMOVE_LIST": ['4K','搜索','我的','哔哩']
        },
        {
            "SOURCE_NAME": "巧技",
            "SOURCE_URL": "http://cdn.qiaoji8.com/tvbox.json",
            "REMOVE_LIST": ['4K']
        }
    ]
    
    for i, source in enumerate(Sources):
        print(f"\n[{i+1}/{len(Sources)}] {'='*50}")
        downloader = TvboxDownloader(
            MY_REPO,
            source["SOURCE_URL"], 
            OUTPUT_DIR, 
            source["SOURCE_NAME"], 
            source["REMOVE_LIST"]
        )
        downloader.run()
    Alljson = {"urls":AllSource}
    all_path = OUTPUT_DIR / "all.json"
    with open(all_path, 'w', encoding='utf-8') as f:
        json.dump(Alljson, f, ensure_ascii=False, indent=4)
        print(f"✓ 配置 JSON 已保存: {all_path}")