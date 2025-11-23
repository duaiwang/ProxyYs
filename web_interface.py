from flask import Flask, jsonify, request
import threading
import logging

class WebInterface:
    def __init__(self, config, ip_manager, socks5_server):
        self.config = config
        self.ip_manager = ip_manager
        self.socks5_server = socks5_server
        self.app = Flask(__name__)
        self.logger = logging.getLogger('WebInterface')
        self.setup_routes()
    
    def setup_routes(self):
        @self.app.route('/')
        def index():
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>SOCKS5代理管理</title>
                <meta charset="utf-8">
                <style>
                    body { font-family: Arial; margin: 40px; }
                    .box { background: #f0f0f0; padding: 20px; margin: 10px 0; border-radius: 5px; }
                    button { background: #007cba; color: white; padding: 10px 15px; border: none; border-radius: 3px; cursor: pointer; margin: 5px; }
                    input { padding: 8px; margin: 5px; width: 250px; }
                    .message { padding: 10px; margin: 10px 0; border-radius: 3px; }
                    .success { background: #d4edda; color: #155724; }
                    .error { background: #f8d7da; color: #721c24; }
                </style>
            </head>
            <body>
                <h1>SOCKS5代理服务器管理</h1>
                
                <div class="box">
                    <h3>🔐 身份验证</h3>
                    <input type="password" id="tokenInput" placeholder="输入管理Token">
                    <button onclick="saveToken()">保存Token</button>
                </div>
                
                <div class="box">
                    <h3>📊 服务器状态</h3>
                    <div id="status">请先保存Token</div>
                </div>
                
                <button onclick="refreshIP()" id="refreshBtn">🔄 强制刷新IP</button>
                <button onclick="refreshStatus()">🔄 刷新状态</button>
                
                <div id="message"></div>
                
                <script>
                    let token = '';
                    
                    function saveToken() {
                        const input = document.getElementById('tokenInput').value;
                        if (!input) {
                            showMessage('请输入Token', 'error');
                            return;
                        }
                        token = input;
                        localStorage.setItem('proxyToken', token);
                        showMessage('Token已保存', 'success');
                        refreshStatus();
                    }
                    
                    function showMessage(msg, type) {
                        const div = document.getElementById('message');
                        div.innerHTML = '<div class="message ' + type + '">' + msg + '</div>';
                        setTimeout(() => div.innerHTML = '', 3000);
                    }
                    
                    function refreshStatus() {
                        if (!token) {
                            showMessage('请先保存Token', 'error');
                            return;
                        }
                        
                        fetch('/status?token=' + encodeURIComponent(token))
                            .then(r => r.json())
                            .then(data => {
                                if (data.error) {
                                    showMessage('错误: ' + data.error, 'error');
                                    return;
                                }
                                document.getElementById('status').innerHTML = 
                                    '运行: ' + (data.running ? '✅' : '❌') + '<br>' +
                                    'IP: ' + (data.current_ip || '无') + '<br>' +
                                    '年龄: ' + (data.ip_age || 0) + '秒<br>' +
                                    '使用: ' + (data.use_count || 0) + '次<br>' +
                                    '剩余: ' + (data.remaining_time || 0) + '秒';
                            })
                            .catch(err => showMessage('获取状态失败: ' + err, 'error'));
                    }
                    
                    function refreshIP() {
                        if (!token) {
                            showMessage('请先保存Token', 'error');
                            return;
                        }
                        
                        const btn = document.getElementById('refreshBtn');
                        btn.disabled = true;
                        btn.textContent = '刷新中...';
                        
                        fetch('/refresh_ip?token=' + encodeURIComponent(token), {method: 'POST'})
                            .then(r => r.json())
                            .then(data => {
                                if (data.success) {
                                    showMessage('IP刷新成功', 'success');
                                    refreshStatus();
                                } else {
                                    showMessage('刷新失败: ' + data.message, 'error');
                                }
                            })
                            .catch(err => showMessage('刷新失败: ' + err, 'error'))
                            .finally(() => {
                                btn.disabled = false;
                                btn.textContent = '🔄 强制刷新IP';
                            });
                    }
                    
                    // 初始化
                    window.onload = function() {
                        const saved = localStorage.getItem('proxyToken');
                        if (saved) {
                            token = saved;
                            document.getElementById('tokenInput').value = saved;
                            refreshStatus();
                        }
                        setInterval(refreshStatus, 5000);
                    }
                </script>
            </body>
            </html>
            '''
        
        @self.app.route('/status')
        def status():
            token = request.args.get('token')
            if self.config.token and token != self.config.token:
                return jsonify({'error': '未授权'}), 401
            
            ip_status = self.ip_manager.get_status()
            return jsonify({
                'running': self.socks5_server.running,
                'current_ip': ip_status.get('current_ip'),
                'ip_age': ip_status.get('ip_age', 0),
                'use_count': ip_status.get('use_count', 0),
                'remaining_time': ip_status.get('remaining_time', 0)
            })
        
        @self.app.route('/refresh_ip', methods=['POST'])
        def refresh_ip():
            token = request.args.get('token')
            if self.config.token and token != self.config.token:
                return jsonify({'error': '未授权'}), 401
            
            self.logger.info("收到强制刷新IP请求")
            
            try:
                result = self.ip_manager.get_valid_ip(force_refresh=True)
                if result:
                    return jsonify({
                        'success': True,
                        'message': f'IP刷新成功: {result["ip"]}:{result["port"]}'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'IP刷新失败：无法获取有效代理IP，请检查API配置和网络连接'
                    })
            except Exception as e:
                self.logger.error(f"刷新IP时发生异常: {e}")
                return jsonify({
                    'success': False,
                    'message': f'IP刷新失败：{str(e)}'
                })
    
    def start(self):
        """启动Web界面"""
        threading.Thread(
            target=lambda: self.app.run(
                host='0.0.0.0', 
                port=self.config.web_port, 
                debug=False,
                use_reloader=False
            ),
            daemon=True
        ).start()
        
        if self.config.log_level >= 1:
            self.logger.info(f"Web管理界面启动在端口 {self.config.web_port}")