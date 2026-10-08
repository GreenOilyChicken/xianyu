# 部署文档模板

> 交付给客户时，把 {{变量}} 替换成实际值。

## 一、环境要求

- 服务器：{{server_requirement}}（如 2核4G / CentOS 7+）
- 已装：Docker / Docker Compose
- 域名：{{domain}}（可选，无则用 IP）

## 二、部署步骤

### 1. 上传代码
```bash
scp -r ./ {{server_user}}@{{server_ip}}:~/{{app_name}}
ssh {{server_user}}@{{server_ip}}
cd ~/{{app_name}}
```

### 2. 启动服务
```bash
docker-compose up -d --build
```

### 3. 验证
```bash
curl http://{{server_ip}}:8080      # 前端
curl http://{{server_ip}}:8000/api/hello  # 后端
```

### 4. 配置 Nginx 反代（可选）
```nginx
server {
    listen 80;
    server_name {{domain}};
    location / {
        proxy_pass http://127.0.0.1:8080;
    }
    location /api {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

## 三、数据备份

```bash
# 每日备份
docker-compose exec backend {{backup_cmd}}
```

## 四、常见问题

| 问题 | 解决 |
|---|---|
| 端口被占 | 改 docker-compose.yml 的端口映射 |
| 前端白屏 | 检查后端是否起来，看浏览器控制台 |
| 接口 404 | 确认 Nginx 反代规则是否把 /api 转给后端 |

## 五、联系支持

部署有问题联系：{{contact}}
交付后 7 天免费答疑。
