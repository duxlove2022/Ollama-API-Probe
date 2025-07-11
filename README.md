# Ollama-API-Probe: Global AI Service Scanner
# # Note: It is only suitable for Microsoft Windows 10 operating system.
## 注意:仅适配微软视窗10操作系统

## 项目概述 / Project Overview
Ollama-API-Probe 是一个用于检测全球公开 Ollama 服务的自动化扫描系统。该项目还包含 Gemini API 密钥探测功能。

Ollama-API-Probe is an automated scanning system designed to detect publicly accessible Ollama services worldwide. The project also includes functionality for probing Gemini API keys.

## 功能特性 / Features

### Ollama 服务探测 / Ollama Service Detection
- 全球 IPv4 地址空间扫描 (1.0.0.1 至 223.255.255.254)
- 多线程高效探测 (默认750线程)
- 实时进度显示和统计
- 发现的服务自动保存到 `ollama.txt`

### Gemini API 密钥探测 / Gemini API Key Detection
- 随机生成并验证 Gemini API 密钥
- 代理服务器验证机制
- 多线程高效探测 (默认30线程)
- 有效的密钥自动保存到 `keys.txt`

### 用户界面 / User Interface
- 基于 curses 的终端仪表盘
- 实时日志显示
- 交互式控制 (启动/停止/切换视图)

## 安装依赖 / Installation

```bash
pip install requests ipaddress
pip install windows-curses
```
