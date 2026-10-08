# Vue + 后端 Web 应用脚手架

> 接 Web 应用定制单的起点。前端 Vue3，后端二选一（FastAPI 或 Spring Boot）。

## 结构

```
vue-webapp/
├── README.md              # 本文件
├── frontend/              # Vue3 + Vite 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       └── api.ts          # 统一封装后端接口调用
├── backend-python/        # FastAPI 后端（推荐小工具）
│   ├── main.py
│   └── requirements.txt
├── backend-java/         # Spring Boot 后端（企业向，按需删一个）
│   ├── pom.xml
│   └── src/main/java/...
├── docker-compose.yml     # 一键部署
└── DEPLOY.md              # 部署文档模板
```

## 用法

1. `cp -r vue-webapp/ ../../products/<你的应用名>/`
2. 前后端二选一：删掉不用的 `backend-python/` 或 `backend-java/`
3. 前端：`cd frontend && npm i && npm run dev`
4. 后端 Python：`cd backend-python && pip install -r requirements.txt && uvicorn main:app --reload`
5. 开发完，`docker-compose up -d` 一键部署

## 交付检查

- [ ] 前端 build 通过，产物在 `frontend/dist/`
- [ ] 后端能独立启动
- [ ] docker-compose up 能起来
- [ ] 写好 DEPLOY.md 部署步骤
- [ ] 数据初始化脚本就绪
