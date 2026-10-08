# Python CLI 工具脚手架

> 接定制单或开发成品小工具的起点。复制本目录改个名即可开工。

## 结构

```
python-cli/
├── README.md          # 本文件（改成工具说明）
├── main.py            # 入口，argparse 参数解析
├── core.py            # 核心逻辑（与 IO/参数解耦，方便测试）
├── requirements.txt   # 依赖锁定
├── tests/             # 测试
│   └── test_core.py
├── assets/            # 图标/字体等资源
└── build.sh           # PyInstaller 打包脚本
```

## 开发

1. `cp -r python-cli/ ../../products/<你的工具名>/`
2. 改 `main.py` 的参数定义和 `core.py` 的核心逻辑
3. `pip install -r requirements.txt`
4. `python main.py --help` 验证

## 打包成 exe

```bash
./build.sh <工具名>
```

## 交付时检查

- [ ] `--help` 输出清晰
- [ ] 异常输入有友好提示（不抛栈）
- [ ] Windows 上跑过
- [ ] 使用说明写好
