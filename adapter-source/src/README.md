# Adapter 与 Connector 调用链

操作与参数以 `../adapter.json` 为准，运行与发布见上级 README。

```text
平台结构化请求 → Connector 校验版本/哈希/schema
→ handler.py --invoke → Unix socket broker
→ core.command + layout.Workspace → 固定 ROS 环境引导 → 厂商工具
```

handler 单次退出后，broker 的 PTY 和 session 继续存在。启动请求成功只证明 session 已建立。
Connector 的资源调用结果与实验 session 的终态必须分开解释。

## 模块分工

- `layout.py`：ribbon_ws 根目录到 pipeline、ROS、libfranka、Nokov、手册和默认起点的统一映射。
- `core.py`：机器合同校验、配置、不可变任务与产物句柄、命令生成、固定 shell 引导。
- `task_files.py`：固定手册读取、trajectories 清单和原 YAML 导入；厂商 Python 只运行 safe_load。
- `assets.py`：流式哈希、文件版本签名、文本与二进制分页。
- `broker.py`：持久会话、PTY、确认 nonce、启动/取消、结果检查和现有控制锁。
- `render_videos.py`：源运行私有副本中的离线渲染；不调用调平、执行或采集接口。
- `stop_guard.py`：只读停稳采样及状态读取不可用的诊断标记。
- `vendor_launch.py`：父进程退出时向直接子进程发 SIGINT；不构成物理停稳证明。

## 命令和不可变输入

Pipeline 只用 task_id 解析受管理的任务，每个新会话从任务重新生成轨迹与本次 mode
需要的仿真、预检和执行结果；不提供检查点复用入口。调用使用参数数组，不把用户输入拼成 shell。
固定引导从 workspace/ros 加载环境，以 workspace/pipeline 为 cwd。

导入的 YAML 保留原始字节，起点引用仅接受共享起点的绝对路径。
导入时保存起点快照与哈希，启动前共享文件已变则拒绝并要求重新导入。
相同 request_id 的重试仍返回原会话；新的 request_id 才产生独立运行。
视频补录的 source_session_id 仅选择保存的轨迹和 marker 输入，输出在新目录重新生成。

独立 home/微动/CSV执行直接启动原生进程，不生成额外 MOVE/QUIT 等待。
默认 home 的共享目标先复制到本次会话；启动前复核被冻结产物的哈希。
原生 pipeline 和调平提示由 PTY 转发；历史 HOME/RELEVEL/QUIT 的识别保留。
RELEVEL 退出，不在同一进程继续旧轨迹。nonce 及允许动作必须匹配当前提示。

## 回执与产物

Pipeline 解析本次 stdout 给出的精确 result.json，要求位于本次会话中。
Nokov 和 ATI 独立验证，disabled 的通道不要求文件；counts 不当作力值。
失败保存完整原生错误与回执，通过 artifact_id 查询，不扫描最近运行猜结果。
状态响应对大回执和清单分页，完整 adapter_result.json 保存在本次会话。

产物文件使用流式 SHA256；稳定的 inode/大小/mtime/ctime 签名避免每次轮询重哈希视频。
消费句柄时检查版本，发生变化拒绝。二进制通过 base64 分块，不按 UTF-8 解码。
离线视频补录只复制轨迹、marker 和输入元数据；排除旧 simulation/videos 目录及视频文件。
仿真视频重新回放，ribbon 视频重新拟合，生成失败不回退到旧录像；源 result.json 不覆盖。

## 控制锁行为

state 与 control_lock_pending 分开。失败后的自动核验读取两次机器人状态，
不检查旧进程是否退出；模式、速度及位置稳定阈值保持不变。
状态读取或解析失败时按策略释放软件控制锁，标记 state_unavailable=true，
physical_stop_verified=false，保留失败和读取错误。有效状态未通过判据或字段无效仍保留锁。
读取不可用的释放结果在状态查询、幂等重试及重启后保留；解锁不证明物理停稳或旧进程退出。

broker_control 默认强制归档阻塞会话，update.sh 仍调用 --force-stop；
两个脚本本次逐字保留。归档只处理软件状态，不构成物理停稳验证。

## 源码与安装包

源码树的 manifest 在上一级；build_adapter.py 将 src/*.py 和 manifest 放在包根。
不要直接用源码 src/handler.py 当正式入口。Connector 通过安装索引选择精确版本和哈希。
源码、包、已安装版本、运行中的 broker 和已同步能力是不同状态，修改源码不自动部署。
