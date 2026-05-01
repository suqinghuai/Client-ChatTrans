# ChatTrans


# 聊天记录翻译工具

## 项目介绍

ChatTrans 是一个基于 OpenAI API 的聊天记录翻译工具，专门用于翻译 HTML 格式的聊天记录文件。

### 功能特性

- 自动识别并提取 HTML 文件中的聊天消息数据（`WEFLOW_DATA`）
- 批量翻译中文消息为英文
- 支持分批处理和失败重试机制
- 自动跳过已翻译的消息、空消息、表情包和简单回复
- 将翻译结果无缝插入回原始 HTML 文件

## 快速开始

### 面向使用者(使用exe文件)

1. 下载并解压程序包
2. 将待翻译的 HTML 文件放入程序同级目录
3. 编辑 `config.ini` 配置文件，填写 API 密钥和相关参数
4. 双击运行 `main.exe`
5. 程序会自动查找并处理第一个 HTML 文件

### 面向开发者（从源码运行）

```bash
# 克隆项目
git clone <项目地址>

# 进入项目目录
cd <项目目录>

# 激活虚拟环境
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 运行程序
python main.py
```

## 配置说明

### 获取 API 密钥

1. 访问 LongCat 官网：https://longcat.chat/
2. 注册并登录账号
3. 进入 **API Keys** 页面
4. 点击 **创建 API Key**
5. 复制生成的密钥

### 配置文件

编辑 `config.ini` 文件配置 API 参数：

```ini
[API]
key=your_api_key_here
url=https://api.longcat.chat/openai
model=LongCat-Flash-Chat

[Settings]
batch_size=20
max_retries=5
```

| 参数 | 说明 |
|------|------|
| `key` | API 密钥（从 LongCat 官网获取） |
| `url` | API 接口地址（兼容 OpenAI 格式） |
| `model` | 模型名称 |
| `batch_size` | 每批次翻译的消息数量 |
| `max_retries` | 失败重试次数 |

## 实现方法

### 技术栈

- **语言**: Python 3.12+
- **核心库**: `openai`, `configparser`, `json`, `re`
- **打包工具**: PyInstaller

### 处理流程

1. **读取 HTML 文件**: 加载程序目录下的 HTML 文件
2. **提取消息数据**: 使用正则表达式匹配 `window.WEFLOW_DATA` 数组
3. **筛选待翻译消息**: 跳过已翻译、空消息、表情包等
4. **批量翻译**: 调用 OpenAI API 进行批量翻译（按配置的 `batch_size` 分批）
5. **插入翻译结果**: 将翻译内容添加到原消息下方（灰色小字显示）
6. **保存文件**: 覆盖原始 HTML 文件
7. **失败重试**: 对翻译失败的消息进行重试（最多 `max_retries` 次）

### 关键代码说明

- `extract_messages()`: 从 HTML 中提取聊天消息数组
- `extract_text_from_html()`: 从消息内容中提取纯文本
- `batch_translate()`: 批量调用 API 翻译文本
- `apply_translation()`: 将翻译结果应用到消息中
- `process_html_file()`: 主处理函数，包含重试逻辑

## 版本日志

### v1.0.0    ----2026.5.1

- 初始版本
- 支持 HTML 聊天记录的批量翻译
- 支持分批处理和失败重试
- 支持配置文件自定义参数

## 许可证

本项目采用 Prosperity Public License 2.0.0 许可证，详见 LICENSE 文件。