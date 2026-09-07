# Joe Rules

三个按服务分组的域名规则集。**直接维护 `.list`，没有 JSON 配置、生成版 JSON 或重复服务目录。**

| 文件 | 用途 | 原始首版 |
| --- | --- | --- |
| [cn-services.list](cn-services.list) | 中国常见服务直连 | 70 个服务入口，323 条 |
| [global-direct.list](global-direct.list) | 国外服务直连例外：Apple、Microsoft、Steam 的具体功能 | 7 个功能组，47 条 |
| [explicit-proxy.list](explicit-proxy.list) | 常用服务明确代理 | 24 个服务组，163 条 |

原始数据来自 [V2Fly domain-list-community](https://github.com/v2fly/domain-list-community)，MIT 许可。每份文件头记录其上游版本；服务组中的 `@sources` 注释记录来源文件。没有复制 Blackmatrix7 的规则数据，也没有整类导入 geosite:cn 或大型集团全集。需随分发保留 [LICENSE](LICENSE) 中的上游版权和许可声明。

## 使用

原始下载地址：

- https://raw.githubusercontent.com/wangpao/joe-rules/main/cn-services.list
- https://raw.githubusercontent.com/wangpao/joe-rules/main/global-direct.list
- https://raw.githubusercontent.com/wangpao/joe-rules/main/explicit-proxy.list

建议先执行用户覆盖、本地网络和可选拦截规则，然后依次：Global Direct → Explicit Proxy → CN Services → CN CIDR → 默认代理。三个域名名单要求无交叉重叠；域名与 CIDR 的重叠按域名优先处理。

`DOMAIN` 只匹配完整主机；`DOMAIN-SUFFIX` 匹配自身及点分隔的子域。`#` 行是注释，消费者应忽略。List 不带策略字段，加载时绑定 DIRECT 或用户选定的 PROXY。Joe 如需 JSON 或二进制，应在客户端构建中自行转换。

本仓库不包含 CN CIDR 数据、代理节点、DNS 配置或在线签名机制。普通连接、直接 IP 连接和语音 UDP 是否可用仍取决于客户端实现与网络；这些规则没有经过多运营商真机验证。

## GitHub Actions 自动更新

每周一北京时间 **06:23** 检查上游；也可在 Actions → Update rules → Run workflow 手动运行。GitHub 排程可能延迟。

三个任务独立运行、独立建立更新 PR，分支分别为 `automation/update-cn-services`、`automation/update-global-direct`、`automation/update-explicit-proxy`。没有规则变化就不提交、不创建空 PR；不会自动合并到 main。PR 合并后，原始下载链接自然提供新版本。

自动化不需要个人 token，使用本仓库的临时 `GITHUB_TOKEN`。仓库 Actions 设置需要允许 GitHub Actions 创建 PR。只有更新任务有 contents/pull-requests 写权限；普通检查为只读。Action 依赖固定到完整 commit，远程上游仅作为数据读取，不执行其脚本。

由 `GITHUB_TOKEN` 创建的 PR 不一定触发另一轮 PR 工作流，因此更新任务在创建 PR 前已对三个名单运行检查与回归测试。若多个更新 PR 先后合并，合并前仍应确认当前分支检查结果；跨名单冲突会使检查失败。

公开仓库若长期无活动，GitHub 可能在 60 天后停用定时工作流，需要重新启用。失败可在 Actions 查看，是否发送通知取决于你的 GitHub 通知设置。

### 更新范围

- **默认 maintain**：保持人工选择的范围，检查每条规则在新版上游是否仍受支持；来源删除或出现相反国家属性时提出移除。不因为集团名单新增产品，就自动扩大路由范围。
- **`# @sync: delta`**：仅对少量较专一的服务启用。同步基线之后新增的合规域名，不把历史上已经排除的域名一次性加入。当前用于拼多多、知乎、喜马拉雅、Keep、虎牙、Signal、Claude、Perplexity 等窄范围来源。
- 新增上游规则可能仍有误分类；**更新 PR 就是审阅这些变化的地方**。新增更宽的父域、共享 CDN 根域、关键词、正则、相反国家属性会被跳过或阻止。
- 超过 10%（最低阈值 5 条）的删除、整个服务组变空、缺失来源、解析错误、跨名单冲突会使任务失败，不发布半成品。
- 未变化时保留原基线版本，避免只有版本号变化的维护噪声。

自动更新不能替代对“该服务应该直连还是代理”的产品判断，也不保证发现所有新域名。大型集团的新根域名需要人工添加到对应服务组。这是保持精简和不误直连的边界。

### 日常维护只改 `.list`

```text
# ===== 喜马拉雅 =====
# @sources: ximalaya
# @sync: delta
# 音频服务
DOMAIN-SUFFIX,ximalaya.com
DOMAIN-SUFFIX,xmcdn.com
```

组内按域名字母排序。共享规则只保留一次；部分组可仅备注其已由其他组覆盖。新增服务时补上 `@sources`，无需维护另一份映射配置。来源不明确的规则应先核实再加入。

`explicit-proxy.list` 中精确的 `ssl.gstatic.com` 和 `www.gstatic.com` 使用 `@allow-cn` 备注记录已审阅的上游属性覆盖：本版选择与 Google 服务一起代理；没有扩大为整个 gstatic.com。`@cn` 不是速度或可用性保证，该决定仍可修改。

## 本地检查

Python 3 标准库，无第三方 Python 依赖：

```sh
python3 scripts/rules.py check
python3 scripts/test_rules.py
```

手动检查某份名单的上游变化：

```sh
git clone https://github.com/v2fly/domain-list-community.git .upstream
python3 scripts/rules.py update --target cn-services.list --upstream .upstream
python3 scripts/rules.py check
python3 scripts/test_rules.py
```

上游本地仓库需包含文件头所指版本；保留历史能对新增规则做增量比较。更新工具只写目标 `.list`，不产生额外仓库报告文件。GitHub Actions 的变化说明保存在运行摘要和 PR 中。

## 功能依据与许可

[Apple 网络端点说明](https://support.apple.com/en-us/101555) 与 [Microsoft 更新端点说明](https://learn.microsoft.com/en-us/troubleshoot/windows-client/installing-updates-features-roles/windows-update-issues-troubleshooting) 用于核对功能边界；实际域名从 MIT 上游派生。官方文章正文未复制进仓库。

修改：按服务筛选、收窄部分域名为具体子域或精确主机、去重、分组、添加 Joe 路由策略和自动检查。上游不代表为 Joe 的策略或连接效果背书。仓库工具与本衍生规则按 MIT 提供，上游版权声明保留在 LICENSE。
