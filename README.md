# 生产返工与设备维修

本仓库当前用于原项目参考资料导入准备，尚未开始业务软件开发。本次公开初始化只包含通用导入工具和说明，不包含客户原代码、产品需求内容或真实数据。

## 私有资料包中的交付

下列文件在单独交付的资料包 `docs/` 中；当前公开仓库不上传这些产品资料，`docs/` 默认被Git忽略。

- `docs/任务目标.md`：可固定的目标、边界、执行路径及完成标准。
- `docs/产品需求规格.md`：已确认规则与默认建议、页面、后台配置、状态及对接要求。
- `docs/字段字典.csv`：逻辑字段设计，不代表数据库已建表。
- `docs/验收场景.csv`：文档走查场景，不代表软件测试已通过。
- `docs/仓库导入方案.md`：将D盘原项目制作成本地分析副本的方法。
- `tools/Import-Reference.ps1`：Windows入口，调用同目录Python导入器。

## 原项目导入

电脑需安装Git及Python 3.9或更高版本。克隆仓库后在PowerShell执行，替换实际原项目目录：

```powershell
.\tools\Import-Reference.ps1 -SourcePath 'D:\IDE\原项目目录' -ImportName 'legacy'
```

如果当前进程禁止运行脚本，可先阅读两个工具源文件，再用本进程有效的执行策略运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Import-Reference.ps1 -SourcePath 'D:\IDE\原项目目录' -ImportName 'legacy'
```

导入器只创建本地 `reference/` 快照，不修改源项目，不运行源代码，不提交或推送。`reference/` 默认被Git忽略。

复制后检查 `import-manifest.json` 的复制和跳过清单。过滤仅用于分析准备，不是完整可部署副本，也不能保证不含秘密；分享前必须复核内容。二进制、数据库、环境秘密配置和依赖产物默认不复制。

目标仓库核查时为公开仓库。发布客户代码前需核对保密范围并使用合适的私有目标；当前资料包不包含原项目代码或真实数据。
