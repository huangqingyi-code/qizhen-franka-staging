# Franka Ribbon Adapter 2.4.3

本目录为 AMD64 真实后端源码。操作及参数的唯一契约是 `adapter.json`。
Agent 操作入口见 `docs/AGENT_OPERATIONS.md`；完整实验背景和原生接口参考保留在 `docs/RIBBON.md`。
新版源码和安装包不会自动替换已安装版本、启动 broker、调用设备或同步平台能力。

## 2.4.3 手册完整读取

手册默认使用合同允许的最大页长，优先一次取全；超出行数或字节预算时仍有界续读。
同一版本及 SHA-256 的已读正文直接复用，平台详情读取不重复执行设备调用。

## 2.4.2 状态读取不可用时释放软件锁

合入先前 2.3.17 候选的解锁策略，并保留 2.4.x 会话事件和安全整数修复。
状态读取或解析失败、超时时释放软件控制锁，保留原错误与读取诊断，
physical_stop_verified=false、stop_verification.state_unavailable=true。
有效状态继续按原模式、速度和位置稳定阈值判断；不满足或字段无效仍保留锁。
后台核验可生成失败且已释放软件锁的持久事件，重启及同请求重试不重新核验或重放任务。
软件解锁不证明物理停稳；本次源码及候选包不自动安装、重启或调用机器人。

## 2.4.1 会话事件安全整数修复

修复能力快照 JCS 哈希失败：session_revision 的 Schema 上限使用 JSON 安全整数，
私有事件游标从同一机器合同读取边界。新增完整 manifest 的 JCS 序列化、游标边界和
真实 Connector 能力同步哈希回归。使用新版本包，不覆盖既有 2.4.0 发布或已安装文件。

## 2.4.0 会话事件

异步操作声明通用会话事件协议。Broker 在原子状态文件中保存不可变事件；Connector
通过私有本地长等待入口增量读取并上报平台。日志变化不创建新的执行状态事件。
失败/未知会话的后台停稳核验独立于 Agent 状态查询；原确认、设备锁及禁止重放规则继续生效。
候选源码/包不会自动安装，不重启服务或执行设备动作。

## 2.3.16 自主设计与实验完成规则

Agent 手册明确：本次实验和运动已授权时，默认直接 execute，由 Agent 自主设计、校验、
读取阶段结果并在既定目标与保护条件内修正；独立 prepare 留给明确的验证任务。
常规缺省参数不逐项反问，仍保留当前提示确认、有效标定和执行结果未知时的停稳核验。
已有 YAML 可在任务结构问题仍无法解决时自主查阅，只作参考，不自动替代本次任务。
本版仅改指令、描述和版本元数据，工具参数及执行逻辑不变；候选包不自动安装或生效。

## 2.3.15 Agent 失败处理说明

Agent 操作手册补充按失败阶段和原因处理的规则：任务内容、环境与服务、执行结果未知、
视频与文件交付分别处理。明确同 request_id 不重新执行，新 Pipeline 请求不是阶段续跑；
环境故障不默认生成新 YAML，无法诊断或缺少处理能力时报告用户。
本版只更新手册和版本元数据，不改变工具参数或执行逻辑；候选包不自动安装或生效。

## 2.3.14 手册版本信息精简

Agent 手册仅在开头保留日期与合同基线；调用仍以运行时 Schema 和回执为准。
保留版本行格式，兼容既有 manual.read 解析；不改变工具参数或执行逻辑。

## 2.3.13 Agent 操作手册入口

`franka.manual.read` 固定读取当前安装包的 `docs/AGENT_OPERATIONS.md`，返回真实文件名、
版本、SHA-256 和分页正文。源码运行读取本源码目录中的同名文件，不使用厂商工作区手册，
也不回退到旧 `RIBBON.md`。工具参数和分页限制不变。
打包和复用检查同时包含 Agent 手册及其链接的 `RIBBON.md` 参考资料，包指纹覆盖两份文档。
2.3.12 的新建任务与已有 YAML 调用时机说明继续保留。
生成候选包后仍须安装、启用并同步能力，平台运行才会使用新手册。

## 2.3.11 安装几何、动捕资产与手册同步

显式起点合同要求 `flange_58mm_v3`，宽面对齐保持法兰外 58 mm 的连接点。
旧标定、旧 CSV/guard 必须重新调平/标定和规划，不能给旧起点补新标签；执行器当前只接受
`FRANKA_RIBBON_GUARD_FLANGE_58MM_V3`。本次不改写共享起点、世界系标定或历史数据。

Nokov monitor/record 选择 `ribbon_1021`；shape.extract 只取该带身资产的有效单帧点列，
不混入旧 `ribbon` 或端板 `x0` / `x1`。手册记录带身 12 点，实际可见点数以本次回执为准。
端点 `x1/Marker2`、`x0/Marker3`、28 mm 端板法向偏移由原生后处理默认值负责，
Adapter 不把端板点当成带身点，不为历史数据自动补名或套用新几何。

随包手册同步到 2026-10-23，保留 Adapter 的独立会话约定；manual.read 仍只读包内手册。
现场 SSH 网关的 `approved` 放行与 extension 队列工具属于另一入口，本 Adapter 不新增远程
approve 或检查点复用操作。源码和候选包不会自动安装、重启 broker 或同步平台能力。

## 2.3.10 会话快照顶层白名单

`Broker.snapshot()` 从 `adapter.json` 的 `franka.session.status.output_schema.properties.data.properties`
读取允许公开的顶层字段，不再复制整个内部会话后排除少数字段。新增内部字段默认不进入回执；
需要公开的新字段先更新机器合同。已有顶层字段继续保留，result、confirmation、stop_verification
和产物条目的嵌套内容保持原样；产物分页、128 KiB 大结果处理、状态核验和控制锁规则保持原样。
这是输出边界收紧，现有长回执不会因此自动变为短摘要；完整错误/日志裁剪与清单拆分仍暂缓。
2.3.9 的任务根迁移及 2.3.8 的人工 --force-stop 清锁入口继续保留。候选包不会自动安装或切换服务。

## 2.3.9 任务根迁出 pipeline

按 2026-10-22 的手册，任务 YAML / 导出 CSV 根从 `<workspace>/pipeline/trajectories` 移到
`<workspace>/trajectories`。`layout.py` 的 `Workspace.tasks` 优先取新位置，旧位置只在
新位置不存在且旧位置存在时作为过渡回退；`task.list` / `franka.task.import` 的边界仍是同一个根，
没有放宽越界检查。`docs/RIBBON.md` 同步到 2026-10-22 版本。行为、路径校验和运动合同不变。

## 2.3.8 人工强制释放

在 `scripts/stop_broker.sh` 等脚本内，沿用原命令：

```bash
"$HOME/.local/lib/qizhen-edge/current/bin/python" "$(dirname -- "$0")/broker_control.py" --force-stop
```

从源码目录的终端手动执行时使用 `scripts/broker_control.py` 路径，不使用 `$0` 定位。
该命令只停止 Broker、备份并移除阻塞会话、释放软件控制锁，不发送机械臂停止指令，
不读取或声称已核验停稳，也不自动重启。成功输出 `locks_released=true` 表示本次确实清除过阻塞会话；
没有阻塞会话时为 false。备份失败或 Broker 未能停止时，不清除会话。
终态会话、产物文件和产物索引保留；被移除会话的原始信息保存在输出 `archive` 指向的备份中，
不再通过 session.status 查询。原请求 ID 仍返回归档回执，不重放动作；其 `physical_stop_verified=false`
和需要停稳核验的标记表示结果仍未确认，Agent 不把人工清锁当成可自动重试的停稳证明。
新任务在后续启动 Broker 后可重新申请软件控制权，原有授权、现场确认和设备约束仍适用。

## 2.3.7 失败与停稳状态

可能控制机械臂的会话失败时先置 unknown 并保留控制锁；只读核验机器人模式、速度和位置稳定性。
核验通过才转 failed、physical_stop_verified=true、control_lock_pending=false。
仍在运动、读取失败、超时或证据不足均保持 unknown；状态查询/后续受控调用可再次核验，
不重新启动任务，不自动清错/回零。failed 只表示已结束的失败，不保证可以原样重复相对运动。
明确未启动运动、mock 或 plan/prepare 且 skip_leveling=true 的失败直接 failed，
stop_verification.required=false，不连接机械臂；execute 不适用跳过调平的例外。

Broker 重启时保留未确认会话为 unknown；旧 failed+停稳未确认也迁为 unknown。
旧 operator_verified_stopped 标签不能直接释放 unknown。已确认的 failed 不因查询旧会话
而重新争用机器人停稳读取。终态错误、已完成结果与请求幂等绑定继续保留。
普通重启保留未解决会话与锁；显式 --force-stop 沿用人工强制释放：先备份，移除阻塞会话，
释放软件锁且不重启 Broker。保留旧请求 ID 的归档回执，重发旧请求不会启动运动。
新版源码及候选包未安装前不影响运行中的设备；安装后需同步新版本能力合同。

## 2.3.6 停稳速度阈值

按用户指定，将 Adapter 停稳核验的每关节速度阈值从 0.001 调整为 0.01 rad/s，
正负速度均按绝对值判定，等于阈值允许通过、超过则拒绝。
位置范围阈值仍为 0.0001 rad；仍采样两次、间隔 0.25 s，并检查机器人模式和数据有效性。
本修改不清除现有会话锁或原生调平 run_pause，不重放失败动作。
候选包需安装并同步能力后启用；已有版本包保持不变。

## 2.3.5 按会话提示确认

按用户指定策略，平台只对 `franka.session.respond` 弹操作确认卡片。
原先的 ribbon.run、home、delta.move、pipeline.start、offline.execute、
session.cancel、session.reconcile 从 high_impact 调整为 reversible，取消这些 Tool
调用前的平台额外确认。它们仍可能执行真实运动或改变设备/会话状态，不能当作只读、
离线或可自动回退的操作；启动请求仍须符合用户意图、资源授权与当前合同。

设备原有提示检测、confirmation_id、actions 和过期提示拒绝保持原样。
会话进入 waiting_confirmation 后，按当前提示向用户展示卡片；用户明确选择后再调用
session.respond。不会自动填写 MOVE，也不会把历史确认用于后续提示。
严格只保留原生终端提示：home、delta.move、offline.execute 不再生成 Adapter
托管 MOVE/QUIT 启动等待，调用后直接启动原生程序；原生程序不询问时不会弹卡片。
输入冻结、启动前哈希复核、当前 nonce/actions 校验和原有控制锁规则仍保留。
这不代表可以自动发起用户未请求的运动，也不代表取消操作能证明物理停稳。

需要安装并启用新包，再同步能力，平台才会使用新版本/哈希和副作用声明。
旧包及历史会话保持原版本；生成候选包本身不会切换已安装版本或同步平台。

## 2.3.2 手册与补录回执修复

`franka.manual.read` 固定读取本版本随包发布的 `docs/RIBBON.md`，不读取厂商工作区手册。
手册与源码一同校验；修改手册也须使用新的 Adapter 版本构建，不能覆盖既有发布包。
仿真补录要求原生 `summary.json` 的 `video.status=ok` 且本次 MP4 非空。
Ribbon 补录验证回执结构、ready/partial 状态与本次非空输出，保留原生 partial 和诊断。
任一路视频回执损坏、缺字段或录像不可用时，仅该路标记 unavailable，仍保存
`render_result.json` 以及其他成功视频；生成失败不返回可下载视频路径。

## 2.3.1 每次会话重新生成

`franka.pipeline.start` 统一使用 `task_id`，每个新会话按本次 mode 完整运行：
plan 重新规划，prepare 重新规划、仿真和预检，execute 重新调平、规划、仿真、
预检、确认并执行。Adapter 不接受 `source_session_id` 或 `on_start_drift`，
不再传入 `--from-run`，也不从旧会话关联仿真报告、录像或检查点。

重试必须沿用原 request_id 和完全相同参数，返回已有会话；明确开始新会话时
使用新的 request_id。每次新会话重新生成，不代表网络重试可以重复启动运动。

视频补录使用所选源会话保存的轨迹和 marker 作为输入，在新会话目录重新生成。
不会复制旧 simulation/videos 目录或旧视频，不以已有录像代替本次生成；生成失败
如实返回 unavailable。补录仍不启动真机运动或重新采集。

## 产物交付

本版需要平台的产物上传迁移/API/Web 和 Linux Edge Connector 0.2.0。
安装顺序为平台、Connector wheel、Adapter，然后重新同步能力。

Broker 的 status 和产物清单只读取索引。后台索引线程在锁外扫描目录、
按 1 MiB 流式计算 SHA-256；运行中的新文件保持“生成中”，任务结束且
文件连续两次扫描未变化后才发布句柄。哈希前后签名不一致时丢弃结果并重试。
最终产物索引还会等待本会话同进程组的渲染器退出，以收齐较晚生成的视频和图。
这一只读检查只用于产物归档，不参与原有控制锁的释放判定。
重复轮询不重新读取不变文件。清单同时按条数和序列化字节预算分页，
完整工具响应（含 envelope）限制为 512 KiB；二进制诊断读取最多 64 KiB/次。

manifest 声明产物协议后，Connector 自动跟踪平台命令产生的会话，等最终索引
就绪再通过独立的二进制通道上传。私有 `--export-artifact` 只接受已登记的产物 ID、
字节偏移与限定长度，不接受文件路径，也不是公开 Tool 操作。
设备上直接手动运行厂商 pipeline 和历史目录不会自动导出。

传输断网或重启后续传已确认分片，不重新执行设备动作。平台校验完整文件后
才关联任务并提供图片预览、视频播放和下载。HTML 使用既有文本预览及下载。
本目录仅为候选源码/包；没有自动安装、重启服务或接触真实设备。

## 本次边界

- 适配 `ribbon_ws` 拆分布局、两路采集、默认起点离线验证、独立生成会话产物及关节回程。
- 增加固定手册读取、受限任务清单/原 YAML 导入、视频补录及产物分页。
- 原有停稳解锁规则保持不变：仍只采样机器人状态，不要求旧执行进程退出。
- `scripts/broker_control.py` 普通重启保留 unknown 与锁；显式 `--force-stop` 备份并强制清锁。
  `scripts/update.sh` 和 `scripts/stop_broker.sh` 调用此强制入口，因此也会归档并清除阻塞会话。
- 停稳核验仍只采样机器人，不以原执行进程退出作为解锁条件；产物归档不等于设备停稳。

## 工作区配置

`config.json` 是 Adapter 运行配置，和 Connector 配对凭据分开，不进入安装包。
配置字段仍保持既有七项，详见 `scripts/config.example.json`。

`workspace` 现在必须指向 `/home/zhaoyunzyq/ribbon_ws` 根目录。
统一路径解析见 `src/layout.py`：流水线在 `pipeline/`，ROS 在 `ros/`，
libfranka 在 `libfranka/`，动捕程序在 `Nokov/recorder/build/`。
不能只把旧路径改成 `ribbon_ws/pipeline`，否则其它工具仍会定位错误。
旧的已安装配置不会被更新脚本自动迁移。

正式 handler/broker 默认读取 `~/.config/qizhen-franka/config.json`。
路径必须为绝对路径，不使用 `~` 或环境变量占位符。
Connector Python 运行 Adapter；`python_executable` 运行厂商 ROS/规划工具，
这两个环境可以不同。厂商 Python 需已具备 ROS 和 PyYAML；原文件导入使用
它的 `yaml.safe_load`，不在 Connector 中安装或执行任务代码。

部署前可执行只读路径预检：

```bash
python3 scripts/check_runtime.py --config /absolute/path/config.json
```

它不启动 broker、ROS、sudo 或任何设备程序。路径检查通过不代表设备就绪。
Connector 的 `adapter health` 仍是包/schema 自检，也不代替该预检。

## 创建、验证与执行

Agent 只提交契约允许的结构化参数，不执行 Shell 或提交任意服务器路径。

- `franka.task.create` 从结构化参数生成任务；关节回程请求会保留在任务文件中。
- `franka.task.list` 只枚举任务根（`<workspace>/trajectories`）范围内目录的当层任务。
- `franka.task.import` 复制已选 YAML 原始字节并记录哈希，不改写源文件。
  任务列表不代表验证通过；文件入口不应通过重新描述为结构化任务来替代。
  引用起点时只接受共享起点的绝对路径，并保存快照；共享起点变化后须重新导入。
- `franka.task.validate` 只做静态解析；`franka.offline.validate` 只验证已有 CSV/guard。
  两者均不能替代完整 prepare。

典型离线验证：先创建/导入任务，再调用 `franka.pipeline.start`：

```json
{"request_id":"prepare_001","task_id":"task_REPLACE","mode":"prepare","skip_leveling":true}
```

只有完整规划、仿真及预检通过，才能报告离线验证完成。
默认起点通过不代表当前真机起点可执行。普通 plan/prepare 分配 PTY，设备可用时
可能自动调平运动；不能依赖 Connector 在后台运行就认为没有运动。

每次执行都从任务重新开始：

```json
{"request_id":"execute_001","task_id":"task_REPLACE","mode":"execute"}
```

上一次 prepare 的结果用于审阅；本次 execute 仍重新进行完整流程，
不沿用上次轨迹或仿真。原有调平、预检、最终 MOVE 和采集保持有效。

`return_to_start_joints` 只是请求，不保证可行；应读取轨迹元数据中的
`joint_return.status` 与 WARN。它由规划器追加回程，不能给用户 waypoint 填 `motion: joint`。

## 会话与确认

启动调用返回 session，不等待整段实验。外层 `ok: true` 表示请求已处理，
会话结果以 `franka.session.status` 的终态和原生回执为准。

- 调平的 RESUME/SKIP/QUIT 及 pipeline 最终 MOVE 保留原生交互。
- 新 pipeline 会话采用完整流程；历史会话的 HOME/RELEVEL/QUIT 提示识别保留，
  HOME 会真实运动，不能自动代替操作者确认。
- 独立 home、微动、CSV 真机执行直接启动原生程序，不生成额外托管 MOVE/QUIT。
  默认 home 目标仍先复制为本次快照，所有受管理输入在启动前复核哈希。
- 确认只能由现有操作者确认流程发起；模型不能猜测现场已经确认。
- 用 `session.cancel` 取消原会话。启动前取消不运行底层程序；发送 SIGINT 不构成物理停稳证明。
- 带 request_id 的重试使用原 ID 与完全相同参数，不能通过重新 start 查询进度。

平台资源调用完成与物理实验完成是两层状态。Connector 0.2.0 会将 Adapter
`ok:false` 上报为失败并保留原始错误；异步实验继续通过 session 查询/取消。
平台通用 resource-job cancel 与输入资源引用没有在本版另造协议；现有
`supports_cancel:false` 保持准确，取消使用明确的 session.cancel 操作。

## 采集、回执与产物

Nokov、ATI 按原生回执分别判断是否启用和成功，支持单路、双路及两路关闭。
启用的通道必须有完成回执、有效文件和覆盖运动的样本。
力采集成功但 `calibrated:false` 时只有 counts，不能报告 N/N·m；设备状态和单位需一并查看。
视频、力图失败仅按原生回执记录告警，不自动升级为运动或测量证据。
底层错误码、失败阶段、details 和原始 result.json 都保留，失败不自动重试。

`franka.session.status` 只带有限产物清单，大回执可通过返回的产物句柄读取。
完整清单使用 `franka.session.artifacts` 分页；文本、MP4、PNG、HTML、TXT 均可登记。
`franka.artifact.read` 的偏移是字节：文本返回 UTF-8，二进制返回 base64，
按 next_offset 读取到结束后，可根据原文件 SHA256 核验重组结果。
不要把 base64 当 UTF-8，也不要将大文件一次塞入 Connector 的 1 MiB 消息。

`franka.pipeline.render_videos` 仅用于已结束且解除控制锁的 pipeline。
它在新会话副本中处理已保存轨迹和 marker；选择仿真视频时重新隔离 Gazebo 回放，
不调平、不接入 FCI、不启动采集、不改写原实验 result.json。
补录不是原始仿真验证，所有视频都标记为可视化旁证；不可用时如实返回 unavailable。
2026-10-20 起 pipeline 任务默认只生成 `videos/ribbon_viewer.html`；本补录接口仍显式带
`--ribbon-videos` 生成两个 MP4，返回结构不变。

## systemd 与执行权限

通用 Connector 服务默认把 HOME 挂为只读，不足以承载厂商工具的正常写入。
`deploy/qizhen-linux-edge-franka.conf` 是专用 drop-in 示例，列出 Adapter 状态、
调平状态、共享起点、审计和流水线锁的写入需求，以及厂商 sudo 调用的限制。
它不会自动安装。部署者应先准备状态目录、确认所列路径存在，并核对已有 sudo 程序白名单。
不得用泛化的 sudo shell 或给 Agent 任意命令权限替代明确的执行边界。
本次修改没有应用该配置，也没有创建/修改厂商工作区中的文件。

## 测试、版本与发布

```bash
bash scripts/test.sh -v
```

测试固定使用 Connector 自带 Python：`~/.local/lib/qizhen-edge/current/bin/python`，
通过 unittest discover 运行全部测试，厂商程序均为临时目录中的替身。
测试不连接硬件、不运行真实 Connector 服务，不安装或升级已部署包。

容器测试入口见 `tests/TESTING.md`，容器网络关闭，不挂载厂商工作区。
本版发布源为 adapter.json 的 2.3.11，旧版本的包保留且不能覆盖。

```bash
python3 scripts/build_adapter.py --architecture amd64 --output packages
```

构建只生成包和 SHA256，不安装、更新或同步能力。
首次安装、更新及 broker 管理仍使用既有脚本；执行前按具体机器完成配置迁移与测试。
`update.sh` 仍会强制停止并归档旧阻塞会话，这一既有行为本次没有调整。
构建、测试、备份成功均不代表已经部署或具备上机条件。
