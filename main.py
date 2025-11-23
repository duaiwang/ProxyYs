import logging
import signal
import sys
import time
import os
from config import Config
from ip_manager import IPManager
from socks5_server import Socks5Server
from web_interface import WebInterface

class ProxyServer:
    def __init__(self):
        # 删除旧的日志文件
        self.cleanup_logs()
        
        # 加载配置
        self.config = Config()
        
        # 配置日志
        self.setup_logging()
        
        # 初始化组件
        self.ip_manager = IPManager(self.config)
        self.socks5_server = Socks5Server(self.config, self.ip_manager)
        self.web_interface = WebInterface(self.config, self.ip_manager, self.socks5_server)
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def cleanup_logs(self):
        """清理旧的日志文件"""
        log_files = ['proxy_server.log']
        for log_file in log_files:
            if os.path.exists(log_file):
                try:
                    os.remove(log_file)
                    print(f"已删除旧日志文件: {log_file}")
                except Exception as e:
                    print(f"删除日志文件失败: {e}")
    
    def setup_logging(self):
        """配置日志"""
        log_level_map = {
            0: logging.CRITICAL,  # 无日志
            1: logging.INFO,      # 仅显示代理切换和错误信息
            2: logging.DEBUG      # 显示所有详细信息
        }
        
        log_level = log_level_map.get(self.config.log_level, logging.INFO)
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('proxy_server.log', encoding='utf-8')
            ]
        )
    
    def signal_handler(self, signum, frame):
        logging.info("接收到停止信号，正在关闭服务器...")
        self.socks5_server.stop()
        sys.exit(0)
    
    def start(self):
        """启动服务器"""
        logging.info("启动SOCKS5代理服务器...")
        
        # 启动Web管理界面
        self.web_interface.start()
        
        # 启动SOCKS5服务器
        try:
            self.socks5_server.start()
        except KeyboardInterrupt:
            self.socks5_server.stop()
        except Exception as e:
            logging.error(f"服务器运行异常: {e}")
            self.socks5_server.stop()

if __name__ == '__main__':
    server = ProxyServer()
    server.start()