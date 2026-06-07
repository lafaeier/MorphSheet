# MorphSheet — 跨系统表格数据转换智能体

基于大模型 Agent 的桌面端数据中枢。通过自然语言指令驱动 LLM 动态生成 Pandas 清洗代码，在安全沙箱中执行，将异构企业系统导出的表格自动转换为目标格式。

## 核心特性

- **自然语言驱动**：用中文描述清洗需求（"删除金额<0的行"、"地址拆分为省市区"），Agent 自动生成并执行转换代码
- **安全沙箱执行**：AST 代码扫描 + 受限命名空间 + 超时控制，确保 LLM 生成代码安全可控
- **格式降级兼容**：支持 xlsx → xls (Excel 97-2003) / CSV (GBK/UTF-8) 的精确转换，处理行数截断、编码 BOM 等兼容性问题
- **Diff 对比视图**：转换前后左右分屏对比，修改单元格黄色、新增列绿色、删除行红色高亮
- **经验记忆**：成功转换可保存为技能模板，后续同类文件一键应用，0 Token 消耗
- **人机协同**：遇到脏数据暂停询问，高亮异常行并提供修复建议，而非直接报错中断

## 技术栈

| 层 | 技术 |
|----|------|
| 桌面壳 | PyWebView |
| 后端 | Python 3.10+ / FastAPI / WebSocket |
| 前端 | Vue 3 (CDN) + HTML/CSS |
| 数据处理 | Pandas / openpyxl / xlrd / xlwt / chardet |
| LLM | DeepSeek API (OpenAI 兼容协议) |
| 沙箱 | AST 扫描 + 受限 exec |
| 存储 | SQLite + ChromaDB |

## 快速开始

### 环境要求

- Python 3.10+
- Windows 10/11

### 安装运行

```bash
# 1. 克隆项目
git clone git@github.com:lafaeier/MorphSheet.git
cd MorphSheet

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key

# 5. 启动
python run.py
```

## 项目结构

```
MorphSheet/
├── run.py                  # 入口：启动 FastAPI + PyWebView
├── app/
│   ├── main.py             # FastAPI 应用
│   ├── config.py           # 配置管理
│   ├── agent/              # Agent 核心（Prompt/LLM/沙箱/编排）
│   ├── processing/         # 文件处理引擎（读写/Schema/Diff）
│   ├── storage/            # 持久化（SQLite/ChromaDB）
│   └── api/                # API 层（REST/WebSocket）
├── static/                 # 前端三栏界面
├── docs/                   # 设计文档与开发指导
├── data/                   # 运行时数据目录
└── tests/                  # 测试
```

## 开发阶段

| Phase | 内容 | 状态 |
|-------|------|------|
| 0 | 项目骨架搭建 | ✅ |
| 1 | 文件处理引擎 | 🔜 |
| 2 | Agent 核心 + 沙箱 | ⬜ |
| 3 | 前端界面 | ⬜ |
| 4 | 记忆系统 | ⬜ |
| 5 | 集成测试 + 验收 | ⬜ |
| 6 | 打包与交付 | ⬜ |

详见 `docs/00-开发总览与路线图.md`
