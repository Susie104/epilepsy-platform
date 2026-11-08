# 接入版运行说明

此版本把指定的 `opening-screen-v5.html` 接到交付包后端，默认地址为 <http://127.0.0.1:3000>。
原始开屏文件和原始交付包未修改。浏览器应打开 HTTP 地址，原来的 file:// 预览仍是静态预览。

## 当前电脑

- 双击 `start.cmd`：后台启动并打开首页；已启动时直接打开。
- 停止：在本目录运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1`。
- 换端口：`powershell -NoProfile -ExecutionPolicy Bypass -File .\start-background.ps1 -Port 3001 -OpenBrowser`。
- 若已启动，先停止再换端口。
- 日志：上级目录 `evidence/local-server.stdout.log`、`local-server.stderr.log`。
- 本地数据：本目录 `var/`；当前联调只使用合成病例。

## 在另一台 Windows 电脑安装

1. 安装 Python 3.12（64 位），解压交付包，保留目录层级。
2. 在本目录运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1`。
3. 双击 `start.cmd`。

安装会在本目录的上级创建 `.venv`，使用已验证的 `requirements.lock.txt`。原始模型由 scikit-learn 1.6.1 生成，版本已固定，避免安装最新版本造成模型兼容性问题。包中没有离线 wheel 仓库，首次安装需要访问 Python 包源。

Linux 研究联调可建立虚拟环境、安装相同 lock 文件，然后执行 `python serve_local.py`。
此启动器使用 Waitress，固定绑定 127.0.0.1，未注册为 Windows 开机服务。

## 页面路径

| 入口 | 路径 |
|---|---|
| 指定的 v5 开屏 | `/` |
| 卒中后癫痫知识图谱 v0.3 | `/knowledge-graph/` |
| 正向单例录入 | `/workspace?view=single&scenario=forward` |
| 逆向单例录入 | `/workspace?view=single&scenario=reverse` |
| 批量导入 | `/workspace?view=flow` |
| 逆向批量导入 | `/workspace?view=flow&scenario=reverse` |
| 模型与审计就绪检查 | `/readyz` |

单例页点击“填入教学示例”后提交。逆向演示可将目标风险设为 0.8 查看可行区间；更低目标可能按模型结果被拒绝。

批量流程：导入员上传或使用合成 CSV → 审核员保存映射并确认 → 运行员运行 → 切换结果查看者加载结果 → 导出授权者生成并下载文件。
点击右上角身份可切换账号、角色和科室/项目；这是演示身份桩，不构成真实登录认证。

## 工作页视觉融合（2026-11-07）

已按批准的预览统一紫色神经网络背景、玻璃面板与荧光绿操作按钮。批量接入每次只展示当前步骤，可返回已完成步骤；确认后的映射保持锁定。上传文件与内网链接使用标签切换，模板随研究用途更新，额外模板及违规合成示例收在“更多”中。

单例、历史、审计与方案工作页沿用同一配色。右上角“更多”提供页面切换、运行配置、方案文档、审计及知识图谱入口。底部只展示研究提示；版本与通道信息在运行配置中查看。更改已上传批次的用途会要求重新上传，空文件预检失败停留在上传页。

浏览器验收 43/43 通过，包括 390/768 像素的批量、映射和单例页面。融合记录见上级目录 `UI_INTEGRATION.md`。

## 验证复跑

在上级目录用 `.venv\Scripts\python.exe verify_api.py` 运行原始版、接入版普通通道和加密通道验收。
`verify_api.py` 只在隔离测试目录生成测试密钥，不把密钥放入可分发交付包。

安装 `requirements-dev.txt` 后可在本目录运行 `python -m pytest tests -q`；上级目录的 `verify_browser.py` 使用本机 Edge 执行浏览器验收，需要先启动 3000 端口服务。
知识图谱接入验收：在上级目录执行 `.venv\Scripts\python.exe verify_graph.py`。图谱包含 151 个节点、428 条关系、5 条演示路径和本地来源附件，页面右上角可返回研究入口。

## 医院正式部署前的剩余工作

当前是研究联调版本：模型为教学合成模型；SSO、HTTPS、数据库、静态数据加密、定期完整销毁、KMS、备份恢复、部署回滚和独立模型验证尚未交付。
加密通道的验收验证了请求信封与防重放，当前仍是同一进程的 HTTP 回环，响应为明文 JSON，未实现独立模型服务、响应信封或双 kid 密钥轮换。
知识问答及其他预测场景保留规划入口；知识图谱已接入卒中后癫痫 v0.3 交互版。


知识图谱已以用户指定 ZIP 为源完成紫色开屏风格改造，包含完整证据和本地附件。首页知识图谱入口保持可用；支持邻近节点分页、搜索键盘操作与离线浏览。改造与验收见交付包 GRAPH_THEME_INTEGRATION.md。
