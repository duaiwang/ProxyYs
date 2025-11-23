import configparser
import os

class Config:
    def __init__(self, config_file='config.ini'):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        if not os.path.exists(self.config_file):
            self.create_default_config()
        
        self.config.read(self.config_file, encoding='utf-8')
        
        # 基本设置
        self.port = self.config.getint('Settings', 'port', fallback=1080)
        self.web_port = self.config.getint('Settings', 'web_port', fallback=5000)
        self.mode = self.config.get('Settings', 'mode', fallback='per_request')
        self.interval = self.config.getint('Settings', 'interval', fallback=0)
        self.ip_lifetime = self.config.getint('Settings', 'ip_lifetime', fallback=180)
        self.max_retries = self.config.getint('Settings', 'max_retries', fallback=3)
        
        # API设置
        self.api_url = self.config.get('Settings', 'api_url', fallback='')
        self.api_key = self.config.get('Settings', 'api_key', fallback='')
        self.api_format = self.config.get('Settings', 'api_format', fallback='json')
        
        # 验证设置
        self.check_proxies = self.config.getboolean('Settings', 'check_proxies', fallback=True)
        self.check_url = self.config.get('Settings', 'check_url', fallback='https://www.bing.com')
        self.check_timeout = self.config.getint('Settings', 'check_timeout', fallback=10)
        
        # 日志设置
        self.log_level = self.config.getint('Settings', 'log_level', fallback=1)
        
        # 认证设置
        self.token = self.config.get('Settings', 'token', fallback='')
        
        # 用户设置
        self.users = {}
        if self.config.has_section('Users'):
            for key, value in self.config.items('Users'):
                self.users[key] = value
    
    def create_default_config(self):
        self.config['Settings'] = {
            'port': '1880',
            'web_port': '1881',
            'mode': 'per_request',
            'interval': '0',
            'ip_lifetime': '180',
            'max_retries': '3',
            'api_url': 'https://api.cliproxy.io/white/api?region=US&num=1&time=10&format=n&type=txt',
            'api_key': '',
            'api_format': 'text',
            'check_proxies': 'True',
            'check_url': 'https://www.bing.com',
            'check_timeout': '10',
            'log_level': '1',
            'token': 'ysld'
        }
        
        self.config['Users'] = {}
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)
    
    def save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)