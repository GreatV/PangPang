# PangPang 学术论文摘要自动生成工具

PangPang是一个集成式工具，旨在自动获取最新学术论文，并生成格式化的摘要报告。该工具将论文获取、排名、下载、解析和总结等步骤整合成一个自动化流程。

## 功能特点

- 🔍 从Papers With Code网站自动抓取最新论文信息
- 🏆 使用AI对论文进行排名，选出最具价值的论文
- 📥 自动下载论文PDF
- 📄 将PDF转换为结构化Markdown格式（支持Doc2X和Mistral OCR两种方式）
- 📝 使用AI生成论文的中文摘要，适合微信公众号等平台分享
- 📊 生成汇总报告，方便阅读和分享

## 系统要求

- Python 3.8+
- 必要的API密钥:
  - OpenAI API密钥（或DeepSeek API密钥）
  - Doc2X API密钥（用于PDF转Markdown，如果使用Doc2X方式）
  - Mistral API密钥（用于PDF转Markdown，如果使用Mistral OCR方式）

## 安装方法

1. 克隆仓库
```bash
git clone https://github.com/yourusername/pangpang.git
cd pangpang
```

2. 创建并激活虚拟环境
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 配置API密钥
创建一个`.env`文件，包含以下内容：
```
OPENAI_API_KEY=your_openai_api_key
DOC2X_APIKEY=your_doc2x_api_key
```

## 使用方法

运行主流水线脚本：
```bash
python paper_pipeline.py
```

这个命令将:
1. 获取最新的学术论文
2. 使用AI对论文进行排名
3. 下载排名靠前的论文PDF
4. 将PDF转换为Markdown格式
5. 使用AI生成论文摘要
6. 创建一个包含所有摘要的汇总报告

最终输出的文件包括:
- `paper_digest_YYYY-MM-DD.md`: 包含所有论文摘要的汇总报告
- `summary_ID_YYYY-MM-DD.md`: 单篇论文的摘要文件

## 模块说明

- `papers_with_code.py`: 从Papers With Code网站爬取论文信息
- `ranking.py`: 使用AI对论文进行排名
- `get_pdf.py`: 下载PDF论文
- `get_markdown.py`: 将PDF转换为Markdown格式
- `summarize_paper.py`: 使用AI对论文进行总结
- `summarize_config.yaml`: 论文总结的配置文件
- `paper_pipeline.py`: 整合所有模块的主流水线脚本

## 自定义配置

可以通过修改`summarize_config.yaml`文件来自定义论文摘要的格式和内容。

## 注意事项

- 该工具需要稳定的网络连接
- 请遵循网站的爬虫政策和API使用条款
- PDF转换服务对文件大小可能有限制
- 请确保API密钥有足够的使用额度

## 贡献指南

欢迎提交问题报告和Pull请求。对于重大更改，请先打开一个issue讨论您想要更改的内容。

## 许可证

此项目采用MIT许可证 - 详情请参阅LICENSE文件。

## 配置

在`config.yaml`文件中可以配置系统的各项参数：

```yaml
# Pipeline Configuration

# Paper fetching settings
paper_fetch:
  limit: 30  # Number of papers to fetch from the API

# Paper ranking settings
paper_ranking:
  default_limit: 3  # Default number of papers to select
  fallback_limit: 1  # Number of papers to select when no new papers are found 

# PDF to Markdown conversion settings
pdf_to_markdown:
  converter: "mistral_ocr"  # Options: "doc2x", "mistral_ocr"
```

### PDF转Markdown配置

系统支持两种PDF转Markdown的方式：

1. **Doc2X**：使用Doc2X API服务进行转换
2. **Mistral OCR**：使用Mistral AI的OCR服务进行转换（默认选项）

可以在`config.yaml`文件中的`pdf_to_markdown.converter`选项中设置使用哪种转换方式。