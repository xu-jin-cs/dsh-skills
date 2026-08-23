# Security Policy

## 报告安全漏洞

请**不要**通过公开 Issue 报告安全漏洞。

推荐通道：本仓库已开启 **Private vulnerability reporting**——仓库主页 → Security 标签 → Advisories → "Report a vulnerability"，私密提交，仅维护者可见。

或线下联系作者（xu-jin-cs）。

## 范围说明

本仓库为 Source-Available 可见源项目（非 OSI 开源协议，见根目录 LICENSE）。插件设计边界如实声明：

- 插件运行时零网络、零第三方依赖，资产为明文 JSON（明文即本意，非漏洞）；
- `xujin-engine sign` 的防伪强度依赖环境变量 `AGENT_ENGINE_SECRET` 的保密性，请勿将该密钥提交到任何仓库；
- 历史版本（≤v1.3.x）的加密资产仅为基础防裸奔设计，不构成安全承诺。

## 支持版本

仅最新发布版本（当前 v1.4.0）接受安全修复。
