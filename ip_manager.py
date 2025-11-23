import requests
import time
import json
import logging
from threading import Lock

class IPManager:
    def __init__(self, config):
        self.config = config
        self.current_ip = None
        self.ip_extract_time = 0
        self.ip_use_count = 0
        self.lock = Lock()
        self.logger = logging.getLogger('IPManager')
        
    def extract_ip(self):
        """从API提取IP"""
        try:
            if self.config.log_level >= 2:
                self.logger.info(f"开始从API提取IP: {self.config.api_url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(self.config.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            if self.config.log_level >= 2:
                self.logger.info(f"API响应状态码: {response.status_code}")
                self.logger.info(f"API响应内容: '{response.text}'")
            
            if self.config.api_format == 'json':
                try:
                    data = response.json()
                    if self.config.log_level >= 2:
                        self.logger.info(f"解析的JSON数据: {data}")
                    
                    # 尝试不同的JSON格式
                    ip_data = data.get('data', data)
                    if isinstance(ip_data, list):
                        ip_data = ip_data[0] if ip_data else {}
                    
                    ip = ip_data.get('ip', '')
                    port = ip_data.get('port', '')
                    username = ip_data.get('username', '')
                    password = ip_data.get('password', '')
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON解析失败: {e}")
                    return None
            else:
                # 文本格式
                if self.config.log_level >= 2:
                    self.logger.info("使用文本格式解析")
                
                parts = response.text.strip().split(':')
                ip = parts[0] if len(parts) > 0 else ''
                port = parts[1] if len(parts) > 1 else ''
                username = parts[2] if len(parts) > 2 else ''
                password = parts[3] if len(parts) > 3 else ''
            
            if self.config.log_level >= 2:
                self.logger.info(f"解析结果 - IP: '{ip}', Port: '{port}', Username: '{username}', Password: '{password}'")
            
            if ip and port:
                proxy_info = {
                    'ip': ip,
                    'port': int(port),
                    'username': username,
                    'password': password,
                    'extract_time': time.time()
                }
                if self.config.log_level >= 2:
                    self.logger.info(f"成功提取IP: {ip}:{port}")
                return proxy_info
            else:
                self.logger.error("API返回的IP格式不正确 - IP或端口为空")
                return None
                
        except Exception as e:
            self.logger.error(f"提取IP失败: {e}")
            return None
    
    def check_ip(self, proxy_info):
        """验证IP是否可用"""
        if not proxy_info:
            self.logger.error("proxy_info为空")
            return False
        
        # 如果关闭验证，直接返回成功
        if not self.config.check_proxies:
            return True
            
        try:
            if self.config.log_level >= 2:
                self.logger.info(f"开始验证IP: {proxy_info['ip']}:{proxy_info['port']}")
            
            # 构建代理URL
            proxy_dict = {}
            if proxy_info.get('username') and proxy_info.get('password'):
                auth = f"{proxy_info['username']}:{proxy_info['password']}"
                proxy_dict = {
                    'http': f"socks5://{auth}@{proxy_info['ip']}:{proxy_info['port']}",
                    'https': f"socks5://{auth}@{proxy_info['ip']}:{proxy_info['port']}"
                }
            else:
                proxy_dict = {
                    'http': f"socks5://{proxy_info['ip']}:{proxy_info['port']}",
                    'https': f"socks5://{proxy_info['ip']}:{proxy_info['port']}"
                }
            
            if self.config.log_level >= 2:
                self.logger.info(f"验证网址: {self.config.check_url}")
            
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(
                self.config.check_url,
                proxies=proxy_dict,
                headers=headers,
                timeout=self.config.check_timeout,
                verify=False
            )
            
            if self.config.log_level >= 2:
                self.logger.info(f"验证响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                # 这里不再记录成功日志，统一在 get_valid_ip 中记录
                return True
            else:
                self.logger.warning(f"IP验证失败，状态码: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectTimeout:
            self.logger.warning("连接超时 - 代理可能不可用")
            return False
        except requests.exceptions.ProxyError as e:
            self.logger.warning(f"代理错误: {e}")
            return False
        except requests.exceptions.ConnectionError as e:
            self.logger.warning(f"连接错误: {e}")
            return False
        except Exception as e:
            self.logger.warning(f"IP验证异常: {e}")
            return False
    
    def get_valid_ip(self, force_refresh=False):
        """获取有效的IP，必要时提取新IP"""
        with self.lock:
            now = time.time()
            
            # 检查是否需要更换IP
            need_refresh = (
                force_refresh or
                not self.current_ip or
                now - self.current_ip['extract_time'] > self.config.ip_lifetime
            )
            
            # 如果是 per_request 模式，每次都需要刷新IP
            if self.config.mode == 'per_request':
                need_refresh = True
            
            # 如果是 interval 模式，检查间隔时间
            elif self.config.mode == 'interval' and self.current_ip:
                if now - self.current_ip['extract_time'] > self.config.interval:
                    need_refresh = True
            
            if not need_refresh and self.current_ip:
                if self.config.log_level >= 2:
                    self.logger.info(f"使用现有IP: {self.current_ip['ip']}:{self.current_ip['port']}")
                self.ip_use_count += 1
                return self.current_ip
            
            if self.config.log_level >= 1:
                self.logger.info(f"需要提取新IP，模式: {self.config.mode}")
            
            # 需要提取新IP
            retries = 0
            while retries < self.config.max_retries:
                if self.config.log_level >= 2:
                    self.logger.info(f"第 {retries + 1} 次尝试提取IP...")
                
                proxy_info = self.extract_ip()
                
                if proxy_info:
                    if self.config.log_level >= 2:
                        self.logger.info("成功提取IP，开始验证...")
                    
                    if self.check_ip(proxy_info):
                        self.current_ip = proxy_info
                        self.ip_extract_time = time.time()
                        self.ip_use_count = 1
                        # 统一在这里记录验证成功和更新IP的日志
                        if self.config.log_level >= 1:
                            if self.config.check_proxies:
                                self.logger.info(f"IP验证成功，更新当前IP: {proxy_info['ip']}:{proxy_info['port']}")
                            else:
                                self.logger.info(f"跳过验证，使用IP: {proxy_info['ip']}:{proxy_info['port']}")
                        return self.current_ip
                    else:
                        if self.config.log_level >= 1:
                            self.logger.warning("IP验证失败")
                else:
                    if self.config.log_level >= 1:
                        self.logger.warning("提取IP返回None")
                
                retries += 1
                if retries < self.config.max_retries:
                    if self.config.log_level >= 2:
                        self.logger.info(f"等待2秒后重试...")
                    time.sleep(2)
            
            self.logger.error("无法获取有效IP，已达到最大重试次数")
            return None
    
    def get_status(self):
        """获取IP管理器状态"""
        if not self.current_ip:
            return {
                'current_ip': None,
                'ip_age': 0,
                'use_count': 0,
                'remaining_time': 0,
                'status': 'no_ip'
            }
        
        now = time.time()
        age = now - self.current_ip['extract_time']
        
        return {
            'current_ip': f"{self.current_ip['ip']}:{self.current_ip['port']}",
            'ip_age': int(age),
            'use_count': self.ip_use_count,
            'remaining_time': max(0, self.config.ip_lifetime - int(age)),
            'status': 'active' if age < self.config.ip_lifetime else 'expired'
        }