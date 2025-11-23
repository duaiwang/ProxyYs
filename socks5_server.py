import socket
import select
import struct
import logging
from threading import Thread
import time

class Socks5Server:
    def __init__(self, config, ip_manager):
        self.config = config
        self.ip_manager = ip_manager
        self.logger = logging.getLogger('Socks5Server')
        self.running = False
        self.server_socket = None
        
    def start(self):
        """启动SOCKS5服务器"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind(('0.0.0.0', self.config.port))
            self.server_socket.listen(100)
            self.running = True
            
            if self.config.log_level >= 1:
                self.logger.info(f"SOCKS5代理服务器启动在端口 {self.config.port}")
                if self.config.users:
                    self.logger.info(f"启用用户认证，共 {len(self.config.users)} 个用户")
                else:
                    self.logger.info("未启用用户认证")
            
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    
                    if self.config.log_level >= 2:
                        self.logger.info(f"新的连接来自: {client_address[0]}:{client_address[1]}")
                    
                    # 为每个客户端创建新线程
                    client_thread = Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except Exception as e:
                    if self.running:
                        self.logger.error(f"接受连接时出错: {e}")
                    
        except Exception as e:
            self.logger.error(f"启动服务器失败: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """停止服务器"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        
        if self.config.log_level >= 1:
            self.logger.info("SOCKS5代理服务器已停止")
    
    def handle_client(self, client_socket, client_address):
        """处理客户端连接"""
        try:
            # SOCKS5握手
            if not self.socks5_handshake(client_socket, client_address):
                return
            
            # 获取客户端请求
            target_host, target_port = self.get_client_request(client_socket)
            if not target_host:
                return
            
            if self.config.log_level >= 1:
                self.logger.info(f"客户端 {client_address[0]} 请求连接: {target_host}:{target_port}")
            
            # 获取有效的代理IP - 在 per_request 模式下强制刷新
            force_refresh = (self.config.mode == 'per_request')
            
            if self.config.log_level >= 2:
                self.logger.info(f"获取有效代理IP, 强制刷新: {force_refresh}")
            
            proxy_info = self.ip_manager.get_valid_ip(force_refresh=force_refresh)
            if not proxy_info:
                client_socket.close()
                self.logger.error("无法获取有效代理IP，连接终止")
                return
            
            # 通过上游代理连接目标
            remote_socket = self.connect_via_proxy(proxy_info, target_host, target_port)
            if not remote_socket:
                client_socket.close()
                return
            
            # 发送成功响应
            self.send_success_response(client_socket, target_host, target_port)
            
            # 开始数据转发
            self.forward_data(client_socket, remote_socket)
            
        except Exception as e:
            self.logger.error(f"处理客户端时出错: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def socks5_handshake(self, client_socket, client_address):
        """SOCKS5握手，包含用户认证"""
        try:
            # 读取客户端认证方法
            data = client_socket.recv(1024)
            
            if self.config.log_level >= 2:
                self.logger.debug(f"收到握手数据: {data.hex()}")
            
            if len(data) < 3:
                return False
            
            version, nmethods = struct.unpack('!BB', data[:2])
            if version != 5:
                return False
            
            # 检查是否需要用户认证
            methods = data[2:2 + nmethods]
            
            # 如果有配置用户，要求用户名密码认证
            if self.config.users:
                if 2 in methods:  # 用户名密码认证
                    # 告诉客户端使用用户名密码认证
                    client_socket.send(struct.pack('!BB', 5, 2))
                    
                    # 读取认证信息
                    auth_data = client_socket.recv(512)
                    if len(auth_data) < 3:
                        return False
                    
                    auth_version, username_len = struct.unpack('!BB', auth_data[:2])
                    if auth_version != 1:
                        return False
                    
                    username = auth_data[2:2+username_len].decode('utf-8')
                    password_len = auth_data[2+username_len]
                    password = auth_data[3+username_len:3+username_len+password_len].decode('utf-8')
                    
                    # 验证用户名和密码
                    if username in self.config.users and self.config.users[username] == password:
                        # 认证成功
                        client_socket.send(struct.pack('!BB', 1, 0))
                        if self.config.log_level >= 1:
                            self.logger.info(f"用户 {username} 认证成功，来自 {client_address[0]}")
                        return True
                    else:
                        # 认证失败
                        client_socket.send(struct.pack('!BB', 1, 1))
                        if self.config.log_level >= 1:
                            self.logger.warning(f"用户认证失败，用户名: {username}，来自 {client_address[0]}")
                        return False
                else:
                    # 客户端不支持用户名密码认证
                    client_socket.send(struct.pack('!BB', 5, 0xFF))
                    return False
            else:
                # 没有配置用户，使用无认证
                if 0 in methods:  # NO AUTHENTICATION REQUIRED
                    client_socket.send(struct.pack('!BB', 5, 0))
                    
                    if self.config.log_level >= 2:
                        self.logger.debug("发送无认证响应")
                    
                    return True
                else:
                    # 不支持其他认证方法
                    client_socket.send(struct.pack('!BB', 5, 0xFF))
                    return False
                
        except Exception as e:
            self.logger.error(f"握手失败: {e}")
            return False
    
    def get_client_request(self, client_socket):
        """获取客户端请求的目标地址"""
        try:
            data = client_socket.recv(1024)
            
            if self.config.log_level >= 2:
                self.logger.debug(f"收到请求数据: {data.hex()}")
            
            if len(data) < 7:
                return None, None
            
            version, cmd, rsv, atyp = struct.unpack('!BBBB', data[:4])
            if version != 5 or cmd != 1:  # 只支持CONNECT命令
                return None, None
            
            if atyp == 1:  # IPv4
                target_host = socket.inet_ntoa(data[4:8])
                target_port = struct.unpack('!H', data[8:10])[0]
            elif atyp == 3:  # 域名
                host_length = data[4]
                target_host = data[5:5 + host_length].decode('utf-8')
                target_port = struct.unpack('!H', data[5 + host_length:7 + host_length])[0]
            elif atyp == 4:  # IPv6
                # 简化处理，不支持IPv6
                return None, None
            else:
                return None, None
            
            return target_host, target_port
            
        except Exception as e:
            self.logger.error(f"解析客户端请求失败: {e}")
            return None, None
    
    def connect_via_proxy(self, proxy_info, target_host, target_port):
        """通过上游代理连接目标"""
        try:
            if self.config.log_level >= 2:
                self.logger.info(f"连接到上游代理 {proxy_info['ip']}:{proxy_info['port']}")
            
            # 创建到上游代理的socket
            proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_socket.settimeout(15)
            proxy_socket.connect((proxy_info['ip'], proxy_info['port']))
            
            if self.config.log_level >= 2:
                self.logger.info("成功连接到上游代理")
            
            # 尝试SOCKS5协议
            try:
                # SOCKS5握手
                handshake = struct.pack('!BBB', 5, 1, 0)
                proxy_socket.send(handshake)
                response = proxy_socket.recv(10)
                
                if self.config.log_level >= 2:
                    self.logger.debug(f"SOCKS5握手响应: {response.hex()}")
                
                if len(response) >= 2:
                    ver, method = struct.unpack('!BB', response[:2])
                    if ver == 5:
                        # 发送连接请求
                        request = struct.pack('!BBBB', 5, 1, 0, 3)
                        request += struct.pack('!B', len(target_host)) + target_host.encode('utf-8')
                        request += struct.pack('!H', target_port)
                        proxy_socket.send(request)
                        
                        response = proxy_socket.recv(1024)
                        if self.config.log_level >= 2:
                            self.logger.debug(f"SOCKS5连接响应: {response.hex()}")
                        
                        if len(response) >= 2:
                            ver, status = struct.unpack('!BB', response[:2])
                            if status == 0:
                                if self.config.log_level >= 1:
                                    self.logger.info("SOCKS5代理连接成功")
                                return proxy_socket
                            elif status == 84:
                                # 特殊处理84错误码 - 尝试忽略错误继续使用连接
                                self.logger.warning(f"上游代理返回84错误码，尝试继续使用连接")
                                return proxy_socket
                            else:
                                self.logger.error(f"SOCKS5代理连接失败，状态码: {status}")
            except Exception as e:
                self.logger.warning(f"SOCKS5协议失败: {e}")
            
            # 如果SOCKS5失败，尝试HTTP代理协议
            try:
                # 重新连接
                proxy_socket.close()
                proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                proxy_socket.settimeout(15)
                proxy_socket.connect((proxy_info['ip'], proxy_info['port']))
                
                # 发送HTTP CONNECT请求
                connect_request = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n\r\n"
                proxy_socket.send(connect_request.encode())
                
                response = proxy_socket.recv(1024)
                if self.config.log_level >= 2:
                    self.logger.debug(f"HTTP代理响应: {response}")
                
                if b"200 Connection established" in response:
                    if self.config.log_level >= 1:
                        self.logger.info("HTTP代理连接成功")
                    return proxy_socket
                else:
                    self.logger.warning("HTTP代理连接失败")
            except Exception as e:
                self.logger.warning(f"HTTP代理协议失败: {e}")
            
            # 如果都失败，尝试直接连接（绕过代理）
            try:
                proxy_socket.close()
                remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote_socket.settimeout(15)
                remote_socket.connect((target_host, target_port))
                if self.config.log_level >= 1:
                    self.logger.info("直接连接成功（绕过代理）")
                return remote_socket
            except Exception as e:
                self.logger.error(f"直接连接也失败: {e}")
            
            return None
            
        except socket.timeout:
            self.logger.error("连接上游代理超时")
            return None
        except Exception as e:
            self.logger.error(f"通过代理连接目标失败: {e}")
            return None
    
    def send_success_response(self, client_socket, target_host, target_port):
        """发送成功响应给客户端"""
        try:
            response = struct.pack('!BBBB', 5, 0, 0, 1)  # SOCKS5, 成功, IPv4
            response += socket.inet_aton('0.0.0.0')  # 绑定地址
            response += struct.pack('!H', 0)  # 绑定端口
            client_socket.send(response)
            
            if self.config.log_level >= 2:
                self.logger.debug("成功响应已发送")
        except Exception as e:
            self.logger.error(f"发送响应失败: {e}")
    
    def forward_data(self, client_socket, remote_socket):
        """转发客户端和远程服务器之间的数据"""
        sockets = [client_socket, remote_socket]
        
        try:
            if self.config.log_level >= 2:
                self.logger.info("开始数据转发")
            
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 60)
                
                if exceptional:
                    if self.config.log_level >= 2:
                        self.logger.info("连接出现异常，关闭连接")
                    break
                
                for sock in readable:
                    try:
                        data = sock.recv(8192)
                        if not data:
                            if self.config.log_level >= 2:
                                self.logger.info("连接被对方关闭")
                            break
                        
                        if sock is client_socket:
                            if self.config.log_level >= 2:
                                self.logger.debug(f"从客户端收到 {len(data)} 字节数据")
                            remote_socket.send(data)
                        else:
                            if self.config.log_level >= 2:
                                self.logger.debug(f"从远程收到 {len(data)} 字节数据")
                            client_socket.send(data)
                    except Exception as e:
                        if self.config.log_level >= 2:
                            self.logger.error(f"数据转发出错: {e}")
                        break
                
        except Exception as e:
            if self.config.log_level >= 2:
                self.logger.error(f"数据转发异常: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            try:
                remote_socket.close()
            except:
                pass
            
            if self.config.log_level >= 2:
                self.logger.info("数据转发结束，连接已关闭")